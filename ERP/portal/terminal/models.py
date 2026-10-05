from django.conf import settings
from django.db import models


class Operator(models.Model):
    """A Django sign-in for a person ERPNext knows as an Employee: their time logs carry that ID."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operator")
    employee = models.CharField("ERPNext Employee ID", max_length=40, unique=True)
    default_workstation = models.CharField(max_length=140, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.employee})"
