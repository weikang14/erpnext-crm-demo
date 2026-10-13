import re
import threading
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import Client, TransactionTestCase
from django.urls import reverse

from sales import access
from sales.models import Account, Opportunity, Product, Quote
from sales.rules import RuleError
from sales.tests.base import CRMTestCase


def page_form(client, quote, action):
    """The hidden fields of the quote page's `action` form, as the browser would post them."""
    page = client.get(reverse("quote", args=[quote.pk])).content.decode()
    form = re.search(rf'<form [^>]*action="{reverse("quote_action", args=[quote.pk, action])}".*?</form>', page, re.S)[0]
    return dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', form))


class QuoteEditorTests(CRMTestCase):
    def test_new_quote_from_deal(self):
        deal = self.deal()
        response = self.client.post(reverse("opportunity_quote_new", args=[deal.pk]))
        quote = Quote.objects.get()
        self.assertRedirects(response, reverse("quote", args=[quote.pk]))
        self.assertEqual(quote.number, f"QT-{quote.created_at.year}-{quote.pk:05d}")

    def test_unit_price_cannot_be_posted(self):  # Q-3
        quote = self.quote(self.deal(), lines=[])
        self.client.post(reverse("quote_line_add", args=[quote.pk]),
                         {"product": self.frame.pk, "qty": "2", "discount_pct": "0", "unit_price": "1"})  # fmt: skip
        self.assertEqual(quote.lines.get().unit_price, Decimal("1450.00"))

    def test_line_validation(self):  # Q-4
        quote = self.quote(self.deal(), lines=[])
        self.frame.active = False
        self.frame.save()
        response = self.client.post(reverse("quote_line_add", args=[quote.pk]),
                                    {"product": self.frame.pk, "qty": "0", "discount_pct": "101"})  # fmt: skip
        self.assertEqual(response.status_code, 400)
        form = response.context["line_form"]
        self.assertEqual(set(form.errors), {"product", "qty", "discount_pct"})
        self.assertFalse(quote.lines.exists())

    def test_submit_routes_by_discount(self):  # QA-1, QA-2 through the view
        ok = self.quote(self.deal(), lines=[(None, "1", "10")])
        self.client.post(reverse("quote_action", args=[ok.pk, "submit"]), page_form(self.client, ok, "submit"))
        ok.refresh_from_db()
        self.assertEqual(ok.status, "approved")
        big = self.quote(self.deal(title="other"), lines=[(None, "1", "10.01")])
        self.client.post(reverse("quote_action", args=[big.pk, "submit"]), page_form(self.client, big, "submit"))
        big.refresh_from_db()
        self.assertEqual(big.status, "pending")

    def test_line_delete_only_on_draft(self):
        quote = self.quote(self.deal(), status=Quote.Status.APPROVED)
        line = quote.lines.get()
        self.client.post(reverse("quote_line_delete", args=[quote.pk, line.pk]))
        self.assertTrue(quote.lines.exists())

    def test_other_reps_quote_is_404(self):  # SEC-1
        quote = self.quote(self.deal(owner=self.kumar))
        self.assertEqual(self.client.get(reverse("quote", args=[quote.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("quote_action", args=[quote.pk, "submit"])).status_code, 404)

    def test_unknown_action_is_404(self):
        quote = self.quote(self.deal())
        self.assertEqual(self.client.post(reverse("quote_action", args=[quote.pk, "delete"])).status_code, 404)


class ApprovalTests(CRMTestCase):
    def pending(self):
        return self.quote(self.deal(), lines=[(None, "10", "15")], status=Quote.Status.PENDING)

    def test_rep_cannot_approve(self):  # QA-4
        quote = self.pending()
        self.assertEqual(self.client.post(reverse("quote_action", args=[quote.pk, "approve"])).status_code, 403)
        quote.refresh_from_db()
        self.assertEqual(quote.status, "pending")

    def test_reject_needs_note(self):  # QA-5
        quote = self.pending()
        self.login(self.manager)
        response = self.client.post(reverse("quote_action", args=[quote.pk, "reject"]), {"note": ""})
        self.assertEqual(response.status_code, 400)
        self.client.post(reverse("quote_action", args=[quote.pk, "reject"]), {"note": "Max 12 % for this customer"})
        quote.refresh_from_db()
        self.assertEqual((quote.status, quote.decision_note), ("draft", "Max 12 % for this customer"))
        self.login(self.rep)
        self.assertContains(self.client.get(reverse("quote", args=[quote.pk])), "Sent back by the sales manager: Max 12 %")

    def test_approve(self):  # QA-6
        quote = self.pending()
        self.login(self.manager)
        response = self.client.post(reverse("quote_action", args=[quote.pk, "approve"]), page_form(self.client, quote, "approve"))
        self.assertRedirects(response, reverse("approvals"))
        quote.refresh_from_db()
        self.assertEqual((quote.status, quote.approved_by), ("approved", self.manager))
        self.assertIsNotNone(quote.approved_at)

    def test_approvals_page_is_manager_only(self):  # SEC-2
        self.pending()
        self.assertEqual(self.client.get(reverse("approvals")).status_code, 403)
        self.login(self.manager)
        response = self.client.get(reverse("approvals"))
        self.assertContains(response, "15 %")
        self.assertContains(response, "722.50")  # 10 x 85.00 less 15 %


class SendPrintTests(CRMTestCase):
    def test_send_only_when_approved(self):  # QS-1
        deal = self.deal()
        for status in (Quote.Status.DRAFT, Quote.Status.PENDING):
            Quote.objects.all().delete()
            quote = self.quote(deal, status=status)
            response = self.client.post(reverse("quote_action", args=[quote.pk, "send"]), follow=True)
            quote.refresh_from_db()
            self.assertEqual(quote.status, status)
            self.assertContains(response, "can&#x27;t be done now")

    def test_approved_quote_is_locked(self):  # QS-2
        quote = self.quote(self.deal(), status=Quote.Status.APPROVED)
        self.client.post(reverse("quote_line_add", args=[quote.pk]), {"product": self.frame.pk, "qty": "1", "discount_pct": "0"})
        self.assertEqual(quote.lines.count(), 1)

    def test_send_moves_deal(self):  # QS-3
        deal = self.deal(stage="enquiry", amount="1")
        quote = self.quote(deal, lines=[(None, "4", "0")], status=Quote.Status.APPROVED)
        self.client.post(reverse("quote_action", args=[quote.pk, "send"]))
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.amount), ("quotation", Decimal("340.00")))

    def test_revise(self):  # QS-4
        deal = self.deal(stage="quotation")
        sent = self.quote(deal, lines=[(None, "4", "5")], status=Quote.Status.SENT)
        response = self.client.post(reverse("quote_action", args=[sent.pk, "revise"]))
        draft = Quote.objects.exclude(pk=sent.pk).get()
        self.assertRedirects(response, reverse("quote", args=[draft.pk]), fetch_redirect_response=False)
        sent.refresh_from_db()
        self.assertEqual((draft.status, sent.status, draft.lines.get().discount_pct), ("draft", "sent", Decimal("5.00")))

    def test_print(self):  # QP-1
        quote = self.quote(self.deal(), lines=[(None, "4", "0")])
        self.assertEqual(self.client.get(reverse("quote_print", args=[quote.pk])).status_code, 404)
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.APPROVED)
        response = self.client.get(reverse("quote_print", args=[quote.pk]))
        for text in (quote.number, "Tanjung Electrical Contractors Sdn Bhd", "FG-CT-300", "340.00", "Valid until", "excluding SST"):
            self.assertContains(response, text)


