from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class SignInTests(TestCase):
    def test_sign_in_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_signed_out_is_redirected(self):  # AUTH-1
        response = self.client.get(reverse("queue"))
        self.assertRedirects(response, f"{reverse('login')}?next=/", fetch_redirect_response=False)

    def test_wrong_password(self):  # AUTH-2
        User.objects.create_user("rajesh", password="right-password-1")
        response = self.client.post(reverse("login"), {"username": "rajesh", "password": "wrong"})
        self.assertContains(response, "Wrong username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sign_out_is_post_only(self):  # AUTH-3
        user = User.objects.create_user("rajesh", password="right-password-1")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
