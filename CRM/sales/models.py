from datetime import timedelta

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from sales import rules
from sales.regions import Region, State, region_of
from sales.rules import RuleError

MANAGER_GROUP = "Sales Manager"
SEND_STALE_AFTER = timedelta(minutes=2)  # a `sending` claim older than this is taken to have died (AC15)
STALE_SEND = "The last send didn't finish; send it again."


def is_manager(user):
    if not user.is_authenticated:
        return False
    if not hasattr(user, "_is_manager"):
        user._is_manager = user.is_superuser or user.groups.filter(name=MANAGER_GROUP).exists()
    return user._is_manager


def display_name(user):
    return (user.get_full_name() or user.username) if user else "Unassigned"


class SalesRep(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="rep")
    region = models.CharField(max_length=20, choices=Region.choices)
    active = models.BooleanField(default=True, help_text="Inactive reps get no new web enquiries.")

    class Meta:
        verbose_name = "sales rep"

    def __str__(self):
        return f"{display_name(self.user)} ({self.get_region_display()})"


class Industry(models.TextChoices):
    ELECTRICAL = "electrical", "Electrical contractor"
    FOOD = "food", "Food processing"
    LOGISTICS = "logistics", "Logistics and warehousing"
    AUTOMATION = "automation", "Automation and machinery"
    PACKAGING = "packaging", "Packaging"
    CONSTRUCTION = "construction", "Construction"
    OTHER = "other", "Other"


class Account(models.Model):
    name = models.CharField(max_length=200)
    registration_no = models.CharField("SSM / UEN no.", max_length=30, blank=True)
    industry = models.CharField(max_length=20, choices=Industry.choices, blank=True)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=30, choices=State.choices)
    postcode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    owner = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name="accounts")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="account_name_unique_ci")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("account", args=[self.pk])

    @property
    def region(self):
        return region_of(self.state)

    @property
    def country(self):
        return "Singapore" if self.state == State.SINGAPORE else "Malaysia"


