"""Won deal -> ERPNext: the Customer, Address and Sales Order payloads (pure), and send_order, the one flow that
claims the deal, talks to ERPNext through a client (sales.erpnext.Client or the tests' fake) and records the outcome.

Numbers go out as JSON numbers (float) taken from 2-decimal Decimals, so 19.12 is sent as 19.12."""

import logging
from collections import namedtuple
from decimal import ROUND_HALF_EVEN, Decimal

from django.utils import timezone

from sales.erpnext import MAX_MESSAGE, Refused, Unavailable
from sales.models import Opportunity, Quote, Stage
from sales.rules import CENT, ZERO

COMPANY = "Ombak Metal Works Sdn Bhd"
WAREHOUSE = "Finished Goods - OMW"
SST_TEMPLATE = "Malaysia SST - OMW"
TAX_KEYS = ("charge_type", "account_head", "rate", "description")

NOT_CONFIGURED = "ERP link not configured"
NO_ANSWER = (
    "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated."
)
ZERO_TOTAL = "The accepted quote is zero; ERPNext needs an order with a value."
UNEXPECTED = "Unexpected error while sending; see the server log."
ALREADY_SENT = "This deal's order is already in ERPNext."
ONLY_WON = "Only won deals can be sent."
BEING_SENT = "This deal is being sent right now; refresh in a moment."
CREATED = "Sales order {} created in ERPNext."
ADOPTED = "Sales order {} is already in ERPNext; linked to this deal."
MISMATCH = "ERPNext order {} totals MYR {:,.2f}, the quote MYR {:,.2f}; check it in ERPNext."
NOT_TAKEN = "Won is saved, but ERPNext didn't take the order: {} Fix it and send again from the deal."  # flash only
OWN_REASONS = (NO_ANSWER, ZERO_TOTAL, UNEXPECTED)  # failures that aren't ERPNext refusing: flashed as they are

logger = logging.getLogger(__name__)
Outcome = namedtuple("Outcome", "status order message level")  # level: success | warning | error | None (no flash)


def territory(account):
    return account.country  # the territories are named after the countries: "Malaysia" or "Singapore"


def taxed(account):
    """SST for every Malaysian state alike (Labuan included); Singapore orders are exports."""
    return account.country == "Malaysia"


def is_zero(deal):
    """A won deal whose accepted quote totals 0 is not sent: ERPNext needs an order with a value (AC10)."""
    return deal.amount == 0


def accepted_quote(deal):
    return deal.quotes.filter(status=Quote.Status.ACCEPTED).first()


def customer_payload(account):
    payload = {
        "customer_name": account.name.strip(), "customer_type": "Company", "customer_group": "Commercial",
        "territory": territory(account),
    }  # fmt: skip
    if account.registration_no.strip():
        payload["tax_id"] = account.registration_no.strip()
    return payload


def address_payload(account, customer):
    """None unless the account has address and city: ERPNext requires both. Empty optional fields are left out."""
    if not (account.address.strip() and account.city.strip()):
        return None
    fields = {
        "address_title": customer, "address_type": "Billing", "address_line1": account.address.strip(),
        "city": account.city.strip(), "state": account.state, "pincode": account.postcode.strip(),
        "country": account.country, "phone": account.phone.strip(),
    }  # fmt: skip
    return {**{k: v for k, v in fields.items() if v}, "links": [{"link_doctype": "Customer", "link_name": customer}]}


def header_discount(lines, amount):
    """Σ qty × unit_price − amount: the discount on Net Total that makes the order's net total the quote total.
    Each item amount is rounded the way ERPNext rounds it (Banker's, to the sen), so a fractional qty stays exact;
    0.5 × 33.33 is 16.66 there and 16.67 in the CRM, which makes the discount -0.01."""
    total = sum(((Decimal(x.qty) * Decimal(x.unit_price)).quantize(CENT, ROUND_HALF_EVEN) for x in lines), ZERO)
    return total - Decimal(amount)


def order_payload(deal, quote, customer, tax_rows, today, delivery_date):
    """The Sales Order for the deal's accepted quote, as a draft that _checked then submits. tax_rows: the SST
    template's rows read from ERPNext."""
    lines = list(quote.lines.select_related("product"))
    payload = {
        "customer": customer, "company": COMPANY, "transaction_date": today.isoformat(),
        "delivery_date": delivery_date.isoformat(), "currency": "MYR", "crm_reference": quote.number,
        "disable_rounded_total": 1, "apply_discount_on": "Net Total",
        "items": [
            {
                "item_code": line.product.item_code, "qty": float(line.qty), "rate": float(line.unit_price),
                "delivery_date": delivery_date.isoformat(), "warehouse": WAREHOUSE,
            }  # fmt: skip
            for line in lines
        ],
        "docstatus": 0,
    }  # fmt: skip
    discount = header_discount(lines, deal.amount)
    if discount:
        payload["discount_amount"] = float(discount)
    if taxed(deal.account):
        payload["taxes_and_charges"] = SST_TEMPLATE
        payload["taxes"] = [{key: row[key] for key in TAX_KEYS} for row in tax_rows]
    return payload


