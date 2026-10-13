from datetime import date

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from sales import rules
from sales.models import Account, Activity, Contact, Lead, LostReason, Opportunity, Product, Stage, display_name
from sales.regions import Region, states_in


class DateInput(forms.DateInput):
    input_type = "date"


def active_reps():
    return User.objects.filter(is_active=True, rep__active=True).order_by("first_name", "username")


class RepChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return f"{display_name(user)} ({user.rep.get_region_display()})"


# --- leads -------------------------------------------------------------------------------------


class LeadForm(forms.ModelForm):
    owner = RepChoiceField(
        queryset=active_reps().select_related("rep"), required=False, empty_label="Assign by region",
        help_text="Left empty, the lead goes to the rep for its region with the fewest open leads.",
    )  # fmt: skip

    class Meta:
        model = Lead
        fields = ["company", "contact_name", "email", "phone", "state", "source", "interest", "notes", "owner"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, manager=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not manager or self.instance.pk:
            del self.fields["owner"]  # a rep's own leads are theirs; after creation only reassign moves a lead (AC7)

    def clean(self):
        data = super().clean()
        if not data.get("email") and not data.get("phone"):
            self.add_error("email", "Give an email or a phone number so someone can reply.")
        return data


class EnquiryForm(forms.ModelForm):
    """The public web form. `website` is a honeypot: people never see it, bots fill it in."""

    website = forms.CharField(required=False, label="Leave this empty")

    class Meta:
        model = Lead
        fields = ["company", "contact_name", "email", "phone", "state", "interest", "notes"]
        labels = {"contact_name": "Your name", "interest": "What do you need?", "notes": "Details"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["website"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})

    @property
    def is_bot(self):
        return bool(self.data.get("website"))


class ConvertForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.all(), required=False, empty_label="Create a new account from this lead",
        help_text="Pick the account if this company already buys from us.",
    )  # fmt: skip
    title = forms.CharField(label="Deal title", max_length=200)
    amount = forms.DecimalField(label="Estimated value (MYR)", min_value=0, max_digits=12, decimal_places=2)
    expected_close = forms.DateField(widget=DateInput)

    def __init__(self, *args, lead, **kwargs):
        super().__init__(*args, **kwargs)
        self.lead = lead
        existing = Account.objects.filter(name__iexact=lead.company).first()
        self.fields["account"].initial = existing
        self.fields["title"].initial = lead.interest[:200] or f"Enquiry from {lead.company}"

    def clean(self):
        data = super().clean()
        if not data.get("account") and Account.objects.filter(name__iexact=self.lead.company).exists():
            self.add_error("account", f"An account named {self.lead.company} already exists: pick it.")
        return data


class ReasonForm(forms.Form):
    reason = forms.CharField(label="Why is this lead disqualified?", max_length=200)


class AssignForm(forms.Form):
    owner = RepChoiceField(queryset=active_reps().select_related("rep"), label="Assign to", empty_label=None)


class LeadFilter(forms.Form):
    STATUS = [("open", "Open"), ("all", "All")] + list(Lead.Status.choices)
    status = forms.ChoiceField(choices=STATUS, required=False)
    owner = forms.ChoiceField(required=False)
    region = forms.ChoiceField(choices=[("", "All regions")] + list(Region.choices), required=False)
    q = forms.CharField(label="Search", required=False, max_length=100)

    def __init__(self, data, manager=False):
        data = data.copy()
        data.setdefault("status", "open")
        super().__init__(data)
        if manager:
            people = [(str(u.pk), display_name(u)) for u in active_reps()]
            self.fields["owner"].choices = [("", "Anyone"), ("none", "Unassigned")] + people
        else:
            del self.fields["owner"]
        self.fields["q"].widget.attrs["placeholder"] = "Company, contact or email"

    def apply(self, qs):
        if not self.is_valid():
            return qs.filter(status__in=Lead.OPEN)
        data = self.cleaned_data
        if data["status"] == "open":
            qs = qs.filter(status__in=Lead.OPEN)
        elif data["status"] != "all":
            qs = qs.filter(status=data["status"])
        if data.get("owner") == "none":
            qs = qs.filter(owner__isnull=True)
        elif data.get("owner"):
            qs = qs.filter(owner_id=data["owner"])
        if data["region"]:
            qs = qs.filter(state__in=states_in(data["region"]))
        if data["q"]:
            q = data["q"]
            qs = qs.filter(Q(company__icontains=q) | Q(contact_name__icontains=q) | Q(email__icontains=q))
        return qs

    @property
    def narrowed(self):
        data = self.cleaned_data if self.is_valid() else {}
        return any(data.get(k) for k in ("owner", "region", "q")) or data.get("status") not in (None, "open")


# --- accounts and activities -------------------------------------------------------------------


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "registration_no", "industry", "address", "city", "state", "postcode", "phone", "website"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Account.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this name already exists.")
        return name


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "job_title", "email", "phone"]


class DealForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["title", "contact", "amount", "expected_close"]
        labels = {"amount": "Estimated value (MYR)"}
        widgets = {"expected_close": DateInput}

    def __init__(self, *args, account, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].queryset = account.contacts.all()
        if self.instance.pk and self.instance.sent_quote():  # sending a quote sets the value (AC16)
            self.fields["amount"].disabled = True
            self.fields["amount"].help_text = "Set by the sent quote. Revise the quote to change it."


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["kind", "subject", "due_date", "done", "notes"]
        labels = {"done": "Already done (log it)", "due_date": "Due"}
        widgets = {"due_date": DateInput, "notes": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        data = super().clean()
        if data.get("kind") == Activity.Kind.NOTE:
            data["done"] = True  # a note is a record, never a to-do
        if not data.get("done") and not data.get("due_date"):
            self.add_error("due_date", "Pick a due date, or tick \"Already done\".")
        return data


# --- deals ---------------------------------------------------------------------------------------


class MoveForm(forms.Form):
    stage = forms.ChoiceField(choices=[(s, Stage(s).label) for s in rules.OPEN_STAGES], label="Move to")


class LostForm(forms.Form):
    reason = forms.ModelChoiceField(queryset=LostReason.objects.filter(active=True), label="Lost reason")
    note = forms.CharField(max_length=300, required=False, label="What happened?")


def quarter_of(day):
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


def quarter_bounds(text):
    """'2026-Q4' -> (date(2026, 10, 1), date(2026, 12, 31)); ValueError for anything else."""
    year, q = text.split("-Q")
    year, q = int(year), int(q)
    if not (2000 <= year <= 2100 and 1 <= q <= 4):
        raise ValueError(text)
    start = date(year, 3 * q - 2, 1)
    end = date(year + 1, 1, 1) if q == 4 else date(year, 3 * q + 1, 1)
    return start, date.fromordinal(end.toordinal() - 1)


def quarter_choices(today, back=5, ahead=2):
    """Recent and coming quarters, newest first."""
    index = today.year * 4 + (today.month - 1) // 3
    return [(f"{i // 4}-Q{i % 4 + 1}", f"Q{i % 4 + 1} {i // 4}") for i in range(index + ahead, index - back - 1, -1)]


class DealFilter(forms.Form):
    STAGE = [("open", "Open"), ("all", "All"), ("closed", "Won and lost")] + list(Stage.choices)
    stage = forms.ChoiceField(choices=STAGE, required=False)
    owner = forms.ChoiceField(required=False)
    region = forms.ChoiceField(choices=[("", "All regions")] + list(Region.choices), required=False)
    quarter = forms.ChoiceField(required=False, label="Closing in")
    q = forms.CharField(label="Search", required=False, max_length=100)

    def __init__(self, data, today, manager=False):
        data = data.copy()
        data.setdefault("stage", "open")
        super().__init__(data)
        self.fields["quarter"].choices = [("", "Any time")] + quarter_choices(today)
        if manager:
            self.fields["owner"].choices = [("", "Anyone")] + [(str(u.pk), display_name(u)) for u in active_reps()]
        else:
            del self.fields["owner"]
        self.fields["q"].widget.attrs["placeholder"] = "Deal or account"

    def apply(self, qs):
        if not self.is_valid():
            return qs.filter(stage__in=rules.OPEN_STAGES)
        data = self.cleaned_data
        stage = data["stage"]
        if stage == "open":
            qs = qs.filter(stage__in=rules.OPEN_STAGES)
        elif stage == "closed":
            qs = qs.filter(stage__in=[rules.WON, rules.LOST])
        elif stage != "all":
            qs = qs.filter(stage=stage)
        if data.get("owner"):
            qs = qs.filter(owner_id=data["owner"])
        if data["region"]:
            qs = qs.filter(account__state__in=states_in(data["region"]))
        if data["quarter"]:
            start, end = quarter_bounds(data["quarter"])
            qs = qs.filter(expected_close__range=(start, end))
        if data["q"]:
            qs = qs.filter(Q(title__icontains=data["q"]) | Q(account__name__icontains=data["q"]))
        return qs

    @property
    def narrowed(self):
        data = self.cleaned_data if self.is_valid() else {}
        return any(data.get(k) for k in ("owner", "region", "quarter", "q")) or data.get("stage") not in (None, "open")


# --- quotes --------------------------------------------------------------------------------------


class QuoteLineForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(active=True), empty_label="Pick a product")
    qty = forms.DecimalField(label="Quantity", min_value=0.01, max_digits=10, decimal_places=2)
    discount_pct = forms.DecimalField(
        label="Discount %", min_value=0, max_value=100, max_digits=5, decimal_places=2, initial=0,
        help_text=f"Above {rules.APPROVAL_LIMIT:g} % the sales manager has to approve the quote.",
    )  # fmt: skip


class DecisionForm(forms.Form):
    note = forms.CharField(label="Note to the rep", max_length=300, required=False)

    def __init__(self, *args, require_note=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].required = require_note
