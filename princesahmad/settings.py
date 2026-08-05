from pathlib import Path
import os
import sys
from django.core.exceptions import ImproperlyConfigured


# =========================
# Base Directory
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    """Read a strict boolean environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value.")


# =========================
# Security
# =========================

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

if not DEBUG and SECRET_KEY == "django-insecure-dev-only-change-me":
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a long random value in production."
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost",
    ).split(",")
    if host.strip()
]


# =========================
# Doors Configuration
# =========================

TOTAL_DOORS_COUNT = 41


# =========================
# Application Definition
# =========================

INSTALLED_APPS = [
    # Django Core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Platform Core Apps
    "apps.core",
    "apps.accounts",

    # Roles and Permissions
    "apps.roles.apps.RolesConfig",

    # Human Resources
    "apps.hr",

    # Locations
    "apps.locations",

    # Scheduling
    "apps.scheduling",

    # Distribution
    "apps.distribution",

    # Breaks
    "apps.breaks",

    # Operations
    "apps.ops",

    # Communications
    "apps.communications",

    # Reporting
    "apps.reporting",

    # Export Center
    "apps.exports_center",

    # Notifications
    "apps.notifications",

    # Dashboard
    "apps.dashboard",

    # Audit and Change History
    "apps.audit.apps.AuditConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "princesahmad.urls"


# =========================
# Templates
# =========================

TEMPLATES = [
    {
        "BACKEND": (
            "django.template.backends.django.DjangoTemplates"
        ),
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                (
                    "django.template.context_processors.debug"
                ),
                (
                    "django.template.context_processors.request"
                ),
                (
                    "django.contrib.auth.context_processors.auth"
                ),
                (
                    "django.contrib.messages.context_processors.messages"
                ),

                # Platform Roles and Permissions
                (
                    "apps.roles.context_processors."
                    "platform_access"
                ),

                # Operations
                (
                    "apps.ops.context_processors."
                    "maintenance_badge"
                ),

                # Notifications
                (
                    "apps.notifications.context_processors."
                    "notifications_badge"
                ),
            ],
        },
    },
]


WSGI_APPLICATION = "princesahmad.wsgi.application"


# =========================
# Database
# =========================

DB_ENGINE = os.getenv("DJANGO_DB_ENGINE", "sqlite").strip().lower()

if DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "princesahmad"),
            "USER": os.getenv("POSTGRES_USER", "princesahmad"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
            "OPTIONS": {"sslmode": os.getenv("POSTGRES_SSLMODE", "prefer")},
        }
    }
elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured("DJANGO_DB_ENGINE must be sqlite or postgresql.")


# =========================
# Password Validation
# =========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]

# Password hashing is intentionally expensive in production.  Tests create many
# users, so use Django's fast non-production hasher only while the test command
# is running.  This keeps the full suite practical without weakening runtime
# authentication.
if "test" in sys.argv:
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


# =========================
# Authentication Redirects
# =========================

LOGIN_URL = "accounts:login"

LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = "accounts:login"


# =========================
# Internationalization
# =========================

LANGUAGE_CODE = "ar"

TIME_ZONE = "Asia/Riyadh"

USE_I18N = True

USE_TZ = True

LANGUAGES = [
    (
        "ar",
        "Arabic",
    ),
    (
        "en",
        "English",
    ),
]


# =========================
# CSRF
# =========================

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        (
            "http://127.0.0.1:8000,"
            "http://localhost:8000"
        ),
    ).split(",")
    if origin.strip()
]


# =========================
# Static Files
# =========================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = (
    BASE_DIR / "staticfiles"
)


# =========================
# Media Files
# =========================

MEDIA_URL = "/media/"

MEDIA_ROOT = (
    BASE_DIR / "media"
)


# =========================
# Default Primary Key
# =========================

DEFAULT_AUTO_FIELD = (
    "django.db.models.BigAutoField"
)


# =========================
# Security Defaults
# =========================

SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_COOKIE_AGE", "28800"))
SESSION_SAVE_EVERY_REQUEST = True

LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW", "900"))
ALLOW_PUBLIC_REGISTRATION = env_bool("ALLOW_PUBLIC_REGISTRATION", DEBUG)

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if env_bool("DJANGO_TRUST_PROXY_HEADERS", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

CACHES = {
    "default": {
        "BACKEND": os.getenv(
            "DJANGO_CACHE_BACKEND",
            "django.core.cache.backends.locmem.LocMemCache",
        ),
        "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "abwaab-platform"),
    }
}

LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        }
    },
}


# =========================
# Production Security
# =========================

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = (
        os.getenv(
            "DJANGO_SECURE_SSL_REDIRECT",
            "true",
        ).lower()
        == "true"
    )

    SECURE_HSTS_SECONDS = int(
        os.getenv(
            "DJANGO_SECURE_HSTS_SECONDS",
            "31536000",
        )
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    if DB_ENGINE == "sqlite":
        raise ImproperlyConfigured(
            "Production requires PostgreSQL; set DJANGO_DB_ENGINE=postgresql."
        )

    if not ALLOWED_HOSTS or any(host in {"*", "localhost", "127.0.0.1"} for host in ALLOWED_HOSTS):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must contain production hostnames only."
        )

    if CACHES["default"]["BACKEND"].endswith("LocMemCache"):
        raise ImproperlyConfigured(
            "Production requires a shared cache for login throttling."
        )


# =========================
# SMS Configuration
# =========================

SMS_ENABLED = (
    os.getenv(
        "SMS_ENABLED",
        "false",
    ).lower()
    == "true"
)

UNIFONIC_APP_SID = (
    os.getenv(
        "UNIFONIC_APP_SID",
        "",
    ).strip()
)

UNIFONIC_SENDER_ID = (
    os.getenv(
        "UNIFONIC_SENDER_ID",
        "",
    ).strip()
)


# =========================
# SMS Validation
# =========================

if (
    SMS_ENABLED
    and not UNIFONIC_APP_SID
):
    raise RuntimeError(
        "SMS_ENABLED=true ولكن "
        "UNIFONIC_APP_SID غير موجود."
    )

if (
    SMS_ENABLED
    and not UNIFONIC_SENDER_ID
):
    raise RuntimeError(
        "SMS_ENABLED=true ولكن "
        "UNIFONIC_SENDER_ID غير موجود."
    )
