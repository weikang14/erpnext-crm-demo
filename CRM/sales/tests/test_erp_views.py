"""004 tasks 3.1-3.3, the screens' side of the send: the Won form's requested delivery date, the order sent right
after Won commits, the resend route and the ERP order panel. ERPNext is a FakeERPNext, injected by patching
sales.erpnext.client_from_settings (the views call it through the module); not-configured cases run the real function
with ERPNEXT_URL empty."""

import re
import threading
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.db import DatabaseError
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from sales.erpnext import Refused, Unavailable, client_from_settings
from sales.forms import WonForm
from sales.models import Account, Opportunity, Product, Quote, StageChange
from sales.regions import Region
from sales.tests.base import CRMTestCase, make_user
from sales.tests.fakes import TEC, FakeERPNext
from sales.tests.test_erp_send import flaky_record, in_thread

NOW = datetime(2026, 10, 15, 1, 0, tzinfo=UTC)  # 09:00 in Kuala Lumpur
EARLY = datetime(2026, 10, 14, 23, 0, tzinfo=UTC)  # 07:00 KL on 15 Oct, still the 14th in UTC
ORDER = "SAL-ORD-2026-00020"
T1 = "ERPNext didn't answer. The order may or may not exist; sending again checks first, so it can't be duplicated."
TU = "Unexpected error while sending; see the server log."
WON = "Won: Cable trays for plant 2, MYR 235.88."
CREATED = f"Sales order {ORDER} created in ERPNext."
PAST = "The delivery date can't be before today."
AHEAD = "The delivery date can't be more than a year ahead."
WITH_TAX = ["find_order", "get_customer", "tax_rows", "create_order", "submit_order"]
ALREADY = "This deal's order is already in ERPNext."
ONLY_WON = "Only won deals can be sent."
BEING_SENT = "This deal is being sent right now; refresh in a moment."
FRACTION = "Row 1: Quantity (1.5) cannot be a fraction. To allow this, disable 'Must be Whole Number' in UOM Nos."


def not_taken(reason):
    """A refusal's flash (round 1): the deal stays won, ERPNext's reason, what to do."""
    return f"Won is saved, but ERPNext didn't take the order: {reason} Fix it and send again from the deal."


def flash(level, text):
    return f'<p class="msg msg-{level}" role="{"alert" if level == "error" else "status"}">{text}</p>'


def claim_error():
    return mock.patch.object(Opportunity, "claim_send", side_effect=DatabaseError("could not claim"))


def date_input(value, minimum):
    maximum = date.fromisoformat(minimum) + timedelta(days=365)  # round 2: at most a year ahead
    return (f'<input type="date" name="delivery_date" value="{value}" min="{minimum}" max="{maximum}" required '
            'id="id_delivery_date">')  # fmt: skip


class ViewTestCase(CRMTestCase):
    def setUp(self):
        super().setUp()
        self.viewer = self.rep
        self.at(NOW)
        self.fake = FakeERPNext()
        erp_link = mock.patch("sales.erpnext.client_from_settings", return_value=self.fake)
        self.erp_link = erp_link.start()
        self.addCleanup(erp_link.stop)

    def at(self, instant):
        clock = mock.patch("django.utils.timezone.now", return_value=instant)
        clock.start()
        self.addCleanup(clock.stop)
        self.login(self.viewer)  # sessions last 10 hours: sign in again on the new clock

    def login(self, user):
        self.viewer = user
        super().login(user)

    def new_fake(self):
        self.fake = self.erp_link.return_value = FakeERPNext()

    def d1(self, account=None):
        """Siti's open deal on TEC with sent quote Q133: 3 x tray at 7.5 % -> 235.88."""
        deal = self.deal(stage="negotiation", account=account)
        self.quote(deal, lines=[(None, "3", "7.5")], status=Quote.Status.SENT)
        return deal

    def won(self, delivery=date(2026, 10, 20), **erp):
        deal = self.d1()
        deal.mark_won(self.rep, delivery)
        Opportunity.objects.filter(pk=deal.pk).update(**erp)
        deal.refresh_from_db()
        return deal

    def win(self, deal, day="2026-10-29", **kwargs):
        data = {} if day is None else {"delivery_date": day}
        return self.client.post(reverse("opportunity_won", args=[deal.pk]), data, **kwargs)

    def body(self):
        return [argument for method, argument in self.fake.calls if method == "create_order"][-1]

    def assert_date_error(self, response, text):  # AC20's pattern: 400, the error by the field, the input points at it
        error = f'<p class="error" id="id_delivery_date_error">{text}</p>'
        self.assertContains(response, error, html=True, status_code=400)
        self.assertContains(response, 'aria-invalid="true"', status_code=400)
        self.assertContains(response, 'aria-describedby="id_delivery_date_error"', status_code=400)
        self.assertEqual(self.fake.calls, [])

    def assert_clean(self, html):  # BRT-12, UI-3 on the rendered page
        self.assertNotRegex(html, r"\sstyle=")
        self.assertNotRegex(html, r"<script(?![^>]*\ssrc=)")
        self.assertIsNone(re.search(r"\son[a-z]+=", html))