class StaleRequestTests(CRMTestCase):
    """FM1/AC15: a request that loaded the quote just before another request changed it must act on the change."""

    def stale(self, quote):
        return access.quotes(self.manager).get(pk=quote.pk)  # what the view loaded at the start of its request

    def post_stale(self, stale, name, *args, data=None):
        with mock.patch.object(access, "get", return_value=stale):
            return self.client.post(reverse(name, args=[stale.pk, *args]), data or {})

    def test_line_added_while_submit_wins_is_refused(self):  # add a 60 % line at the same moment as Submit
        quote = self.quote(self.deal(), lines=[(None, "1", "5")])
        stale = self.stale(quote)
        quote.submit(self.rep)  # no line needs approval yet, so it is approved
        self.post_stale(stale, "quote_line_add", data={"product": self.tray.pk, "qty": "1", "discount_pct": "60"})
        quote.refresh_from_db()
        self.assertEqual((quote.status, quote.needs_approval), ("approved", False))

    def test_line_deleted_while_submit_wins_is_refused(self):
        quote = self.quote(self.deal(), lines=[(None, "1", "5"), (None, "2", "0")])
        stale = self.stale(quote)
        quote.submit(self.rep)
        self.post_stale(stale, "quote_line_delete", quote.lines.first().pk)
        self.assertEqual(quote.lines.count(), 2)

    def test_approve_after_reject_and_new_line_is_refused(self):  # the manager never saw the 60 % line
        quote = self.quote(self.deal(), lines=[(None, "1", "15")], status=Quote.Status.PENDING)
        stale = self.stale(quote)
        quote.reject(self.manager, "Max 12 %")
        quote.add_line(self.tray, Decimal("1"), Decimal("60"))
        self.login(self.manager)
        self.post_stale(stale, "quote_action", "approve", data={"note": ""})
        quote.refresh_from_db()
        self.assertEqual(quote.status, "draft")

    def test_send_refuses_discount_no_manager_approved(self):  # defence in depth if a quote ever got here
        quote = self.quote(self.deal(), lines=[(None, "1", "60")], status=Quote.Status.APPROVED)
        Quote.objects.filter(pk=quote.pk).update(approved_by=self.rep)
        response = self.client.post(reverse("quote_action", args=[quote.pk, "send"]), follow=True)
        quote.refresh_from_db()
        self.assertEqual(quote.status, "approved")
        self.assertContains(response, "needs the sales manager")


