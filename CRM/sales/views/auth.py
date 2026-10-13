import unicodedata

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.views import LoginView

from sales import ratelimit

LOGIN_LIMIT = 10
LOGIN_WINDOW = 15 * 60


def login_key(username):
    # NFKC like Django's UsernameField, so look-alike spellings of one account share its counter
    return unicodedata.normalize("NFKC", (username or "").strip()).lower()


class LockoutBackend(ModelBackend):
    """Ten failed sign-ins for one username lock it for the rest of the 15-minute window.

    Enforced here rather than in a view so every sign-in path, /login/ and /admin/login/ alike, shares the counter."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        key = login_key(username)
        # reserve this attempt before the password check, so a burst of parallel guesses still gets only ten checks
        if ratelimit.hit("login", key, LOGIN_WINDOW) > LOGIN_LIMIT:
            # ponytail: anyone can lock a username for 15 minutes; add per-IP limits if that gets abused
            return None
        user = super().authenticate(request, username, password, **kwargs)
        if user is not None:
            ratelimit.clear("login", key)
        return user


class RateLimitedLoginView(LoginView):
    redirect_authenticated_user = True

    def form_invalid(self, form):
        locked = ratelimit.count("login", login_key(form.cleaned_data.get("username"))) > LOGIN_LIMIT
        return self.render_to_response(self.get_context_data(form=form, locked=locked))
