"""Fixed-window attempt counters in the database, shared by both gunicorn workers."""

import hashlib
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from sales.models import RateLimit


def _key(scope, value):
    return f"{scope}:{hashlib.sha256(value.encode()).hexdigest()[:32]}"  # user input never reaches the key raw


def count(scope, value):
    live = RateLimit.objects.filter(key=_key(scope, value), expires__gt=timezone.now())
    return live.values_list("count", flat=True).first() or 0


def hit(scope, value, window):
    """Record one attempt and return how many there have been in this window, this one included.

    The row lock makes parallel hits take turns, so each gets its own number and none is lost."""
    now = timezone.now()
    RateLimit.objects.filter(expires__lte=now).delete()  # finished windows, so made-up usernames don't pile up
    with transaction.atomic():
        row, _ = RateLimit.objects.select_for_update().get_or_create(
            key=_key(scope, value), defaults={"expires": now + timedelta(seconds=window)}
        )
        if row.expires <= now:  # an old window the prune above missed: start afresh
            row.count, row.expires = 0, now + timedelta(seconds=window)
        row.count += 1
        row.save()
    return row.count


def clear(scope, value):
    RateLimit.objects.filter(key=_key(scope, value)).delete()
