import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from sales.models import Activity, Contact, Opportunity, Quote, SalesRep, StageChange
from sales.rules import RuleError
from sales.tests.base import CRMTestCase


class PipelineTests(CRMTestCase):
    def board(self):
        return {c["stage"]: c for c in self.client.get(reverse("pipeline")).context["columns"]}

    def test_column_totals(self):  # PIPE-1
        for amount in ("100", "200", "300.50"):
            self.deal(amount=amount)
        column = self.board()["enquiry"]
        self.assertEqual((column["count"], column["value"]), (3, Decimal("600.50")))

    def test_cards_sorted_by_next_activity(self):  # PIPE-2
        today = timezone.localdate()
        future = self.deal(title="future")
        none = self.deal(title="none")
        overdue = self.deal(title="overdue")
        due_today = self.deal(title="today")
        for deal, days in ((future, 5), (overdue, -2), (due_today, 0)):
            Activity.objects.create(opportunity=deal, owner=self.rep, subject="next", due_date=today + timedelta(days=days))
        Activity.objects.create(opportunity=none, owner=self.rep, subject="old", done=True)
        cards = self.board()["enquiry"]["cards"]
        self.assertEqual([c.title for c in cards], ["overdue", "today", "none", "future"])
        self.assertEqual([c.indicator for c in cards], ["overdue", "today", "none", "future"])
        html = self.client.get(reverse("pipeline")).content.decode()
        for label in ("Overdue activity", "Activity today", "No next activity"):
            self.assertIn(label, html)

    def test_stale_flag(self):  # PIPE-3
        self.deal(last_activity_at=timezone.now() - timedelta(days=15))
        self.assertTrue(self.board()["enquiry"]["cards"][0].stale)

    def test_closed_deals_not_on_board(self):  # PIPE-4
        self.deal(stage="won")
        self.deal(stage="lost")
        self.assertEqual(sum(c["count"] for c in self.board().values()), 0)

    def test_keyboard_move_control(self):  # MOVE-4
        deal = self.deal()
        response = self.client.get(reverse("pipeline"))
        self.assertContains(response, f'<label class="visually-hidden" for="move-{deal.pk}">Move Cable trays for plant 2 to</label>', html=True)
        self.assertContains(response, f'action="{reverse("opportunity_move", args=[deal.pk])}"')

    def test_rep_board_has_only_own_deals(self):
        self.deal(owner=self.kumar, title="Kumar's")
        self.assertEqual(self.board()["enquiry"]["count"], 0)


class MoveTests(CRMTestCase):
    def move(self, deal, stage, **extra):
        return self.client.post(reverse("opportunity_move", args=[deal.pk]), {"stage": stage, **extra}, follow=True)

    def test_move_records_history(self):  # MOVE-1
        deal = self.deal()
        response = self.move(deal, "technical", next=reverse("pipeline"))
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "technical")
        change = StageChange.objects.get(opportunity=deal)
        self.assertEqual((change.from_stage, change.to_stage, change.by), ("enquiry", "technical", self.rep))
        self.assertEqual(response.redirect_chain[-1][0], reverse("pipeline"))

    def test_quotation_needs_a_sent_quote(self):  # MOVE-2
        deal = self.deal()
        response = self.move(deal, "quotation")
        self.assertContains(response, "Send a quote first")
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "enquiry")

    def test_won_and_lost_not_through_move(self):  # MOVE-3
        deal = self.deal()
        self.move(deal, "won")
        self.move(deal, "lost")
        deal.refresh_from_db()
        self.assertEqual(deal.stage, "enquiry")

    def test_other_reps_deal_is_404(self):  # SEC-1
        other = self.deal(owner=self.kumar)
        self.assertEqual(self.client.post(reverse("opportunity_move", args=[other.pk]), {"stage": "technical"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("opportunity", args=[other.pk])).status_code, 404)


class WonLostTests(CRMTestCase):
    @property
    def delivery(self):  # 004 AC1: Won asks for a requested delivery date
        return {"delivery_date": (timezone.localdate() + timedelta(days=14)).isoformat()}

    def test_won_needs_sent_quote(self):  # WON-1
        deal = self.deal(stage="negotiation")
        self.quote(deal, status=Quote.Status.APPROVED)
        response = self.client.post(reverse("opportunity_won", args=[deal.pk]), self.delivery, follow=True)
        self.assertContains(response, "Send a quote before marking the deal won.")
        deal.refresh_from_db()
        self.assertTrue(deal.is_open)

    def test_won(self):  # WON-2
        deal = self.deal(stage="negotiation", amount="1")
        quote = self.quote(deal, lines=[(None, "10", "0"), (self.frame, "1", "0")], status=Quote.Status.SENT)
        self.client.post(reverse("opportunity_won", args=[deal.pk]), self.delivery)
        deal.refresh_from_db()
        quote.refresh_from_db()
        self.assertEqual((deal.stage, deal.amount, quote.status), ("won", Decimal("2300.00"), "accepted"))

    def test_lost_needs_reason(self):  # LOST-1
        deal = self.deal()
        response = self.client.post(reverse("opportunity_lost", args=[deal.pk]), {"reason": "", "note": ""})
        self.assertContains(response, "This field is required", status_code=400)
        deal.refresh_from_db()
        self.assertTrue(deal.is_open)

    def test_lost(self):  # LOST-2
        deal = self.deal(stage="quotation")
        quote = self.quote(deal, status=Quote.Status.SENT)
        self.client.post(reverse("opportunity_lost", args=[deal.pk]), {"reason": self.price_reason.pk, "note": "15 % cheaper"})
        deal.refresh_from_db()
        quote.refresh_from_db()
        self.assertEqual((deal.stage, deal.lost_reason, deal.lost_note, quote.status), ("lost", self.price_reason, "15 % cheaper", "declined"))

    def test_closed_deal_refuses_changes(self):  # CLOSED-1
        deal = self.deal(stage="won")
        self.client.post(reverse("opportunity_move", args=[deal.pk]), {"stage": "enquiry"})
        self.client.post(reverse("opportunity_quote_new", args=[deal.pk]))
        response = self.client.post(reverse("opportunity_lost", args=[deal.pk]), {"reason": self.price_reason.pk}, follow=True)
        self.assertContains(response, "This deal is closed.")
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.quotes.count()), ("won", 0))


