"""Demo data for Ombak Metal Works: the sales team, ERPNext's products, customers, leads, deals, quotes, activities.

Safe to run again: people and master data are matched by name, and deals, leads, quotes and
activities are only generated when there are no deals yet. Dates are relative to today, so
the reports always have a current quarter to show. Same random seed, same data.
"""

import os
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from sales import rules
from sales.models import (
    MANAGER_GROUP, Account, Activity, Contact, Industry, Lead, LostReason, Opportunity, Product, Quote,
    QuoteLine, SalesRep, Stage, StageChange,
)  # fmt: skip
from sales.regions import Region, region_of

DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Sales@2026")  # local demo only, documented in the README

# username: (first name, last name, region; None = the sales manager)
TEAM = {
    "hafiz": ("Hafiz", "Rahman", None),
    "aisyah": ("Nur", "Aisyah", Region.NORTH),
    "kumar": ("Kumar", "Selvam", Region.CENTRAL),
    "jason": ("Jason", "Lee", Region.CENTRAL),
    "siti": ("Siti", "Hajar", Region.SOUTH),
    "weiling": ("Wei Ling", "Tan", Region.SINGAPORE),
}

# the ERPNext finished goods: same item codes and selling rates (ERP/apps/ombak_mfg/ombak_mfg/setup/masters.py)
PRODUCTS = {
    "FG-CT-300": ("Cable Tray 300mm x 2.4m", "85"),
    "FG-MG-1200": ("Machine Guard Panel 1200x1000", "520"),
    "FG-WB-150": ("Wall Bracket 150mm", "18"),
    "FG-PR-UP3": ("Pallet Rack Upright 3m", "310"),
    "FG-EBF-1000": ("Equipment Base Frame 1000x800", "1450"),
}

LOST_REASONS = [
    "Price too high", "Lead time too long", "Lost to competitor", "Specification not met",
    "Project cancelled or delayed", "No response from customer",
]  # fmt: skip

# name: (state, city, industry, contact, job title); the first five are ERPNext's customers
ACCOUNTS = {
    "Tanjung Electrical Contractors Sdn Bhd": ("Johor", "Johor Bahru", Industry.ELECTRICAL, "Azman Yusof", "Project Manager"),
    "Kulai Food Processing Sdn Bhd": ("Johor", "Kulai", Industry.FOOD, "Lim Mei Fong", "Plant Engineer"),
    "Seri Alam Logistics Sdn Bhd": ("Johor", "Pasir Gudang", Industry.LOGISTICS, "Ravi Chandran", "Warehouse Manager"),
    "Mutiara Automation Sdn Bhd": ("Selangor", "Shah Alam", Industry.AUTOMATION, "Chong Kah Wai", "Purchasing Executive"),
    "Harbourline Packaging Pte Ltd": ("Singapore", "Singapore", Industry.PACKAGING, "Grace Ong", "Operations Lead"),
    "Prai Precision Engineering Sdn Bhd": ("Penang", "Prai", Industry.AUTOMATION, "Teoh Boon Huat", "Engineering Manager"),
    "Kedah Rice Mill Machinery Sdn Bhd": ("Kedah", "Alor Setar", Industry.FOOD, "Rosli Ahmad", "Maintenance Head"),
    "Ipoh Cold Storage Sdn Bhd": ("Perak", "Ipoh", Industry.LOGISTICS, "Wong Siew Lan", "Facilities Manager"),
    "Klang Port Warehousing Sdn Bhd": ("Selangor", "Port Klang", Industry.LOGISTICS, "Suresh Nair", "Site Manager"),
    "Bangsar Fit-Out Contractors Sdn Bhd": ("Kuala Lumpur", "Kuala Lumpur", Industry.CONSTRUCTION, "Farah Idris", "Quantity Surveyor"),
    "Nilai Pharma Packaging Sdn Bhd": ("Negeri Sembilan", "Nilai", Industry.PACKAGING, "Dr. Tan Hui Min", "Plant Manager"),
    "Kuantan Palm Equipment Sdn Bhd": ("Pahang", "Kuantan", Industry.FOOD, "Zulkifli Hassan", "Procurement Officer"),
    "Melaka Glove Automation Sdn Bhd": ("Melaka", "Ayer Keroh", Industry.AUTOMATION, "Ng Chee Keong", "Automation Lead"),
    "Senai Data Centre Builders Sdn Bhd": ("Johor", "Senai", Industry.ELECTRICAL, "Priya Menon", "MEP Coordinator"),
    "Tuas Marine Fabrication Pte Ltd": ("Singapore", "Singapore", Industry.CONSTRUCTION, "Daniel Koh", "Yard Manager"),
    "Jurong Food Hub Pte Ltd": ("Singapore", "Singapore", Industry.FOOD, "Siti Rahimah", "Facility Engineer"),
}  # fmt: skip