class Contact(models.Model):
    account = models.ForeignKey(Account, models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=120)
    job_title = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LostReason(models.Model):
    name = models.CharField(max_length=80, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    item_code = models.CharField("ERPNext item code", max_length=40, unique=True)
    name = models.CharField(max_length=140)
    uom = models.CharField("unit", max_length=20, default="Nos")
    list_price = models.DecimalField("list price (MYR)", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["item_code"]

    def __str__(self):
        return f"{self.item_code} {self.name}"


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CONVERTED = "converted", "Converted"
        DISQUALIFIED = "disqualified", "Disqualified"

    class Source(models.TextChoices):
        WEBSITE = "website", "Website enquiry"
        PHONE = "phone", "Phone"
        EMAIL = "email", "Email"
        TRADE_SHOW = "trade_show", "Trade show"
        REFERRAL = "referral", "Referral"
        WALK_IN = "walk_in", "Walk-in"

    OPEN = [Status.NEW, Status.CONTACTED]

    company = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    state = models.CharField(max_length=30, choices=State.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.PHONE)
    interest = models.CharField("product interest", max_length=200, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    disqualify_reason = models.CharField(max_length=200, blank=True)
    owner = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name="leads")
    opportunity = models.OneToOneField("Opportunity", models.SET_NULL, null=True, blank=True, related_name="lead")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self):
        return f"{self.company} ({self.contact_name})"

    def get_absolute_url(self):
        return reverse("lead", args=[self.pk])

    @property
    def region(self):
        return region_of(self.state)

    @property
    def is_open(self):
        return self.status in self.OPEN

    def _locked(self):
        lead = Lead.objects.select_for_update().get(pk=self.pk)
        if not lead.is_open:
            raise RuleError(f"This lead is already {lead.get_status_display().lower()}.")
        return lead

    @transaction.atomic
    def convert(self, by, title, amount, expected_close, account=None):
        """Create the contact and an Enquiry deal (and the account unless one is given). Returns the deal."""
        lead = self._locked()  # a double submit waits here, then finds the lead converted
        owner = lead.owner or by
        if account is None:
            account = Account.objects.create(name=lead.company, state=lead.state, phone=lead.phone, owner=owner)
        contact = Contact.objects.create(account=account, name=lead.contact_name, email=lead.email, phone=lead.phone)
        deal = Opportunity.objects.create(
            title=title, account=account, contact=contact, owner=owner, amount=amount, expected_close=expected_close
        )
        StageChange.objects.create(opportunity=deal, from_stage="", to_stage=deal.stage, by=by)
        lead.status, lead.opportunity, lead.owner = Lead.Status.CONVERTED, deal, owner
        lead.save(update_fields=["status", "opportunity", "owner"])
        self.refresh_from_db()
        return deal

    @transaction.atomic
    def edit(self, **fields):
        """An open lead's details (AC24). The region follows the state; the owner changes only by reassign (AC7)."""
        lead = self._locked()  # an edit racing Convert or Disqualify waits here, then finds the lead closed
        for name, value in fields.items():
            setattr(lead, name, value)
        lead.save(update_fields=list(fields))
        self.refresh_from_db()

    @transaction.atomic
    def disqualify(self, reason):
        lead = self._locked()
        lead.status, lead.disqualify_reason = Lead.Status.DISQUALIFIED, reason
        lead.save(update_fields=["status", "disqualify_reason"])
        self.refresh_from_db()


class Stage(models.TextChoices):
    ENQUIRY = rules.ENQUIRY, "Enquiry"
    TECHNICAL = rules.TECHNICAL, "Technical review / sampling"
    QUOTATION = rules.QUOTATION, "Quotation"
    NEGOTIATION = rules.NEGOTIATION, "Negotiation"
    WON = rules.WON, "Won"
    LOST = rules.LOST, "Lost"


class Opportunity(models.Model):
    class ErpStatus(models.TextChoices):
        NOT_SENT = "not_sent", "Not sent"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=200)
    account = models.ForeignKey(Account, models.PROTECT, related_name="opportunities")
    contact = models.ForeignKey(Contact, models.SET_NULL, null=True, blank=True, related_name="+")
    owner = models.ForeignKey(User, models.PROTECT, related_name="opportunities")
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.ENQUIRY)
    amount = models.DecimalField("value (MYR)", max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    expected_close = models.DateField()
    lost_reason = models.ForeignKey(LostReason, models.PROTECT, null=True, blank=True, related_name="+")
    lost_note = models.CharField(max_length=300, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    delivery_date = models.DateField("requested delivery date", null=True, blank=True)
    erp_status = models.CharField("ERP order", max_length=10, choices=ErpStatus.choices, default=ErpStatus.NOT_SENT)
    # not unique: ERPNext names orders per site; its unique crm_reference is the duplicate guard (AC11, AC13)
    erp_order = models.CharField("ERPNext sales order", max_length=140, null=True, blank=True)
    erp_error = models.TextField(blank=True)
    erp_attempted_at = models.DateTimeField("last ERP send", null=True, blank=True)

    class Meta:
        verbose_name_plural = "opportunities"
        ordering = ["expected_close", "pk"]
        indexes = [models.Index(fields=["owner", "stage"]), models.Index(fields=["stage", "expected_close"])]
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0), name="opportunity_amount_not_negative")]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("opportunity", args=[self.pk])

    @property
    def is_open(self):
        return self.stage in rules.OPEN_STAGES

    @property
    def probability(self):
        return rules.PROBABILITY[self.stage]

    @property
    def weighted_amount(self):
        return rules.weighted(self.amount, self.stage)

    def is_stale(self, now=None):
        now = now or timezone.now()
        return self.is_open and self.last_activity_at < now - timedelta(days=rules.STALE_DAYS)

    def sent_quote(self):
        return self.quotes.filter(status=Quote.Status.SENT).first()

    def _locked(self):
        return Opportunity.objects.select_for_update().get(pk=self.pk)

    def _set_stage(self, stage, by, **fields):
        StageChange.objects.create(opportunity=self, from_stage=self.stage, to_stage=stage, by=by)
        self.stage, self.last_activity_at = stage, timezone.now()
        for name, value in fields.items():
            setattr(self, name, value)
        self.save(update_fields=["stage", "last_activity_at", *fields])

    @transaction.atomic
    def move_to(self, stage, by):
        deal = self._locked()
        rules.check_move(deal.stage, stage, deal.sent_quote() is not None)
        if stage != deal.stage:
            deal._set_stage(stage, by)
        self.refresh_from_db()

    @transaction.atomic
    def mark_won(self, by, delivery_date=None):
        deal = self._locked()
        quote = deal.sent_quote()
        rules.check_won(deal.stage, quote is not None)
        quote.status = Quote.Status.ACCEPTED
        quote.save(update_fields=["status"])
        deal._set_stage(Stage.WON, by, amount=quote.total, closed_at=timezone.now(), delivery_date=delivery_date)
        self.refresh_from_db()

    def claim_send(self, now):
        """Take a won deal for one ERPNext send (AC15): one conditional UPDATE, only from not sent, failed, or a
        `sending` older than SEND_STALE_AFTER. Call it outside a transaction, so the claim is committed and no row
        lock is held while ERPNext answers. True if this call claimed it."""
        status = Opportunity.ErpStatus
        claimable = Q(erp_status=status.NOT_SENT) | Opportunity.erp_not_created(now)
        claimed = Opportunity.objects.filter(claimable, pk=self.pk, stage=Stage.WON).update(
            erp_status=status.SENDING, erp_attempted_at=now
        )
        if claimed:
            self.erp_status, self.erp_attempted_at = status.SENDING, now
        return bool(claimed)

    @staticmethod
    def erp_not_created(now):
        """Deals whose order didn't reach ERPNext and wants a resend (Clar.): failed sends, and `sending` claims older
        than SEND_STALE_AFTER, which died. A sent deal with a total mismatch is not one of them."""
        status = Opportunity.ErpStatus
        return Q(erp_status=status.FAILED) | Q(erp_status=status.SENDING, erp_attempted_at__lt=now - SEND_STALE_AFTER)

    def erp_state(self, now):
        """erp_status as the ERP panel shows it: a stale `sending` (as erp_not_created) is failed."""
        status = Opportunity.ErpStatus
        attempted = self.erp_attempted_at
        if self.erp_status == status.SENDING and attempted and attempted < now - SEND_STALE_AFTER:
            return status.FAILED
        return self.erp_status

    @property
    def erp_reason(self):
        """Why a failed or stale `sending` deal's order isn't in ERPNext."""
        return STALE_SEND if self.erp_status == Opportunity.ErpStatus.SENDING else self.erp_error

    def record_send(self, status, order="", error=""):
        """Store a send's outcome: a plain update of the ERP fields only, no lock (AC11). No order is stored as NULL."""
        self.erp_status, self.erp_order, self.erp_error = status, order or None, error
        self.save(update_fields=["erp_status", "erp_order", "erp_error"])

    @transaction.atomic
    def mark_lost(self, by, reason, note=""):
        deal = self._locked()
        if not deal.is_open:
            raise RuleError("This deal is closed.")
        deal.quotes.filter(status=Quote.Status.SENT).update(status=Quote.Status.DECLINED)
        deal._set_stage(Stage.LOST, by, lost_reason=reason, lost_note=note, closed_at=timezone.now())
        self.refresh_from_db()

    @transaction.atomic
    def edit(self, **fields):
        """Title, contact, expected close and value of an open deal (AC23). Once a quote is sent, it sets the value (AC16)."""
        deal = self._locked()  # an edit racing Won/Lost or Send waits here, then sees the outcome
        if not deal.is_open:
            raise RuleError("This deal is closed.")
        if fields.get("amount", deal.amount) != deal.amount and deal.sent_quote():
            raise RuleError("A quote has been sent, so the value comes from it. Revise the quote to change it.")
        for name, value in fields.items():
            setattr(deal, name, value)
        deal.save(update_fields=list(fields))
        self.refresh_from_db()

    @transaction.atomic
    def reassign(self, to):
        """Hand an open deal to another rep; the old owner's open activities on it go along, done ones stay (AC25)."""
        deal = self._locked()
        if not deal.is_open:
            raise RuleError("This deal is closed.")
        deal.activities.filter(owner=deal.owner, done=False).update(owner=to)
        deal.owner = to
        deal.save(update_fields=["owner"])
        self.refresh_from_db()


