from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from terminal.models import Operator
from terminal.tests.fakes import FakeERPNext


class OperatorTestCase(TestCase):
    """Signed in as Rajesh (Welding Bay), with a fake ERPNext behind the views."""

    def setUp(self):
        self.user = User.objects.create_user("rajesh", password="pw-for-tests-only", first_name="Rajesh")
        Operator.objects.create(user=self.user, employee="HR-EMP-00003", default_workstation="Welding Bay")
        self.client.force_login(self.user)
        self.erp = FakeERPNext()
        patcher = mock.patch("terminal.views.erpnext_client", return_value=self.erp)
        patcher.start()
        self.addCleanup(patcher.stop)
