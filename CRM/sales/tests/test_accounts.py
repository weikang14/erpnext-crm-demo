from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from sales.models import Account, Activity, Contact, Lead, Opportunity
from sales.tests.base import CRMTestCase


class AccountTests(CRMTestCase):
    def test_account_page(self):  # ACC-1
        account = self.account()
        self.deal(title="Siti's deal", account=account)
        self.deal(owner=self.kumar, title="Kumar's deal", account=account)
        response = self.client.post(
            reverse("account_contact_add", args=[account.pk]),
            {"name": "Azman", "job_title": "PM", "email": "azman@t.example", "phone": ""}, follow=True,
        )  # fmt: skip
        self.assertContains(response, "Azman")
        self.assertContains(response, "Siti&#x27;s deal")
        self.assertNotContains(response, "Kumar&#x27;s deal")  # a rep sees only their own deals, even on a shared account

    def test_new_account_and_duplicate_name(self):
        data = {"name": "Gelang Patah Steel", "state": "Johor", "registration_no": "", "industry": "", "address": "",
                "city": "", "postcode": "", "phone": "", "website": ""}  # fmt: skip
        self.client.post(reverse("account_new"), data)
        self.assertEqual(Account.objects.get().owner, self.rep)
        response = self.client.post(reverse("account_new"), data | {"name": "gelang patah steel"})
        self.assertContains(response, "already exists")
        self.assertEqual(Account.objects.count(), 1)

    def test_new_deal_from_account(self):
        account = self.account()
        response = self.client.post(
            reverse("account_deal_new", args=[account.pk]),
            {"title": "Repeat order", "contact": "", "amount": "4200", "expected_close": "2026-11-30"},
        )  # fmt: skip
        deal = Opportunity.objects.get()
        self.assertRedirects(response, reverse("opportunity", args=[deal.pk]), fetch_redirect_response=False)
        self.assertEqual((deal.owner, deal.stage, deal.history.get().to_stage), (self.rep, "enquiry", "enquiry"))


class AccountEditTests(CRMTestCase):
    def edit(self, account, **changes):
        data = {"name": account.name, "registration_no": account.registration_no, "industry": account.industry,
                "address": account.address, "city": account.city, "state": account.state, "postcode": account.postcode,
                "phone": account.phone, "website": account.website, **changes}  # fmt: skip
        return self.client.post(reverse("account_edit", args=[account.pk]), data)

    def test_any_rep_edits_a_shared_account(self):  # AC24
        account = self.account(owner=self.kumar)
        page = reverse("account", args=[account.pk])
        self.assertContains(self.client.get(page), f'href="{reverse("account_edit", args=[account.pk])}"')
        renamed = "TANJUNG Electrical Contractors Sdn Bhd"  # its own name in another case is fine
        self.assertRedirects(self.edit(account, name=renamed, city="Muar"), page)
        account.refresh_from_db()
        self.assertEqual((account.name, account.city, account.owner), (renamed, "Muar", self.kumar))

    def test_rename_to_another_accounts_name(self):  # EDIT-8
        self.account("Penang Packaging Sdn Bhd", "Penang")
        account = self.account()
        response = self.edit(account, name="PENANG packaging sdn bhd", city="Muar")
        error = '<p class="error" id="id_name_error">An account with this name already exists.</p>'
        self.assertContains(response, error, html=True)
        account.refresh_from_db()
        self.assertEqual((account.name, account.city), ("Tanjung Electrical Contractors Sdn Bhd", ""))

    def test_edit_contact_from_account_page(self):  # EDIT-9
        account = self.account()
        contact = Contact.objects.create(account=account, name="Azman", job_title="PM", email="azman@t.example")
        page = reverse("account", args=[account.pk])
        url = reverse("account_contact_edit", args=[account.pk, contact.pk])
        self.assertContains(self.client.get(page), f'href="{url}"')
        data = {"name": "Azman", "job_title": "PM", "email": "azman@t.example", "phone": "012-345 6789"}
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, page)
        self.assertContains(response, "012-345 6789")
        contact.refresh_from_db()
        self.assertEqual((contact.phone, contact.account), ("012-345 6789", account))

    def test_contact_of_another_account_is_404(self):
        stranger = Contact.objects.create(account=self.account("Penang Packaging Sdn Bhd", "Penang"), name="Stranger")
        url = reverse("account_contact_edit", args=[self.account().pk, stranger.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"name": "Mine now"}).status_code, 404)
        stranger.refresh_from_db()
        self.assertEqual(stranger.name, "Stranger")


