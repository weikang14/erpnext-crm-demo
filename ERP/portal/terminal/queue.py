"""Queue logic with no HTTP and no views: ERPNext rows in, cards out."""

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

ERP_FORMAT = "%Y-%m-%d %H:%M:%S"  # ERPNext's naive, site-local wall-clock format
HIDDEN = {"Completed", "Cancelled"}
STATUS_ORDER = {"running": 0, "paused": 1}  # jobs in hand first, then the rest
TIMING_ORDER = {"overdue": 0, "today": 1, "later": 2}  # then overdue before today before later


def erp_now(now=None):
    """Now, as ERPNext expects it: naive local time (sending UTC shifts logs by 8 h)."""
    return timezone.localtime(now).strftime(ERP_FORMAT)


def parse_erp(value):
    return timezone.make_aware(datetime.strptime(value[:19], ERP_FORMAT)) if value else None


@dataclass
class Card:
    name: str
    work_order: str
    operation: str
    item_name: str
    qty: float
    remaining: float
    planned_start: datetime | None
    planned_end: datetime | None
    status: str  # running | paused | ready | waiting
    waits_for: str = ""
    elapsed_seconds: int = 0
    timing: str = ""  # overdue | today | later

    @property
    def planned_window(self):
        if not (self.planned_start and self.planned_end):
            return ""
        start, end = timezone.localtime(self.planned_start), timezone.localtime(self.planned_end)
        if start.date() == end.date():
            return f"{start:%a} {start.day} {start:%b}, {start:%H:%M}–{end:%H:%M}"
        return f"{start:%a} {start.day} {start:%b %H:%M} – {end:%a} {end.day} {end:%b %H:%M}"

    @property
    def elapsed_display(self):
        hours, rest = divmod(self.elapsed_seconds, 3600)
        return f"{hours:02d}:{rest // 60:02d}:{rest % 60:02d}"


def timing_of(start, end, now):
    """Overdue once the planned end has passed; Today if planned to start by end of today."""
    if end and end < now:
        return "overdue"
    if start and timezone.localtime(start).date() <= timezone.localtime(now).date():
        return "today"
    return "later"


def has_open_log(job_card):
    return any(log.get("from_time") and not log.get("to_time") for log in job_card.get("time_logs", []))


def sort_cards(cards):
    """Running, paused, then overdue / today / later; stable, so planned order within each group."""
    return sorted(cards, key=lambda c: (STATUS_ORDER.get(c.status, 2), TIMING_ORDER.get(c.timing, 1)))


def build_cards(rows, siblings, now=None):
    """Status per job card; Waiting when an earlier operation of the same work order is open."""
    now = now or timezone.now()
    open_ops = {}
    for s in siblings:
        if s["docstatus"] != 1:
            open_ops.setdefault(s["work_order"], []).append((s["sequence_id"], s["operation"]))

    cards = []
    for row in rows:
        if row["status"] in HIDDEN:
            continue
        earlier = sorted(op for op in open_ops.get(row["work_order"], []) if op[0] < row["sequence_id"])
        if row["is_paused"]:
            status = "paused"
        elif row["status"] == "Work In Progress":
            status = "running"
        else:
            status = "waiting" if earlier else "ready"
        cards.append(
            Card(
                name=row["name"],
                work_order=row["work_order"],
                operation=row["operation"],
                item_name=row["item_name"],
                qty=row["for_quantity"],
                remaining=row["for_quantity"] - row["total_completed_qty"],
                planned_start=parse_erp(row["expected_start_date"]),
                planned_end=parse_erp(row["expected_end_date"]),
                status=status,
                waits_for=earlier[0][1] if status == "waiting" else "",
                timing=timing_of(parse_erp(row["expected_start_date"]), parse_erp(row["expected_end_date"]), now),
            )
        )
    return sort_cards(cards)


def elapsed_seconds(job_card, now=None):
    """Logged time so far plus the open log, for the running timer."""
    now = now or timezone.now()
    seconds = (job_card.get("total_time_in_mins") or 0) * 60
    for log in job_card.get("time_logs", []):
        if log.get("from_time") and not log.get("to_time"):
            seconds += (now - parse_erp(log["from_time"])).total_seconds()
    return max(int(seconds), 0)
