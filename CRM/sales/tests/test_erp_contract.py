"""004 live contract tests (layer C): the real sales.erpnext client, with the CRM Integration keys, against ERPNext's
contract.localhost site. Run by scripts/test-erp.sh (ERP_CONTRACT=1); skipped otherwise, and they refuse any other
site: they create customers and submitted sales orders, so never the demo site localhost.

Rows: CT-* in test-cases.md, ACT-* in api-contract-tests.md. Each run uses its own references (QT-CT-<run>-<n>) and
customer names (ending in <run>), so reruns never collide with earlier runs' records."""

import json
import os
import re
import time
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import quote, urlencode

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from sales import erp, erpnext, rules
from sales.erpnext import PERMISSION_REFUSED, Client, Refused, Unavailable
from sales.models import Account, Quote
from sales.tests.base import CRMTestCase

SITE = "contract.localhost"
RUN = int(time.time())
MY_NAME = f"A&B Steel / Ng's Fab #1 {RUN} Sdn Bhd"  # "&", "/", "'" and "#" must survive the URL (ACT-2)
SG_NAME = f"Jurong Precision Engineering {RUN} Pte Ltd"
EXISTING = "Existing Fixture Steel Sdn Bhd"  # made by ombak_mfg.setup.contract.existing_customer (test-erp.sh)
# Administrator's draft and submitted order, made by ombak_mfg.setup.contract.others_orders: {"draft": name, ...}
OTHERS = json.loads(os.environ.get("ERP_OTHERS_ORDERS") or "{}")
OTHERS_REFERENCES = {"draft": "QT-FIXTURE-OTHERS-DRAFT", "submitted": "QT-FIXTURE-OTHERS-SUBMITTED"}
SKS = {
    "state": "Selangor", "registration_no": "202001023456", "address": "Lot 5, Jalan SR 8/3", "city": "Seri Kembangan",
    "postcode": "43300", "phone": "+60 3-8941 2200",
}  # fmt: skip

# the live tests opt back in to the URL that settings drop for every unit-test run
live = unittest.skipUnless(os.environ.get("ERP_CONTRACT") == "1", "live: run via scripts/test-erp.sh")
erp_url = override_settings(ERPNEXT_URL=os.environ.get("ERPNEXT_URL", ""))


def refuse_other_sites(site):
    """AC22: these tests write; only the contract site may get the writes. Checked before any request."""
    if site != SITE:
        raise RuntimeError(f"Live contract tests run on {SITE} only, not {site!r}.")


def line(item_code, qty, unit_price, discount_pct="0"):
    return SimpleNamespace(
        product=SimpleNamespace(item_code=item_code), qty=Decimal(qty), unit_price=Decimal(unit_price),
        discount_pct=Decimal(discount_pct),
    )  # fmt: skip


def tray(qty, discount_pct="0", price="85.00"):
    return line("FG-CT-300", qty, price, discount_pct)


def frame(qty, discount_pct="0"):
    return line("FG-EBF-1000", qty, "1450.00", discount_pct)


def order_body(customer, reference, lines, state, tax_rows):
    """The CRM's own order payload (erp.order_payload) for these quote lines; amount from the CRM's money rules."""
    deal = SimpleNamespace(amount=rules.quote_total(lines), account=Account(state=state))
    quote_ = SimpleNamespace(number=reference, lines=SimpleNamespace(select_related=lambda *fields: lines))
    today = timezone.localdate()
    return erp.order_payload(deal, quote_, customer, tax_rows, today, today + timedelta(days=14)), deal.amount


def money(value):
    return Decimal(str(value))


def placed(client, body):
    """Calls 5 and 5b: the order created as a draft, then submitted."""
    return client.submit_order(client.create_order(body)["name"])


