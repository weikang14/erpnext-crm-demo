from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from sales import access, rules
from sales.forms import DecisionForm, QuoteLineForm
from sales.models import Quote, is_manager
from sales.rules import RuleError

COMPANY = {
    "name": "Ombak Metal Works Sdn Bhd",
    "address": "Lot 7, Jalan Perindustrian 2, Kawasan Perindustrian Senai, 81400 Senai, Johor, Malaysia",
    "phone": "+60 7-599 0000",
    "email": "sales@ombakmetal.example",
}


def quote_context(quote, **forms):
    lines = list(quote.lines.select_related("product"))
    return {
        "quote": quote,
        "deal": quote.opportunity,
        "lines": lines,
        "total": rules.quote_total(lines),
        "needs_approval": rules.needs_approval(lines),
        "limit": rules.APPROVAL_LIMIT,
        "printable": quote.status in Quote.PRINTABLE,
        "line_form": QuoteLineForm(),
        "decision_form": DecisionForm(),
    } | forms


@login_required
@require_POST
def quote_new(request, pk):
    deal = access.get(access.opportunities, request.user, pk)
    try:
        quote = Quote.start(deal, request.user)
    except RuleError as error:
        messages.error(request, str(error))
        current = deal.quotes.filter(status__in=Quote.IN_PROGRESS).first()
        return redirect("quote", current.pk) if current else redirect(deal)
    return redirect("quote", quote.pk)


@login_required
def quote_detail(request, pk):
    quote = access.get(access.quotes, request.user, pk)
    return render(request, "sales/quotes/detail.html", quote_context(quote))


@login_required
@require_POST
def line_add(request, pk):
    quote = access.get(access.quotes, request.user, pk)
    form = QuoteLineForm(request.POST)  # no unit price field: the list price is the only price
    if not form.is_valid():
        return render(request, "sales/quotes/detail.html", quote_context(quote, line_form=form), status=400)
    try:
        quote.add_line(**form.cleaned_data)
    except RuleError as error:
        messages.error(request, str(error))
    return redirect("quote", quote.pk)


@login_required
@require_POST
def line_delete(request, pk, line):
    quote = access.get(access.quotes, request.user, pk)
    try:
        quote.delete_line(line)
    except RuleError as error:
        messages.error(request, str(error))
    return redirect("quote", quote.pk)


DONE = {
    "submit": "{number} is {status}.",
    "approve": "{number} approved.",
    "reject": "{number} sent back to the rep as a draft.",
    "send": "{number} marked as sent to the customer.",
}


@login_required
@require_POST
def quote_action(request, pk, action):
    quote = access.get(access.quotes, request.user, pk)
    if action in ("approve", "reject"):
        if not is_manager(request.user):
            raise PermissionDenied
        form = DecisionForm(request.POST, require_note=action == "reject")
        if not form.is_valid():
            return render(request, "sales/quotes/detail.html", quote_context(quote, decision_form=form), status=400)
        args = (request.user, form.cleaned_data["note"])
    elif action in ("submit", "send", "revise"):
        args = (request.user,)
    else:
        raise Http404
    # both can approve, so only the lines the page showed; a POST without the revision never matches (AC15, FM1)
    seen = {"seen": request.POST.get("revision", "")} if action in ("approve", "submit") else {}
    try:
        result = getattr(quote, action)(*args, **seen)
    except RuleError as error:
        messages.error(request, str(error))
        return redirect("quote", quote.pk)
    if action == "revise":
        messages.success(request, f"{result.number} drafted from {quote.number}. {quote.number} stays sent until this one goes out.")
        return redirect("quote", result.pk)
    messages.success(request, DONE[action].format(number=quote.number, status=quote.get_status_display().lower()))
    if action in ("approve", "reject"):
        return redirect("approvals")
    return redirect("quote", quote.pk)


@login_required
def quote_print(request, pk):
    quote = access.get(access.quotes, request.user, pk)
    if quote.status not in Quote.PRINTABLE:
        raise Http404("Only approved quotes can be printed.")  # an unapproved discount never reaches a customer
    return render(request, "sales/quotes/print.html", quote_context(quote, company=COMPANY))


@access.manager_required
def approvals(request):
    pending = list(access.quotes(request.user).filter(status=Quote.Status.PENDING).prefetch_related("lines"))
    for quote in pending:
        lines = list(quote.lines.all())
        quote.total_value = rules.quote_total(lines)
        quote.max_discount = max((line.discount_pct for line in lines), default=0)
    return render(request, "sales/quotes/approvals.html", {"pending": pending, "limit": rules.APPROVAL_LIMIT})
