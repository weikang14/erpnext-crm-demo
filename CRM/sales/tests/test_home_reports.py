from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from sales.forms import quarter_bounds, quarter_of
from sales.models import Activity, Lead, Opportunity, Quote
from sales.tests.base import CRMTestCase

# 07:30 on 6 Oct in Kuala Lumpur, still 5 Oct in UTC
EARLY_MORNING_KL = datetime(2026, 10, 5, 23, 30, tzinfo=UTC)


class MyDayTests(CRMTestCase):
    def test_today_is_a_malaysian_date(self):  # DAY-1, FM13
        deal = self.deal()
        for subject, due in (("yesterday", date(2026, 10, 5)), ("today", date(2026, 10, 6)), ("tomorrow", date(2026, 10, 7))):
            Activity.objects.create(opportunity=deal, owner=self.rep, subject=subject, due_date=due)
        with mock.patch("django.utils.timezone.now", return_value=EARLY_MORNING_KL):
            self.client.force_login(self.rep)  # session made inside the patch, so it isn't expired
            response = self.client.get(reverse("home"))
        self.assertEqual([a.subject for a in response.context["overdue"]], ["yesterday"])
        self.assertEqual([a.subject for a in response.context["due_today"]], ["today"])

    def test_deals_needing_attention(self):  # DAY-2
        self.deal(title="no plan")
        self.deal(title="idle", last_activity_at=timezone.now() - timedelta(days=15))
        planned = self.deal(title="planned")
        Activity.objects.create(opportunity=planned, owner=self.rep, subject="x", due_date=timezone.localdate() + timedelta(days=3))
        response = self.client.get(reverse("home"))
        self.assertEqual(sorted(d.title for d in response.context["no_next_step"]), ["idle", "no plan"])
        self.assertEqual([d.title for d in response.context["stale"]], ["idle"])

    def test_manager_panels(self):  # DAY-3
        self.quote(self.deal(), lines=[(None, "1", "20")], status=Quote.Status.PENDING)
        Lead.objects.create(company="Orphan Sdn Bhd", contact_name="X", state="Sabah")
        rep_page = self.client.get(reverse("home"))
        self.assertNotIn("pending_quotes", rep_page.context)
        self.assertNotContains(rep_page, "Orphan Sdn Bhd")
        self.login(self.manager)
        manager_page = self.client.get(reverse("home"))
        self.assertEqual(len(manager_page.context["pending_quotes"]), 1)
        self.assertContains(manager_page, "Orphan Sdn Bhd")

    def team_deals(self):
        self.deal(title="no plan", amount="1000")
        self.deal(owner=self.kumar, title="idle", amount="2500", last_activity_at=timezone.now() - timedelta(days=15))
        planned = self.deal(owner=self.jason, title="planned", amount="400")
        Activity.objects.create(opportunity=planned, owner=self.jason, subject="x", due_date=timezone.localdate() + timedelta(days=3))
        self.deal(owner=self.aisyah, stage="won", amount="9999", closed_at=timezone.now())

    def test_manager_sees_the_team(self):  # DAY-4
        self.team_deals()
        self.login(self.manager)
        response = self.client.get(reverse("home"))
        self.assertEqual(sorted(d.title for d in response.context["no_next_step"]), ["idle", "no plan"])
        self.assertEqual([d.title for d in response.context["stale"]], ["idle"])
        self.assertEqual(response.context["open_value"], Decimal("3900"))
        self.assertContains(response, "Team open pipeline")
        self.assertContains(response, "Siti")
        self.assertContains(response, "Kumar")

    def test_rep_sees_only_own_deals(self):  # DAY-5
        self.team_deals()
        response = self.client.get(reverse("home"))
        self.assertEqual([d.title for d in response.context["no_next_step"]], ["no plan"])
        self.assertEqual(response.context["stale"], [])
        self.assertEqual(response.context["open_value"], Decimal("1000"))
        self.assertNotContains(response, "Team open pipeline")
        self.assertNotContains(response, "Kumar")

    def test_manager_day_constant_query_count(self):  # DAY-4, FM12
        def queries_for(n):
            for i in range(n):
                self.deal(owner=[self.siti, self.kumar, self.jason][i % 3], last_activity_at=timezone.now() - timedelta(days=15))
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse("home"))
            self.assertEqual(len(response.context["stale"]), Opportunity.objects.count())
            return len(queries)

        self.login(self.manager)
        self.assertEqual(queries_for(3), queries_for(12))