class StalePageTests(CRMTestCase):
    """AC15/FM1: Approve and Finish approve only the lines their page showed. Real pages, real changes in between."""

    STALE = "This quote changed since you opened it; review it again."

    def setUp(self):
        super().setUp()
        self.other = Client()  # the rep, in another browser
        self.other.force_login(self.rep)

    def post(self, client, quote, action, data):
        return client.post(reverse("quote_action", args=[quote.pk, action]), data, follow=True)

    def add_60(self, quote):
        self.other.post(reverse("quote_line_add", args=[quote.pk]), {"product": self.tray.pk, "qty": "1", "discount_pct": "60"})

    def test_approve_from_before_a_reject_and_resubmit_is_refused(self):
        quote = self.quote(self.deal(), lines=[(None, "1", "15")])
        self.post(self.client, quote, "submit", page_form(self.client, quote, "submit"))
        self.login(self.manager)
        approve = page_form(self.client, quote, "approve") | {"note": ""}  # the page shows the 15 % line only
        self.post(self.client, quote, "reject", approve | {"note": "Max 12 %"})  # another tab, or another manager
        self.add_60(quote)
        self.post(self.other, quote, "submit", page_form(self.other, quote, "submit"))
        quote.refresh_from_db()
        self.assertEqual(quote.status, "pending")
        response = self.post(self.client, quote, "approve", approve)  # the old page's Approve
        quote.refresh_from_db()
        self.assertEqual((quote.status, quote.approved_by), ("pending", None))
        self.assertContains(response, self.STALE)

    def test_manager_finish_from_before_a_line_change_is_refused(self):
        quote = self.quote(self.deal(), lines=[(None, "1", "5")])
        self.login(self.manager)
        finish = page_form(self.client, quote, "submit")  # "Finish quote", within the limit
        self.add_60(quote)
        response = self.post(self.client, quote, "submit", finish)
        quote.refresh_from_db()
        self.assertEqual((quote.status, quote.approved_by), ("draft", None))
        self.assertContains(response, self.STALE)
        finish = page_form(self.client, quote, "submit")  # reviewed: the page shows the 60 % line now
        self.other.post(reverse("quote_line_delete", args=[quote.pk, quote.lines.last().pk]))
        self.post(self.client, quote, "submit", finish)
        quote.refresh_from_db()
        self.assertEqual(quote.status, "draft")  # a removed line is a change too
        self.post(self.client, quote, "submit", page_form(self.client, quote, "submit"))
        quote.refresh_from_db()
        self.assertEqual((quote.status, quote.approved_by), ("approved", self.manager))

    def test_approve_or_finish_without_a_revision_is_refused(self):  # a page from before the field, or a hand-made POST
        pending = self.quote(self.deal(), lines=[(None, "1", "15")], status=Quote.Status.PENDING)
        draft = self.quote(self.deal(title="other"), lines=[(None, "1", "5")])
        self.login(self.manager)
        self.post(self.client, pending, "approve", {"note": ""})
        self.post(self.client, draft, "submit", {})
        pending.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual((pending.status, draft.status), ("pending", "draft"))


class QuoteLockTests(TransactionTestCase):
    """FM1 with a real row lock held in another connection (StaleRequestTests only fake the stale read)."""

    def test_add_line_waits_for_submit_then_is_refused(self):
        rep = User.objects.create_user("siti")
        tray = Product.objects.create(item_code="FG-CT-300", name="Cable Tray", list_price=Decimal("85"))
        account = Account.objects.create(name="Tanjung", state="Johor")
        deal = Opportunity.objects.create(title="Trays", account=account, owner=rep, expected_close="2026-12-31")
        quote = Quote.start(deal, rep)
        quote.add_line(tray, Decimal("1"), Decimal("5"))
        stale = Quote.objects.get(pk=quote.pk)  # what the line-add view loaded
        outcome = []

        def add_60():
            try:
                stale.add_line(tray, Decimal("1"), Decimal("60"))
                outcome.append("added")
            except RuleError:
                outcome.append("refused")
            finally:
                connection.close()

        with transaction.atomic():
            mine = Quote.objects.get(pk=quote.pk)
            mine._require(Quote.Status.DRAFT)  # Submit holds the deal and quote locks
            worker = threading.Thread(target=add_60)
            worker.start()
            worker.join(1.5)
            waited = worker.is_alive()
            mine.status = Quote.Status.APPROVED
            mine.save()
        worker.join(15)
        self.assertTrue(waited, "add_line did not wait for Submit's lock")
        self.assertEqual((outcome, quote.lines.count()), (["refused"], 1))
