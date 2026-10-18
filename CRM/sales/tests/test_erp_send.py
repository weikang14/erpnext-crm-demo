"""004 task 2.4: send_order, the won deal -> ERPNext flow (claim, lookup-first adopt, customer, SST, create, re-lookup,
net-total check), against FakeERPNext. Call names c1-c5 as in test-cases.md: find_order c1, get_customer c2,
create_customer c3, create_address c4, tax_rows c4b, create_order c5, submit_order c5b."""

import threading
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, override_settings

from sales import erp, erpnext
from sales.erpnext import UNEXPECTED_REPLY, Refused, Unavailable
from sales.models import Account, Activity, Opportunity, Product, Quote
from sales.regions import Region
from sales.tests.base import CRMTestCase, make_user
from sales.tests.fakes import SST_ROW, TEC, FakeERPNext

NOW = datetime(2026, 10, 15, 1, 0, tzinfo=UTC)  # 09:00 in Kuala Lumpur
TODAY, DELIVERY = date(2026, 10, 15), date(2026, 10, 29)
ORDER = "SAL-ORD-2026-00020"
SKS = "Seri Kembangan Steel Works Sdn Bhd"
T1 = "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated."
T0 = "The accepted quote is zero; ERPNext needs an order with a value."
TU = "Unexpected error while sending; see the server log."
CREATED = f"Sales order {ORDER} created in ERPNext."
ALREADY = "This deal's order is already in ERPNext."
ONLY_WON = "Only won deals can be sent."
BEING_SENT = "This deal is being sent right now; refresh in a moment."
WITH_TAX = ["find_order", "get_customer", "tax_rows", "create_order", "submit_order"]


def adopted(name=ORDER):
    return f"Sales order {name} is already in ERPNext; linked to this deal."


def held(name=ORDER, net=235.88, docstatus=1):
    return {"name": name, "docstatus": docstatus, "net_total": net, "grand_total": round(net * 1.1, 2)}


def flaky_record(failures):
    """record_send raising for its first `failures` calls (the database refused the row), then the real one."""
    real, calls = Opportunity.record_send, []

    def record(deal, *args, **kwargs):
        calls.append(args)
        if len(calls) <= failures:
            raise DatabaseError("could not write the row")
        return real(deal, *args, **kwargs)

    return mock.patch.object(Opportunity, "record_send", autospec=True, side_effect=record)


class SendTestCase(CRMTestCase):
    def setUp(self):
        super().setUp()
        clock = mock.patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.fake = FakeERPNext()

    def d1(self, account=None, lines=((None, "3", "7.5"),)):
        """Siti's deal with sent quote Q133 (3 x tray at 7.5 % -> 235.88), marked won with delivery 2026-10-29."""
        deal = self.deal(stage="negotiation", account=account)
        self.quote(deal, lines=list(lines), status=Quote.Status.SENT)
        deal.mark_won(self.rep, DELIVERY)
        return deal

    def sks(self, **fields):
        values = {
            "state": "Selangor", "registration_no": "202001023456", "address": "Lot 5, Jalan SR 8/3",
            "city": "Seri Kembangan", "postcode": "43300", "phone": "+60 3-8941 2200",
        }  # fmt: skip
        return Account.objects.create(name=SKS, **{**values, **fields})

    def send(self, deal, delivery_date=None, today=TODAY):
        return erp.send_order(deal, self.fake, today, delivery_date)

    def stored(self, deal):
        deal.refresh_from_db()
        return deal.erp_status, deal.erp_order, deal.erp_error, deal.erp_attempted_at

    def body(self):
        return [argument for method, argument in self.fake.calls if method == "create_order"][-1]

    def ref(self, deal):
        return erp.accepted_quote(deal).number

    def fail(self, deal, **fields):
        Opportunity.objects.filter(pk=deal.pk).update(erp_status="failed", erp_error=T1, **fields)


