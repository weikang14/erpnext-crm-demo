from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from sales import access
from sales.forms import ActivityForm
from sales.models import Account
from sales.views import accounts, back, leads, opportunities

# url part (also the Activity field): the records the user may add activities to, and the page that shows them
PARENTS = {
    "lead": (access.leads, "sales/leads/detail.html", leads.detail_context),
    "opportunity": (access.opportunities, "sales/deals/detail.html", opportunities.detail_context),
    "account": (lambda user: Account.objects.all(), "sales/accounts/detail.html", accounts.detail_context),  # shared by the team
}


@login_required
@require_POST
def activity_add(request, parent, pk):
    if parent not in PARENTS:
        raise Http404
    records, template, detail_context = PARENTS[parent]
    record = get_object_or_404(records(request.user), pk=pk)
    if getattr(record, "is_open", True) is False:
        messages.error(request, "This record is closed; activities can't be added.")
        return redirect(record)
    form = ActivityForm(request.POST)
    if not form.is_valid():
        return render(request, template, detail_context(request, record, activity_form=form), status=400)
    activity = form.save(commit=False)
    activity.owner = request.user
    setattr(activity, parent, record)
    if activity.done:
        activity.done_at = timezone.now()
    activity.save()
    activity.touch_parent()
    messages.success(request, f"{activity.get_kind_display()} {'logged' if activity.done else 'scheduled'}: {activity.subject}")
    return redirect(record)


@login_required
@require_POST
def activity_done(request, pk):
    activity = access.get(access.activities, request.user, pk)
    activity.complete()
    messages.success(request, f"Done: {activity.subject}")
    return back(request, activity.parent)
