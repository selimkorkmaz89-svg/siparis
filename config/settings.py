"""Django settings for the dealer order management system."""
from pathlib import Path

from decouple import Csv, config
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="django-insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())
# The loopback interface always answers: a local `runserver`, and the container
# health check, reach the app as "localhost" whatever the public host name is.
ALLOWED_HOSTS += [
    host for host in ("localhost", "127.0.0.1", "[::1]") if host not in ALLOWED_HOSTS
]
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "core",
    "accounts",
    "dealers",
    "catalog",
    "orders",
    "payments",
    "logistics",
    "reports",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.UserLanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_context",
                "notifications.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if config("USE_SQLITE", default=True, cast=bool):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB", default="siparis"),
            "USER": config("POSTGRES_USER", default="siparis"),
            "PASSWORD": config("POSTGRES_PASSWORD", default="siparis"),
            "HOST": config("POSTGRES_HOST", default="db"),
            "PORT": config("POSTGRES_PORT", default="5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# --- Internationalisation ---------------------------------------------------
# Source strings are authored in English; Turkish ships as a translation and is
# the default language of the deployed system.
LANGUAGE_CODE = config("LANGUAGE_CODE", default="tr")
LANGUAGES = [
    ("tr", _("Turkish")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = config("TIME_ZONE", default="Europe/Istanbul")
USE_I18N = True
USE_TZ = True
LANGUAGE_COOKIE_NAME = "siparis_language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email ------------------------------------------------------------------
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@example.com")

# --- Celery -----------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/1")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)

# --- Domain settings --------------------------------------------------------
COMPANY_NAME = config("COMPANY_NAME", default="BSH Diagnostics")
COMPANY_TAX_NO = config("COMPANY_TAX_NO", default="")
COMPANY_ADDRESS = config("COMPANY_ADDRESS", default="")
COMPANY_PHONE = config("COMPANY_PHONE", default="")
COMPANY_EMAIL = config("COMPANY_EMAIL", default="")
COMPANY_LOGO = config("COMPANY_LOGO", default="img/logo.svg")
BRAND_COLOR = "#0D8DBE"
ORDER_NO_PREFIX = config("ORDER_NO_PREFIX", default="BSH")

# TCMB publishes the daily rate at 15:30 local time.
TCMB_RATE_PUBLISH_HOUR = 15
TCMB_RATE_PUBLISH_MINUTE = 30
TCMB_TODAY_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
TCMB_ARCHIVE_URL = "https://www.tcmb.gov.tr/kurlar/{yyyymm}/{ddmmyyyy}.xml"
# Payment amounts that differ from the order total by more than this ratio raise
# a warning to the finance user, but never block approval.
PAYMENT_MISMATCH_TOLERANCE = config(
    "PAYMENT_MISMATCH_TOLERANCE", default="0.02", cast=str
)

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

if not DEBUG:
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
}
