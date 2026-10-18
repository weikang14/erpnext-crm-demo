import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from sales.models import Account, Opportunity, Quote, StageChange
from sales.rules import RuleError
from sales.tests.base import CRMTestCase

NOW = datetime(2026, 10, 15, 1, 0, tzinfo=UTC)  # 09:00 in Kuala Lumpur
ORDER = "SAL-ORD-2026-00020"
T1 = "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated."


def erp_fields(deal):
    deal.refresh_from_db()
    return deal.erp_status, deal.erp_order, deal.erp_error, deal.erp_attempted_at


class ErpDealTestCase(CRMTestCase):
    def d1(self):
        """Siti's open deal on TEC with sent quote Q133: 3 x tray at 7.5 % -> 235.88."""
        deal = self.deal(stage="negotiation")
        self.quote(deal, lines=[(None, "3", "7.5")], status=Quote.Status.SENT)
        return deal

    def won(self, **erp):
        deal = self.d1()
        deal.mark_won(self.rep, date(2026, 10, 29))
        Opportunity.objects.filter(pk=deal.pk).update(**erp)
        deal.refresh_from_db()
        return deal


class ErpFieldTests(ErpDealTestCase):
    def test_new_deal_defaults(self):  # AC11
        deal = self.deal()
        self.assertEqual((deal.delivery_date, *erp_fields(deal)), (None, "not_sent", None, "", None))

    def test_won_stores_delivery_date_with_every_003_effect(self):  # BRT-1, WON-D-7
        deal = self.d1()
        quote = deal.sent_quote()
        deal.mark_won(self.rep, date(2026, 11, 30))
        self.assertEqual((deal.stage, deal.delivery_date), ("won", date(2026, 11, 30)))  # mark_won refreshes the caller's copy
        quote.refresh_from_db()
        self.assertEqual((deal.amount, quote.status, deal.erp_status), (Decimal("235.88"), "accepted", "not_sent"))
        self.assertIsNotNone(deal.closed_at)
        self.assertEqual(StageChange.objects.filter(opportunity=deal, to_stage="won").count(), 1)

    def test_won_without_a_date_still_works(self):  # AC1: the form requires the date (task 3.1), the model doesn't
        deal = self.d1()
        deal.mark_won(self.rep)
        self.assertEqual((deal.stage, deal.amount, deal.delivery_date), ("won", Decimal("235.88"), None))

    def test_won_needs_a_sent_quote_and_stores_no_date(self):  # BRT-4
        deal = self.deal(stage="negotiation")
        self.quote(deal)
        with self.assertRaisesMessage(RuleError, "Send a quote before marking the deal won."):
            deal.mark_won(self.rep, date(2026, 10, 29))
        deal.refresh_from_db()
        self.assertEqual((deal.is_open, deal.delivery_date), (True, None))

    def test_won_twice_is_refused(self):  # BRT-5
        deal = self.won(erp_status="sent", erp_order=ORDER)
        with self.assertRaisesMessage(RuleError, "This deal is closed."):
            deal.mark_won(self.rep, date(2026, 12, 31))
        deal.refresh_from_db()
        self.assertEqual((deal.amount, deal.delivery_date), (Decimal("235.88"), date(2026, 10, 29)))
        self.assertEqual(erp_fields(deal)[:2], ("sent", ORDER))
        self.assertEqual(deal.history.filter(to_stage="won").count(), 1)

    def test_won_deal_stays_read_only_in_every_erp_state(self):  # BRT-7
        for status in ("not_sent", "sending", "sent", "failed"):
            deal = self.won(erp_status=status)
            actions = {
                "edit": lambda: deal.edit(title="Renamed"),
                "lost": lambda: deal.mark_lost(self.rep, self.price_reason),
                "move": lambda: deal.move_to("enquiry", self.rep),
                "reassign": lambda: deal.reassign(self.jason),
            }
            for name, action in actions.items():
                with self.subTest(status=status, action=name), self.assertRaisesMessage(RuleError, "This deal is closed."):
                    action()
            deal.refresh_from_db()
            self.assertEqual((deal.stage, deal.title, deal.owner), ("won", "Cable trays for plant 2", self.rep))

    def test_reports_ignore_erp_status(self):  # BRT-8, AC2, AC11
        for status, amount in (("sent", "100"), ("failed", "200"), ("not_sent", "300")):
            self.deal(stage="won", amount=amount, closed_at=timezone.now(), erp_status=status)
        self.deal(stage="lost", amount="999", closed_at=timezone.now(), lost_reason=self.price_reason)

        def figures():
            report = self.client.get(reverse("reports")).context
            day = self.client.get(reverse("home")).context
            reps = [(r["won"], r["lost"], r["rate"], r["won_value"]) for r in report["reps"]]
            return reps, report["forecast"]["won"], day["won_this_month"]

        mixed = figures()
        self.assertEqual(mixed, ([(3, 1, 75, Decimal("600"))], Decimal("600"), Decimal("600")))
        Opportunity.objects.update(erp_status="not_sent")
        self.assertEqual(figures(), mixed)


