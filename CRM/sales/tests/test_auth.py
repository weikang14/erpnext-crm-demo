import threading
import time
from unittest import mock

from django.contrib.auth.backends import ModelBackend
from django.db import connection
from django.test import Client, TransactionTestCase
from django.urls import reverse

from sales.forms import EnquiryForm
from sales.models import Lead
from sales.tests.base import PASSWORD, CRMTestCase
from sales.tests.test_leads import ENQUIRY


class SignInTests(CRMTestCase):
    def setUp(self):
        pass  # signed out

    def test_login_page(self):  # RUN-1
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')

    def test_signed_out_redirect(self):  # AUTH-1
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, "/login/?next=/", fetch_redirect_response=False)

    def test_wrong_password(self):  # AUTH-2
        response = self.client.post(reverse("login"), {"username": "siti", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wrong username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sign_in_and_out(self):  # AUTH-3
        response = self.client.post(reverse("login"), {"username": "siti", "password": PASSWORD})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lockout_after_ten_failures(self):  # AUTH-4
        for _ in range(10):
            self.client.post(reverse("login"), {"username": "Siti ", "password": "nope"})
        response = self.client.post(reverse("login"), {"username": "siti", "password": PASSWORD})
        self.assertContains(response, "Too many attempts")
        self.assertNotIn("_auth_user_id", self.client.session)
        other = self.client.post(reverse("login"), {"username": "kumar", "password": PASSWORD})
        self.assertEqual(other.status_code, 302)  # other usernames are not affected

    def test_lockout_shared_by_unicode_lookalikes(self):  # AUTH-4: Django NFKC-normalises usernames
        fullwidth = "ａisyah"  # fullwidth "a", signs in as aisyah
        for name in ["aisyah", fullwidth, "ＡISYAH"] * 3 + ["aisyah"]:  # ten failures over three spellings
            self.client.post(reverse("login"), {"username": name, "password": "nope"})
        for name in ["aisyah", fullwidth, "Ａisyah "]:
            response = self.client.post(reverse("login"), {"username": name, "password": PASSWORD})
            self.assertContains(response, "Too many attempts")
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_sign_in_shares_the_lockout(self):  # AUTH-4: /admin/login/ is a second way in for staff
        for _ in range(10):
            self.client.post("/admin/login/", {"username": "hafiz", "password": "nope"})
        self.assertContains(self.client.post(reverse("login"), {"username": "hafiz", "password": PASSWORD}), "Too many attempts")
        response = self.client.post("/admin/login/", {"username": "hafiz", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_security_headers(self):  # SEC-4
        response = self.client.get(reverse("login"))
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_csrf_enforced(self):  # SEC-3
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("login"), {"username": "siti", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)


class BurstTests(TransactionTestCase):
    """Limits under a burst: real threads and connections, because the race between parallel requests is the point."""

    def burst(self, url, data, n=20):
        start = threading.Barrier(n)

        def post():
            try:
                start.wait()
                Client().post(url, data)
            finally:
                connection.close()

        threads = [threading.Thread(target=post) for _ in range(n)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def test_sign_in_burst_checks_at_most_ten_passwords(self):  # AUTH-4
        checked, real = [], ModelBackend.authenticate

        def slow_check(backend, *args, **kwargs):  # holds every attempt in the password check a moment, so they overlap
            checked.append(1)
            time.sleep(0.2)
            return real(backend, *args, **kwargs)

        with mock.patch.object(ModelBackend, "authenticate", slow_check):
            self.burst(reverse("login"), {"username": "nosuchuser-burst", "password": "nope"})
        self.assertEqual(len(checked), 10)

    def test_enquiry_burst_saves_at_most_five(self):  # ENQ-5
        real = EnquiryForm.is_valid

        def slow_validation(form):
            time.sleep(0.2)
            return real(form)

        with mock.patch.object(EnquiryForm, "is_valid", slow_validation):
            self.burst(reverse("enquiry"), ENQUIRY, n=12)
        self.assertEqual(Lead.objects.count(), 5)