class WonFormTests(ViewTestCase):
    def test_won_form_asks_for_the_delivery_date(self):  # WON-D-1, AC1
        deal = self.d1()
        response = self.client.get(deal.get_absolute_url())
        self.assertContains(response, '<label for="id_delivery_date">Requested delivery date</label>', html=True)
        self.assertContains(response, date_input("2026-10-29", "2026-10-15"), html=True)
        url = reverse("opportunity_won", args=[deal.pk])
        won_form = re.search(rf'action="{url}".*?</form>', response.content.decode(), re.S).group()
        self.assertIn('name="delivery_date"', won_form)
        self.assertIn("Mark won", won_form)
        self.assert_clean(response.content.decode())

    def test_dates_are_kuala_lumpur_dates(self):  # WON-D-2, SO-3, Review Focus 5, FM14
        cases = [
            (EARLY, "2026-10-15", "2026-10-29"),
            (datetime(2026, 10, 31, 15, 59, tzinfo=UTC), "2026-10-31", "2026-11-14"),  # 23:59 KL, a month's last day
            (datetime(2026, 10, 31, 16, 1, tzinfo=UTC), "2026-11-01", "2026-11-15"),  # 00:01 KL on 1 Nov, 31 Oct in UTC
        ]  # fmt: skip
        for instant, today, default in cases:
            with self.subTest(instant=instant):
                self.at(instant)
                deal = self.d1()
                self.assertContains(self.client.get(deal.get_absolute_url()), date_input(default, today), html=True)
                self.assertRedirects(self.win(deal, default), deal.get_absolute_url())
                self.assertEqual((self.body()["transaction_date"], self.body()["delivery_date"]), (today, default))

    def test_past_date_is_refused_by_the_kl_date(self):  # WON-D-3, FM14
        self.at(EARLY)
        deal = self.d1()
        response = self.win(deal, "2026-10-14")
        self.assert_date_error(response, PAST)
        self.assert_clean(response.content.decode())
        deal.refresh_from_db()
        self.assertEqual((deal.is_open, deal.delivery_date, deal.quotes.get().status), (True, None, "sent"))

    def test_today_is_accepted(self):  # WON-D-4
        self.at(EARLY)
        deal = self.d1()
        self.assertRedirects(self.win(deal, "2026-10-15"), deal.get_absolute_url())
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.delivery_date), ("won", date(2026, 10, 15)))

    def test_at_most_a_year_ahead_by_the_kl_date(self):  # round 2: today + 365 days inclusive
        self.at(EARLY)
        deal = self.d1()
        response = self.win(deal, "2027-10-16")
        self.assert_date_error(response, AHEAD)
        deal.refresh_from_db()
        self.assertEqual((deal.is_open, deal.delivery_date), (True, None))
        self.assertRedirects(self.win(deal, "2027-10-15"), deal.get_absolute_url())
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.delivery_date), ("won", date(2027, 10, 15)))
        self.assertEqual(self.body()["delivery_date"], "2027-10-15")

    def test_missing_or_invalid_date_is_400_by_the_field(self):  # WON-D-5, WON-D-6, AC1, AC20
        deal = self.d1()
        for day, text in ((None, "This field is required."), ("", "This field is required."),
                          ("2026-02-30", "Enter a valid date.")):  # fmt: skip
            with self.subTest(day=day):
                self.assert_date_error(self.win(deal, day), text)
                deal.refresh_from_db()
                self.assertEqual((deal.is_open, deal.delivery_date), (True, None))