class ClaimTests(ErpDealTestCase):
    def test_claim_from_not_sent_or_failed(self):  # CLAIM-2, AC15
        for status in ("not_sent", "failed"):
            deal = self.won(erp_status=status, erp_attempted_at=NOW - timedelta(minutes=1))
            self.assertTrue(deal.claim_send(NOW))
            self.assertEqual((deal.erp_status, deal.erp_attempted_at), ("sending", NOW))  # the caller's copy too
            self.assertEqual(erp_fields(deal)[::3], ("sending", NOW))

    def test_fresh_sending_refuses_a_second_claim(self):  # CLAIM-3, FM3
        for age in (timedelta(minutes=1), timedelta(minutes=2)):  # "older than 2 minutes": exactly 2 is still fresh
            deal = self.won(erp_status="sending", erp_attempted_at=NOW - age)
            self.assertFalse(deal.claim_send(NOW))
            self.assertEqual(erp_fields(deal)[::3], ("sending", NOW - age))

    def test_stale_sending_can_be_claimed_again(self):  # CLAIM-4
        deal = self.won(erp_status="sending", erp_attempted_at=NOW - timedelta(minutes=3))
        self.assertTrue(deal.claim_send(NOW))
        self.assertEqual(erp_fields(deal)[::3], ("sending", NOW))

    def test_only_an_unsent_won_deal_can_be_claimed(self):  # AC15
        sent = self.won(erp_status="sent", erp_order=ORDER, erp_attempted_at=NOW - timedelta(hours=1))
        open_deal = self.d1()
        lost = self.deal(stage="lost", closed_at=timezone.now(), lost_reason=self.price_reason)
        for deal in (sent, open_deal, lost):
            before = erp_fields(deal)
            self.assertFalse(deal.claim_send(NOW))
            self.assertEqual(erp_fields(deal), before)

    def test_claim_is_one_conditional_update_without_a_lock(self):  # AC15, FM1
        deal = self.won()
        with CaptureQueriesContext(connection) as queries:
            deal.claim_send(NOW)
        self.assertEqual(len(queries), 1)
        self.assertTrue(queries[0]["sql"].startswith("UPDATE"))
        self.assertNotIn("FOR UPDATE", queries[0]["sql"])