class SendTests(SendTestCase):
    def test_sends_the_order_and_records_it(self):  # SEND-1, SEND-2, CUST-1, TAX-1, TOT-9
        deal = self.d1()
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, CREATED, "success"))
        self.assertEqual(self.fake.names, WITH_TAX)
        self.assertEqual(self.stored(deal), ("sent", ORDER, "", NOW))
        body = self.body()
        self.assertEqual(
            (body["customer"], body["crm_reference"], body["transaction_date"], body["delivery_date"]),
            (TEC, self.ref(deal), "2026-10-15", "2026-10-29"),
        )
        self.assertEqual((body["taxes_and_charges"], body["taxes"]), ("Malaysia SST - OMW", [SST_ROW]))
        self.assertEqual((deal.stage, deal.amount), ("won", Decimal("235.88")))
        # created as a draft, then submitted (5b), so ERPNext computes its status (AC6)
        self.assertEqual((body["docstatus"], self.fake.calls[-1]), (0, ("submit_order", ORDER)))
        self.assertEqual(self.fake.orders[self.ref(deal)]["docstatus"], 1)

    def test_customer_is_the_name_erpnext_returned(self):  # CUST-2, EC-17
        deal = self.d1(self.account(TEC.upper()))
        self.assertEqual(self.send(deal).status, "sent")
        self.assertEqual(self.fake.names, WITH_TAX)
        self.assertEqual(self.body()["customer"], TEC)

    def test_padded_account_name_is_looked_up_stripped(self):  # CUST-14
        deal = self.d1(self.account(f" {TEC} "))
        self.send(deal)
        self.assertEqual(self.fake.calls[1], ("get_customer", TEC))
        self.assertNotIn("create_customer", self.fake.names)

    def test_name_that_needs_url_quoting_is_reused(self):  # Review Focus 1
        name = "A&B / Ng's Sdn Bhd"
        self.fake.customers[name] = {"name": name, "customer_name": name, "territory": "Malaysia"}
        deal = self.d1(self.account(name, state="Selangor"))
        self.assertEqual(self.send(deal).status, "sent")
        self.assertEqual(self.fake.calls[1], ("get_customer", name))
        self.assertNotIn("create_customer", self.fake.names)
        self.assertEqual(self.body()["customer"], name)

    def test_new_customer_with_address_then_reused(self):  # CUST-3, CUST-7, CUST-11
        account = self.sks()
        deal = self.d1(account)
        self.assertEqual(self.send(deal).status, "sent")
        self.assertEqual(
            self.fake.names,
            ["find_order", "get_customer", "create_customer", "create_address", "tax_rows", "create_order",
             "submit_order"],
        )
        calls = dict(self.fake.calls)
        self.assertEqual(calls["create_customer"], erp.customer_payload(account))
        self.assertEqual(calls["create_address"], erp.address_payload(account, SKS))
        self.assertEqual(self.body()["customer"], SKS)
        self.fake.calls.clear()
        second = self.d1(account)
        self.assertEqual(self.send(second).order, "SAL-ORD-2026-00021")
        self.assertEqual(self.fake.names, WITH_TAX)

    def test_singapore_customer_without_address_gets_no_address_and_no_tax(self):  # CUST-4, CUST-8, TAX-4
        jpe = Account.objects.create(name="Jurong Precision Engineering Pte Ltd", state="Singapore")
        deal = self.d1(jpe)
        self.assertEqual(self.send(deal).status, "sent")
        self.assertEqual(
            self.fake.names, ["find_order", "get_customer", "create_customer", "create_order", "submit_order"]
        )
        self.assertEqual(dict(self.fake.calls)["create_customer"]["territory"], "Singapore")
        self.assertNotIn("taxes", self.body())

    def test_address_refused_then_resend_reuses_the_customer(self):  # CUST-15, CUST-16, EC-26
        deal = self.d1(self.sks())
        self.fake.fail["create_address"] = Refused("Address Line 1 is mandatory")
        outcome = self.send(deal)
        self.assertEqual(outcome, erp.Outcome("failed", None, "Address Line 1 is mandatory", "warning"))
        self.assertNotIn("create_order", self.fake.names)
        self.assertEqual(self.stored(deal)[:3], ("failed", None, "Address Line 1 is mandatory"))
        self.fake.fail.clear()
        self.fake.calls.clear()
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, CREATED, "success"))
        self.assertEqual(self.fake.names, WITH_TAX)

    def test_template_refused_sends_no_order(self):  # TAX-5
        deal = self.d1()
        reason = "Sales Taxes and Charges Template Malaysia SST - OMW not found"
        self.fake.fail["tax_rows"] = Refused(reason)
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, reason, "warning"))
        self.assertNotIn("create_order", self.fake.names)

    def test_delivery_date_replaces_the_stored_one(self):  # RES-13, RES-15
        deal = self.d1()
        self.fail(deal, delivery_date=date(2026, 10, 20))
        self.assertEqual(self.send(deal, date(2026, 11, 5), today=date(2026, 10, 20)).status, "sent")
        body = self.body()
        self.assertEqual((body["transaction_date"], body["delivery_date"]), ("2026-10-20", "2026-11-05"))
        self.assertEqual({item["delivery_date"] for item in body["items"]}, {"2026-11-05"})
        deal.refresh_from_db()
        self.assertEqual(deal.delivery_date, date(2026, 11, 5))


