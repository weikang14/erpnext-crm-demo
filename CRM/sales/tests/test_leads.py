from django.test import Client
from django.urls import reverse

from sales.models import Account, Contact, Lead, Opportunity, SalesRep
from sales.tests.base import CRMTestCase

ENQUIRY = {
    "company": "Shah Alam Panel Builders Sdn Bhd", "contact_name": "Rahim", "email": "rahim@sapb.example",
    "phone": "", "state": "Selangor", "interest": "Cable trays", "notes": "", "website": "",
}  # fmt: skip


def lead(owner, company="Muar Ice Plant Sdn Bhd", **extra):
    return Lead.objects.create(company=company, contact_name="Yap", state=extra.pop("state", "Johor"), owner=owner, **extra)


class LeadFormTests(CRMTestCase):
    def test_rep_owns_the_lead_they_type(self):  # LEAD-1
        data = {"company": "Pontian Fish Farm", "contact_name": "Ali", "email": "ali@pff.example", "state": "Johor",
                "source": "phone", "interest": "", "notes": ""}  # fmt: skip
        response = self.client.post(reverse("lead_new"), data)
        created = Lead.objects.get(company="Pontian Fish Farm")
        self.assertRedirects(response, reverse("lead", args=[created.pk]), fetch_redirect_response=False)
        self.assertEqual((created.owner, created.region, created.status), (self.rep, "south", "new"))

    def test_email_or_phone_required(self):  # LEAD-2
        response = self.client.post(reverse("lead_new"), {"company": "X", "contact_name": "Y", "state": "Johor", "source": "phone"})
        self.assertContains(response, "Give an email or a phone number")
        self.assertFalse(Lead.objects.exists())

    def test_manager_without_owner_assigns_by_region(self):
        self.login(self.manager)
        data = {"company": "Alor Gajah Tiles", "contact_name": "Lim", "phone": "06-555", "state": "Melaka",
                "source": "phone", "owner": ""}  # fmt: skip
        self.client.post(reverse("lead_new"), data)
        self.assertEqual(Lead.objects.get().owner, self.siti)


class EnquiryTests(CRMTestCase):
    def setUp(self):
        self.client = Client()  # the public form, signed out

    def post(self, **changes):
        return self.client.post(reverse("enquiry"), ENQUIRY | changes)

    def test_form_is_public(self):  # ENQ-6
        self.assertEqual(self.client.get(reverse("enquiry")).status_code, 200)

    def test_goes_to_rep_with_fewest_open_leads(self):  # ENQ-1
        lead(self.kumar, state="Selangor")
        lead(self.kumar, company="B", state="Selangor")
        lead(self.jason, company="C", state="Selangor")
        lead(self.jason, company="D", state="Selangor", status=Lead.Status.CONVERTED)  # closed leads don't count
        response = self.post()
        self.assertRedirects(response, reverse("enquiry_thanks"))
        created = Lead.objects.get(company=ENQUIRY["company"])
        self.assertEqual((created.owner, created.source), (self.jason, "website"))

    def test_tie_goes_to_lower_id(self):  # ENQ-2
        lead(self.kumar, state="Selangor")
        lead(self.jason, company="B", state="Selangor")
        self.post()
        self.assertEqual(Lead.objects.get(company=ENQUIRY["company"]).owner, self.kumar)

    def test_no_active_rep_leaves_it_unassigned(self):  # ENQ-3
        SalesRep.objects.filter(user=self.weiling).update(active=False)
        self.post(state="Singapore")
        created = Lead.objects.get(company=ENQUIRY["company"])
        self.assertIsNone(created.owner)
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("home")), ENQUIRY["company"])
        self.client.force_login(self.weiling)
        self.assertNotContains(self.client.get(reverse("home")), ENQUIRY["company"])

    def test_honeypot_saves_nothing(self):  # ENQ-4
        response = self.post(website="http://spam.example")
        self.assertRedirects(response, reverse("enquiry_thanks"))
        self.assertFalse(Lead.objects.exists())

    def test_rate_limited_per_address(self):  # ENQ-5
        for i in range(5):
            self.post(company=f"Company {i}")
        response = self.post(company="Company 6")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(Lead.objects.count(), 5)

    def test_email_required_and_no_account_hints(self):  # FM8: same answer whether or not the email is known
        self.assertContains(self.post(email=""), "This field is required")
        Contact.objects.create(account=self.account(), name="Known", email=ENQUIRY["email"])
        self.assertRedirects(self.post(), reverse("enquiry_thanks"))


