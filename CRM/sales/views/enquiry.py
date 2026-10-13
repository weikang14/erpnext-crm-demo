"""The public "request a quote" form: no sign-in, creates a website lead for the region's rep."""

from django.shortcuts import redirect, render

from sales import ratelimit
from sales.forms import EnquiryForm
from sales.models import Lead
from sales.regions import pick_owner

LIMIT = 5  # enquiries per address per hour
WINDOW = 60 * 60


def enquiry(request):
    # ponytail: REMOTE_ADDR is the docker gateway for every local visitor; read X-Forwarded-For from a trusted proxy in production
    address = request.META.get("REMOTE_ADDR", "")
    form = EnquiryForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and (form.is_bot or form.is_valid()):
        # take this submission's slot before saving, so a burst of parallel posts can't overrun the limit
        if ratelimit.hit("enquiry", address, WINDOW) > LIMIT:
            return render(request, "sales/enquiry/form.html", {"form": form, "limited": True}, status=429)
        if not form.is_bot:  # a bot gets the same thanks page, and nothing is saved
            lead = form.save(commit=False)
            lead.source, lead.owner = Lead.Source.WEBSITE, pick_owner(lead.region)
            lead.save()
        return redirect("enquiry_thanks")
    return render(request, "sales/enquiry/form.html", {"form": form})


def thanks(request):
    return render(request, "sales/enquiry/thanks.html")