class IdempotencyTests(SendTestCase):
    def test_existing_order_is_adopted(self):  # IDEM-2, AC12
        deal = self.d1()
        self.fake.orders[self.ref(deal)] = held()
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, adopted(), "success"))
        self.assertEqual(self.fake.names, ["find_order"])
        self.assertEqual(self.stored(deal), ("sent", ORDER, "", NOW))

    def test_found_draft_is_submitted_not_adopted_as_is(self):  # AC6, round 1
        deal = self.d1()
        self.fake.orders[self.ref(deal)] = held(docstatus=0)  # an earlier send created it; its submit never ran
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, adopted(), "success"))
        self.assertEqual(self.fake.names, ["find_order", "submit_order"])
        self.assertEqual(self.fake.orders[self.ref(deal)]["docstatus"], 1)

    def test_submit_refused_then_resend_submits_the_draft(self):  # AC6, AC12, round 1
        deal = self.d1()
        reason = "Credit limit has been crossed for customer Tanjung Electrical Contractors Sdn Bhd"
        self.fake.fail["submit_order"] = Refused(reason)
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, reason, "warning"))
        self.assertEqual(self.stored(deal)[:3], ("failed", None, reason))
        self.assertEqual(self.fake.orders[self.ref(deal)]["docstatus"], 0)  # the draft stays in ERPNext
        self.fake.fail.clear()
        self.fake.calls.clear()
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, adopted(), "success"))
        self.assertEqual(self.fake.names, ["find_order", "submit_order"])  # no second order
        self.assertEqual((len(self.fake.orders), self.fake.orders[self.ref(deal)]["docstatus"]), (1, 1))

    def test_submit_timed_out_after_it_landed_then_resend_adopts(self):  # AC12, round 1
        deal = self.d1()
        self.fake.fail_after["submit_order"] = Unavailable("timed out")
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, T1, "warning"))
        self.fake.fail_after.clear()
        self.fake.calls.clear()
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, adopted(), "success"))
        self.assertEqual(self.fake.names, ["find_order"])  # submitted already: adopted, not submitted twice

    def test_timeout_after_the_order_landed_then_resend_adopts(self):  # IDEM-3, EC-2, FM2
        deal = self.d1()
        self.fake.fail_after["create_order"] = Unavailable("timed out")
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, T1, "warning"))
        self.fake.fail_after.clear()
        self.fake.calls.clear()
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, adopted(), "success"))
        self.assertEqual(self.fake.names, ["find_order", "submit_order"])  # the draft that landed is submitted
        self.assertEqual(len(self.fake.orders), 1)

    def test_failed_deal_resent_creates_once(self):  # IDEM-4, CLAIM-2
        deal = self.d1()
        self.fail(deal)
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, CREATED, "success"))
        self.assertEqual(self.fake.names.count("create_order"), 1)
        self.assertEqual(self.stored(deal), ("sent", ORDER, "", NOW))

    def test_duplicate_refused_then_relookup_adopts(self):  # IDEM-5, AC13
        deal = self.d1()
        meanwhile = held("SAL-ORD-2026-00019")
        self.fake.hooks["create_order"] = lambda: self.fake.orders.setdefault(self.ref(deal), meanwhile)
        name = "SAL-ORD-2026-00019"
        self.assertEqual(self.send(deal), erp.Outcome("sent", name, adopted(name), "success"))
        self.assertEqual(self.fake.names[-2:], ["create_order", "find_order"])
        self.assertEqual(len(self.fake.orders), 1)

    def test_cancelled_order_holding_the_reference_fails_without_a_loop(self):  # IDEM-6, EC-22
        deal = self.d1()
        reference = self.ref(deal)
        self.fake.orders[reference] = held("SAL-ORD-2026-00007", docstatus=2)
        message = f"Duplicate entry '{reference}' for key 'crm_reference'"
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, message, "warning"))
        self.assertEqual((self.fake.names.count("find_order"), self.fake.names.count("create_order")), (2, 1))
        self.assertEqual(self.stored(deal)[:3], ("failed", None, message))

    def test_unexpected_reply_on_create_is_not_adopted(self):  # Review Focus 3
        deal = self.d1()
        self.fake.fail["create_order"] = Refused(UNEXPECTED_REPLY)
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, UNEXPECTED_REPLY, "warning"))
        self.assertEqual(self.fake.names[-2:], ["create_order", "find_order"])
        self.assertEqual(self.fake.orders, {})