class StageChange(models.Model):
    opportunity = models.ForeignKey(Opportunity, models.CASCADE, related_name="history")
    from_stage = models.CharField(max_length=20, choices=Stage.choices, blank=True)
    to_stage = models.CharField(max_length=20, choices=Stage.choices)
    by = models.ForeignKey(User, models.SET_NULL, null=True, related_name="+")
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at", "-pk"]


class Activity(models.Model):
    class Kind(models.TextChoices):
        CALL = "call", "Call"
        MEETING = "meeting", "Meeting"
        VISIT = "visit", "Site visit"
        EMAIL = "email", "Email"
        TASK = "task", "Task"
        NOTE = "note", "Note"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CALL)
    subject = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    owner = models.ForeignKey(User, models.PROTECT, related_name="activities")
    lead = models.ForeignKey(Lead, models.CASCADE, null=True, blank=True, related_name="activities")
    opportunity = models.ForeignKey(Opportunity, models.CASCADE, null=True, blank=True, related_name="activities")
    account = models.ForeignKey(Account, models.CASCADE, null=True, blank=True, related_name="activities")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ["done", "due_date", "-created_at"]
        indexes = [models.Index(fields=["owner", "done", "due_date"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(lead__isnull=False, opportunity__isnull=True, account__isnull=True)
                    | Q(lead__isnull=True, opportunity__isnull=False, account__isnull=True)
                    | Q(lead__isnull=True, opportunity__isnull=True, account__isnull=False)
                ),
                name="activity_has_one_parent",
            ),
            models.CheckConstraint(condition=Q(done=True) | Q(due_date__isnull=False), name="planned_activity_has_due_date"),
        ]

    def __str__(self):
        return self.subject

    @property
    def parent(self):
        return self.opportunity or self.lead or self.account

    def touch_parent(self):
        """A logged activity counts as contact: it clears the stale flag and moves a new lead to Contacted."""
        if self.opportunity_id:
            Opportunity.objects.filter(pk=self.opportunity_id).update(last_activity_at=timezone.now())
        if self.lead_id and self.done and self.kind != self.Kind.NOTE:
            Lead.objects.filter(pk=self.lead_id, status=Lead.Status.NEW).update(status=Lead.Status.CONTACTED)

    def complete(self):
        if not self.done:
            self.done, self.done_at = True, timezone.now()
            self.save(update_fields=["done", "done_at"])
        self.touch_parent()


