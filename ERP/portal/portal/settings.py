"""Settings for the Ombak shop-floor terminal. Everything environment-specific comes from env vars."""

import os
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-demo-only-not-secret")
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ERPNext REST API (see .specship/completed/002-shopfloor-terminal/artifacts/api-contract.md)
ERPNEXT_URL = os.environ.get("ERPNEXT_URL", "http://backend:8000")
ERPNEXT_SITE = os.environ.get("ERPNEXT_SITE", "localhost")
ERPNEXT_API_KEY = os.environ.get("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.environ.get("ERPNEXT_API_SECRET", "")
ERPNEXT_TIMEOUT = 10  # seconds

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "terminal",
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

# no inline scripts or styles anywhere, so the strict policy costs nothing
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

ROOT_URLCONF = "portal.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "queue"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 12 * 60 * 60  # one shift

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kuala_Lumpur"  # the factory's (and the ERPNext site's) wall clock
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# ponytail: serve straight from app static dirs (works with the dev bind mount); collectstatic + manifest if this ever runs behind a CDN
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True  # dev bind mount: re-read edited files instead of serving a stale (cut-off) copy

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# containers log to stdout; without this Django swallows 500 tracebacks when DEBUG is off
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO"}},
}
