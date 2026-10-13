import re
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse

from sales.models import MANAGER_GROUP, Lead
from sales.regions import Region
from sales.tests.base import PASSWORD, CRMTestCase

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


class AccessTests(CRMTestCase):
    def test_other_reps_lead_is_404(self):  # SEC-1
        lead = Lead.objects.create(company="Kumar's", contact_name="X", state="Selangor", owner=self.kumar)
        self.assertEqual(self.client.get(reverse("lead", args=[lead.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("lead_convert", args=[lead.pk]), {}).status_code, 404)
        self.assertEqual(self.client.post(reverse("lead_disqualify", args=[lead.pk]), {"reason": "x"}).status_code, 404)

    def test_state_changes_are_post_only(self):  # SEC-5
        deal = self.deal()
        lead = Lead.objects.create(company="X", contact_name="Y", state="Johor", owner=self.rep)
        quote = self.quote(deal)
        urls = [
            reverse("opportunity_move", args=[deal.pk]), reverse("opportunity_won", args=[deal.pk]),
            reverse("opportunity_lost", args=[deal.pk]), reverse("opportunity_quote_new", args=[deal.pk]),
            reverse("lead_convert", args=[lead.pk]), reverse("lead_disqualify", args=[lead.pk]),
            reverse("quote_line_add", args=[quote.pk]), reverse("quote_action", args=[quote.pk, "submit"]),
            reverse("activity_add", args=["opportunity", deal.pk]), reverse("account_contact_add", args=[deal.account_id]),
        ]  # fmt: skip
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_csrf_on_crm_actions(self):  # SEC-3
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.rep)
        deal = self.deal()
        self.assertEqual(strict.post(reverse("opportunity_move", args=[deal.pk]), {"stage": "technical"}).status_code, 403)


class AdminUserTests(CRMTestCase):
    """The manager onboards reps in /admin/ but never hands out admin rights or touches a superuser."""

    NEW_PASSWORD = "Ombak-onboard-2026!"

    def setUp(self):
        self.login(self.manager)

    @staticmethod
    def user_form(user, **extra):
        return {
            "username": user.username, "first_name": user.first_name, "last_name": user.last_name, "email": user.email,
            "is_active": "on", "date_joined_0": "2026-01-02", "date_joined_1": "09:00:00", **extra,
        }  # fmt: skip

    def add_user(self, username):
        pw = self.NEW_PASSWORD
        data = {"username": username, "usable_password": "true", "password1": pw, "password2": pw}
        self.assertEqual(self.client.post("/admin/auth/user/add/", data).status_code, 302)
        return User.objects.get(username=username)

    def test_manager_cannot_grant_admin_rights(self):  # SEC-6
        root = User.objects.create_superuser("root", password=PASSWORD)
        group = Group.objects.get(name=MANAGER_GROUP)
        grants = {
            "is_staff": "on", "is_superuser": "on", "groups": [group.pk],
            "user_permissions": [Permission.objects.get(codename="delete_user").pk],
        }  # fmt: skip
        for user in (self.manager, self.rep, self.add_user("newboss")):
            self.client.post(f"/admin/auth/user/{user.pk}/change/", self.user_form(user, **grants))
        self.assertEqual(list(User.objects.filter(is_superuser=True)), [root])
        self.assertEqual(set(User.objects.filter(is_staff=True)), {root, self.manager})
        self.assertEqual(list(group.user_set.all()), [self.manager])
        self.assertFalse(User.user_permissions.through.objects.exists())
        # a superuser's account is off limits: no edits, no password reset
        response = self.client.post(f"/admin/auth/user/{root.pk}/change/", self.user_form(root, username="taken"))
        self.assertEqual(response.status_code, 403)
        pw = self.NEW_PASSWORD
        response = self.client.post(f"/admin/auth/user/{root.pk}/password/", {"password1": pw, "password2": pw})
        self.assertEqual(response.status_code, 403)
        root.refresh_from_db()
        self.assertEqual(root.username, "root")
        self.assertTrue(root.check_password(PASSWORD))

    def test_manager_onboards_and_deactivates_reps(self):  # ADM-2
        farid = self.add_user("farid")
        response = self.client.post("/admin/sales/salesrep/add/", {"user": farid.pk, "region": Region.SOUTH, "active": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(farid.rep.region, Region.SOUTH)
        data = self.user_form(self.kumar, last_name="Raj", is_active="")
        self.assertEqual(self.client.post(f"/admin/auth/user/{self.kumar.pk}/change/", data).status_code, 302)
        self.kumar.refresh_from_db()
        self.assertEqual((self.kumar.last_name, self.kumar.is_active), ("Raj", False))


class ErrorPageTests(CRMTestCase):
    def test_database_error_shows_friendly_500(self):  # UI-2
        client = Client(raise_request_exception=False)
        client.force_login(self.rep)
        with mock.patch("sales.views.leads.LeadFilter.apply", side_effect=DatabaseError("relation sales_lead is locked")):
            response = client.get(reverse("leads"))
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Something went wrong", status_code=500)
        self.assertNotContains(response, "Traceback", status_code=500)
        self.assertNotContains(response, "sales_lead", status_code=500)

    def test_not_found_page(self):
        response = self.client.get("/deals/999999/")
        self.assertContains(response, "belongs to another sales rep", status_code=404)


class TemplateHygieneTests(CRMTestCase):
    def test_no_inline_styles_or_scripts(self):  # UI-3 (the CSP would block them anyway)
        for path in TEMPLATES.rglob("*.html"):
            html = path.read_text(encoding="utf-8")
            with self.subTest(template=path.name):
                self.assertNotRegex(html, r"\sstyle=")
                self.assertNotRegex(html, r"<script(?![^>]*\ssrc=)")
                self.assertIsNone(re.search(r"\son[a-z]+=", html))  # no inline event handlers