class Quote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        SUPERSEDED = "superseded", "Superseded"

    IN_PROGRESS = [Status.DRAFT, Status.PENDING, Status.APPROVED]
    PRINTABLE = [Status.APPROVED, Status.SENT, Status.ACCEPTED, Status.DECLINED, Status.SUPERSEDED]
    VALID_DAYS = 30

    opportunity = models.ForeignKey(Opportunity, models.CASCADE, related_name="quotes")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    valid_until = models.DateField()
    created_by = models.ForeignKey(User, models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(User, models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    revision = models.PositiveIntegerField(default=0, editable=False)  # moved on by every line or status change: see _lock

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.number

    @property
    def number(self):
        return f"QT-{timezone.localtime(self.created_at).year}-{self.pk:05d}"  # unique without a counter table

    @property
    def total(self):
        return rules.quote_total(self.lines.all())

    @property
    def needs_approval(self):
        return rules.needs_approval(self.lines.all())

    @property
    def editable(self):
        return self.status == self.Status.DRAFT and self.opportunity.is_open

    @classmethod
    @transaction.atomic
    def start(cls, deal, by):
        deal = deal._locked()  # a double click waits here, then finds the first draft
        if not deal.is_open:
            raise RuleError("This deal is closed.")
        current = deal.quotes.filter(status__in=cls.IN_PROGRESS).first()
        if current:
            raise RuleError(f"Finish {current.number} first.")
        return cls.objects.create(
            opportunity=deal, created_by=by, valid_until=timezone.localdate() + timedelta(days=cls.VALID_DAYS)
        )

    def _lock(self, seen=None):
        """Re-read this quote under a row lock: a line edit racing Submit waits, then sees the other's outcome (FM1).
        Every change starts here and moves the revision on; `seen` is the revision the user's page showed (AC15)."""
        self.opportunity._locked()  # the deal first, then the quote: the order the deal's own methods lock in
        self.refresh_from_db(from_queryset=Quote.objects.select_for_update())
        if seen is not None and str(seen) != str(self.revision):
            raise RuleError("This quote changed since you opened it; review it again.")
        self.revision += 1  # every caller is atomic, so a refused change takes this back with it
        self.save(update_fields=["revision"])

    @transaction.atomic
    def add_line(self, product, qty, discount_pct):
        """The unit price is always the product's list price: the discount is the only lever."""
        self._lock()
        if not self.editable:
            raise RuleError("Only a draft quote can be changed.")
        return self.lines.create(product=product, qty=qty, discount_pct=discount_pct, unit_price=product.list_price)

    @transaction.atomic
    def delete_line(self, pk):
        self._lock()
        if not self.editable:
            raise RuleError("Only a draft quote can be changed.")
        self.lines.filter(pk=pk).delete()

    def _require(self, *statuses, seen=None):
        self._lock(seen)
        if self.status not in statuses or not self.opportunity.is_open:
            raise RuleError(f"{self.number} is {self.get_status_display().lower()}; that can't be done now.")

    @transaction.atomic
    def submit(self, by, seen=None):
        self._require(self.Status.DRAFT, seen=seen)
        if not self.lines.exists():
            raise RuleError("Add at least one line first.")
        if self.needs_approval and not is_manager(by):
            self.status, self.decision_note = self.Status.PENDING, ""
        else:  # a manager's own quote needs no second signature
            self.status, self.approved_by, self.approved_at, self.decision_note = self.Status.APPROVED, by, timezone.now(), ""
        self.save()

    @transaction.atomic
    def approve(self, by, note="", seen=None):
        self._require(self.Status.PENDING, seen=seen)
        self.status, self.approved_by, self.approved_at, self.decision_note = self.Status.APPROVED, by, timezone.now(), note
        self.save()

    @transaction.atomic
    def reject(self, by, note):
        self._require(self.Status.PENDING)
        self.status, self.approved_by, self.approved_at, self.decision_note = self.Status.DRAFT, None, None, note
        self.save()

    @transaction.atomic
    def send(self, by):
        self._require(self.Status.APPROVED)
        if self.needs_approval and not (self.approved_by and is_manager(self.approved_by)):
            raise RuleError(f"{self.number} has a discount above {rules.APPROVAL_LIMIT} % and needs the sales manager's approval.")
        deal = self.opportunity._locked()
        deal.quotes.filter(status=self.Status.SENT).update(status=self.Status.SUPERSEDED)  # the revision replaces it
        self.status, self.sent_at = self.Status.SENT, timezone.now()
        self.save()
        if deal.stage in (Stage.ENQUIRY, Stage.TECHNICAL):
            deal._set_stage(Stage.QUOTATION, by, amount=self.total)
        else:
            deal.amount, deal.last_activity_at = self.total, timezone.now()
            deal.save(update_fields=["amount", "last_activity_at"])

    @transaction.atomic
    def revise(self, by):
        """A new draft with the same products and discounts at today's list prices; this one stays sent until it goes out."""
        self._require(self.Status.SENT)
        draft = Quote.start(self.opportunity, by)
        for line in self.lines.select_related("product"):
            draft.add_line(line.product, line.qty, line.discount_pct)
        return draft


class QuoteLine(models.Model):
    quote = models.ForeignKey(Quote, models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_pct = models.DecimalField(
        "discount %", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=Q(qty__gt=0), name="quote_line_qty_positive"),
            models.CheckConstraint(condition=Q(discount_pct__gte=0, discount_pct__lte=100), name="quote_line_discount_range"),
        ]

    @property
    def total(self):
        return rules.line_total(self.qty, self.unit_price, self.discount_pct)

    @property
    def needs_approval(self):
        return self.discount_pct > rules.APPROVAL_LIMIT


class RateLimit(models.Model):
    """One fixed-window counter for sales.ratelimit: sign-ins per username, enquiries per address."""

    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField(db_index=True)