class DealListTests(CRMTestCase):
    def test_pagination(self):  # LIST-1
        for i in range(30):
            self.deal(title=f"Deal {i:02d}")
        first = self.client.get(reverse("opportunities"))
        second = self.client.get(reverse("opportunities"), {"page": 2})
        self.assertEqual((len(first.context["page"].object_list), len(second.context["page"].object_list)), (25, 5))

    def test_filters(self):  # LIST-2
        self.deal(title="Big frames", stage="won", closed_at=timezone.now())
        self.deal(title="Big trays")
        self.deal(title="Small frames", stage="won", closed_at=timezone.now())
        response = self.client.get(reverse("opportunities"), {"stage": "won", "q": "big"})
        self.assertEqual([d.title for d in response.context["page"].object_list], ["Big frames"])

    def test_quarter_filter(self):
        self.deal(title="Q4", expected_close=timezone.datetime(2026, 11, 3).date())
        self.deal(title="Q1", expected_close=timezone.datetime(2027, 1, 3).date())
        response = self.client.get(reverse("opportunities"), {"quarter": "2026-Q4"})
        self.assertEqual([d.title for d in response.context["page"].object_list], ["Q4"])

    def test_csv_export(self):  # LIST-3
        self.deal(title="=HYPERLINK(\"http://evil.example\")")
        self.deal(title="Mine")
        self.deal(owner=self.kumar, title="Kumar's")
        response = self.client.get(reverse("opportunities"), {"format": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][:2], ["Deal", "Account"])
        titles = sorted(r[0] for r in rows[1:])
        self.assertEqual(titles, ["'=HYPERLINK(\"http://evil.example\")", "Mine"])  # formula neutralised, no Kumar

    def test_empty_states(self):  # UI-1
        self.assertContains(self.client.get(reverse("opportunities")), "No open deals yet")
        self.assertContains(self.client.get(reverse("opportunities"), {"q": "nothing"}), "No deals match")

    def test_bad_quarter_ignored(self):
        self.assertEqual(self.client.get(reverse("opportunities"), {"quarter": "2026-Q9"}).status_code, 200)


class DealPageTests(CRMTestCase):
    def test_detail(self):
        deal = self.deal()
        Opportunity.objects.filter(pk=deal.pk).update(stage="technical")
        StageChange.objects.create(opportunity=deal, from_stage="enquiry", to_stage="technical", by=self.rep)
        response = self.client.get(reverse("opportunity", args=[deal.pk]))
        self.assertContains(response, "Stage history")
        self.assertContains(response, "send the customer a quote first")