class ErrorTests(SendTestCase):
    def test_unavailable_stops_at_the_first_call(self):  # SEND-4, SEND-5, EC-13
        deal = self.d1()
        self.fake.fail["find_order"] = Unavailable("ERPNext answered 503.")
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, T1, "warning"))
        self.assertEqual(self.fake.names, ["find_order"])
        self.assertEqual(self.stored(deal), ("failed", None, T1, NOW))
        self.assertEqual((deal.stage, deal.amount), ("won", Decimal("235.88")))

    def test_timeout_on_create(self):  # ERR-1
        deal = self.d1()
        self.fake.fail["create_order"] = Unavailable("timed out")
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, T1, "warning"))
        self.assertEqual(self.stored(deal)[2], T1)

    def test_refusal_reason_is_stored_and_capped(self):  # EC-20, ERR-8
        deal = self.d1()
        self.fake.fail["create_order"] = Refused("Could not find Item: FG-XX-999")
        self.assertEqual(self.send(deal), erp.Outcome("failed", None, "Could not find Item: FG-XX-999", "warning"))
        self.assertEqual(self.fake.names.count("create_order"), 1)  # no hidden retry
        long = "Value missing for: Delivery Date " * 40
        self.fake.fail["create_order"] = Refused(long)
        self.send(deal)
        stored = self.stored(deal)[2]
        self.assertLessEqual(len(stored), 300)
        self.assertTrue(stored.startswith(long[:100]))

    def test_mapping_error_fails_with_tu_and_is_logged(self):  # ERR-13, ERR-15, EC-25
        deal = self.d1()
        self.fake.taxes = [{"rate": 10}]  # a template row without its keys: the mapping raises KeyError
        with self.assertLogs("sales.erp", "ERROR") as logs:
            self.assertEqual(self.send(deal), erp.Outcome("failed", None, TU, "warning"))
        self.assertEqual(self.stored(deal)[:3], ("failed", None, TU))
        self.assertEqual((deal.stage, deal.amount), ("won", Decimal("235.88")))
        self.assertEqual(len(logs.records), 1)
        self.assertIn(str(deal.pk), logs.records[0].getMessage())
        self.assertIn(self.ref(deal), logs.records[0].getMessage())
        self.assertNotIn("create_order", self.fake.names)

    def test_unexpected_exception_on_resend(self):  # ERR-14
        deal = self.d1()
        self.fail(deal)
        self.fake.fail["create_order"] = RuntimeError("boom")
        with self.assertLogs("sales.erp", "ERROR"):
            self.assertEqual(self.send(deal), erp.Outcome("failed", None, TU, "warning"))

    @override_settings(
        ERPNEXT_URL="http://erp.test", ERPNEXT_SITE="localhost", ERPNEXT_API_KEY="k", ERPNEXT_API_SECRET="s3cr3t-xyz"
    )
    def test_unexpected_error_is_logged_without_secrets(self):  # ERR-15, FM10
        deal = self.d1()
        with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with self.assertLogs("sales.erp", "ERROR") as logs:
                outcome = erp.send_order(deal, erpnext.client_from_settings(), TODAY)
        self.assertEqual(outcome, erp.Outcome("failed", None, TU, "warning"))
        self.assertEqual([record.levelname for record in logs.records], ["ERROR"])
        text = "\n".join(logs.output)
        self.assertIn("Traceback", text)  # the server log has the detail; the deal and the page don't
        for secret in ("s3cr3t-xyz", "token k:", "Authorization"):
            self.assertNotIn(secret, text)

    def test_same_order_name_on_two_deals_is_recorded_on_both(self):  # AC11, round 1: no IntegrityError
        first, second = self.d1(), self.d1()
        self.assertEqual(self.send(first).order, ORDER)
        self.fake = FakeERPNext()  # another ERPNext site: its numbering starts over
        self.assertEqual(self.send(second), erp.Outcome("sent", ORDER, CREATED, "success"))
        self.assertEqual([self.stored(deal)[:2] for deal in (first, second)], [("sent", ORDER)] * 2)

    def test_recording_error_is_a_failed_send(self):  # round 1: recording never raises
        deal = self.d1()
        with flaky_record(1), self.assertLogs("sales.erp", "ERROR") as logs:
            self.assertEqual(self.send(deal), erp.Outcome("failed", None, TU, "warning"))
        self.assertEqual(self.stored(deal)[:3], ("failed", None, TU))  # the resend adopts the order made meanwhile
        self.assertIn(str(deal.pk), logs.records[0].getMessage())

    def test_recording_that_keeps_failing_still_raises_nothing(self):  # round 1
        deal = self.d1()
        with flaky_record(2), self.assertLogs("sales.erp", "ERROR") as logs:
            self.assertEqual(self.send(deal), erp.Outcome("failed", None, TU, "warning"))
        self.assertEqual(len(logs.records), 2)
        self.assertEqual(self.stored(deal)[0], "sending")  # shown as failed once stale, and resendable

    def test_claim_error_records_nothing_and_raises_nothing(self):  # round 2: never a 500 after Won
        deal = self.d1()
        before = self.stored(deal)
        claim = mock.patch.object(Opportunity, "claim_send", side_effect=DatabaseError("could not claim"))
        with claim, self.assertLogs("sales.erp", "ERROR") as logs:
            self.assertEqual(self.send(deal, date(2026, 11, 30)), erp.Outcome("failed", None, TU, "warning"))
        self.assertIn(str(deal.pk), logs.records[0].getMessage())
        self.assertEqual((self.stored(deal), deal.delivery_date), (before, DELIVERY))  # the date entered isn't stored
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.send(deal).status, "sent")  # still not_sent, so it can be sent later

    def test_reread_error_after_a_refused_claim_raises_nothing(self):  # round 2
        deal = self.d1()
        Opportunity.objects.filter(pk=deal.pk).update(erp_status="sent", erp_order=ORDER)
        reread = mock.patch.object(Opportunity, "refresh_from_db", side_effect=DatabaseError("could not read"))
        with reread, self.assertLogs("sales.erp", "ERROR"):
            self.assertEqual(self.send(deal), erp.Outcome("failed", None, TU, "warning"))
        self.assertEqual(self.stored(deal)[:2], ("sent", ORDER))
        self.assertEqual(self.fake.calls, [])

    def test_never_left_sending(self):  # CLAIM-8
        deal = self.d1()
        for error, message in [(Refused("Item FG-CT-300 is disabled"), "Item FG-CT-300 is disabled"),
                               (Unavailable("timed out"), T1), (RuntimeError("boom"), TU)]:  # fmt: skip
            logged = self.assertLogs("sales.erp", "ERROR") if message == TU else self.assertNoLogs("sales.erp")
            with self.subTest(error=error), logged:
                self.fake.fail["create_order"] = error
                self.assertEqual(self.send(deal).message, message)
                self.assertEqual(self.stored(deal)[:3], ("failed", None, message))


