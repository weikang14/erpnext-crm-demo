from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from sales import access
from sales.forms import AccountForm, ActivityForm, ContactForm, DealForm
from sales.models import Account, Contact, StageChange
from sales.regions import Region, states_in
from sales.views import page_of


@login_required
def account_list(request):
    accounts = Account.objects.select_related("owner")
    q = request.GET.get("q", "").strip()[:100]
    region = request.GET.get("region", "")
    if q:
        accounts = accounts.filter(name__icontains=q)
    if region in Region.values:
        accounts = accounts.filter(state__in=states_in(region))
    context = {"page": page_of(request, accounts), "q": q, "region": region, "regions": Region.choices}
    return render(request, "sales/accounts/list.html", context)


@login_required
def account_new(request):
    form = AccountForm(request.POST if request.method == "POST" else None)
    if form.is_valid():
        account = form.save(commit=False)
        account.owner = request.user
        account.save()
        messages.success(request, f"{account.name} added.")
        return redirect("account", account.pk)
    return render(request, "sales/accounts/form.html", {"form": form})


def detail_context(request, account, **forms):
    deals = access.opportunities(request.user).filter(account=account)
    activities = access.activities(request.user).filter(Q(account=account) | Q(opportunity__account=account))
    return {
        "account": account,
        "contacts": account.contacts.all(),
        "open_deals": [d for d in deals if d.is_open],
        "closed_deals": [d for d in deals if not d.is_open],
        "activities": activities.select_related("owner", "opportunity")[:30],
        "activity_form": ActivityForm(),
        "contact_form": ContactForm(),
        "deal_form": DealForm(account=account),
    } | forms


@login_required
def account_detail(request, pk):
    account = get_object_or_404(Account, pk=pk)  # accounts are shared by the whole team
    return render(request, "sales/accounts/detail.html", detail_context(request, account))


@login_required
def account_edit(request, pk):
    account = get_object_or_404(Account, pk=pk)  # shared, so anyone signed in edits it (AC24)
    form = AccountForm(request.POST if request.method == "POST" else None, instance=account)
    if form.is_valid():
        form.save()
        messages.success(request, f"{account.name} saved.")
        return redirect(account)
    return render(request, "sales/accounts/form.html", {"account": account, "form": form})


@login_required
def contact_edit(request, pk, contact):
    contact = get_object_or_404(Contact.objects.select_related("account"), pk=contact, account_id=pk)
    form = ContactForm(request.POST if request.method == "POST" else None, instance=contact)
    if form.is_valid():
        form.save()
        messages.success(request, f"{contact.name} saved.")
        return redirect(contact.account)
    return render(request, "sales/accounts/contact_form.html", {"contact": contact, "form": form})


@login_required
@require_POST
def contact_add(request, pk):
    account = get_object_or_404(Account, pk=pk)
    form = ContactForm(request.POST)
    if not form.is_valid():
        return render(request, "sales/accounts/detail.html", detail_context(request, account, contact_form=form), status=400)
    form.instance.account = account
    form.save()
    messages.success(request, f"{form.instance.name} added to {account.name}.")
    return redirect("account", account.pk)


@login_required
@require_POST
def deal_new(request, pk):
    """A deal straight from an account: repeat customers don't come in as leads."""
    account = get_object_or_404(Account, pk=pk)
    form = DealForm(request.POST, account=account)
    if not form.is_valid():
        return render(request, "sales/accounts/detail.html", detail_context(request, account, deal_form=form), status=400)
    deal = form.save(commit=False)
    deal.account, deal.owner = account, request.user
    deal.save()
    StageChange.objects.create(opportunity=deal, from_stage="", to_stage=deal.stage, by=request.user)
    messages.success(request, f"Deal \"{deal.title}\" created in Enquiry.")
    return redirect("opportunity", deal.pk)