class DuplicateAndConvertTests(CRMTestCase):
    def test_duplicate_account_name(self):  # DUP-1
        self.account("Mutiara Automation Sdn Bhd", "Selangor")
        record = lead(self.rep, company="mutiara automation sdn bhd")
        response = self.client.get(reverse("lead", args=[record.pk]))
        self.assertContains(response, "Possible duplicates")
        self.assertContains(response, "Account <a")

    def test_duplicate_email(self):  # DUP-2
        Contact.objects.create(account=self.account(), name="Grace", email="grace@x.example")
        lead(self.rep, company="Other", email="GRACE@x.example")
        record = lead(self.rep, company="Third", email="grace@x.example")
        response = self.client.get(reverse("lead", args=[record.pk]))
        self.assertContains(response, "has the same email", count=2)

    def convert(self, record, **extra):
        data = {"title": "Cold room racking", "amount": "12000", "expected_close": "2026-12-15", "account": ""} | extra
        return self.client.post(reverse("lead_convert", args=[record.pk]), data)

    def test_convert_with_new_account(self):  # CONV-1
        record = lead(self.rep, email="yap@muar.example")
        response = self.convert(record)
        deal = Opportunity.objects.get()
        self.assertRedirects(response, reverse("opportunity", args=[deal.pk]), fetch_redirect_response=False)
        record.refresh_from_db()
        self.assertEqual((record.status, record.opportunity), ("converted", deal))
        self.assertEqual((deal.stage, deal.owner, deal.account.name), ("enquiry", self.rep, "Muar Ice Plant Sdn Bhd"))
        self.assertEqual(deal.contact.email, "yap@muar.example")

    def test_convert_into_existing_account(self):  # CONV-2
        existing = self.account("Muar Ice Plant Sdn Bhd")
        self.convert(lead(self.rep), account=existing.pk)
        self.assertEqual(Account.objects.count(), 1)
        self.assertEqual(Opportunity.objects.get().account, existing)

    def test_new_account_refused_when_name_exists(self):
        self.account("Muar Ice Plant Sdn Bhd")
        response = self.convert(lead(self.rep))
        self.assertContains(response, "already exists: pick it", status_code=400)
        self.assertFalse(Opportunity.objects.exists())

    def test_convert_twice(self):  # CONV-3
        record = lead(self.rep)
        self.convert(record)
        response = self.convert(record)
        self.assertEqual(Opportunity.objects.count(), 1)
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("lead", args=[record.pk])), "already converted")

    def test_disqualify_needs_reason(self):  # DISQ-1, AC20: the error sits by the field and the input is kept
        record = lead(self.rep)
        url = reverse("lead_disqualify", args=[record.pk])
        response = self.client.post(url, {"reason": ""})
        self.assertContains(response, '<p class="error" id="id_reason_error">This field is required.</p>', html=True, status_code=400)
        self.assertContains(response, 'aria-describedby="id_reason_error"', status_code=400)
        too_long = "Wants stainless " * 13  # 208 characters
        self.assertContains(self.client.post(url, {"reason": too_long}), f'value="{too_long}"', status_code=400)
        record.refresh_from_db()
        self.assertEqual(record.status, "new")
        self.assertRedirects(self.client.post(url, {"reason": "Wants stainless, we don't do it"}), record.get_absolute_url())
        record.refresh_from_db()
        self.assertEqual((record.status, record.disqualify_reason), ("disqualified", "Wants stainless, we don't do it"))


