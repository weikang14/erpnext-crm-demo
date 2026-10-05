"""python manage.py seed_operators: demo sign-ins for the four operators ERPNext knows."""

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from terminal.models import Operator
from terminal.views import erpnext_client

# ERPNext employee name -> (username, home station); mirrors ombak_mfg setup/masters.py OPERATORS
DEMO_OPERATORS = {
    "Ahmad Faizal": ("ahmad", "Laser Cutting"),
    "Mei Ling Tan": ("meiling", "CNC Press Brake"),
    "Rajesh Kumar": ("rajesh", "Welding Bay"),
    "Nurul Aina": ("nurul", "Powder Coating"),
}


class Command(BaseCommand):
    help = "Create the demo operators and link each to their ERPNext Employee."

    def handle(self, *args, **options):
        password = os.environ.get("OPERATOR_PASSWORD", "Operator@2026")  # local demo only
        employees = {e["employee_name"]: e["name"] for e in erpnext_client().employees()}
        for full_name, (username, station) in DEMO_OPERATORS.items():
            employee = employees.get(full_name)
            if not employee:
                self.stderr.write(f"Skipped {full_name}: not an active ERPNext employee.")
                continue
            first, last = full_name.split(" ", 1)
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "last_name": last}
            )
            if created:
                user.set_password(password)
                user.save()
            Operator.objects.update_or_create(
                user=user, defaults={"employee": employee, "default_workstation": station}
            )
            self.stdout.write(f"{username} -> {employee} ({station})")
