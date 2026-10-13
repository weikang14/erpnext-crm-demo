from django.core.paginator import Paginator
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

PAGE_SIZE = 25


def page_of(request, qs):
    return Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))


def back(request, fallback):
    """Redirect to the form's `next` field when it points at this site, otherwise to `fallback`."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return redirect(target)
    return redirect(fallback)
