"""Sales rules with no database or HTTP: money, discount approval and stage gates."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
APPROVAL_LIMIT = Decimal("10")  # % discount on any line above this needs the sales manager
STALE_DAYS = 14

ENQUIRY, TECHNICAL, QUOTATION, NEGOTIATION, WON, LOST = (
    "enquiry", "technical", "quotation", "negotiation", "won", "lost",
)  # fmt: skip
OPEN_STAGES = [ENQUIRY, TECHNICAL, QUOTATION, NEGOTIATION]
NEEDS_SENT_QUOTE = {QUOTATION, NEGOTIATION}
PROBABILITY = {ENQUIRY: 10, TECHNICAL: 25, QUOTATION: 50, NEGOTIATION: 75, WON: 100, LOST: 0}


class RuleError(Exception):
    """A business rule refused the change; the message is shown to the user as is."""


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(qty, unit_price, discount_pct):
    return money(Decimal(qty) * Decimal(unit_price) * (100 - Decimal(discount_pct)) / 100)


def quote_total(lines):
    """lines: objects with qty, unit_price and discount_pct. Each line is rounded, then summed."""
    return sum((line_total(line.qty, line.unit_price, line.discount_pct) for line in lines), ZERO)


def needs_approval(lines):
    return any(Decimal(line.discount_pct) > APPROVAL_LIMIT for line in lines)


def weighted(amount, stage):
    return money(Decimal(amount) * PROBABILITY[stage] / 100)


def check_move(current, target, has_sent_quote):
    """Raise RuleError if a deal in `current` may not move to `target` on the board."""
    if current not in OPEN_STAGES:
        raise RuleError("This deal is closed.")
    if target not in OPEN_STAGES:
        raise RuleError("Use Won or Lost on the deal page.")
    if target in NEEDS_SENT_QUOTE and not has_sent_quote:
        raise RuleError("Send a quote first.")


def check_won(current, has_sent_quote):
    if current not in OPEN_STAGES:
        raise RuleError("This deal is closed.")
    if not has_sent_quote:
        raise RuleError("Send a quote before marking the deal won.")


# next-activity indicator on a deal, in the order the board sorts them (Pipedrive's convention)
INDICATORS = ["overdue", "today", "none", "future"]


def indicator(next_due, today):
    """State of a deal's earliest open activity: overdue, today, none (nothing planned) or future."""
    if next_due is None:
        return "none"
    if next_due < today:
        return "overdue"
    return "today" if next_due == today else "future"


def win_rate(won, lost):
    """Percent of closed deals that were won, by count; None when nothing closed."""
    closed = won + lost
    return round(won * 100 / closed) if closed else None