def send_order(deal, client, today, delivery_date=None):
    """Send a won deal's accepted quote to ERPNext as a submitted sales order and store the outcome on the deal.

    client None (not configured): nothing happens. Otherwise the deal is claimed first (one committed conditional
    UPDATE, so call this outside any transaction: no row lock is held while ERPNext answers). A refused claim changes
    nothing, and a claim the database fails records nothing (the deal stays sendable). After a claim the deal always
    ends sent or failed, whatever ERPNext or the code does; nothing is raised.
    today: the Kuala Lumpur date (transaction_date); delivery_date, when given, replaces the deal's stored one."""
    if client is None:
        return Outcome(deal.erp_status, deal.erp_order, NOT_CONFIGURED, None)
    try:
        claimed = deal.claim_send(timezone.now())
        if not claimed:
            deal.refresh_from_db()
    except Exception:  # never a 500 after Won committed; the database is likely unhealthy, so nothing is recorded
        logger.exception("Unexpected error claiming deal %s for its ERPNext send", deal.pk)
        return Outcome(Opportunity.ErpStatus.FAILED, None, UNEXPECTED, "warning")
    if not claimed:
        if deal.stage != Stage.WON:
            message = ONLY_WON
        else:
            message = ALREADY_SENT if deal.erp_status == Opportunity.ErpStatus.SENT else BEING_SENT
        return Outcome(deal.erp_status, deal.erp_order, message, "error")

    quote = None
    status, order, message, level = Opportunity.ErpStatus.FAILED, "", UNEXPECTED, "warning"
    try:
        if delivery_date:
            deal.delivery_date = delivery_date
            deal.save(update_fields=["delivery_date"])
        quote = accepted_quote(deal)
        status, order, message, level = _send(deal, quote, client, today)
    except Unavailable:
        message = NO_ANSWER
    except Refused as refusal:
        message = str(refusal)[:MAX_MESSAGE]
    except Exception:  # never a 500 after Won committed; ids only in the log, no payloads or credentials
        logger.exception("Unexpected error sending deal %s (quote %s) to ERPNext", deal.pk, quote and quote.number)
    if not _recorded(deal, status, order, "" if level == "success" else message):
        status, order, message, level = Opportunity.ErpStatus.FAILED, "", UNEXPECTED, "warning"
        _recorded(deal, status, order, message)  # if this fails too, the claim goes stale and the deal shows failed
    return Outcome(status, order or None, message, level)


def _recorded(deal, status, order, error):
    """record_send that never raises, since Won has committed: False (and logged) when the row couldn't be stored."""
    try:
        deal.record_send(status, order, error)
        return True
    except Exception:
        logger.exception("Unexpected error recording the ERPNext send of deal %s", deal.pk)
        return False


def _send(deal, quote, client, today):
    """Lookup first (adopt), then customer (+ address), SST rows, create; a refused create is looked up once more.
    Every order found or created goes through _checked, which submits a draft."""
    if is_zero(deal):
        return Opportunity.ErpStatus.FAILED, "", ZERO_TOTAL, "warning"
    found = client.find_order(quote.number)
    if found:
        return _checked(deal, client, found, ADOPTED)
    account = deal.account
    wanted = customer_payload(account)
    customer = client.get_customer(wanted["customer_name"])
    if customer is None:
        customer = client.create_customer(wanted)
        address = address_payload(account, customer["name"])
        if address:
            client.create_address(address)
    rows = client.tax_rows(SST_TEMPLATE) if taxed(account) else []
    try:
        created = client.create_order(order_payload(deal, quote, customer["name"], rows, today, deal.delivery_date))
    except Refused:
        found = client.find_order(quote.number)  # created meanwhile (unique crm_reference): adopt; else the refusal
        if not found:
            raise
        return _checked(deal, client, found, ADOPTED)
    return _checked(deal, client, created, CREATED)


def _checked(deal, client, order, message):
    """Submit a draft (just created, or found because its submit failed or never ran), then sent either way; a net
    total that differs from the deal amount becomes the warning (AC8)."""
    if order["docstatus"] == 0:
        order = client.submit_order(order["name"])
    net = Decimal(str(order["net_total"]))
    if net != deal.amount:
        return Opportunity.ErpStatus.SENT, order["name"], MISMATCH.format(order["name"], net, deal.amount), "warning"
    return Opportunity.ErpStatus.SENT, order["name"], message.format(order["name"]), "success"
