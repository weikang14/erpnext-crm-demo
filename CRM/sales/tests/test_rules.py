from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.test import SimpleTestCase

from sales import rules
from sales.models import Account, Activity, Lead, Opportunity, Quote, StageChange
from sales.regions import Region, region_of
from sales.rules import RuleError
from sales.tests.base import CRMTestCase


def line(qty, price, discount="0"):
    return SimpleNamespace(qty=Decimal(qty), unit_price=Decimal(price), discount_pct=Decimal(discount))


class PureRuleTests(SimpleTestCase):
    def test_regions(self):  # REG-1
        self.assertEqual(region_of("Penang"), Region.NORTH)
        self.assertEqual(region_of("Johor"), Region.SOUTH)
        self.assertEqual(region_of("Pahang"), Region.CENTRAL)
        self.assertEqual(region_of("Singapore"), Region.SINGAPORE)

    def test_line_total_rounds_half_up(self):  # Q-1
        self.assertEqual(rules.line_total(Decimal("3"), Decimal("85.00"), Decimal("7.5")), Decimal("235.88"))

    def test_totals_are_exact(self):  # Q-2
        self.assertEqual(rules.quote_total([line("1", "0.10"), line("1", "0.20")]), Decimal("0.30"))

    def test_each_line_rounded_before_summing(self):  # FM3
        lines = [line("1", "0.125"), line("1", "0.125")]
        self.assertEqual(rules.quote_total(lines), Decimal("0.26"))  # 0.13 + 0.13, not round(0.25)

    def test_approval_threshold(self):  # QA-1, QA-2
        self.assertFalse(rules.needs_approval([line("1", "100", "10")]))
        self.assertTrue(rules.needs_approval([line("1", "100", "0"), line("1", "100", "10.01")]))

    def test_stage_gates(self):  # MOVE-2, MOVE-3, WON-1
        rules.check_move("enquiry", "technical", has_sent_quote=False)
        for target, sent in (("quotation", False), ("negotiation", False), ("won", True), ("lost", True)):
            with self.assertRaises(RuleError, msg=target):
                rules.check_move("enquiry", target, sent)
        rules.check_move("enquiry", "negotiation", has_sent_quote=True)
        with self.assertRaisesMessage(RuleError, "closed"):
            rules.check_move("won", "enquiry", True)
        with self.assertRaisesMessage(RuleError, "Send a quote"):
            rules.check_won("negotiation", has_sent_quote=False)

    def test_win_rate_counts_closed_deals_only(self):  # FM4
        self.assertEqual(rules.win_rate(3, 1), 75)
        self.assertIsNone(rules.win_rate(0, 0))

    def test_weighted(self):
        self.assertEqual(rules.weighted(Decimal("2000"), "negotiation"), Decimal("1500.00"))