def raw(client, method, path, body=None):
    """(status, parsed body) straight from ERPNext, bypassing the client's error mapping (some rows check both)."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{client.url}/api/v2/document/{path}", data, client.headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status, text = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read()
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


@live
@erp_url
class ContractTests(SimpleTestCase):
    """Calls 1-5 of api-contract.md with the client the CRM uses. setUpClass makes CT-2's Malaysian customer, its
    address and its order; the tests read them back."""

    @classmethod
    def setUpClass(cls):
        refuse_other_sites(settings.ERPNEXT_SITE)
        super().setUpClass()
        cls.erp = erpnext.client_from_settings()
        if cls.erp is None:
            raise RuntimeError("ERPNEXT_URL is not set: run via scripts/test-erp.sh")
        cls.sst = cls.erp.tax_rows(erp.SST_TEMPLATE)  # call 4b
        account = Account(name=MY_NAME, **SKS)
        cls.customer = cls.erp.create_customer(erp.customer_payload(account))  # call 3
        cls.address = cls.erp.create_address(erp.address_payload(account, cls.customer["name"]))  # call 4
        cls.reference = f"QT-CT-{RUN}-2"
        body, cls.amount = order_body(cls.customer["name"], cls.reference, [tray("3", "7.5")], "Selangor", cls.sst)
        cls.body, cls.draft = body, cls.erp.create_order(body)  # call 5
        cls.order = cls.erp.submit_order(cls.draft["name"])  # call 5b

    def rows(self, reference):
        """Call 1's whole `data` list (the client returns only its first row)."""
        filters = [["crm_reference", "=", reference], ["docstatus", "<", 2]]
        query = urlencode({"fields": json.dumps(erpnext.ORDER_FIELDS), "filters": json.dumps(filters)}, quote_via=quote)
        return self.erp._call("GET", f"Sales%20Order?{query}", expect=list)

    def test_refuses_any_site_but_contract(self):  # CT-1, AC22
        for site in ("localhost", "", "test.localhost"):
            with self.subTest(site=site), self.assertRaisesMessage(RuntimeError, SITE):
                refuse_other_sites(site)
        self.assertEqual(settings.ERPNEXT_SITE, SITE)
        self.assertEqual(self.erp.headers["Host"], SITE)

    def test_customer_created_under_its_own_name(self):  # ACT-3, ACT-2, CT-8
        self.assertEqual(self.customer["name"], MY_NAME)  # the order's customer and the Address link use it
        self.assertEqual(self.erp.get_customer(MY_NAME)["name"], MY_NAME)  # quoted path: "&", "/", "'", "#"
        self.assertEqual(self.erp.get_customer(MY_NAME.lower())["name"], MY_NAME)  # FM8: case-insensitive match
        self.assertIsNone(self.erp.get_customer(f"No Such Customer {RUN} / #1"))  # 404 is "missing", not Refused

    def test_address_linked_to_the_customer(self):  # ACT-4
        self.assertEqual(self.address["links"][0]["link_doctype"], "Customer")
        self.assertEqual(self.address["links"][0]["link_name"], MY_NAME)
        self.assertEqual((self.address["address_line1"], self.address["city"]), (SKS["address"], SKS["city"]))

    def test_sst_template_rows(self):  # ACT-5
        status, body = raw(self.erp, "GET", "Sales%20Taxes%20and%20Charges%20Template/Malaysia%20SST%20-%20OMW")
        self.assertEqual((status, len(body["data"]["taxes"])), (200, 1))
        [row] = self.sst
        self.assertEqual(list(row), list(erp.TAX_KEYS))  # only the four keys; no name/parent/idx copied
        self.assertEqual((row["charge_type"], row["rate"]), ("On Net Total", 10))
        self.assertTrue(row["account_head"] and row["description"])

    def test_order_submitted_with_the_quote_total_and_one_sst_row(self):  # CT-2, ACT-6, FM5, FM6
        self.assertEqual((self.body["discount_amount"], self.body["taxes_and_charges"]), (19.12, erp.SST_TEMPLATE))
        order = self.order
        self.assertRegex(order["name"], r"^SAL-ORD-\d{4}-\d{5}$")
        draft = self.draft
        self.assertEqual((draft["name"], draft["docstatus"], draft["status"]), (order["name"], 0, "Draft"))
        self.assertEqual((order["docstatus"], order["status"]), (1, "To Deliver and Bill"))  # AC6: ERPNext computed it
        self.assertEqual(order["crm_reference"], self.reference)
        self.assertEqual(money(order["net_total"]), self.amount)
        self.assertEqual(self.amount, Decimal("235.88"))
        # the template named and its rows sent explicitly: still one row, not doubled
        self.assertEqual([money(t["tax_amount"]) for t in order["taxes"]], [Decimal("23.59")])
        self.assertEqual(money(order["grand_total"]), Decimal("259.47"))

    def test_singapore_customer_and_order_without_tax(self):  # ACT-3 (Singapore), ACT-7, CT-3, FM5
        account = Account(name=SG_NAME, state="Singapore", registration_no="201812345K")
        customer = self.erp.create_customer(erp.customer_payload(account))
        self.assertEqual(customer["name"], SG_NAME)
        self.assertIsNone(erp.address_payload(account, SG_NAME))
        body, amount = order_body(SG_NAME, f"QT-CT-{RUN}-3", [frame("2", "5")], "Singapore", [])
        self.assertNotIn("taxes_and_charges", body)
        self.assertEqual(body["discount_amount"], 145.00)
        order = placed(self.erp, body)
        self.assertEqual(order["taxes"], [])  # ERPNext adds no template on its own
        self.assertEqual((money(order["net_total"]), money(order["grand_total"])), (amount, Decimal("2755.00")))

    def test_order_for_an_existing_customer(self):  # CT-12, AC20
        """A customer the CRM didn't create, as on the demo site: ERPNext fills the order from its primary address,
        which Administrator owns, so the CRM user must be able to read it (the 'All' rule is if_owner only)."""
        self.assertEqual(self.erp.get_customer(EXISTING)["name"], EXISTING, "run via scripts/test-erp.sh")
        body, amount = order_body(EXISTING, f"QT-CT-{RUN}-9", [tray("3", "7.5")], "Johor", self.sst)
        order = placed(self.erp, body)
        self.assertEqual((order["docstatus"], order["customer"]), (1, EXISTING))
        self.assertTrue(order["shipping_address_name"])  # the existing address, read as the CRM user
        self.assertEqual((money(order["net_total"]), money(order["grand_total"])), (amount, Decimal("259.47")))

    def test_net_total_is_the_quote_total(self):  # CT-4, CT-5, TOT-*, Review Focus 4, FM4
        cases = [  # lines, the CRM quote total, tax, grand total
            ([tray("3", "12.5")], "223.13", "22.31", "245.44"),  # CT-4: discount 31.87
            ([tray("3", "7.5"), frame("2", "5")], "2990.88", "299.09", "3289.97"),  # CT-5: 164.12, per-line rounding
            ([tray("3", "33.3", "33.33")], "66.69", "6.67", "73.36"),  # awkward price and discount: 33.30
            # half-sen edge: ERPNext rounds 0.5 x 33.33 to 16.66 (half-even), the CRM to 16.67 (half-up), so the
            # header discount is negative (-0.01) and ERPNext must take it for the net total to be exact. Every FG
            # item is in Nos (whole numbers only), so a fractional qty needs an item sold by the Kg
            ([line("RM-PP-GRY", "0.5", "33.33")], "16.67", "1.67", "18.34"),
        ]
        for n, (lines, total, tax, grand) in enumerate(cases, start=4):
            with self.subTest(total=total):
                body, amount = order_body(MY_NAME, f"QT-CT-{RUN}-{n}", lines, "Selangor", self.sst)
                self.assertEqual(amount, Decimal(total))
                if total == "16.67":
                    self.assertEqual(body["discount_amount"], -0.01)
                order = placed(self.erp, body)
                self.assertEqual(order["docstatus"], 1)
                self.assertEqual(money(order["net_total"]), amount)
                self.assertEqual([money(t["tax_amount"]) for t in order["taxes"]], [Decimal(tax)])
                self.assertEqual(money(order["grand_total"]), Decimal(grand))

    def test_fractional_qty_of_a_whole_number_item_is_refused(self):  # Review Focus 4: fails visibly, no wrong total
        body, _ = order_body(MY_NAME, f"QT-CT-{RUN}-8", [tray("0.5", "0", "33.33")], "Selangor", self.sst)
        with self.assertRaisesMessage(Refused, "Quantity (0.5) cannot be a fraction"):
            self.erp.create_order(body)

    def test_lookup_finds_the_order(self):  # CT-6, ACT-1
        found = self.erp.find_order(self.reference)
        self.assertEqual((found["name"], found["docstatus"]), (self.order["name"], 1))
        self.assertEqual((money(found["net_total"]), money(found["grand_total"])), (self.amount, Decimal("259.47")))
        self.assertEqual(len(self.rows(self.reference)), 1)
        self.assertEqual(self.rows(f"QT-CT-{RUN}-unused"), [])  # data is [] (not an error)
        self.assertIsNone(self.erp.find_order(f"QT-CT-{RUN}-unused"))

    def test_duplicate_reference_refused_then_found(self):  # CT-7, ACT-E4, AC13
        status, body = raw(self.erp, "POST", "Sales%20Order", self.body)
        self.assertIn(status, (409, 417))
        self.assertTrue(body["errors"][0]["message"])
        with self.assertRaises(Refused) as caught:
            self.erp.create_order(self.body)
        self.assertNotEqual(str(caught.exception), PERMISSION_REFUSED)
        self.assertEqual([row["name"] for row in self.rows(self.reference)], [self.order["name"]])  # no second order

    def test_integration_user_is_least_privilege(self):  # CT-9, ACT-E2, AC20, FM12
        order = erpnext._doc("Sales Order", self.order["name"])
        refused = [
            ("POST", f"{order}/method/cancel", {}), ("DELETE", order, None),
            ("GET", "Sales%20Invoice", None), ("POST", "Work%20Order", {"production_item": "FG-CT-300", "qty": 1}),
            ("GET", "Job%20Card", None),
        ]  # fmt: skip
        for method, path, body in refused:
            with self.subTest(method=method, path=path):
                self.assertEqual(raw(self.erp, method, path, body)[0], 403)
                with self.assertRaisesMessage(Refused, PERMISSION_REFUSED):
                    self.erp._call(method, path, body, expect=(dict, list, str))
        self.assertEqual(self.erp.find_order(self.reference)["docstatus"], 1)  # still submitted
        # write is there to submit a draft (5b); a submitted order still can't be edited
        status, _ = raw(self.erp, "PUT", order, {"customer": EXISTING})
        self.assertTrue(400 <= status < 500, status)
        self.assertEqual(self.erp._call("GET", order)["customer"], MY_NAME)

    def test_orders_it_did_not_create_are_out_of_reach(self):  # CT-13, AC20, FM12: its Sales Order rule is if_owner
        self.assertEqual(set(OTHERS), {"draft", "submitted"}, "run via scripts/test-erp.sh")
        for state, name in OTHERS.items():
            order = erpnext._doc("Sales Order", name)
            with self.subTest(state=state):
                # po_no stays editable after submit; and a human's draft is theirs to finish
                self.assertEqual(raw(self.erp, "PUT", order, {"po_no": f"CRM-{RUN}"})[0], 403)
                self.assertEqual(raw(self.erp, "GET", order)[0], 403)
                self.assertIsNone(self.erp.find_order(OTHERS_REFERENCES[state]))  # call 1 lists only its own orders
        self.assertEqual(self.erp.find_order(self.reference)["name"], self.order["name"])
        self.assertEqual(self.erp._call("GET", erpnext._doc("Sales Order", self.order["name"]))["docstatus"], 1)

    def test_wrong_secret_is_unavailable(self):  # CT-10, ACT-E1
        wrong = Client(settings.ERPNEXT_URL, SITE, settings.ERPNEXT_API_KEY, "wrong")
        self.assertEqual(raw(wrong, "GET", "Sales%20Order")[0], 401)
        with self.assertRaises(Unavailable) as caught:
            wrong.find_order(self.reference)
        self.assertNotIn("wrong", str(caught.exception))

    def test_validation_error_is_plain_text(self):  # ACT-E3, FM10
        body = {**self.body, "crm_reference": f"QT-CT-{RUN}-E3"}
        body["items"] = [{**body["items"][0], "item_code": "FG-NOPE-999"}]
        status, reply = raw(self.erp, "POST", "Sales%20Order", body)
        self.assertTrue(400 <= status < 500 and status != 403, status)
        self.assertTrue(all({"message", "exception"} <= set(error) for error in reply["errors"]))
        self.assertIn("Traceback", reply["errors"][0]["exception"])  # the trap the client must not fall into
        with self.assertRaises(Refused) as caught:
            self.erp.create_order(body)
        message = str(caught.exception)
        self.assertIn("FG-NOPE-999", message)
        self.assertLessEqual(len(message), 300)
        for leak in ("<", "Traceback", "Error:", settings.ERPNEXT_API_SECRET):
            self.assertNotIn(leak, message)

    def test_connection_error_is_unavailable(self):  # ACT-E5
        started = time.monotonic()
        with self.assertRaises(Unavailable):
            Client("http://backend:9", SITE, "k", "s").find_order(self.reference)
        self.assertLess(time.monotonic() - started, 10)


