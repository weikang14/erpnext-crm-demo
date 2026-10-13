"""Every page renders for a rep and for the manager on the full demo data set."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from sales.models import Account, Lead, Opportunity, Quote
from sales.tests.base import make_user


class PageSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())

    def pages(self, user):
        deal = Opportunity.objects.filter(owner=user).first() or Opportunity.objects.first()
        quote = Quote.objects.filter(opportunity__owner=user).first() or Quote.objects.first()
        lead = Lead.objects.filter(owner=user).first() or Lead.objects.first()
        return [
            reverse("home"), reverse("pipeline"), reverse("leads"), reverse("lead_new"), reverse("lead", args=[lead.pk]),
            reverse("accounts"), reverse("account_new"), reverse("account", args=[Account.objects.first().pk]),
            reverse("opportunities"), reverse("opportunities") + "?stage=all&quarter=2026-Q4",
            reverse("opportunity", args=[deal.pk]), reverse("quote", args=[quote.pk]), reverse("reports"),
            reverse("reports") + "?quarter=2026-Q3", reverse("enquiry"),
        ]  # fmt: skip

    def test_rep_pages(self):
        siti = Opportunity.objects.filter(owner__username="siti").first().owner
        self.client.force_login(siti)
        for url in self.pages(siti):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_manager_pages(self):
        from django.contrib.auth.models import User

        hafiz = User.objects.get(username="hafiz")
        self.client.force_login(hafiz)
        for url in self.pages(hafiz) + [reverse("approvals"), reverse("pipeline") + "?region=south"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_user_without_records(self):
        self.client.force_login(make_user("newbie", "north"))
        for url in (reverse("home"), reverse("pipeline"), reverse("leads"), reverse("opportunities"), reverse("reports")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