class RecordSendTests(ErpDealTestCase):
    def test_record_send_stores_the_outcome(self):  # SEND-2, AC11
        sent, failed = self.won(), self.won()
        for deal in (sent, failed):
            deal.claim_send(NOW)
        sent.record_send("sent", order=ORDER)
        failed.record_send("failed", error=T1)
        self.assertEqual(erp_fields(sent), ("sent", ORDER, "", NOW))
        self.assertEqual(erp_fields(failed), ("failed", None, T1, NOW))

    def test_record_send_touches_only_erp_fields_and_takes_no_lock(self):  # AC11, FM1
        deal = self.won()
        closed_at = deal.closed_at
        Opportunity.objects.filter(pk=deal.pk).update(title="Renamed elsewhere")  # deal is now a stale copy
        with CaptureQueriesContext(connection) as queries:
            deal.record_send("failed", error="Item FG-CT-300 is disabled")
        self.assertEqual(len(queries), 1)
        self.assertNotIn("FOR UPDATE", queries[0]["sql"])
        deal.refresh_from_db()
        self.assertEqual(
            (deal.title, deal.stage, deal.amount, deal.closed_at, deal.erp_status),
            ("Renamed elsewhere", "won", Decimal("235.88"), closed_at, "failed"),
        )

    def test_erp_order_is_not_unique(self):  # IDEM-8, AC11 (round 1): names are unique per ERPNext site only
        first, second, third = self.won(), self.won(), self.won()
        third.record_send("failed", error="x")
        for deal in (first, second):  # e.g. the CRM pointed at another site that reuses the names
            deal.record_send("sent", order=ORDER)
        self.assertEqual([erp_fields(deal)[:2] for deal in (first, second, third)],
                         [("sent", ORDER), ("sent", ORDER), ("failed", None)])  # fmt: skip


def won_deal():
    rep = User.objects.create_user("siti")
    account = Account.objects.create(name="Tanjung Electrical Contractors Sdn Bhd", state="Johor")
    return Opportunity.objects.create(
        title="Cable trays for plant 2", account=account, owner=rep, stage="won", amount=Decimal("235.88"),
        expected_close=date(2026, 10, 31), closed_at=NOW,
    )  # fmt: skip


class ClaimConcurrencyTests(TransactionTestCase):
    def in_threads(self, *targets):
        def run(target):
            try:
                target()
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=[t]) for t in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)

    def test_claim_is_committed_and_no_lock_is_held_after_it(self):  # CLAIM-1, CLAIM-6, FM1
        deal = won_deal()
        self.assertTrue(deal.claim_send(NOW))
        seen = []

        def other_request():  # what another connection sees while the claimer talks to ERPNext
            with transaction.atomic():
                row = Opportunity.objects.select_for_update(nowait=True).get(pk=deal.pk)
                seen.append((row.erp_status, row.erp_attempted_at))

        self.in_threads(other_request)
        self.assertEqual(seen, [("sending", NOW)])

    def test_two_claims_at_once_one_wins(self):  # FM3
        deal = won_deal()
        start, results = threading.Barrier(2), []

        def claim():
            copy = Opportunity.objects.get(pk=deal.pk)
            start.wait(5)
            results.append(copy.claim_send(NOW))

        self.in_threads(claim, claim)
        self.assertEqual(sorted(results), [False, True])


class MigrationTests(TransactionTestCase):
    def test_deals_won_before_004_migrate_as_not_sent(self):  # BRT-16, AC11
        before, after = [("sales", "0003_ratelimit")], [("sales", "0004_opportunity_erp")]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            rep = old.get_model("auth", "User").objects.create(username="siti")
            account = old.get_model("sales", "Account").objects.create(name="Tanjung", state="Johor")
            Deal = old.get_model("sales", "Opportunity")
            common = {"account": account, "owner": rep, "expected_close": date(2026, 10, 31)}
            won = Deal.objects.create(title="Won", stage="won", amount=Decimal("1000.00"), closed_at=NOW, **common)
            still_open = Deal.objects.create(title="Open", stage="enquiry", amount=Decimal("500.00"), **common)
            MigrationExecutor(connection).migrate(after)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        for pk, stage, amount, closed_at in ((won.pk, "won", "1000.00", NOW), (still_open.pk, "enquiry", "500.00", None)):
            deal = Opportunity.objects.get(pk=pk)
            self.assertEqual((deal.stage, deal.amount, deal.closed_at), (stage, Decimal(amount), closed_at))
            self.assertEqual((deal.delivery_date, *erp_fields(deal)), (None, "not_sent", None, "", None))
