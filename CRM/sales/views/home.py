from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from sales import access, rules
from sales.models import Activity, Lead, Quote, is_manager
from sales.views.opportunities import decorate, with_next_due


@login_required
def my_day(request):
    """What the signed-in user should do today. Activities are the user's own (owner = who does it);
    deals are the user's own, or the whole team's for the manager."""
    user, today, now = request.user, timezone.localdate(), timezone.now()
    todo = Activity.objects.filter(owner=user, done=False).select_related("opportunity__account", "lead", "account")
    deals = decorate(
        list(with_next_due(access.opportunities(user).filter(stage__in=rules.OPEN_STAGES))),
        today, now,
    )  # fmt: skip
    month_end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    context = {
        "today": today,
        "overdue": todo.filter(due_date__lt=today).order_by("due_date"),
        "due_today": todo.filter(due_date=today),
        "no_next_step": [d for d in deals if d.indicator == "none"],
        "stale": [d for d in deals if d.stale],
        "new_leads": Lead.objects.filter(owner=user, status=Lead.Status.NEW),
        "open_value": sum((d.amount for d in deals), rules.ZERO),
        "weighted_value": sum((d.weighted_amount for d in deals), rules.ZERO),
        "closing_this_month": [d for d in deals if d.expected_close <= month_end],
        "won_this_month": access.opportunities(user).filter(
            stage=rules.WON, closed_at__date__gte=today.replace(day=1)
        ).aggregate(v=Sum("amount"))["v"] or rules.ZERO,
    }  # fmt: skip
    if is_manager(user):
        context["pending_quotes"] = Quote.objects.filter(status=Quote.Status.PENDING).select_related(
            "opportunity__account", "opportunity__owner"
        )
        context["unassigned"] = Lead.objects.filter(owner__isnull=True, status__in=Lead.OPEN)
    return render(request, "sales/home.html", context)
