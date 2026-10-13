from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone

from sales.models import MANAGER_GROUP, Account, LostReason, Opportunity, Product, Quote, SalesRep
from sales.regions import Region

PASSWORD = "pw-for-tests-only"


def make_user(username, region=None, manager=False):
    user = User.objects.create_user(username, password=PASSWORD, first_name=username.title())
    if region:
        SalesRep.objects.create(user=user, region=region)
    if manager:
        user.groups.add(Group.objects.get_or_create(name=MANAGER_GROUP)[0])
        user.is_staff = True
        user.save()
    return user


class CRMTestCase(TestCase):
    """Manager Hafiz; reps Aisyah (North), Kumar and Jason (Central), Siti (South), Wei Ling (Singapore)."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_user("hafiz", manager=True)
        cls.aisyah = make_user("aisyah", Region.NORTH)
        cls.kumar = make_user("kumar", Region.CENTRAL)
        cls.jason = make_user("jason", Region.CENTRAL)
        cls.siti = make_user("siti", Region.SOUTH)
        cls.weiling = make_user("weiling", Region.SINGAPORE)
        cls.rep = cls.siti
        cls.tray = Product.objects.create(item_code="FG-CT-300", name="Cable Tray 300mm x 2.4m", list_price=Decimal("85"))
        cls.frame = Product.objects.create(
            item_code="FG-EBF-1000", name="Equipment Base Frame 1000x800", list_price=Decimal("1450")
        )
        cls.price_reason = LostReason.objects.create(name="Price too high")
        cls.lead_time_reason = LostReason.objects.create(name="Lead time too long")

    def setUp(self):
        self.client.force_login(self.rep)

    def login(self, user):
        self.client.force_login(user)

    @staticmethod
    def account(name="Tanjung Electrical Contractors Sdn Bhd", state="Johor", owner=None):
        return Account.objects.get_or_create(name=name, defaults={"state": state, "owner": owner})[0]

    def deal(self, owner=None, stage="enquiry", amount="1000", close_in_days=30, account=None, **extra):
        return Opportunity.objects.create(
            title=extra.pop("title", "Cable trays for plant 2"),
            account=account or self.account(),
            owner=owner or self.rep,
            stage=stage,
            amount=Decimal(amount),
            expected_close=extra.pop("expected_close", timezone.localdate() + timedelta(days=close_in_days)),
            **extra,
        )

    def quote(self, deal, lines=((None, "10", "0"),), status=Quote.Status.DRAFT, by=None):
        """lines: (product or None for the cable tray, qty, discount %). Created as a draft, then status forced."""
        quote = Quote.start(deal, by or deal.owner)
        for product, qty, discount in lines:
            quote.add_line(product or self.tray, Decimal(qty), Decimal(discount))
        if status != Quote.Status.DRAFT:
            Quote.objects.filter(pk=quote.pk).update(status=status)
            quote.refresh_from_db()
        return quote
