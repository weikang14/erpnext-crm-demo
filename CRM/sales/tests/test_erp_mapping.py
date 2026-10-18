"""004 task 2.3: the pure mapping from a won deal to ERPNext Customer, Address and Sales Order payloads."""

import json
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from sales import erp, rules
from sales.models import Account, Product, Quote
from sales.tests.base import CRMTestCase

TODAY, DELIVERY = date(2026, 10, 15), date(2026, 10, 29)
TEC = "Tanjung Electrical Contractors Sdn Bhd"
SST_ROW = {"charge_type": "On Net Total", "account_head": "SST - OMW", "rate": 10, "description": "SST 10%"}


def sks(**fields):
    values = {
        "name": "Seri Kembangan Steel Works Sdn Bhd", "state": "Selangor", "registration_no": "202001023456",
        "address": "Lot 5, Jalan SR 8/3", "city": "Seri Kembangan", "postcode": "43300", "phone": "+60 3-8941 2200",
    }  # fmt: skip
    return Account(**{**values, **fields})


def jpe():
    return Account(name="Jurong Precision Engineering Pte Ltd", state="Singapore", registration_no="201812345K")


def line(qty, price, discount="0"):
    return SimpleNamespace(qty=Decimal(qty), unit_price=Decimal(price), discount_pct=Decimal(discount))


def erpnext_net_total(items, discount):
    """What ERPNext makes of the order: each item amount rounded to the sen (Banker's), less the header discount."""
    amounts = (
        (Decimal(str(i["qty"])) * Decimal(str(i["rate"]))).quantize(rules.CENT, ROUND_HALF_EVEN) for i in items
    )
    return sum(amounts, rules.ZERO) - Decimal(str(discount))


class CustomerMappingTests(SimpleTestCase):
    def test_customer_payload(self):  # CUST-3
        self.assertEqual(
            erp.customer_payload(sks()),
            {
                "customer_name": "Seri Kembangan Steel Works Sdn Bhd", "customer_type": "Company",
                "customer_group": "Commercial", "territory": "Malaysia", "tax_id": "202001023456",
            },
        )  # fmt: skip

    def test_singapore_customer(self):  # CUST-4
        payload = erp.customer_payload(jpe())
        self.assertEqual((payload["territory"], payload["tax_id"]), ("Singapore", "201812345K"))
        self.assertEqual(erp.territory(jpe()), "Singapore")
        self.assertFalse(erp.taxed(jpe()))

    def test_every_malaysian_state_is_malaysia_and_taxed(self):  # CUST-5, TAX-6
        for state in ["Johor", "Kuala Lumpur", "Sabah", "Sarawak", "Labuan"]:
            with self.subTest(state):
                account = sks(state=state)
                self.assertEqual(erp.territory(account), "Malaysia")
                self.assertTrue(erp.taxed(account))
                self.assertEqual(erp.customer_payload(account)["territory"], "Malaysia")

    def test_no_tax_id_without_registration_no(self):  # CUST-6
        self.assertNotIn("tax_id", erp.customer_payload(sks(registration_no="")))
        self.assertNotIn("tax_id", erp.customer_payload(sks(registration_no="  ")))

    def test_customer_name_is_stripped(self):  # CUST-14
        self.assertEqual(erp.customer_payload(sks(name=f" {TEC} "))["customer_name"], TEC)

    def test_address_payload(self):  # CUST-7
        self.assertEqual(
            erp.address_payload(sks(), "Seri Kembangan Steel Works Sdn Bhd"),
            {
                "address_title": "Seri Kembangan Steel Works Sdn Bhd", "address_type": "Billing",
                "address_line1": "Lot 5, Jalan SR 8/3", "city": "Seri Kembangan", "state": "Selangor",
                "pincode": "43300", "country": "Malaysia", "phone": "+60 3-8941 2200",
                "links": [{"link_doctype": "Customer", "link_name": "Seri Kembangan Steel Works Sdn Bhd"}],
            },
        )  # fmt: skip

    def test_address_links_the_customer_erpnext_named(self):  # CUST-7
        name = "SERI KEMBANGAN STEEL WORKS SDN BHD"
        self.assertEqual(erp.address_payload(sks(), name)["links"], [{"link_doctype": "Customer", "link_name": name}])

    def test_no_address_without_city_or_line1(self):  # CUST-8, CUST-9
        for fields in [{"city": ""}, {"address": ""}, {"city": "  "}, {"address": " "}]:
            with self.subTest(fields):
                self.assertIsNone(erp.address_payload(sks(**fields), "Seri Kembangan Steel Works Sdn Bhd"))
        self.assertIsNone(erp.address_payload(jpe(), "Jurong Precision Engineering Pte Ltd"))

    def test_address_omits_empty_postcode_and_phone(self):  # CUST-10
        payload = erp.address_payload(sks(postcode="", phone=""), "Seri Kembangan Steel Works Sdn Bhd")
        self.assertNotIn("pincode", payload)
        self.assertNotIn("phone", payload)
        self.assertEqual(payload["city"], "Seri Kembangan")

    def test_singapore_address_country(self):  # CUST-7
        account = jpe()
        account.address, account.city = "2 Jurong West Way", "Singapore"
        self.assertEqual(erp.address_payload(account, account.name)["country"], "Singapore")