class WorkflowTests(CRMTestCase):
    def test_submit_within_limit_is_approved(self):  # QA-1
        quote = self.quote(self.deal(), lines=[(None, "2", "10")])
        quote.submit(self.rep)
        self.assertEqual(quote.status, Quote.Status.APPROVED)
        self.assertEqual(quote.approved_by, self.rep)

    def test_submit_over_limit_waits(self):  # QA-2
        quote = self.quote(self.deal(), lines=[(None, "2", "10.01")])
        quote.submit(self.rep)
        self.assertEqual(quote.status, Quote.Status.PENDING)
        self.assertIsNone(quote.approved_by)

    def test_manager_own_quote_needs_no_second_signature(self):  # QA-3
        quote = self.quote(self.deal(owner=self.manager), lines=[(None, "2", "25")])
        quote.submit(self.manager)
        self.assertEqual((quote.status, quote.approved_by), (Quote.Status.APPROVED, self.manager))

    def test_only_drafts_change(self):  # QS-2 at model level
        quote = self.quote(self.deal(), status=Quote.Status.APPROVED)
        with self.assertRaises(RuleError):
            quote.add_line(self.tray, Decimal("1"), Decimal("0"))

    def test_unit_price_is_list_price(self):  # Q-3 at model level
        quote = self.quote(self.deal(), lines=[(self.frame, "2", "0")])
        self.assertEqual(quote.lines.get().unit_price, Decimal("1450.00"))

    def test_send_moves_deal_to_quotation(self):  # QS-3
        deal = self.deal(stage="enquiry", amount="1")
        quote = self.quote(deal, lines=[(None, "10", "0")], status=Quote.Status.APPROVED)
        quote.send(self.rep)
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.amount), ("quotation", Decimal("850.00")))
        self.assertTrue(StageChange.objects.filter(opportunity=deal, to_stage="quotation", by=self.rep).exists())

    def test_revision_supersedes_on_send(self):  # QS-4
        deal = self.deal(stage="enquiry")
        first = self.quote(deal, lines=[(None, "10", "5")], status=Quote.Status.APPROVED)
        first.send(self.rep)
        revision = first.revise(self.rep)
        self.assertEqual(revision.status, Quote.Status.DRAFT)
        self.assertEqual([(l.product, l.discount_pct) for l in revision.lines.all()], [(self.tray, Decimal("5.00"))])
        first.refresh_from_db()
        self.assertEqual(first.status, Quote.Status.SENT)
        revision.submit(self.rep)
        revision.send(self.rep)
        first.refresh_from_db()
        self.assertEqual(first.status, Quote.Status.SUPERSEDED)

    def test_one_quote_in_progress(self):
        deal = self.deal()
        current = self.quote(deal)
        with self.assertRaisesMessage(RuleError, f"Finish {current.number} first."):
            Quote.start(deal, self.rep)

    def test_won_takes_the_sent_quote(self):  # WON-2
        deal = self.deal(stage="negotiation", amount="5")
        quote = self.quote(deal, lines=[(None, "10", "0")], status=Quote.Status.SENT)
        deal.mark_won(self.rep)
        quote.refresh_from_db()
        self.assertEqual((deal.stage, deal.amount, quote.status), ("won", Decimal("850.00"), Quote.Status.ACCEPTED))
        self.assertIsNotNone(deal.closed_at)

    def test_lost_declines_the_sent_quote(self):  # LOST-2
        deal = self.deal(stage="quotation")
        quote = self.quote(deal, status=Quote.Status.SENT)
        deal.mark_lost(self.rep, self.price_reason, "went with a cheaper supplier")
        quote.refresh_from_db()
        self.assertEqual((deal.stage, deal.lost_reason, quote.status), ("lost", self.price_reason, Quote.Status.DECLINED))

    def test_closed_deal_is_read_only(self):  # CLOSED-1
        deal = self.deal(stage="won")
        with self.assertRaises(RuleError):
            deal.move_to("enquiry", self.rep)
        with self.assertRaises(RuleError):
            Quote.start(deal, self.rep)
        with self.assertRaises(RuleError):
            deal.mark_lost(self.rep, self.price_reason)

    def test_convert_twice_refused(self):  # CONV-3 at model level
        lead = Lead.objects.create(company="Muar Ice Plant Sdn Bhd", contact_name="Yap", state="Johor", owner=self.rep)
        lead.convert(self.rep, "Cold room racking", Decimal("5000"), "2026-12-31")
        with self.assertRaises(RuleError):
            lead.convert(self.rep, "Cold room racking", Decimal("5000"), "2026-12-31")
        self.assertEqual(Opportunity.objects.count(), 1)
        self.assertEqual(Account.objects.get().region, Region.SOUTH)

    def test_logged_call_marks_lead_contacted(self):
        lead = Lead.objects.create(company="X Sdn Bhd", contact_name="Y", state="Johor", owner=self.rep)
        activity = Activity.objects.create(lead=lead, owner=self.rep, kind="call", subject="Called", done=True)
        activity.touch_parent()
        lead.refresh_from_db()
        self.assertEqual(lead.status, Lead.Status.CONTACTED)


class AdminAndSeedTests(CRMTestCase):
    def test_manager_maintains_products_in_admin(self):  # ADM-1
        self.login(self.manager)
        self.assertEqual(self.client.get("/admin/sales/product/").status_code, 200)
        self.login(self.rep)
        self.assertEqual(self.client.get("/admin/sales/product/").status_code, 302)

    def test_seed_is_idempotent(self):  # RUN-2
        call_command("seed_demo", verbosity=0, stdout=StringIO())
        models = (Account, Opportunity, Quote, Lead, Activity, StageChange)
        first = [m.objects.count() for m in models]
        self.assertGreater(first[1], 30)
        call_command("seed_demo", verbosity=0, stdout=StringIO())
        self.assertEqual([m.objects.count() for m in models], first)
        self.assertEqual(Quote.objects.filter(status=Quote.Status.PENDING).count(), 2)