class WonSendTests(ViewTestCase):
    def test_order_is_sent_right_after_won(self):  # SEND-1, SEND-2, BRT-3, WON-D-7, AC3
        deal = self.d1()
        response = self.win(deal, "2026-11-30", follow=True)
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertContains(response, flash("success", WON), html=True)
        self.assertContains(response, flash("success", CREATED), html=True)
        self.assertEqual(self.fake.names, WITH_TAX)
        self.assertEqual(self.body()["delivery_date"], "2026-11-30")
        deal.refresh_from_db()
        erp_fields = (deal.erp_status, deal.erp_order, deal.erp_error, deal.erp_attempted_at)
        self.assertEqual(erp_fields, ("sent", ORDER, "", NOW))
        self.assertEqual((deal.stage, deal.delivery_date), ("won", date(2026, 11, 30)))

    def test_won_is_kept_whatever_erpnext_does(self):  # SEND-4, BRT-1, BRT-2, ERR-11, AC2, FM13
        cases = [("find_order", Unavailable("timed out"), T1, T1),  # says what to do already: no lead-in
                 ("create_order", Refused(FRACTION), FRACTION, not_taken(FRACTION)),
                 ("submit_order", Refused("Item FG-CT-300 is disabled"), "Item FG-CT-300 is disabled",
                  not_taken("Item FG-CT-300 is disabled."))]  # fmt: skip
        for call, error, reason, shown in cases:
            with self.subTest(call=call):
                self.new_fake()
                self.fake.fail[call] = error
                deal = self.d1()
                response = self.win(deal, "2026-11-30", follow=True)
                self.assert_won_kept(deal, response, reason, shown)

    def test_unexpected_error_is_a_warning_not_a_500(self):  # ERR-13, ERR-14, Clar.
        self.fake.fail["tax_rows"] = KeyError("taxes")
        deal = self.d1()
        with self.assertLogs("sales.erp", "ERROR"):
            response = self.win(deal, "2026-11-30", follow=True)
        self.assert_won_kept(deal, response, TU)
        self.assertNotContains(response, "KeyError")

    def test_recording_error_is_a_warning_not_a_500(self):  # round 1: an order name another deal holds, a db error
        deal = self.d1()
        with flaky_record(1), self.assertLogs("sales.erp", "ERROR"):
            response = self.win(deal, "2026-11-30", follow=True)
        self.assert_won_kept(deal, response, TU)

    def test_claim_error_is_a_warning_not_a_500(self):  # round 2: a database error in the claim's UPDATE
        deal = self.d1()
        with claim_error(), self.assertLogs("sales.erp", "ERROR"):
            response = self.win(deal, "2026-11-30", follow=True)
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertContains(response, flash("success", WON), html=True)
        self.assertContains(response, flash("warning", TU), html=True)
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.delivery_date, deal.erp_status), ("won", date(2026, 11, 30), "not_sent"))
        self.assertEqual(self.fake.calls, [])

    def assert_won_kept(self, deal, response, reason, shown=None):
        """shown: the flash, when it isn't the reason alone; the panel and erp_error keep the reason alone."""
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertContains(response, flash("success", WON), html=True)
        self.assertContains(response, flash("warning", shown or reason), html=True)
        self.assertContains(response, f"<dd>{reason}</dd>", html=True)
        self.assertNotContains(response, "Traceback")
        deal.refresh_from_db()
        self.assertEqual(deal.erp_error, reason)
        self.assertEqual((deal.stage, deal.amount, deal.delivery_date, deal.erp_status, deal.quotes.get().status),
                         ("won", Decimal("235.88"), date(2026, 11, 30), "failed", "accepted"))  # fmt: skip
        self.assertIsNotNone(deal.closed_at)
        self.assertEqual(StageChange.objects.filter(opportunity=deal, to_stage="won").count(), 1)

    def test_won_refused_by_the_003_rules_sends_nothing(self):  # BRT-4, BRT-5, EB2, EB3
        draft_only = self.deal(stage="negotiation")
        self.quote(draft_only)
        response = self.win(draft_only, follow=True)
        self.assertContains(response, flash("error", "Send a quote before marking the deal won."), html=True)
        draft_only.refresh_from_db()
        self.assertEqual((draft_only.is_open, draft_only.delivery_date), (True, None))
        won = self.won(erp_status="sent", erp_order=ORDER)
        for day in ("2026-12-31", None):  # a closed deal has no date field to show an error by: the rule answers
            with self.subTest(day=day):
                response = self.win(won, day, follow=True)
                self.assertContains(response, flash("error", "This deal is closed."), html=True)
        won.refresh_from_db()
        self.assertEqual((won.delivery_date, won.erp_status, won.erp_order), (date(2026, 10, 20), "sent", ORDER))
        self.assertEqual(self.fake.calls, [])

    def test_other_reps_won_is_404(self):  # BRT-11, EB8
        deal = self.d1()
        self.login(self.jason)
        self.assertEqual(self.win(deal).status_code, 404)
        deal.refresh_from_db()
        self.assertTrue(deal.is_open)
        self.assertEqual(self.fake.calls, [])

    @override_settings(ERPNEXT_URL="")
    def test_not_configured_won_is_as_in_003(self):  # CFG-1, CFG-5, AC16
        self.erp_link.side_effect = client_from_settings  # the real one
        deal = self.d1()
        with mock.patch("urllib.request.urlopen") as urlopen:
            response = self.win(deal, follow=True)
        urlopen.assert_not_called()
        self.assertContains(response, flash("success", WON), html=True)
        self.assertNotContains(response, "Sales order")
        self.assertNotContains(response, "msg-warning")
        deal.refresh_from_db()
        self.assertEqual((deal.stage, deal.erp_status), ("won", "not_sent"))

    def test_won_page_has_no_deal_controls(self):  # BRT-7, EB4
        self.login(self.manager)
        for status in ("not_sent", "failed", "sent"):
            with self.subTest(status=status):
                deal = self.won(erp_status=status)
                html = self.client.get(deal.get_absolute_url()).content.decode()
                self.assertIn("Won on 15 Oct 2026.", html)
                self.assertNotIn("Mark won", html)
                for name in ("opportunity_won", "opportunity_move", "opportunity_lost", "opportunity_edit",
                             "opportunity_assign", "opportunity_quote_new"):  # fmt: skip
                    self.assertNotIn(reverse(name, args=[deal.pk]), html)
                self.assert_clean(html)


