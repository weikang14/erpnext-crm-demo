from io import StringIO
from unittest import mock

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.test import TestCase

from terminal.models import Operator
from terminal.tests.fakes import FakeERPNext


@mock.patch("terminal.management.commands.seed_operators.erpnext_client", return_value=FakeERPNext())
class SeedOperatorsTests(TestCase):
    def test_links_operators_to_employees(self, _client):  # AC 3 (operator default station)
        out, err = StringIO(), StringIO()
        call_command("seed_operators", stdout=out, stderr=err)
        call_command("seed_operators", stdout=StringIO(), stderr=StringIO())  # second run: no duplicates

        operators = {o.user.username: o for o in Operator.objects.select_related("user")}
        self.assertEqual(set(operators), {"ahmad", "meiling", "rajesh"})
        self.assertEqual(operators["rajesh"].employee, "HR-EMP-00003")
        self.assertEqual(operators["meiling"].default_workstation, "CNC Press Brake")
        self.assertIn("Nurul Aina", err.getvalue())
        self.assertIsNotNone(authenticate(username="ahmad", password="Operator@2026"))