# (title, product, qty range)
DEAL_KINDS = [
    ("Cable trays for {site}", "FG-CT-300", (40, 400)),
    ("Machine guards for {site}", "FG-MG-1200", (4, 30)),
    ("Wall brackets for {site}", "FG-WB-150", (200, 2000)),
    ("Pallet rack uprights for {site}", "FG-PR-UP3", (20, 120)),
    ("Equipment base frames for {site}", "FG-EBF-1000", (2, 12)),
]
SITES = ["plant 2 expansion", "the new warehouse", "production line 3", "the office fit-out", "the cold room",
         "the packing hall", "data hall B", "the service workshop", "the mezzanine", "line 1 upgrade"]  # fmt: skip
DISCOUNTS = ["0", "0", "0", "5", "7.5", "10", "12.5", "15"]

# (company, contact, email, state, source, interest, status)
LEADS = [
    ("Butterworth Cable Systems Sdn Bhd", "Lee Chun Wah", "chunwah@butterworth-cable.example", "Penang", Lead.Source.WEBSITE, "Cable trays, 300 mm, about 200 lengths", Lead.Status.NEW),
    ("Cyberjaya Server Rooms Sdn Bhd", "Hidayah Kamal", "hidayah@cj-serverrooms.example", "Selangor", Lead.Source.WEBSITE, "Cable trays and wall brackets for 2 server rooms", Lead.Status.NEW),
    ("Batu Pahat Furniture Works Sdn Bhd", "Goh Swee Lin", "swee.lin@bpfurniture.example", "Johor", Lead.Source.PHONE, "Machine guards for 6 panel saws", Lead.Status.NEW),
    ("Woodlands Precision Pte Ltd", "Marcus Tan", "marcus@woodlands-precision.example", "Singapore", Lead.Source.REFERRAL, "Base frames for CNC machines", Lead.Status.NEW),
    ("Seremban Auto Parts Sdn Bhd", "Kavitha Raj", "kavitha@sap-auto.example", "Negeri Sembilan", Lead.Source.TRADE_SHOW, "Pallet racking for finished goods store", Lead.Status.NEW),
    ("Taiping Rubber Products Sdn Bhd", "Ismail Bakar", "ismail@taiping-rubber.example", "Perak", Lead.Source.EMAIL, "Guarding for 3 mixers", Lead.Status.CONTACTED),
    ("Muar Ice Plant Sdn Bhd", "Yap Kok Leong", "kl.yap@muarice.example", "Johor", Lead.Source.WALK_IN, "Cold room racking", Lead.Status.CONTACTED),
    ("Petaling Print Hub Sdn Bhd", "Aaron Fernandez", "aaron@pphub.example", "Selangor", Lead.Source.WEBSITE, "Machine guards for a folding line", Lead.Status.CONTACTED),
    ("Kota Bharu Bakery Supplies", "Wan Nurul", "wan.nurul@kbbakery.example", "Kelantan", Lead.Source.PHONE, "Wall brackets, small quantity", Lead.Status.DISQUALIFIED),
    ("Sentosa Events Pte Ltd", "Jolene Lim", "jolene@sentosa-events.example", "Singapore", Lead.Source.WEBSITE, "One-off stage frame", Lead.Status.DISQUALIFIED),
]  # fmt: skip


class Command(BaseCommand):
    help = "Load the Ombak Metal Works demo sales data (idempotent)."

    def handle(self, *args, **options):
        with transaction.atomic():
            team = self.team()
            self.masters()
            if Opportunity.objects.exists():
                self.stdout.write("Demo deals already loaded; team and master data checked.")
                return
            Generator(team).run()
        self.stdout.write(self.style.SUCCESS(f"Demo data loaded. Demo password: {DEMO_PASSWORD}"))

    def team(self):
        group = Group.objects.get(name=MANAGER_GROUP)
        team = {}
        for username, (first, last, region) in TEAM.items():
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "last_name": last, "is_staff": region is None}
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            if region is None:
                user.groups.add(group)
            else:
                SalesRep.objects.get_or_create(user=user, defaults={"region": region})
            team[username] = user
        return team

    def masters(self):
        for code, (name, price) in PRODUCTS.items():
            Product.objects.get_or_create(item_code=code, defaults={"name": name, "list_price": Decimal(price)})
        for name in LOST_REASONS:
            LostReason.objects.get_or_create(name=name)