class WonCommitTests(TransactionTestCase):
    """Real commits: another connection sees what the Won request has committed while ERPNext is being called."""

    def setUp(self):
        clock = mock.patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.rep = make_user("siti", Region.SOUTH)
        self.tray = Product.objects.create(item_code="FG-CT-300", name="Cable Tray", list_price=Decimal("85"))
        self.fake = FakeERPNext()
        erp_link = mock.patch("sales.erpnext.client_from_settings", return_value=self.fake)
        erp_link.start()
        self.addCleanup(erp_link.stop)
        account = Account.objects.create(name=TEC, state="Johor")
        self.deal = Opportunity.objects.create(
            title="Cable trays for plant 2", account=account, owner=self.rep, stage="negotiation",
            expected_close=date(2026, 10, 31),
        )  # fmt: skip
        quote = Quote.start(self.deal, self.rep)
        quote.add_line(self.tray, Decimal("3"), Decimal("7.5"))
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.SENT)

    def post_won(self, client=None):
        if client is None:
            client = Client()
            client.force_login(self.rep)
        url = reverse("opportunity_won", args=[self.deal.pk])
        return client.post(url, {"delivery_date": "2026-10-29"}, follow=True).content.decode()

    def test_send_starts_after_won_commits_and_stops_at_the_first_failure(self):  # SEND-3, SEND-5, AC2, FM1, NFR
        seen = {}

        def at_lookup():  # another connection, while c1 is in flight
            row = Opportunity.objects.get(pk=self.deal.pk)
            seen["c1"] = (row.stage, row.amount, row.quotes.get().status)

        def slow_lookup():
            in_thread(at_lookup)
            time.sleep(0.5)

        self.fake.hooks["find_order"] = slow_lookup
        self.fake.fail["find_order"] = Unavailable("timed out")
        start = time.monotonic()
        html = self.post_won()
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertEqual(seen["c1"], ("won", Decimal("235.88"), "accepted"))
        self.assertEqual(self.fake.names, ["find_order"])
        self.assertIn("msg-warning", html)
        self.deal.refresh_from_db()
        self.assertEqual((self.deal.stage, self.deal.erp_status), ("won", "failed"))

    def test_two_won_posts_at_once_win_and_send_once(self):  # BRT-6, EB3, FM3
        self.fake.hooks["create_order"] = lambda: time.sleep(0.5)
        start, pages = threading.Barrier(2), []

        def post():
            client = Client()
            client.force_login(self.rep)
            start.wait(5)
            pages.append(self.post_won(client))

        threads = [threading.Thread(target=in_thread, args=[post]) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
        self.assertEqual(sorted("This deal is closed." in page for page in pages), [False, True])
        self.assertEqual(StageChange.objects.filter(opportunity=self.deal, to_stage="won").count(), 1)
        self.assertEqual(self.fake.names.count("create_order"), 1)


class ResendTests(ViewTestCase):
    def resend(self, deal, day="2026-10-29", client=None, **kwargs):
        data = {} if day is None else {"delivery_date": day}
        return (client or self.client).post(reverse("opportunity_erp_send", args=[deal.pk]), data, **kwargs)

    def failed(self, delivery=date(2026, 10, 20)):
        return self.won(delivery, erp_status="failed", erp_error=T1, erp_attempted_at=NOW)

    def stored(self, deal):
        return Opportunity.objects.filter(pk=deal.pk).values(
            "stage", "delivery_date", "erp_status", "erp_order", "erp_error", "erp_attempted_at"
        ).get()  # fmt: skip

    def test_owner_and_manager_can_resend(self):  # RES-1, RES-2, CLAIM-2, AC15
        for user, order in ((self.rep, ORDER), (self.manager, "SAL-ORD-2026-00021")):
            with self.subTest(user=user.username):
                self.login(user)
                deal = self.failed()
                response = self.resend(deal, follow=True)
                self.assertRedirects(response, deal.get_absolute_url())
                self.assertContains(response, flash("success", f"Sales order {order} created in ERPNext."), html=True)
                deal.refresh_from_db()
                self.assertEqual((deal.erp_status, deal.erp_order, deal.erp_error), ("sent", order, ""))

    def test_the_date_entered_replaces_the_stored_one(self):  # RES-13, RES-15, Clar.
        deal = self.failed(date(2026, 10, 20))
        self.at(datetime(2026, 10, 20, 1, 0, tzinfo=UTC))
        self.resend(deal, "2026-11-05")
        body = self.body()
        self.assertEqual((body["transaction_date"], body["delivery_date"]), ("2026-10-20", "2026-11-05"))
        self.assertEqual({item["delivery_date"] for item in body["items"]}, {"2026-11-05"})
        deal.refresh_from_db()
        self.assertEqual((deal.erp_status, deal.delivery_date), ("sent", date(2026, 11, 5)))

    def test_deal_won_before_004_can_be_sent(self):  # RES-9
        deal = self.won(None)
        self.assertEqual((deal.erp_status, deal.delivery_date), ("not_sent", None))
        self.resend(deal, "2026-10-29")
        deal.refresh_from_db()
        self.assertEqual((deal.erp_status, deal.erp_order, deal.delivery_date), ("sent", ORDER, date(2026, 10, 29)))

    def test_form_prefills_the_stored_date_unless_none_or_past(self):  # RES-9, RES-10, RES-11
        today, default, later = date(2026, 10, 15), date(2026, 10, 29), date(2026, 10, 20)
        for stored, prefilled in ((None, default), (later, later), (today, today), (date(2026, 10, 1), default),
                                  (date(2027, 10, 15), date(2027, 10, 15)), (date(9999, 12, 31), default)):  # fmt: skip
            with self.subTest(stored=stored):
                self.assertEqual(WonForm(stored=stored)["delivery_date"].value(), prefilled)

    def test_other_reps_resend_is_404(self):  # RES-3, FM9
        deal = self.failed()
        self.login(self.jason)
        self.assertEqual(self.resend(deal).status_code, 404)
        self.assertEqual(self.stored(deal)["erp_status"], "failed")
        self.assertEqual(self.fake.calls, [])

    def test_get_is_405_and_viewing_never_sends(self):  # RES-5, RES-6, FM9
        deal = self.failed()
        self.assertEqual(self.client.get(reverse("opportunity_erp_send", args=[deal.pk])).status_code, 405)
        for status in ("failed", "not_sent"):
            Opportunity.objects.filter(pk=deal.pk).update(erp_status=status)
            self.assertEqual(self.client.get(deal.get_absolute_url()).status_code, 200)
        self.assertEqual(self.stored(deal)["erp_status"], "not_sent")
        self.assertEqual(self.fake.calls, [])

    def test_csrf_is_required(self):  # RES-7
        deal = self.failed()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.rep)
        self.assertEqual(self.resend(deal, client=strict).status_code, 403)
        self.assertEqual(self.fake.calls, [])

    def test_refusals_are_flashed_and_change_nothing(self):  # RES-4, RES-8, CLAIM-3, Clar.
        sent = self.won(erp_status="sent", erp_order=ORDER, erp_attempted_at=NOW)
        sending = self.won(erp_status="sending", erp_attempted_at=NOW - timedelta(minutes=1))
        open_deal = self.d1()
        lost = self.deal(stage="lost", closed_at=NOW, lost_reason=self.price_reason)
        cases = [(sent, "2026-11-30", ALREADY), (sent, None, ALREADY), (sending, "2026-11-30", BEING_SENT),
                 (open_deal, "2026-11-30", ONLY_WON), (lost, "2026-11-30", ONLY_WON)]  # fmt: skip
        for deal, day, message in cases:
            with self.subTest(message=message, day=day):
                before = self.stored(deal)
                response = self.resend(deal, day, follow=True)
                self.assertRedirects(response, deal.get_absolute_url())
                self.assertContains(response, flash("error", message), html=True)
                self.assertEqual(self.stored(deal), before)  # the date entered is not stored either
        self.assertEqual(self.fake.calls, [])

    def test_refused_resend_says_the_deal_stays_won(self):  # round 1, AC14
        deal = self.failed()
        self.fake.fail["create_order"] = Refused(FRACTION)
        response = self.resend(deal, follow=True)
        self.assertContains(response, flash("warning", not_taken(FRACTION)), html=True)
        self.assertContains(response, f"<dd>{FRACTION}</dd>", html=True)
        self.assertEqual(self.stored(deal)["erp_error"], FRACTION)
        self.new_fake()
        self.fake.fail["find_order"] = Unavailable("timed out")
        self.assertContains(self.resend(deal, follow=True), flash("warning", T1), html=True)

    def test_double_click_sends_once(self):  # RES (double click), IDEM-4, FM3
        deal = self.failed()
        self.resend(deal)
        response = self.resend(deal, follow=True)
        self.assertContains(response, flash("error", ALREADY), html=True)
        self.assertEqual(self.fake.names.count("create_order"), 1)
        self.assertEqual(self.stored(deal)["erp_order"], ORDER)

    def test_claim_error_is_a_warning_not_a_500(self):  # round 2
        deal = self.failed()
        before = self.stored(deal)
        with claim_error(), self.assertLogs("sales.erp", "ERROR"):
            response = self.resend(deal, "2026-11-30", follow=True)
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertContains(response, flash("warning", TU), html=True)
        self.assertEqual(self.stored(deal), before)  # still failed: the panel offers the form again
        self.assertEqual(self.fake.calls, [])

    def test_past_or_missing_date_is_400_and_claims_nothing(self):  # RES-12, RES-14, FM14, Clar.
        deal = self.failed(date(2026, 10, 20))
        before = self.stored(deal)
        for day, text in (("2026-10-14", PAST), ("2027-10-16", AHEAD), (None, "This field is required."),
                          ("", "This field is required.")):  # fmt: skip
            with self.subTest(day=day):
                response = self.resend(deal, day)
                self.assertEqual(response.status_code, 400)
                self.assertTemplateUsed(response, "sales/deals/detail.html")
                self.assertEqual(response.context["send_form"].errors["delivery_date"], [text])
                self.assert_date_error(response, text)  # in the panel's form, by the field
                self.assertEqual(self.stored(deal), before)
        self.assertEqual(self.fake.calls, [])

    @override_settings(ERPNEXT_URL="")
    def test_not_configured_makes_no_call(self):  # CFG-3, AC16
        self.erp_link.side_effect = client_from_settings  # the real one
        deal = self.failed()
        before = self.stored(deal)
        with mock.patch("urllib.request.urlopen") as urlopen:
            response = self.resend(deal, follow=True)
        urlopen.assert_not_called()
        self.assertRedirects(response, deal.get_absolute_url())
        self.assertEqual(self.stored(deal), before)


