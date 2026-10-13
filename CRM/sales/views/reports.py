from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from sales import access, reports
from sales.forms import active_reps, quarter_bounds, quarter_choices, quarter_of
from sales.models import is_manager
from sales.regions import Region, states_in


@login_required
def report_page(request):
    today = timezone.localdate()
    manager = is_manager(request.user)
    quarter = request.GET.get("quarter", "")
    try:
        start, end = quarter_bounds(quarter)
    except ValueError:
        quarter = quarter_of(today)
        start, end = quarter_bounds(quarter)

    deals = access.opportunities(request.user)
    region, owner = request.GET.get("region", ""), request.GET.get("owner", "")
    if manager and region in Region.values:
        deals = deals.filter(account__state__in=states_in(region))
    if manager and owner.isdigit():
        deals = deals.filter(owner_id=owner)

    stages, stage_total = reports.pipeline_by_stage(deals)
    reps, rep_total = reports.win_rate_by_rep(deals, start, end)
    reasons, reason_total = reports.lost_reasons(deals, start, end)
    context = {
        "quarter": quarter, "quarters": quarter_choices(today), "start": start, "end": end,
        "region": region, "owner": owner, "regions": Region.choices, "owners": active_reps() if manager else [],
        "stages": stages, "stage_total": stage_total, "reps": reps, "rep_total": rep_total,
        "forecast": reports.forecast(deals, start, end, today), "reasons": reasons, "reason_total": reason_total,
    }  # fmt: skip
    return render(request, "sales/reports.html", context)