class TotalTests(SendTestCase):
    def test_net_total_mismatch_keeps_the_order_and_warns(self):  # TOT-7
        deal = self.d1()
        self.fake.net_total = 235.89
        warning = f"ERPNext order {ORDER} totals MYR 235.89, the quote MYR 235.88; check it in ERPNext."
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, warning, "warning"))
        self.assertEqual(self.stored(deal), ("sent", ORDER, warning, NOW))

    def test_adopted_order_is_checked_too(self):  # TOT-8
        deal = self.d1()
        self.fake.orders[self.ref(deal)] = held(net=200.0)
        warning = f"ERPNext order {ORDER} totals MYR 200.00, the quote MYR 235.88; check it in ERPNext."
        self.assertEqual(self.send(deal), erp.Outcome("sent", ORDER, warning, "warning"))
        self.assertEqual(self.stored(deal)[:3], ("sent", ORDER, warning))

    def test_zero_quote_is_never_sent(self):  # ZERO-1, ZERO-2, EC-15
        deal = self.d1(lines=((None, "3", "100"),))
        self.assertEqual(deal.amount, Decimal("0.00"))
        for attempt in ("won", "resend"):
            with self.subTest(attempt):
                self.assertEqual(self.send(deal), erp.Outcome("failed", None, T0, "warning"))
                self.assertEqual(self.fake.calls, [])
                self.assertEqual((self.stored(deal)[:3], deal.stage), (("failed", None, T0), "won"))


