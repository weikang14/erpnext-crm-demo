"""An in-memory stand-in for sales.erpnext.Client (behaviour: 004 test-cases.md, Fixtures).

Call names map to the API contract: find_order c1, get_customer c2, create_customer c3, create_address c4,
tax_rows c4b, create_order c5, submit_order c5b. Each call is recorded in `calls` as (method, argument), then runs
`hooks[method]()` (slow call, a read through a second connection...), then raises `fail[method]` if set
(nothing happens), then takes effect, then raises `fail_after[method]` if set (it happened, the reply was lost).
"""

from decimal import Decimal

from sales.erpnext import Refused

CENT = Decimal("0.01")
TEC = "Tanjung Electrical Contractors Sdn Bhd"
SST_ROW = {"charge_type": "On Net Total", "account_head": "SST Payable - OMW", "rate": 10, "description": "SST 10%"}


def _key(name):
    return name.rstrip().casefold()  # MariaDB's collation: case-insensitive, trailing spaces ignored


def _dec(value):
    return Decimal(str(value))


class FakeERPNext:
    def __init__(self):
        self.orders = {}  # crm_reference -> {"name", "docstatus", "net_total", "grand_total"}; 0 draft, 2 cancelled
        self.customers = {TEC: {"name": TEC, "customer_name": TEC, "territory": "Malaysia"}}  # name -> doc
        self.addresses = []
        self.taxes = [dict(SST_ROW)]  # the "Malaysia SST - OMW" template's rows
        self.next_order = 20  # first order: SAL-ORD-2026-00020
        self.net_total = None  # when set, create_order reports this net total instead of the computed one (TOT-7)
        self.calls = []
        self.hooks = {}
        self.fail = {}
        self.fail_after = {}

    @property
    def names(self):
        return [method for method, _ in self.calls]

    def _call(self, method, argument):
        self.calls.append((method, argument))
        if method in self.hooks:
            self.hooks[method]()
        if method in self.fail:
            raise self.fail[method]

    def _done(self, method, result):
        if method in self.fail_after:
            raise self.fail_after[method]
        return result

    def find_order(self, reference):
        self._call("find_order", reference)
        order = self.orders.get(reference)
        return dict(order) if order and order["docstatus"] < 2 else None

    def get_customer(self, name):
        self._call("get_customer", name)
        found = next((doc for stored, doc in self.customers.items() if _key(stored) == _key(name)), None)
        return dict(found) if found else None

    def create_customer(self, payload):
        self._call("create_customer", payload)
        name = payload["customer_name"].strip()
        self.customers[name] = {**payload, "name": name}
        return self._done("create_customer", dict(self.customers[name]))

    def create_address(self, payload):
        self._call("create_address", payload)
        address = {**payload, "name": f"{payload.get('address_title')}-Billing"}
        self.addresses.append(address)
        return self._done("create_address", dict(address))

    def tax_rows(self, template):
        self._call("tax_rows", template)
        return self._done("tax_rows", [dict(row) for row in self.taxes])

    def create_order(self, payload):
        """Totals as ERPNext computes them: Σ qty × rate − header discount; each tax row rounded to the sen."""
        self._call("create_order", payload)
        reference = payload["crm_reference"]
        if reference in self.orders:  # the unique custom field, cancelled orders included
            raise Refused(f"Duplicate entry '{reference}' for key 'crm_reference'")
        net = sum(_dec(item["qty"]) * _dec(item["rate"]) for item in payload["items"]) - _dec(
            payload.get("discount_amount", 0)
        )
        net = net.quantize(CENT)
        tax = sum((net * _dec(row["rate"]) / 100).quantize(CENT) for row in payload.get("taxes", []))
        net = _dec(self.net_total) if self.net_total is not None else net
        order = {
            "name": f"SAL-ORD-2026-{self.next_order:05d}",
            "docstatus": payload.get("docstatus", 0),  # ERPNext's default: a draft
            "net_total": float(net),  # floats, as json.loads gives them
            "grand_total": float(net + tax),
        }
        self.next_order += 1
        self.orders[reference] = order
        return self._done("create_order", dict(order))

    def submit_order(self, name):
        """A draft becomes submitted; any other order is refused, so a second submit shows up in the tests."""
        self._call("submit_order", name)
        order = next((order for order in self.orders.values() if order["name"] == name), None)
        if order is None or order["docstatus"] != 0:
            raise Refused(f"Sales Order {name} is not a draft")
        order["docstatus"] = 1
        return self._done("submit_order", dict(order))