class HeaderDiscountTests(SimpleTestCase):
    def test_discount_makes_the_quote_total(self):  # TOT-1, TOT-3, TOT-4, TOT-5, TOT-6
        cases = [
            ([line("3", "85.00", "7.5")], "235.88", "19.12"),
            ([line("3", "85.00", "12.5")], "223.13", "31.87"),
            ([line("40", "85.00", "7.5")], "3145.00", "255.00"),
            ([line("3", "85.00", "7.5"), line("2", "1450.00", "5")], "2990.88", "164.12"),
            ([line("10", "85.00")], "850.00", "0.00"),
        ]
        for lines, total, discount in cases:
            with self.subTest(total):
                amount = rules.quote_total(lines)
                self.assertEqual(amount, Decimal(total))
                self.assertEqual(erp.header_discount(lines, amount), Decimal(discount))

    def test_fractional_qty_and_awkward_prices_stay_exact(self):  # Review Focus 4
        cases = [
            [line("3", "33.33", "33.3")],
            [line("0.5", "33.33")],  # ERPNext 16.66 (Banker's), the CRM 16.67 (half-up): discount -0.01
            [line("0.5", "85.00", "7.5")],
            [line("3", "33.33", "33.3"), line("0.5", "33.33"), line("0.5", "85.00", "7.5"), line("0.25", "0.10")],
            [line("1.5", "0.03"), line("0.5", "0.01"), line("2.5", "0.07", "50")],
        ]
        for lines in cases:
            with self.subTest(lines):
                amount = rules.quote_total(lines)
                discount = erp.header_discount(lines, amount)
                self.assertEqual(discount, discount.quantize(rules.CENT))
                items = [{"qty": float(x.qty), "rate": float(x.unit_price)} for x in lines]
                self.assertEqual(erpnext_net_total(items, float(discount)), amount)

    def test_half_sen_line_rounds_like_erpnext(self):  # Review Focus 4
        self.assertEqual(erp.header_discount([line("0.5", "33.33")], Decimal("16.67")), Decimal("-0.01"))