class ClaimAndConfigTests(SendTestCase):
    def test_refused_sends_change_nothing(self):  # RES-4, RES-8, CLAIM-3, Clar.
        sent = self.d1()
        Opportunity.objects.filter(pk=sent.pk).update(erp_status="sent", erp_order=ORDER, erp_attempted_at=NOW)
        sending = self.d1()
        fresh_claim = NOW - timedelta(minutes=1)
        Opportunity.objects.filter(pk=sending.pk).update(erp_status="sending", erp_attempted_at=fresh_claim)
        open_deal = self.deal(stage="negotiation")
        self.quote(open_deal, status=Quote.Status.SENT)
        lost = self.deal(stage="lost", closed_at=NOW, lost_reason=self.price_reason)
        cases = [(sent, "sent", ORDER, ALREADY), (sending, "sending", None, BEING_SENT),
                 (open_deal, "not_sent", None, ONLY_WON), (lost, "not_sent", None, ONLY_WON)]  # fmt: skip
        fields = ["stage", "delivery_date", "erp_status", "erp_order", "erp_error", "erp_attempted_at"]
        for deal, status, order, message in cases:  # each `deal` is a stale copy: the refusal re-reads it
            with self.subTest(message=message, stage=deal.stage):
                before = Opportunity.objects.filter(pk=deal.pk).values(*fields).get()
                self.assertEqual(self.send(deal, date(2026, 11, 30)), erp.Outcome(status, order, message, "error"))
                after = Opportunity.objects.filter(pk=deal.pk).values(*fields).get()
                self.assertEqual(after, before)  # the date entered is not stored either
        self.assertEqual(self.fake.calls, [])

    def test_stale_sending_is_claimed_again(self):  # CLAIM-4, CLAIM-5, EC-23
        died_after_create = "SAL-ORD-2026-00030"
        cases = [(ORDER, CREATED, WITH_TAX), (died_after_create, adopted(died_after_create), ["find_order"])]
        for name, message, calls in cases:
            with self.subTest(message):
                self.fake = FakeERPNext()
                deal = self.d1()
                stale = NOW - timedelta(minutes=3)
                Opportunity.objects.filter(pk=deal.pk).update(erp_status="sending", erp_attempted_at=stale)
                if name == died_after_create:  # the process that died had already created it
                    self.fake.orders[self.ref(deal)] = held(name)
                self.assertEqual(self.send(deal), erp.Outcome("sent", name, message, "success"))
                self.assertEqual(self.fake.names, calls)
                self.assertEqual(self.stored(deal), ("sent", name, "", NOW))

    def test_not_configured_makes_no_call_and_no_claim(self):  # CFG-1, CFG-3, CFG-5, AC16
        for setting in ({"ERPNEXT_URL": ""}, {"ERPNEXT_URL": "  "}):
            for status in ("not_sent", "failed"):
                with self.subTest(setting=setting, status=status), override_settings(**setting):
                    deal = self.d1()
                    Opportunity.objects.filter(pk=deal.pk).update(erp_status=status)
                    deal.refresh_from_db()
                    before = self.stored(deal)
                    with mock.patch("urllib.request.urlopen") as urlopen:
                        outcome = erp.send_order(deal, erpnext.client_from_settings(), TODAY, date(2026, 11, 30))
                    self.assertEqual(outcome, erp.Outcome(status, None, "ERP link not configured", None))
                    urlopen.assert_not_called()
                    self.assertEqual(self.stored(deal), before)
                    self.assertEqual(deal.delivery_date, DELIVERY)