class Generator:
    """Deals, quotes, activities and leads spread over the last five quarters."""

    def __init__(self, team):
        self.rng = random.Random(2026)
        self.team = team
        self.reps = {region: [u for u in team.values() if hasattr(u, "rep") and u.rep.region == region] for region in Region}
        self.manager = team["hafiz"]
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.products = {p.item_code: p for p in Product.objects.all()}
        self.reasons = list(LostReason.objects.all())

    def at(self, days_ago, hour=10):
        day = self.today - timedelta(days=days_ago)
        return timezone.make_aware(datetime.combine(day, time(hour, self.rng.randrange(0, 60, 5))))

    def owner_for(self, state, index):
        reps = self.reps[region_of(state)]
        return reps[index % len(reps)]

    def run(self):
        deals = []
        for index, (name, (state, city, industry, contact, job)) in enumerate(ACCOUNTS.items()):
            owner = self.owner_for(state, index)
            slug = name.split()[0].lower()
            account = Account.objects.create(
                name=name, state=state, city=city, industry=industry, owner=owner,
                phone=f"+65 6{index:03d} 4400" if state == "Singapore" else f"+60 3-5{index:03d} 8800",
                created_at=self.at(450),
            )  # fmt: skip
            person = Contact.objects.create(
                account=account, name=contact, job_title=job, email=f"{contact.split()[0].lower()}@{slug}.example"
            )
            for _ in range(self.rng.choice([2, 3, 3, 4])):
                deals.append(self.deal(account, person, owner))
        self.pending_approvals(deals)
        self.leads(deals)

    def deal(self, account, contact, owner):
        title, code, (low, high) = self.rng.choice(DEAL_KINDS)
        product = self.products[code]
        qty = Decimal(self.rng.randrange(low, high + 1, 2 if high < 50 else 10))
        discount = Decimal(self.rng.choice(DISCOUNTS))
        amount = rules.line_total(qty, product.list_price, discount)
        outcome = self.rng.choices(["won", "lost", "open"], weights=[30, 20, 50])[0]

        if outcome == "open":
            created_ago = self.rng.randint(5, 120)
            stage = self.rng.choices(rules.OPEN_STAGES, weights=[30, 25, 25, 20])[0]
            expected = self.today + timedelta(days=self.rng.randint(-10, 100))
            closed_at = None
        else:
            # some close in the current quarter so far, so the default report view is never empty
            quarter_start = self.today.replace(month=(self.today.month - 1) // 3 * 3 + 1, day=1)
            recent = self.rng.random() < 0.3
            closed_ago = self.rng.randint(0, (self.today - quarter_start).days) if recent else self.rng.randint(3, 420)
            created_ago = closed_ago + self.rng.randint(20, 90)
            stage = Stage.WON if outcome == "won" else Stage.LOST
            closed_at = self.at(closed_ago, 16)
            expected = closed_at.date()
        deal = Opportunity.objects.create(
            title=title.format(site=self.rng.choice(SITES)), account=account, contact=contact, owner=owner,
            stage=stage, amount=amount, expected_close=expected, closed_at=closed_at, created_at=self.at(created_ago, 9),
            last_activity_at=closed_at or self.at(self.rng.choice([0, 1, 2, 3, 5, 8, 12, 16, 20, 25])),
        )  # fmt: skip
        StageChange.objects.create(opportunity=deal, from_stage="", to_stage=Stage.ENQUIRY, by=owner, at=deal.created_at)
        if stage != Stage.ENQUIRY:
            moved = closed_at or deal.created_at + timedelta(days=self.rng.randint(2, 10))
            StageChange.objects.create(opportunity=deal, from_stage=Stage.ENQUIRY, to_stage=stage, by=owner, at=min(moved, self.now))

        quoted = stage in (Stage.QUOTATION, Stage.NEGOTIATION, Stage.WON) or (stage == Stage.LOST and self.rng.random() < 0.6)
        if quoted:
            status = {Stage.WON: Quote.Status.ACCEPTED, Stage.LOST: Quote.Status.DECLINED}.get(stage, Quote.Status.SENT)
            self.quote(deal, product, qty, discount, status)
        if stage == Stage.LOST:
            deal.lost_reason = self.rng.choice(self.reasons)
            deal.save(update_fields=["lost_reason"])
        if deal.is_open:
            self.activities(deal)
        return deal

    def quote(self, deal, product, qty, discount, status):
        created = min(deal.created_at + timedelta(days=self.rng.randint(3, 12)), self.now)
        if status == Quote.Status.PENDING:  # waiting for the manager now, so still valid
            created = self.now - timedelta(days=self.rng.randint(0, 2))
        quote = Quote.objects.create(
            opportunity=deal, status=status, created_by=deal.owner, created_at=created,
            valid_until=created.date() + timedelta(days=Quote.VALID_DAYS),
            sent_at=created if status != Quote.Status.PENDING else None,
        )  # fmt: skip
        if status != Quote.Status.PENDING and discount > rules.APPROVAL_LIMIT:
            quote.approved_by, quote.approved_at = self.manager, created
            quote.save(update_fields=["approved_by", "approved_at"])
        QuoteLine.objects.create(quote=quote, product=product, qty=qty, unit_price=product.list_price, discount_pct=discount)
        return quote

    def activities(self, deal):
        owner = deal.owner
        Activity.objects.create(
            opportunity=deal, owner=owner, kind=Activity.Kind.CALL, subject="Intro call: drawings and quantities",
            done=True, done_at=deal.created_at + timedelta(hours=3), created_at=deal.created_at,
        )  # fmt: skip
        plan = self.rng.choices(["overdue", "today", "future", "none"], weights=[20, 20, 40, 20])[0]
        if plan == "none":
            return
        due = {"overdue": -self.rng.randint(1, 6), "today": 0, "future": self.rng.randint(1, 14)}[plan]
        kind, subject = self.rng.choice([
            (Activity.Kind.VISIT, "Site visit: measure cable routes"),
            (Activity.Kind.CALL, "Follow-up call with the buyer"),
            (Activity.Kind.MEETING, "Technical meeting with the plant engineer"),
            (Activity.Kind.TASK, "Send revised drawings"),
            (Activity.Kind.EMAIL, "Email sample photos"),
        ])  # fmt: skip
        Activity.objects.create(
            opportunity=deal, owner=owner, kind=kind, subject=subject, due_date=self.today + timedelta(days=due)
        )

    def pending_approvals(self, deals):
        """Two open deals with a quote over the 10 % limit, waiting for the manager."""
        candidates = [d for d in deals if d.stage in (Stage.ENQUIRY, Stage.TECHNICAL)][:2]
        for deal, code, qty, discount in zip(candidates, ["FG-MG-1200", "FG-PR-UP3"], ["12", "60"], ["12.5", "15"]):
            self.quote(deal, self.products[code], Decimal(qty), Decimal(discount), Quote.Status.PENDING)

    def leads(self, deals):
        for index, (company, person, email, state, source, interest, status) in enumerate(LEADS):
            owner = None if source == Lead.Source.TRADE_SHOW else self.owner_for(state, index)
            lead = Lead.objects.create(
                company=company, contact_name=person, email=email, state=state, source=source, interest=interest,
                status=status, owner=owner, created_at=self.at(self.rng.randint(0, 20), 11),
                disqualify_reason="Order too small for a fabrication job" if status == Lead.Status.DISQUALIFIED else "",
            )  # fmt: skip
            if status == Lead.Status.CONTACTED:
                Activity.objects.create(
                    lead=lead, owner=owner, kind=Activity.Kind.CALL, subject="First call: needs and timeline",
                    done=True, done_at=lead.created_at + timedelta(hours=2), created_at=lead.created_at,
                )  # fmt: skip
        # three open deals came from leads that were converted
        for deal in [d for d in deals if d.is_open][:3]:
            Lead.objects.create(
                company=deal.account.name, contact_name=deal.contact.name, email=deal.contact.email,
                state=deal.account.state, source=Lead.Source.WEBSITE, status=Lead.Status.CONVERTED,
                owner=deal.owner, opportunity=deal, created_at=deal.created_at - timedelta(days=2),
            )  # fmt: skip