class LeadListTests(CRMTestCase):
    def test_filters(self):  # LL-1
        lead(self.rep, company="Johor Match", email="buyer@jm.example")
        lead(self.rep, company="Johor Other", email="x@other.example")
        lead(self.rep, company="Old one", email="buyer@old.example", status=Lead.Status.DISQUALIFIED)
        response = self.client.get(reverse("leads"), {"status": "new", "region": "south", "q": "buyer@"})
        self.assertEqual([l.company for l in response.context["page"].object_list], ["Johor Match"])

    def test_rep_sees_only_own_leads(self):  # SEC-1 for lists
        lead(self.kumar, company="Kumar's lead", state="Selangor")
        self.assertNotContains(self.client.get(reverse("leads")), "Kumar&#x27;s lead")

    def test_only_manager_reassigns(self):  # LL-2
        record = lead(self.rep)
        self.assertEqual(self.client.post(reverse("lead_assign", args=[record.pk]), {"owner": self.kumar.pk}).status_code, 403)
        self.login(self.manager)
        self.client.post(reverse("lead_assign", args=[record.pk]), {"owner": self.kumar.pk})
        record.refresh_from_db()
        self.assertEqual(record.owner, self.kumar)

    def test_reassign_error_sits_by_the_field(self):  # AC20
        record = lead(self.rep)
        SalesRep.objects.filter(user=self.kumar).update(active=False)
        self.login(self.manager)
        url = reverse("lead_assign", args=[record.pk])
        response = self.client.post(url, {"owner": self.kumar.pk})
        error = '<p class="error" id="id_owner_error">Select a valid choice. That choice is not one of the available choices.</p>'
        self.assertContains(response, error, html=True, status_code=400)
        self.assertContains(response, 'aria-describedby="id_owner_error"', status_code=400)
        record.refresh_from_db()
        self.assertEqual(record.owner, self.rep)
        self.assertRedirects(self.client.post(url, {"owner": self.jason.pk}), record.get_absolute_url())

    def test_unassigned_filter_for_manager(self):
        lead(None, company="Nobody's")
        lead(self.rep, company="Siti's")
        self.login(self.manager)
        response = self.client.get(reverse("leads"), {"owner": "none"})
        self.assertEqual([l.company for l in response.context["page"].object_list], ["Nobody's"])

    def test_list_empty_states(self):  # UI-1
        self.assertContains(self.client.get(reverse("leads")), "No leads yet")
        self.assertContains(self.client.get(reverse("leads"), {"q": "zzz"}), "No leads match")


class LeadEditTests(CRMTestCase):
    def edit(self, record, follow=False, **changes):
        data = {"company": record.company, "contact_name": record.contact_name, "email": record.email,
                "phone": record.phone, "state": record.state, "source": record.source, "interest": record.interest,
                "notes": record.notes, **changes}  # fmt: skip
        return self.client.post(reverse("lead_edit", args=[record.pk]), data, follow=follow)

    def test_new_state_moves_the_region_not_the_owner(self):  # EDIT-6
        record = lead(self.rep, email="yap@mip.example")
        page = reverse("lead", args=[record.pk])
        self.assertContains(self.client.get(page), f'href="{reverse("lead_edit", args=[record.pk])}"')
        self.assertRedirects(self.edit(record, state="Penang"), page)
        record.refresh_from_db()
        self.assertEqual((record.state, record.region, record.owner, record.status), ("Penang", "north", self.rep, "new"))
        self.assertContains(self.client.get(page), "North (Penang)")

    def test_posted_owner_is_ignored(self):  # AC7: only reassign changes the owner
        record = lead(self.rep, email="yap@mip.example")
        for user in (self.rep, self.manager):
            with self.subTest(user=user.username):
                self.login(user)
                self.assertNotIn("owner", self.client.get(reverse("lead_edit", args=[record.pk])).context["form"].fields)
                self.edit(record, owner=self.kumar.pk, interest=f"Edited by {user.username}")
                record.refresh_from_db()
                self.assertEqual((record.interest, record.owner), (f"Edited by {user.username}", self.rep))

    def test_other_reps_lead_is_404(self):  # EDIT-7
        record = lead(self.kumar, state="Selangor", email="yap@mip.example")
        self.assertEqual(self.client.get(reverse("lead_edit", args=[record.pk])).status_code, 404)
        self.assertEqual(self.edit(record, company="Mine now").status_code, 404)

    def test_converted_and_disqualified_leads_are_read_only(self):  # EDIT-7
        for status in (Lead.Status.CONVERTED, Lead.Status.DISQUALIFIED):
            for user in (self.rep, self.manager):
                with self.subTest(status=status, user=user.username):
                    self.login(user)
                    record = lead(self.rep, company=f"{status} {user.username}", email="yap@mip.example", status=status)
                    page = reverse("lead", args=[record.pk])
                    self.assertNotContains(self.client.get(page), reverse("lead_edit", args=[record.pk]))
                    self.assertRedirects(self.client.get(reverse("lead_edit", args=[record.pk])), page)
                    response = self.edit(record, company="changed", follow=True)
                    self.assertContains(response, f"This lead is already {status.label.lower()}.")
                    record.refresh_from_db()
                    self.assertEqual((record.company, record.status), (f"{status} {user.username}", status))

    def test_field_errors(self):  # AC20
        record = lead(self.rep, email="yap@mip.example")
        response = self.edit(record, company="", email="", phone="")
        self.assertContains(response, '<p class="error" id="id_company_error">This field is required.</p>', html=True)
        self.assertContains(response, 'id="id_email_error"')
        record.refresh_from_db()
        self.assertEqual((record.company, record.email), ("Muar Ice Plant Sdn Bhd", "yap@mip.example"))