class OrderPayloadTests(CRMTestCase):
    def won(self, lines=((None, "3", "7.5"),), account=None):
        deal = self.deal(stage="quotation", account=account)
        quote = self.quote(deal, lines, status=Quote.Status.SENT)
        deal.mark_won(self.rep)
        quote.refresh_from_db()
        return deal, quote

    def body(self, deal, quote, tax_rows=(SST_ROW,), customer=TEC):
        return erp.order_payload(deal, quote, customer, list(tax_rows), TODAY, DELIVERY)

    def test_order_header(self):  # SO-1, SO-2
        deal, quote = self.won()
        body = self.body(deal, quote)
        expected = {
            "customer": TEC, "company": "Ombak Metal Works Sdn Bhd", "transaction_date": "2026-10-15",
            "delivery_date": "2026-10-29", "currency": "MYR", "crm_reference": quote.number,
            "disable_rounded_total": 1, "docstatus": 0,  # a draft: submitted by call 5b
        }  # fmt: skip
        self.assertEqual({key: body[key] for key in expected}, expected)
        self.assertRegex(body["crm_reference"], r"^QT-\d{4}-\d{5}$")

    def test_customer_is_the_name_erpnext_returned(self):  # CUST-2
        deal, quote = self.won()
        self.assertEqual(self.body(deal, quote, customer=TEC.upper())["customer"], TEC.upper())

    def test_items_follow_the_quote_lines(self):  # SO-4
        deal, quote = self.won(lines=((None, "3", "7.5"), (self.frame, "2", "5")))
        common = {"delivery_date": "2026-10-29", "warehouse": "Finished Goods - OMW"}
        self.assertEqual(
            self.body(deal, quote)["items"],
            [
                {"item_code": "FG-CT-300", "qty": 3, "rate": 85.00, **common},
                {"item_code": "FG-EBF-1000", "qty": 2, "rate": 1450.00, **common},
            ],
        )

    def test_rate_is_the_quote_snapshot(self):  # SO-5
        deal, quote = self.won()
        Product.objects.filter(pk=self.tray.pk).update(list_price=Decimal("90.00"))
        body = self.body(deal, quote)
        self.assertEqual(body["items"][0]["rate"], 85.00)
        self.assertEqual(body["discount_amount"], 19.12)

    def test_only_the_accepted_quote(self):  # SO-6
        deal = self.deal(stage="quotation")
        self.quote(deal, ((None, "5", "0"),), status=Quote.Status.SUPERSEDED)
        draft = self.quote(deal, ((self.frame, "100", "0"),), status=Quote.Status.DECLINED)
        pending = self.quote(deal, ((self.frame, "7", "0"),), status=Quote.Status.DECLINED)
        q133 = self.quote(deal, ((None, "3", "7.5"),), status=Quote.Status.SENT)
        deal.mark_won(self.rep)
        Quote.objects.filter(pk=draft.pk).update(status=Quote.Status.DRAFT)
        Quote.objects.filter(pk=pending.pk).update(status=Quote.Status.PENDING)
        quote = erp.accepted_quote(deal)
        self.assertEqual(quote, q133)
        self.assertEqual([(i["item_code"], i["qty"]) for i in self.body(deal, quote)["items"]], [("FG-CT-300", 3)])

    def test_no_accepted_quote_on_an_open_deal(self):  # SO-6
        deal = self.deal(stage="quotation")
        self.quote(deal, status=Quote.Status.SENT)
        self.assertIsNone(erp.accepted_quote(deal))

    def test_header_discount_not_line_discounts(self):  # TOT-1, TOT-2
        deal, quote = self.won()
        body = self.body(deal, quote)
        self.assertEqual(body["apply_discount_on"], "Net Total")
        self.assertEqual(body["discount_amount"], 19.12)
        self.assertIsInstance(body["discount_amount"], float)
        for item in body["items"]:
            self.assertFalse({"discount_percentage", "discount_amount", "price_list_rate"} & set(item))
        self.assertEqual(erpnext_net_total(body["items"], body["discount_amount"]), Decimal("235.88"))

    def test_no_discount_key_when_zero(self):  # TOT-6
        deal, quote = self.won(lines=((None, "10", "0"),))
        self.assertNotIn("discount_amount", self.body(deal, quote))

    def test_fractional_qty_order_is_exact(self):  # Review Focus 4
        odd = Product.objects.create(item_code="FG-ODD-1", name="Odd bracket", list_price=Decimal("33.33"))
        deal, quote = self.won(lines=((odd, "3", "33.3"), (odd, "0.5", "0"), (None, "0.5", "7.5")))
        self.assertEqual(deal.amount, Decimal("122.67"))
        body = self.body(deal, quote)
        self.assertEqual([i["qty"] for i in body["items"]], [3, 0.5, 0.5])
        self.assertEqual(body["discount_amount"], 36.48)
        self.assertEqual(erpnext_net_total(body["items"], body["discount_amount"]), deal.amount)

    def test_malaysian_order_carries_the_template_rows(self):  # TAX-1
        deal, quote = self.won()
        fetched = {**SST_ROW, "name": "abc123", "idx": 1, "included_in_print_rate": 0, "parent": "Malaysia SST - OMW"}
        body = self.body(deal, quote, tax_rows=[fetched])
        self.assertEqual(body["taxes_and_charges"], "Malaysia SST - OMW")
        self.assertEqual(body["taxes"], [SST_ROW])
        self.assertEqual(erp.SST_TEMPLATE, "Malaysia SST - OMW")

    def test_rate_comes_from_the_template(self):  # TAX-2
        deal, quote = self.won()
        self.assertEqual(self.body(deal, quote, tax_rows=[{**SST_ROW, "rate": 5}])["taxes"][0]["rate"], 5)

    def test_two_template_rows_sent_once(self):  # TAX-3
        deal, quote = self.won()
        second = {"charge_type": "On Net Total", "account_head": "Levy - OMW", "rate": 1, "description": "Levy"}
        self.assertEqual(self.body(deal, quote, tax_rows=[SST_ROW, second])["taxes"], [SST_ROW, second])

    def test_singapore_order_has_no_tax(self):  # TAX-4
        account = Account.objects.create(name="Jurong Precision Engineering Pte Ltd", state="Singapore")
        deal, quote = self.won(account=account)
        for rows in ([], [SST_ROW]):
            with self.subTest(rows=rows):
                body = self.body(deal, quote, tax_rows=rows, customer=account.name)
                self.assertNotIn("taxes", body)
                self.assertNotIn("taxes_and_charges", body)

    def test_east_malaysia_order_is_taxed(self):  # TAX-6
        for state in ["Kuala Lumpur", "Sabah", "Labuan"]:
            with self.subTest(state):
                account = Account.objects.create(name=f"Customer in {state}", state=state)
                deal, quote = self.won(account=account)
                self.assertEqual(self.body(deal, quote, customer=account.name)["taxes"], [SST_ROW])

    def test_body_is_json_with_two_decimals(self):  # TOT-1, TOT-5
        deal, quote = self.won(lines=((None, "3", "7.5"), (self.frame, "2", "5")))
        text = json.dumps(self.body(deal, quote))
        self.assertIn('"discount_amount": 164.12', text)
        self.assertIn('"rate": 1450.0', text)
        self.assertEqual(json.loads(text)["discount_amount"], 164.12)

    def test_zero_quote_is_detected(self):  # ZERO-1, ZERO-2
        deal, _ = self.won(lines=((None, "3", "100"),))
        self.assertEqual(deal.amount, Decimal("0.00"))
        self.assertTrue(erp.is_zero(deal))
        d1, _ = self.won()
        self.assertFalse(erp.is_zero(d1))