def in_thread(target):
    """Run target on its own database connection (another request) and wait for it."""

    def run():
        try:
            target()
        finally:
            connection.close()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(15)


class SendConcurrencyTests(TransactionTestCase):
    def setUp(self):
        clock = mock.patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.rep = make_user("siti", Region.SOUTH)
        self.tray = Product.objects.create(item_code="FG-CT-300", name="Cable Tray", list_price=Decimal("85"))
        self.fake = FakeERPNext()

    def won(self, name=TEC, **account):
        account = Account.objects.create(name=name, **{"state": "Johor", **account})
        deal = Opportunity.objects.create(
            title="Cable trays for plant 2", account=account, owner=self.rep, stage="negotiation",
            expected_close=date(2026, 10, 31),
        )  # fmt: skip
        quote = Quote.start(deal, self.rep)
        quote.add_line(self.tray, Decimal("3"), Decimal("7.5"))
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.SENT)
        deal.mark_won(self.rep, DELIVERY)
        return deal

    def test_claim_is_committed_before_the_first_call_and_no_lock_is_held(self):  # CLAIM-1, SEND-3, CLAIM-6, CLAIM-7
        deal = self.won()
        seen = {}

        def at_lookup():  # another connection, while c1 is in flight
            row = Opportunity.objects.get(pk=deal.pk)
            seen["c1"] = (row.stage, row.amount, row.erp_status, row.erp_attempted_at, row.quotes.get().status)

        def at_create():  # another request locks the deal and logs a call while c5 is in flight
            start = time.monotonic()
            with transaction.atomic():
                Opportunity.objects.select_for_update(nowait=True).get(pk=deal.pk)
            call = Activity.objects.create(subject="Called about delivery", done=True, owner=self.rep, opportunity=deal)
            call.touch_parent()
            seen["c5"] = time.monotonic() - start

        self.fake.hooks = {"find_order": lambda: in_thread(at_lookup), "create_order": lambda: in_thread(at_create)}
        self.assertEqual(erp.send_order(deal, self.fake, TODAY), erp.Outcome("sent", ORDER, CREATED, "success"))
        self.assertEqual(seen["c1"], ("won", Decimal("235.88"), "sending", NOW, "accepted"))
        self.assertLess(seen["c5"], 1)
        self.assertEqual(Activity.objects.filter(opportunity=deal).count(), 1)

    def test_two_sends_at_once_make_one_customer_and_one_order(self):  # IDEM-7, EC-3, FM3
        deal = self.won(SKS, state="Selangor", address="Lot 5, Jalan SR 8/3", city="Seri Kembangan")
        Opportunity.objects.filter(pk=deal.pk).update(erp_status="failed", erp_error=T1)
        self.fake.hooks["create_order"] = lambda: time.sleep(0.5)
        start, outcomes = threading.Barrier(2), []

        def send():  # owner and manager, each with their own copy of the deal
            copy = Opportunity.objects.get(pk=deal.pk)
            start.wait(5)
            outcomes.append(erp.send_order(copy, self.fake, TODAY))

        threads = [threading.Thread(target=in_thread, args=[send]) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
        self.assertEqual(sorted(o.level for o in outcomes), ["error", "success"])
        self.assertIn(next(o.message for o in outcomes if o.level == "error"), (BEING_SENT, ALREADY))
        self.assertEqual([self.fake.names.count(m) for m in ("create_customer", "create_order")], [1, 1])
        self.assertEqual(len(self.fake.orders), 1)
        deal.refresh_from_db()
        self.assertEqual((deal.erp_status, deal.erp_order), ("sent", ORDER))