class DealEditTests(CRMTestCase):
    def edit(self, deal, follow=False, **changes):
        data = {"title": deal.title, "contact": deal.contact_id or "", "amount": deal.amount,
                "expected_close": deal.expected_close, **changes}  # fmt: skip
        return self.client.post(reverse("opportunity_edit", args=[deal.pk]), data, follow=follow)

    def test_owner_edits_open_deal(self):  # EDIT-1
        deal = self.deal(stage="negotiation", amount="1000", close_in_days=400)
        buyer = Contact.objects.create(account=deal.account, name="Encik Rahman")
        page = reverse("opportunity", args=[deal.pk])
        self.assertContains(self.client.get(page), f'href="{reverse("opportunity_edit", args=[deal.pk])}"')
        today = timezone.localdate()
        self.assertRedirects(self.edit(deal, amount="2000", expected_close=today, contact=buyer.pk), page)
        deal.refresh_from_db()
        self.assertEqual((deal.amount, deal.expected_close, deal.contact), (Decimal("2000"), today, buyer))
        self.assertContains(self.client.get(page), "MYR 2,000.00")
        self.assertEqual(self.client.get(reverse("reports")).context["forecast"]["weighted"], Decimal("1500.00"))

    def test_value_locked_after_a_sent_quote(self):  # EDIT-2
        deal = self.deal(stage="quotation", amount="850")
        self.quote(deal, status=Quote.Status.SENT)
        self.assertTrue(self.client.get(reverse("opportunity_edit", args=[deal.pk])).context["form"].fields["amount"].disabled)
        self.edit(deal, amount="1", title="Trays for plant 3")
        deal.refresh_from_db()
        self.assertEqual((deal.title, deal.amount), ("Trays for plant 3", Decimal("850")))
        with self.assertRaises(RuleError):  # a quote sent while the form was open: the model refuses too
            deal.edit(amount=Decimal("1"))

    def test_other_reps_deal_is_404(self):  # EDIT-3
        deal = self.deal(owner=self.kumar)
        self.assertEqual(self.client.get(reverse("opportunity_edit", args=[deal.pk])).status_code, 404)
        self.assertEqual(self.edit(deal, title="Mine now").status_code, 404)

    def test_closed_deals_are_read_only(self):  # EDIT-4
        for stage in ("won", "lost"):
            with self.subTest(stage=stage):
                deal = self.deal(stage=stage, title=stage)
                page = reverse("opportunity", args=[deal.pk])
                self.assertNotContains(self.client.get(page), reverse("opportunity_edit", args=[deal.pk]))
                self.assertRedirects(self.client.get(reverse("opportunity_edit", args=[deal.pk])), page)
                self.assertContains(self.edit(deal, title="changed", amount="1", follow=True), "This deal is closed.")
                deal.refresh_from_db()
                self.assertEqual((deal.title, deal.amount), (stage, Decimal("1000")))

    def test_field_errors(self):  # EDIT-5
        deal = self.deal()
        stranger = Contact.objects.create(account=self.account("Penang Packaging Sdn Bhd", "Penang"), name="Stranger")
        response = self.edit(deal, title="", contact=stranger.pk)
        self.assertContains(response, '<p class="error" id="id_title_error">This field is required.</p>', html=True)
        self.assertContains(response, 'id="id_contact_error"')
        deal.refresh_from_db()
        self.assertEqual((deal.title, deal.contact), ("Cable trays for plant 2", None))


class DealReassignTests(CRMTestCase):
    def assign(self, deal, to):
        return self.client.post(reverse("opportunity_assign", args=[deal.pk]), {"owner": to.pk})

    def test_manager_reassigns_with_open_activities(self):  # RA-1
        deal = self.deal()
        due = timezone.localdate()
        todo = Activity.objects.create(opportunity=deal, owner=self.siti, subject="Call back", due_date=due)
        logged = Activity.objects.create(opportunity=deal, owner=self.siti, subject="Site visit", done=True)
        mine = Activity.objects.create(opportunity=deal, owner=self.manager, subject="Check margin", due_date=due)
        self.login(self.manager)
        self.assertContains(self.client.get(reverse("opportunity", args=[deal.pk])), reverse("opportunity_assign", args=[deal.pk]))
        self.assign(deal, self.jason)
        deal.refresh_from_db()
        self.assertEqual(deal.owner, self.jason)
        owners = {a.subject: a.owner for a in Activity.objects.filter(pk__in=[todo.pk, logged.pk, mine.pk])}
        self.assertEqual(owners, {"Call back": self.jason, "Site visit": self.siti, "Check margin": self.manager})

    def test_rep_cannot_reassign(self):  # RA-2
        deal = self.deal()
        self.assertNotContains(self.client.get(reverse("opportunity", args=[deal.pk])), reverse("opportunity_assign", args=[deal.pk]))
        self.assertEqual(self.assign(deal, self.jason).status_code, 403)
        deal.refresh_from_db()
        self.assertEqual(deal.owner, self.siti)

    def test_closed_deal_and_inactive_rep_refused(self):  # RA-3
        won = self.deal(stage="won")
        deal = self.deal()
        SalesRep.objects.filter(user=self.jason).update(active=False)
        self.kumar.is_active = False
        self.kumar.save()
        self.login(self.manager)
        for record, to in ((won, self.aisyah), (deal, self.jason), (deal, self.kumar)):
            self.assign(record, to)
        self.assertEqual(set(Opportunity.objects.values_list("owner", flat=True)), {self.siti.pk})

    def test_reassign_error_sits_by_the_field(self):  # AC20
        deal = self.deal()
        SalesRep.objects.filter(user=self.jason).update(active=False)
        self.login(self.manager)
        response = self.assign(deal, self.jason)
        error = '<p class="error" id="id_owner_error">Select a valid choice. That choice is not one of the available choices.</p>'
        self.assertContains(response, error, html=True, status_code=400)
        self.assertContains(response, 'aria-describedby="id_owner_error"', status_code=400)
        deal.refresh_from_db()
        self.assertEqual(deal.owner, self.siti)
        self.assertRedirects(self.assign(deal, self.kumar), deal.get_absolute_url())
