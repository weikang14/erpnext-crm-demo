"""Sales regions: which state belongs to which team, and who gets a new lead."""

from django.db import models
from django.db.models import Count, Q


class Region(models.TextChoices):
    NORTH = "north", "North"
    CENTRAL = "central", "Central"
    SOUTH = "south", "South"
    SINGAPORE = "singapore", "Singapore"


class State(models.TextChoices):
    PERLIS = "Perlis"
    KEDAH = "Kedah"
    PENANG = "Penang"
    PERAK = "Perak"
    KELANTAN = "Kelantan"
    TERENGGANU = "Terengganu"
    PAHANG = "Pahang"
    SELANGOR = "Selangor"
    KUALA_LUMPUR = "Kuala Lumpur"
    PUTRAJAYA = "Putrajaya"
    NEGERI_SEMBILAN = "Negeri Sembilan"
    MELAKA = "Melaka"
    JOHOR = "Johor"
    SABAH = "Sabah"
    SARAWAK = "Sarawak"
    LABUAN = "Labuan"
    SINGAPORE = "Singapore"


# the east coast and East Malaysia have no team of their own; the nearest team covers them
STATE_REGION = {
    State.PERLIS: Region.NORTH, State.KEDAH: Region.NORTH, State.PENANG: Region.NORTH,
    State.PERAK: Region.NORTH, State.KELANTAN: Region.NORTH, State.TERENGGANU: Region.NORTH,
    State.SELANGOR: Region.CENTRAL, State.KUALA_LUMPUR: Region.CENTRAL, State.PUTRAJAYA: Region.CENTRAL,
    State.NEGERI_SEMBILAN: Region.CENTRAL, State.PAHANG: Region.CENTRAL, State.SABAH: Region.CENTRAL,
    State.SARAWAK: Region.CENTRAL, State.LABUAN: Region.CENTRAL,
    State.JOHOR: Region.SOUTH, State.MELAKA: Region.SOUTH,
    State.SINGAPORE: Region.SINGAPORE,
}  # fmt: skip


def region_of(state):
    return STATE_REGION.get(state)


def states_in(region):
    return [state for state, r in STATE_REGION.items() if r == region]


def pick_owner(region):
    """The active rep of the region with the fewest open leads (tie: the longest-serving, lowest id)."""
    from django.contrib.auth.models import User

    from sales.models import Lead

    # ponytail: two enquiries in the same instant may both pick the same rep; the next one evens it out
    return (
        User.objects.filter(is_active=True, rep__active=True, rep__region=region)
        .annotate(open_leads=Count("leads", filter=Q(leads__status__in=Lead.OPEN)))
        .order_by("open_leads", "pk")
        .first()
    )
