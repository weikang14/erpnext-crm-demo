"""Who sees what. Reps see their own leads, deals, quotes and activities; managers see everything.

Every view gets its records through these functions, so a rep asking for someone else's
record by id gets a 404, never the record.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from sales.models import Activity, Lead, Opportunity, Quote, is_manager


def leads(user):
    qs = Lead.objects.select_related("owner")
    return qs if is_manager(user) else qs.filter(owner=user)


def opportunities(user):
    qs = Opportunity.objects.select_related("account", "owner")
    return qs if is_manager(user) else qs.filter(owner=user)


def quotes(user):
    qs = Quote.objects.select_related("opportunity__account", "opportunity__owner", "created_by", "approved_by")
    return qs if is_manager(user) else qs.filter(opportunity__owner=user)


def activities(user):
    """A rep's own activities plus anyone's on the rep's deals and leads."""
    qs = Activity.objects.select_related("opportunity", "lead", "account")
    if is_manager(user):
        return qs
    return qs.filter(Q(owner=user) | Q(opportunity__owner=user) | Q(lead__owner=user))


def get(scope, user, pk):
    return get_object_or_404(scope(user), pk=pk)


def manager_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


# (url name, label, section); a page belongs to the section its url name starts with
NAV = [
    ("home", "My day", "home"),
    ("pipeline", "Pipeline", "pipeline"),
    ("leads", "Leads", "leads"),
    ("opportunities", "Deals", "deals"),
    ("accounts", "Accounts", "accounts"),
    ("reports", "Reports", "reports"),
]
MANAGER_NAV = [("approvals", "Approvals", "approvals")]
SECTIONS = {
    "home": "home", "pipeline": "pipeline", "lead": "leads", "opportunit": "deals", "quote": "deals",
    "account": "accounts", "report": "reports", "approval": "approvals",
}  # fmt: skip


def nav(request):
    """Template context for the top bar."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    manager = is_manager(user)
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else ""
    section = next((s for prefix, s in SECTIONS.items() if (url_name or "").startswith(prefix)), "")
    return {
        "is_manager": manager,
        "nav_links": NAV + MANAGER_NAV if manager else NAV,
        "section": section,
        "today": timezone.localdate(),
        "pending_approvals": Quote.objects.filter(status=Quote.Status.PENDING).count() if manager else 0,
    }
