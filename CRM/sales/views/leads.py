from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from sales import access
from sales.forms import ActivityForm, AssignForm, ConvertForm, LeadFilter, LeadForm, ReasonForm
from sales.models import Account, Contact, Lead, display_name, is_manager
from sales.regions import pick_owner
from sales.rules import RuleError
from sales.views import page_of


@login_required
def lead_list(request):
    filters = LeadFilter(request.GET, manager=is_manager(request.user))
    leads = filters.apply(access.leads(request.user))
    return render(request, "sales/leads/list.html", {"filters": filters, "page": page_of(request, leads)})


@login_required
def lead_new(request):
    manager = is_manager(request.user)
    form = LeadForm(request.POST if request.method == "POST" else None, manager=manager)
    if form.is_valid():
        lead = form.save(commit=False)
        if not manager:
            lead.owner = request.user
        elif not lead.owner:
            lead.owner = pick_owner(lead.region)
        lead.save()
        messages.success(request, f"Lead saved and assigned to {display_name(lead.owner)}.")
        return redirect("lead", lead.pk)
    return render(request, "sales/leads/form.html", {"form": form})


def duplicates(lead):
    """Accounts with the same name, and contacts or other open leads with the same email."""
    found = {"accounts": Account.objects.filter(name__iexact=lead.company)}
    if lead.email:
        found["contacts"] = Contact.objects.filter(email__iexact=lead.email).select_related("account")
        found["leads"] = Lead.objects.filter(email__iexact=lead.email, status__in=Lead.OPEN).exclude(pk=lead.pk)
    return {name: list(qs) for name, qs in found.items() if qs.exists()}


def detail_context(request, lead, **forms):
    context = {
        "lead": lead,
        "duplicates": duplicates(lead),
        "activities": lead.activities.select_related("owner"),
        "activity_form": ActivityForm(),
    }
    if lead.is_open:
        context |= {"convert_form": ConvertForm(lead=lead), "reason_form": ReasonForm()}
        if is_manager(request.user):
            context["assign_form"] = AssignForm(initial={"owner": lead.owner})
    return context | forms


@login_required
def lead_detail(request, pk):
    lead = access.get(access.leads, request.user, pk)
    return render(request, "sales/leads/detail.html", detail_context(request, lead))


@login_required
def lead_edit(request, pk):
    lead = access.get(access.leads, request.user, pk)
    if not lead.is_open:
        messages.error(request, f"This lead is already {lead.get_status_display().lower()}.")
        return redirect(lead)
    form = LeadForm(request.POST if request.method == "POST" else None, instance=lead)
    if not form.is_valid():
        return render(request, "sales/leads/form.html", {"lead": lead, "form": form})
    try:
        lead.edit(**form.cleaned_data)
        messages.success(request, f"{lead.company} saved.")
    except RuleError as error:
        messages.error(request, str(error))
    return redirect(lead)


@login_required
@require_POST
def lead_convert(request, pk):
    lead = access.get(access.leads, request.user, pk)
    if not lead.is_open:  # a second click on Convert; the model also refuses it under a row lock
        messages.error(request, f"This lead is already {lead.get_status_display().lower()}.")
        return redirect("lead", lead.pk)
    form = ConvertForm(request.POST, lead=lead)
    if not form.is_valid():
        return render(request, "sales/leads/detail.html", detail_context(request, lead, convert_form=form), status=400)
    try:
        deal = lead.convert(request.user, **{k: form.cleaned_data[k] for k in ("title", "amount", "expected_close", "account")})
    except RuleError as error:
        messages.error(request, str(error))
        return redirect("lead", lead.pk)
    messages.success(request, f"{lead.company} is now a deal in Enquiry.")
    return redirect("opportunity", deal.pk)


@login_required
@require_POST
def lead_disqualify(request, pk):
    lead = access.get(access.leads, request.user, pk)
    if not lead.is_open:  # a closed lead's page has no disqualify form to show the error on
        messages.error(request, f"This lead is already {lead.get_status_display().lower()}.")
        return redirect("lead", lead.pk)
    form = ReasonForm(request.POST)
    if not form.is_valid():
        return render(request, "sales/leads/detail.html", detail_context(request, lead, reason_form=form), status=400)
    try:
        lead.disqualify(form.cleaned_data["reason"])
        messages.success(request, f"{lead.company} disqualified.")
    except RuleError as error:
        messages.error(request, str(error))
    return redirect("lead", lead.pk)


@access.manager_required
@require_POST
def lead_assign(request, pk):
    lead = access.get(access.leads, request.user, pk)
    if not lead.is_open:
        messages.error(request, f"This lead is already {lead.get_status_display().lower()}.")
        return redirect("lead", lead.pk)
    form = AssignForm(request.POST)
    if not form.is_valid():
        return render(request, "sales/leads/detail.html", detail_context(request, lead, assign_form=form), status=400)
    lead.owner = form.cleaned_data["owner"]
    lead.save(update_fields=["owner"])
    messages.success(request, f"{lead.company} assigned to {display_name(lead.owner)}.")
    return redirect("lead", lead.pk)


def unassigned(user):
    return Lead.objects.filter(owner__isnull=True, status__in=Lead.OPEN) if is_manager(user) else Lead.objects.none()

