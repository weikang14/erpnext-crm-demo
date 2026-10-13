"""The four sales reports. Each takes the deals the viewer may see and runs a fixed number of
aggregate queries, however many deals there are."""

from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum

from sales import rules
from sales.models import Stage, display_name

WON_LOST = [rules.WON, rules.LOST]


def share(part, whole):
    """Whole-number percent for bar widths and labels; 0 when there is nothing to share."""
    return round(part * 100 / whole) if whole else 0


def pipeline_by_stage(deals):
    totals = {
        row["stage"]: row
        for row in deals.filter(stage__in=rules.OPEN_STAGES).values("stage").annotate(count=Count("id"), value=Sum("amount"))
    }
    rows = []
    for stage in rules.OPEN_STAGES:
        row = totals.get(stage, {"count": 0, "value": rules.ZERO})
        rows.append({
            "stage": stage, "label": Stage(stage).label, "probability": rules.PROBABILITY[stage],
            "count": row["count"], "value": row["value"], "weighted": rules.weighted(row["value"], stage),
        })  # fmt: skip
    top = max((r["value"] for r in rows), default=0)
    for row in rows:
        row["bar"] = share(row["value"], top)
    total = {k: sum((r[k] for r in rows), 0) for k in ("count", "value", "weighted")}
    return rows, total


def win_rate_by_rep(deals, start, end):
    closed = (
        deals.filter(stage__in=WON_LOST, closed_at__date__range=(start, end))
        .values("owner")
        .annotate(
            won=Count("id", filter=Q(stage=rules.WON)),
            lost=Count("id", filter=Q(stage=rules.LOST)),
            won_value=Sum("amount", filter=Q(stage=rules.WON)),
        )
    )
    names = {u.pk: display_name(u) for u in User.objects.filter(pk__in=[row["owner"] for row in closed])}
    rows = [
        {"rep": names[row["owner"]], "won": row["won"], "lost": row["lost"],
         "won_value": row["won_value"] or rules.ZERO, "rate": rules.win_rate(row["won"], row["lost"])}
        for row in closed
    ]  # fmt: skip
    rows.sort(key=lambda r: (-(r["rate"] or 0), r["rep"]))
    won, lost = sum(r["won"] for r in rows), sum(r["lost"] for r in rows)
    total = {"won": won, "lost": lost, "won_value": sum((r["won_value"] for r in rows), rules.ZERO),
             "rate": rules.win_rate(won, lost)}  # fmt: skip
    return rows, total


def forecast(deals, start, end, today):
    won = deals.filter(stage=rules.WON, closed_at__date__range=(start, end)).aggregate(v=Sum("amount"))["v"] or rules.ZERO
    closing = (
        deals.filter(stage__in=rules.OPEN_STAGES, expected_close__range=(start, end))
        .values("stage")
        .annotate(count=Count("id"), value=Sum("amount"))
    )
    weighted = sum((rules.weighted(row["value"], row["stage"]) for row in closing), rules.ZERO)
    open_value = sum((row["value"] for row in closing), rules.ZERO)
    overdue = deals.filter(stage__in=rules.OPEN_STAGES, expected_close__lt=today).count()
    return {
        "won": won,
        "weighted": weighted,
        "forecast": won + weighted,
        "best_case": won + open_value,
        "open_count": sum(row["count"] for row in closing),
        "overdue": overdue,
    }


def lost_reasons(deals, start, end):
    rows = list(
        deals.filter(stage=rules.LOST, closed_at__date__range=(start, end))
        .values("lost_reason__name")
        .annotate(count=Count("id"), value=Sum("amount"))
        .order_by("-count", "lost_reason__name")
    )
    total = sum(r["count"] for r in rows)
    for row in rows:
        row["reason"] = row.pop("lost_reason__name") or "No reason recorded"
        row["share"] = share(row["count"], total)
    return rows, {"count": total, "value": sum((r["value"] for r in rows), rules.ZERO)}