class ReportTests(CRMTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.start, self.end = quarter_bounds(quarter_of(self.today))

    def report(self, **params):
        return self.client.get(reverse("reports"), params).context

    def closed(self, stage, amount, owner=None, reason=None):
        return self.deal(owner=owner, stage=stage, amount=amount, closed_at=timezone.now(), lost_reason=reason)

    def test_pipeline_by_stage(self):  # REP-1
        self.deal(amount="1000")
        self.deal(stage="negotiation", amount="2000")
        rows = {r["stage"]: r for r in self.report()["stages"]}
        self.assertEqual((rows["enquiry"]["count"], rows["enquiry"]["weighted"]), (1, Decimal("100.00")))
        self.assertEqual((rows["negotiation"]["value"], rows["negotiation"]["weighted"]), (Decimal("2000"), Decimal("1500.00")))
        self.assertEqual(rows["quotation"]["count"], 0)

    def test_win_rate_counts_deals_not_value(self):  # REP-2, FM4
        for amount in ("100", "100", "100"):
            self.closed("won", amount)
        self.closed("lost", "99999", reason=self.price_reason)
        self.deal()
        self.deal()
        rows = self.report()["reps"]
        self.assertEqual([(r["won"], r["lost"], r["rate"]) for r in rows], [(3, 1, 75)])

    def test_forecast(self):  # REP-3, FM5
        self.closed("won", "1000")
        self.deal(stage="negotiation", amount="2000", expected_close=self.today)
        self.deal(stage="enquiry", amount="5000", expected_close=self.end + timedelta(days=10))
        old = self.deal(stage="won", amount="7777", expected_close=self.today)  # won last quarter, closing date says now
        old.closed_at = timezone.make_aware(datetime.combine(self.start - timedelta(days=5), datetime.min.time()))
        old.save()
        forecast = self.report()["forecast"]
        self.assertEqual(
            (forecast["won"], forecast["weighted"], forecast["forecast"], forecast["best_case"]),
            (Decimal("1000"), Decimal("1500.00"), Decimal("2500.00"), Decimal("3000")),
        )

    def test_lost_reasons(self):  # REP-4
        self.closed("lost", "1000", reason=self.price_reason)
        self.closed("lost", "500", reason=self.price_reason)
        self.closed("lost", "500", reason=self.lead_time_reason)
        rows = self.report()["reasons"]
        self.assertEqual(
            [(r["reason"], r["count"], r["value"], r["share"]) for r in rows],
            [("Price too high", 2, Decimal("1500"), 67), ("Lead time too long", 1, Decimal("500"), 33)],
        )

    def test_scope(self):  # REP-5
        self.closed("won", "100")
        kumar_deal = self.closed("won", "100", owner=self.kumar)
        kumar_deal.account = self.account("Mutiara Automation Sdn Bhd", "Selangor")
        kumar_deal.save()
        self.assertEqual([r["rep"] for r in self.report()["reps"]], ["Siti"])
        self.login(self.manager)
        self.assertEqual(sorted(r["rep"] for r in self.report()["reps"]), ["Kumar", "Siti"])
        self.assertEqual([r["rep"] for r in self.report(region="central")["reps"]], ["Kumar"])

    def test_constant_query_count(self):  # REP-6, FM12
        for i in range(30):
            self.deal(stage=["enquiry", "won", "lost", "negotiation"][i % 4], amount=str(100 + i), closed_at=timezone.now(),
                      lost_reason=self.price_reason)  # fmt: skip
        self.login(self.manager)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("reports"))
        self.assertLessEqual(len(queries), 15)

    def test_bad_quarter_falls_back(self):  # REP-7
        self.assertEqual(self.report(quarter="garbage")["quarter"], quarter_of(self.today))
        self.assertEqual(self.report(quarter="2026-Q7")["quarter"], quarter_of(self.today))