class ActivityTests(CRMTestCase):
    def test_log_a_call_touches_the_deal(self):  # ACT-1
        deal = self.deal(last_activity_at=timezone.now() - timedelta(days=20))
        self.client.post(
            reverse("activity_add", args=["opportunity", deal.pk]),
            {"kind": "call", "subject": "Called the buyer", "done": "on", "due_date": "", "notes": ""},
        )  # fmt: skip
        deal.refresh_from_db()
        self.assertTrue(Activity.objects.get().done)
        self.assertFalse(deal.is_stale())

    def test_schedule_then_done(self):  # ACT-2
        deal = self.deal()
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.client.post(reverse("activity_add", args=["opportunity", deal.pk]),
                         {"kind": "visit", "subject": "Measure site", "due_date": tomorrow.isoformat()})  # fmt: skip
        activity = Activity.objects.get()
        self.assertFalse(activity.done)
        self.client.post(reverse("activity_done", args=[activity.pk]), {"next": "/"})
        activity.refresh_from_db()
        self.assertTrue(activity.done)
        self.assertIsNotNone(activity.done_at)

    def test_planned_activity_needs_a_date(self):  # AC20: the error sits by the field and the input is kept
        deal = self.deal()
        lead = Lead.objects.create(company="X", contact_name="Y", state="Johor", owner=self.rep)
        # an open activity on each page, so its Mark done form is shown
        Activity.objects.create(opportunity=deal, owner=self.rep, subject="Open", due_date=timezone.localdate())
        Activity.objects.create(lead=lead, owner=self.rep, subject="Open", due_date=timezone.localdate())
        error = '<p class="error" id="id_due_date_error">Pick a due date, or tick "Already done".</p>'
        for parent, record in (("opportunity", deal), ("lead", lead), ("account", deal.account)):
            with self.subTest(parent=parent):
                url, page = reverse("activity_add", args=[parent, record.pk]), record.get_absolute_url()
                response = self.client.post(url, {"kind": "task", "subject": "Ring the buyer"})
                self.assertContains(response, error, html=True, status_code=400)
                self.assertContains(response, 'aria-describedby="id_due_date_error"', status_code=400)
                self.assertContains(response, 'value="Ring the buyer"', status_code=400)
                self.assertContains(response, f'name="next" value="{page}"', status_code=400)  # not the POST-only url
                self.assertEqual(Activity.objects.filter(subject="Ring the buyer").count(), 0)
                valid = {"kind": "task", "subject": "Ring the buyer", "due_date": timezone.localdate().isoformat()}
                self.assertRedirects(self.client.post(url, valid), page)
                Activity.objects.filter(subject="Ring the buyer").delete()

    def test_other_reps_activity_is_hidden(self):  # ACT-3
        other = self.deal(owner=self.kumar)
        activity = Activity.objects.create(opportunity=other, owner=self.kumar, subject="Kumar's call",
                                           due_date=timezone.localdate())  # fmt: skip
        self.assertEqual(self.client.post(reverse("activity_done", args=[activity.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("activity_add", args=["opportunity", other.pk]),
                                          {"kind": "note", "subject": "x"}).status_code, 404)  # fmt: skip

    def test_done_redirect_stays_on_site(self):
        deal = self.deal()
        activity = Activity.objects.create(opportunity=deal, owner=self.rep, subject="x", due_date=timezone.localdate())
        response = self.client.post(reverse("activity_done", args=[activity.pk]), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("opportunity", args=[deal.pk]), fetch_redirect_response=False)

    def test_activity_on_lead_marks_contacted(self):
        lead = Lead.objects.create(company="X", contact_name="Y", state="Johor", owner=self.rep)
        self.client.post(reverse("activity_add", args=["lead", lead.pk]), {"kind": "call", "subject": "Hi", "done": "on"})
        lead.refresh_from_db()
        self.assertEqual(lead.status, "contacted")

    def test_unknown_parent_is_404(self):
        self.assertEqual(self.client.post(reverse("activity_add", args=["quote", 1]), {}).status_code, 404)