DESK = "http://localhost:8080"
STALE = "The last send didn't finish; send it again."
MISMATCH = f"ERPNext order {ORDER} totals MYR 235.89, the quote MYR 235.88; check it in ERPNext."


@override_settings(ERPNEXT_DESK_URL=DESK)
class PanelTests(ViewTestCase):
    """Task 3.3: the "ERP order" panel on a won deal, in each state (AC16, AC17, Clar.)."""

    def page(self, deal):
        response = self.client.get(deal.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assert_clean(html)  # PANEL-6, BRT-12, UI-3: every state
        return response, html

    def send_form(self, deal, html):
        url = reverse("opportunity_erp_send", args=[deal.pk])
        found = re.search(rf'<form[^>]*action="{url}".*?</form>', html, re.S)
        return found and found.group()

    def chip(self, response, classes, text):
        self.assertContains(response, f'<span class="{classes}">{text}</span>', html=True)

    def test_sent_links_to_the_order_in_desk(self):  # PANEL-1, PANEL-2
        deal = self.won(erp_status="sent", erp_order=ORDER, erp_attempted_at=datetime(2026, 10, 14, 23, 30, tzinfo=UTC))
        response, html = self.page(deal)
        self.assertContains(response, '<h2 id="erp-heading">ERP order</h2>', html=True)
        self.chip(response, "chip chip-green", "Sent")
        self.assertContains(response, f'<a class="btn" href="{DESK}/app/sales-order/{ORDER}">{ORDER}</a>', html=True)
        self.assertIn("15 Oct 2026, 07:30", html)  # KL, not UTC's 14 Oct 23:30
        self.assertIsNone(self.send_form(deal, html))
        with self.settings(ERPNEXT_DESK_URL=""):  # no Desk to link to: the name alone
            response, html = self.page(deal)
            self.assertNotIn("/app/sales-order/", html)
            self.assertContains(response, f"<dd>{ORDER}</dd>", html=True)

    def test_failed_shows_the_reason_the_time_and_the_form(self):  # PANEL-3, PANEL-6
        deal = self.won(erp_status="failed", erp_error=T1, erp_attempted_at=NOW)
        response, html = self.page(deal)
        self.chip(response, "chip chip-red", "Failed")
        self.assertContains(response, f"<dd>{T1}</dd>", html=True)
        self.assertIn("15 Oct 2026, 09:00", html)
        form = self.send_form(deal, html)
        self.assertIn('name="csrfmiddlewaretoken"', form)
        self.assertIn('<div class="field">', form)  # _field.html: label, input, error by the field
        self.assertInHTML(date_input("2026-10-20", "2026-10-15"), form)
        self.assertInHTML('<button class="btn btn-primary btn-block" type="submit">Send again</button>', form)

    def test_not_sent_offers_the_form_to_the_manager(self):  # PANEL-4, RES-9
        self.login(self.manager)
        deal = self.won(None)
        response, html = self.page(deal)
        self.chip(response, "chip", "Not sent")
        form = self.send_form(deal, html)
        self.assertInHTML(date_input("2026-10-29", "2026-10-15"), form)
        self.assertInHTML('<button class="btn btn-primary btn-block" type="submit">Send to ERPNext</button>', form)

    def test_requested_delivery_date_in_every_state_with_one(self):  # round 1
        delivery = "<dt>Delivery</dt><dd>30 Oct 2026</dd>"
        states = [
            {"erp_status": "sent", "erp_order": ORDER, "erp_attempted_at": NOW},
            {"erp_status": "sent", "erp_order": ORDER, "erp_error": MISMATCH, "erp_attempted_at": NOW},
            {"erp_status": "failed", "erp_error": T1, "erp_attempted_at": NOW},
            {"erp_status": "sending", "erp_attempted_at": NOW - timedelta(minutes=1)},
            {"erp_status": "sending", "erp_attempted_at": NOW - timedelta(minutes=3)},
            {"erp_status": "not_sent"},
        ]
        for erp in states:
            with self.subTest(**erp):
                self.assertIn(delivery, self.page(self.won(date(2026, 10, 30), **erp))[1])
        self.erp_link.return_value = None  # not configured
        self.assertIn(delivery, self.page(self.won(date(2026, 10, 30)))[1])
        self.assertNotIn("<dt>Delivery</dt>", self.page(self.won(None))[1])  # won before 004: no date

    def test_no_panel_on_open_or_lost_deals(self):  # PANEL-5
        for deal in (self.d1(), self.deal(stage="lost", closed_at=NOW, lost_reason=self.price_reason)):
            with self.subTest(stage=deal.stage):
                self.assertNotContains(self.client.get(deal.get_absolute_url()), "ERP order")

    def test_erpnext_text_is_escaped(self):  # PANEL-7, FM10
        deal = self.won(erp_status="failed", erp_error="<script>alert(1)</script>", erp_attempted_at=NOW)
        response, html = self.page(deal)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_total_mismatch_is_an_amber_warning(self):  # PANEL-8, AC8, Clar.
        deal = self.won(erp_status="sent", erp_order=ORDER, erp_error=MISMATCH, erp_attempted_at=NOW)
        response, html = self.page(deal)
        self.chip(response, "chip chip-amber", "Sent, total differs")
        self.assertNotContains(response, '<span class="chip chip-green">Sent</span>', html=True)
        self.assertContains(response, f"<dd>{MISMATCH}</dd>", html=True)
        self.assertContains(response, f'<a class="btn" href="{DESK}/app/sales-order/{ORDER}">{ORDER}</a>', html=True)
        self.assertIsNone(self.send_form(deal, html))

    def test_stale_sending_is_failed_with_the_form(self):  # Clar. (sending), CLAIM
        deal = self.won(erp_status="sending", erp_attempted_at=NOW - timedelta(minutes=3))
        response, html = self.page(deal)
        self.chip(response, "chip chip-red", "Failed")
        self.assertContains(response, f"<dd>{STALE}</dd>", html=True)
        self.assertIn("Send again", self.send_form(deal, html))

    def test_fresh_sending_is_a_plain_chip_and_no_form(self):  # Clar. (sending)
        for age in (timedelta(minutes=1), timedelta(minutes=2)):  # 2 minutes is not yet stale, as for the claim
            with self.subTest(age=age):
                deal = self.won(erp_status="sending", erp_attempted_at=NOW - age)
                response, html = self.page(deal)
                self.chip(response, "chip", "Sending…")
                self.assertIsNone(self.send_form(deal, html))

    @override_settings(ERPNEXT_URL="")
    def test_not_configured_is_a_neutral_chip_and_no_form(self):  # CFG-2, CFG-5, CFG-6, AC16
        self.erp_link.side_effect = client_from_settings  # the real one
        for status in ("not_sent", "failed"):
            deal = self.won(None, erp_status=status, erp_error=T1 if status == "failed" else "")
            for user in (self.rep, self.manager):
                with self.subTest(status=status, user=user.username):
                    self.login(user)
                    response, html = self.page(deal)
                    self.chip(response, "chip", "ERP link not configured")
                    self.assertIsNone(self.send_form(deal, html))