@live
@erp_url
class SendOrderContractTests(CRMTestCase):
    @classmethod
    def setUpClass(cls):
        refuse_other_sites(settings.ERPNEXT_SITE)
        super().setUpClass()

    @staticmethod
    def restart_quote_numbers(at):
        with connection.cursor() as cursor:
            cursor.execute("SELECT setval(pg_get_serial_sequence('sales_quote', 'id'), %s)", [at])

    def test_won_deal_sent_end_to_end(self):  # CT-11, AC2, AC3, AC5, AC9
        # the test DB numbers quotes from 1 on every run, but ERPNext keeps every run's orders: number this quote
        # from RUN (QT-<year>-<RUN>), then put the sequence back (it isn't rolled back) for the tests that follow
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(pg_get_serial_sequence('sales_quote', 'id'))")
            self.addCleanup(self.restart_quote_numbers, cursor.fetchone()[0])
        self.restart_quote_numbers(RUN)
        account = Account.objects.create(name=f"Seri Kembangan Steel Works {RUN} Sdn Bhd", **SKS)
        deal = self.deal(stage="negotiation", account=account)
        self.quote(deal, lines=[(None, "3", "7.5")], status=Quote.Status.SENT)
        today = timezone.localdate()
        deal.mark_won(self.rep, today + timedelta(days=14))
        client = erpnext.client_from_settings()

        outcome = erp.send_order(deal, client, today)

        deal.refresh_from_db()
        number = erp.accepted_quote(deal).number
        self.assertEqual((outcome.status, outcome.level), ("sent", "success"), outcome.message)
        self.assertEqual((deal.erp_status, deal.erp_error), ("sent", ""))
        found = client.find_order(number)  # crm_reference is the quote number
        self.assertEqual(found["name"], deal.erp_order)
        self.assertEqual(money(found["net_total"]), deal.amount)
        self.assertEqual(deal.amount, Decimal("235.88"))
        self.assertEqual(client.get_customer(account.name)["name"], account.name)
        link = json.dumps([["Dynamic Link", "link_name", "=", account.name]])
        addresses = client._call("GET", f"Address?{urlencode({'filters': link}, quote_via=quote)}", expect=list)
        self.assertEqual(len(addresses), 1)  # the Address was created and linked to the new customer
        self.assertTrue(re.match(r"^SAL-ORD-\d{4}-\d{5}$", deal.erp_order))
        order = client._call("GET", erpnext._doc("Sales Order", deal.erp_order))
        self.assertEqual((order["docstatus"], order["status"]), (1, "To Deliver and Bill"))  # AC6: not "Draft"
