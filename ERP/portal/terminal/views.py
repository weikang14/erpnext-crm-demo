from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from terminal import queue
from terminal.erpnext import ERPNext, ERPNextError, ERPNextUnavailable
from terminal.forms import CompleteForm

DONE = {"start": "started", "pause": "paused", "resume": "resumed"}


def erpnext_client():
    return ERPNext()


def operator_of(user):
    return getattr(user, "operator", None)


NOT_LINKED = "This sign-in isn't linked to an ERPNext employee."


def unavailable(request, message="", saving=False):
    """503 when ERPNext can't be reached; 502 with ERPNext's own message when it refused.
    saving=True: the connection dropped mid-write, so the change may or may not be in ERPNext."""
    status = 502 if message else 503
    return render(request, "terminal/unavailable.html", {"message": message, "saving": saving}, status=status)


def pick_station(request, stations):
    """?workstation= wins if it is real; then this session's choice; then the operator's own."""
    chosen = request.GET.get("workstation")
    if chosen in stations:
        request.session["station"] = chosen
    station = request.session.get("station")
    if station in stations:
        return station
    operator = operator_of(request.user)
    if operator and operator.default_workstation in stations:
        return operator.default_workstation
    return stations[0] if stations else ""


@login_required
def queue_view(request):
    erp = erpnext_client()
    try:
        stations = erp.workstations()
        station = pick_station(request, stations)
        rows = erp.queue(station) if station else []
        cards = queue.build_cards(rows, erp.siblings({row["work_order"] for row in rows}))
        for card in cards:
            if card.status == "running":
                job = erp.job_card(card.name)
                if queue.has_open_log(job):
                    card.elapsed_seconds = queue.elapsed_seconds(job)
                else:  # "Work In Progress" with no open log: started earlier, nobody on it now
                    card.status = "ready"
        cards = queue.sort_cards(cards)
    except ERPNextError as exc:
        return unavailable(request, str(exc))
    except ERPNextUnavailable:
        return unavailable(request)
    context = {"stations": stations, "station": station, "cards": cards, "operator": operator_of(request.user)}
    return render(request, "terminal/queue.html", context)


@login_required
@require_POST
def job_action(request, name, action):
    operator = operator_of(request.user)
    if operator is None:
        messages.error(request, NOT_LINKED)
        return redirect("queue")
    erp, at = erpnext_client(), queue.erp_now()
    try:
        # ERPNext accepts a second start on the same card (overlapping logs): refuse it here
        if action == "start":
            job = erp.job_card(name)
            if queue.has_open_log(job):
                messages.info(request, f"{name} is already running.")
                return redirect("queue")
            if job.get("is_paused"):  # a stale page can still show Start on a paused card
                messages.info(request, f"{name} is paused: tap Resume.")
                return redirect("queue")
            erp.start(name, operator.employee, at)
        elif action == "pause":
            erp.pause(name, at)
        else:
            if not erp.job_card(name).get("is_paused"):
                messages.info(request, f"{name} isn't paused.")
                return redirect("queue")
            erp.resume(name, at)
    except ERPNextError as exc:
        messages.error(request, str(exc))
    except ERPNextUnavailable:
        return unavailable(request, saving=True)  # the write may or may not have landed
    else:
        messages.success(request, f"{name} {DONE[action]}.")
    return redirect("queue")


@login_required
def complete_view(request, name):
    if operator_of(request.user) is None:
        messages.error(request, NOT_LINKED)
        return redirect("queue")
    erp = erpnext_client()
    try:
        job = erp.job_card(name)
        reasons = erp.defect_reasons()
    except ERPNextError as exc:
        messages.error(request, str(exc))
        return redirect("queue")
    except ERPNextUnavailable:
        return unavailable(request)

    if not job.get("time_logs"):  # only reachable by typing the URL: the queue offers Start instead
        messages.info(request, f"Start {name} before completing it.")
        return redirect("queue")

    # always the full remaining quantity, re-read from ERPNext (owner's decision: no partial completion)
    remaining = job["for_quantity"] - job["total_completed_qty"]
    form = CompleteForm(request.POST if request.method == "POST" else None, reasons=reasons)
    if request.method != "POST" or not form.is_valid():
        context = {"job": job, "name": name, "remaining": remaining, "form": form}
        return render(request, "terminal/complete.html", context)

    at = queue.erp_now()
    try:
        if job.get("is_paused"):  # ERPNext won't submit a card that is On Hold
            erp.resume(name, at)
        erp.complete(name, remaining, at)
    except ERPNextError as exc:
        messages.error(request, str(exc))
        return redirect("queue")
    except ERPNextUnavailable:
        return unavailable(request, saving=True)

    # the completion is already booked in ERPNext: a rejected defect line must not hide it
    logged = 0
    for reason, qty in form.defects():
        try:
            erp.log_defect(name, reason, qty)
            logged += 1
        except ERPNextError as exc:
            messages.error(request, f"Defect {reason} x {qty} was not saved: {exc}")
        except ERPNextUnavailable:
            messages.error(request, f"Defect {reason} x {qty} was not saved: the ERP stopped answering.")
    plural = "line" if logged == 1 else "lines"
    messages.success(request, f"{name} completed: {remaining:g} done, {logged} defect {plural} logged.")
    return redirect("queue")
