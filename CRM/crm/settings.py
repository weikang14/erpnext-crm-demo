"""Settings for the Ombak sales CRM. Everything environment-specific comes from env vars."""

import os
import sys
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-demo-only-not-secret")
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "sales",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

# our pages use no inline scripts or styles, so the strict policy costs nothing
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

ROOT_URLCONF = "crm.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "sales.access.nav",
            ],
        },
    },
]

WSGI_APPLICATION = "crm.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "NAME": os.environ.get("POSTGRES_DB", "crm"),
        "USER": os.environ.get("POSTGRES_USER", "crm"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "CONN_MAX_AGE": 60,
        "TEST": {"NAME": os.environ.get("POSTGRES_TEST_DB", "test_crm")},  # parallel runs each take their own
    }
}

AUTHENTICATION_BACKENDS = ["sales.views.auth.LockoutBackend"]  # the sign-in lockout, on every sign-in path

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 10 * 60 * 60  # a working day

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kuala_Lumpur"  # "today" and "overdue" are Malaysian dates
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# ponytail: served straight from the app's static dir (works with the dev bind mount); collectstatic + manifest behind a CDN
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# containers log to stdout; without this Django swallows 500 tracebacks when DEBUG is off
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "sales": {"handlers": ["console"], "level": "INFO"},  # send_order logs unexpected errors (ids, no secrets)
    },
}

# ERPNext link (004): an empty URL means not configured. docker-compose.erp.yml sets these.
ERPNEXT_URL = os.environ.get("ERPNEXT_URL", "")
ERPNEXT_SITE = os.environ.get("ERPNEXT_SITE", "localhost")
ERPNEXT_API_KEY = os.environ.get("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.environ.get("ERPNEXT_API_SECRET", "")
ERPNEXT_DESK_URL = os.environ.get("ERPNEXT_DESK_URL", "")
if sys.argv[1:2] == ["test"]:  # unit tests never reach ERPNext; the live contract tests opt back in from the env
    ERPNEXT_URL = ""
