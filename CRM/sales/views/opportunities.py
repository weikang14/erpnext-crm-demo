import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Min, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from sales import access, rules
from sales.forms import ActivityForm, AssignForm, DealFilter, DealForm, LostForm, MoveForm, active_reps
from sales.models import Quote, Stage, display_name, is_manager
from sales.regions import Region, states_in
from sales.rules import RuleError
from sales.views import back, page_of


def with_next_due(deals):
    return deals.annotate(next_due=Min("activities__due_date", filter=Q(activities__done=False)))


def decorate(deals, today, now):
    """Attach the next-activity indicator and stale flag the board and lists show."""
    for deal in deals:
        deal.indicator = rules.indicator(deal.next_due, today)
        deal.stale = deal.is_stale(now)
    return deals


# --- list and CSV ----------------------------------------------------------------------------------


def safe_cell(value):
    """Stop spreadsheet formula injection: names typed into the public enquiry form end up in this file."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_response(deals):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="deals-{timezone.localdate():%Y-%m-%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Deal", "Account", "Region", "Owner", "Stage", "Value (MYR)", "Probability %",
                     "Expected close", "Closed", "Lost reason"])  # fmt: skip
    for deal in deals.select_related("lost_reason"):
        region = deal.account.region
        writer.writerow([safe_cell(v) for v in (
            deal.title, deal.account.name, region.label if region else "", display_name(deal.owner),
            deal.get_stage_display(), f"{deal.amount:.2f}", deal.probability, deal.expected_close.isoformat(),
            timezone.localtime(deal.closed_at).date().isoformat() if deal.closed_at else "",
            deal.lost_reason.name if deal.lost_reason else "",
        )])  # fmt: skip
    return response


@login_required
def deal_list(request):
    today = timezone.localdate()
    filters = DealFilter(request.GET, today=today, manager=is_manager(request.user))
    deals = filters.apply(access.opportunities(request.user))
    if request.GET.get("format") == "csv":
        return csv_response(deals)
    page = page_of(request, with_next_due(deals).order_by("expected_close", "pk"))
    decorate(page.object_list, today, timezone.now())
    total = deals.aggregate(value=Sum("amount"))["value"] or 0
    return render(request, "sales/deals/list.html", {"filters": filters, "page": page, "total": total})


# --- board ----------------------------------------------------------------------------------------


@login_required
def pipeline(request):
    today, now = timezone.localdate(), timezone.now()
    manager = is_manager(request.user)
    deals = with_next_due(access.opportunities(request.user).filter(stage__in=rules.OPEN_STAGES))
    owner, region = request.GET.get("owner", ""), request.GET.get("region", "")
    if manager and owner.isdigit():
        deals = deals.filter(owner_id=owner)
    if region in Region.values:
        deals = deals.filter(account__state__in=states_in(region))
    deals = decorate(list(deals), today, now)
    order = {name: i for i, name in enumerate(rules.INDICATORS)}
    deals.sort(key=lambda d: (order[d.indicator], d.next_due or today, -d.pk))
    columns = []
    for stage in rules.OPEN_STAGES:
        cards = [d for d in deals if d.stage == stage]
        columns.append({
            "stage": stage, "label": Stage(stage).label, "probability": rules.PROBABILITY[stage],
            "cards": cards, "count": len(cards), "value": sum((d.amount for d in cards), rules.ZERO),
        })  # fmt: skip
    context = {
        "columns": columns, "move_form": MoveForm(), "owner": owner, "region": region, "regions": Region.choices,
        "owners": active_reps() if manager else [],
    }  # fmt: skip
    return render(request, "sales/deals/pipeline.html", context)


# --- one deal --------------------------------------------------------------------------------------


def detail_context(request, deal, **forms):
    today = timezone.localdate()
    deal.next_due = deal.activities.filter(done=False).aggregate(d=Min("due_date"))["d"]
    decorate([deal], today, timezone.now())
    return {
        "deal": deal,
        "quotes": deal.quotes.prefetch_related("lines").select_related("created_by", "approved_by"),
        "quote_in_progress": deal.quotes.filter(status__in=Quote.IN_PROGRESS).first(),
        "sent_quote": deal.sent_quote(),
        "activities": deal.activities.select_related("owner"),
        "history": deal.history.select_related("by"),
        "move_form": MoveForm(initial={"stage": deal.stage}),
        "lost_form": LostForm(),
        "activity_form": ActivityForm(),
        "today": today,
        "assign_form": AssignForm(initial={"owner": deal.owner}) if deal.is_open and is_manager(request.user) else None,
    } | forms


@login_required
def deal_detail(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    return render(request, "sales/deals/detail.html", detail_context(request, deal))


@login_required
@require_POST
def deal_move(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    form = MoveForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Pick an open stage.")
    else:
        try:
            before = deal.stage
            deal.move_to(form.cleaned_data["stage"], request.user)
            if deal.stage != before:
                messages.success(request, f"{deal.title} moved to {deal.get_stage_display()}.")
        except RuleError as error:
            messages.error(request, f"{deal.title}: {error}")
    return back(request, deal)


@login_required
@require_POST
def deal_won(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    try:
        deal.mark_won(request.user)
        messages.success(request, f"Won: {deal.title}, MYR {deal.amount:,.2f}.")
    except RuleError as error:
        messages.error(request, str(error))
    return redirect(deal)


@login_required
@require_POST
def deal_lost(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    form = LostForm(request.POST)
    if not form.is_valid():
        return render(request, "sales/deals/detail.html", detail_context(request, deal, lost_form=form), status=400)
    try:
        deal.mark_lost(request.user, form.cleaned_data["reason"], form.cleaned_data["note"])
        messages.success(request, f"Marked lost: {deal.title} ({deal.lost_reason}).")
    except RuleError as error:
        messages.error(request, str(error))
    return redirect(deal)


@login_required
def deal_edit(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    if not deal.is_open:
        messages.error(request, "This deal is closed.")
        return redirect(deal)
    form = DealForm(request.POST if request.method == "POST" else None, instance=deal, account=deal.account)
    if not form.is_valid():
        return render(request, "sales/deals/form.html", {"deal": deal, "form": form})
    try:
        deal.edit(**form.cleaned_data)
        messages.success(request, f"{deal.title} saved.")
    except RuleError as error:
        messages.error(request, str(error))
    return redirect(deal)


@access.manager_required
@require_POST
def deal_assign(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    if not deal.is_open:  # a closed deal's page has no reassign form to show the error on
        messages.error(request, "This deal is closed.")
        return redirect(deal)
    form = AssignForm(request.POST)
    if not form.is_valid():
        return render(request, "sales/deals/detail.html", detail_context(request, deal, assign_form=form), status=400)
    try:
        deal.reassign(form.cleaned_data["owner"])
        messages.success(request, f"{deal.title} assigned to {display_name(deal.owner)}.")
    except RuleError as error:
        messages.error(request, str(error))
    return redirect(deal)
