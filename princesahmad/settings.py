from pathlib import Path
import json
import os
import sys
from urllib.parse import urlsplit

import dj_database_url
from dotenv import load_dotenv

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key


# ============================================================
# Base Directory
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# Environment File
# ============================================================

ENV_FILE = BASE_DIR / ".env"

load_dotenv(
    dotenv_path=ENV_FILE,
    override=False,
    encoding="utf-8",
)


# ============================================================
# Environment Helpers
# ============================================================

def env_bool(
    name: str,
    default: bool = False,
) -> bool:
    """
    قراءة Boolean من متغيرات البيئة بأمان.

    القيم المقبولة:
    true / false
    1 / 0
    yes / no
    on / off

    إذا كان المتغير غير موجود أو فارغًا،
    يتم استخدام القيمة الافتراضية.
    """

    raw_value = os.getenv(name)

    if (
        raw_value is None
        or not raw_value.strip()
    ):
        return default

    normalized = raw_value.strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise ImproperlyConfigured(
        f"{name} must be a boolean value."
    )


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """
    قراءة Integer من متغيرات البيئة بأمان.

    القيمة الفارغة تعتبر غير محددة
    ويتم استخدام default.
    """

    raw_value = os.getenv(name)

    if (
        raw_value is None
        or not raw_value.strip()
    ):
        value = default

    else:
        try:
            value = int(
                raw_value.strip()
            )

        except ValueError as exc:
            raise ImproperlyConfigured(
                f"{name} must be an integer."
            ) from exc

    if (
        minimum is not None
        and value < minimum
    ):
        raise ImproperlyConfigured(
            f"{name} must be at least "
            f"{minimum}."
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ImproperlyConfigured(
            f"{name} must be at most "
            f"{maximum}."
        )

    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """
    قراءة Float من متغيرات البيئة بأمان.
    """

    raw_value = os.getenv(name)

    if (
        raw_value is None
        or not raw_value.strip()
    ):
        value = default

    else:
        try:
            value = float(
                raw_value.strip()
            )

        except ValueError as exc:
            raise ImproperlyConfigured(
                f"{name} must be a number."
            ) from exc

    if (
        minimum is not None
        and value < minimum
    ):
        raise ImproperlyConfigured(
            f"{name} must be at least "
            f"{minimum}."
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ImproperlyConfigured(
            f"{name} must be at most "
            f"{maximum}."
        )

    return value


def env_json_object(
    name: str,
) -> dict:
    """
    قراءة JSON Object من متغيرات البيئة.

    القيمة الفارغة تعيد قاموسًا فارغًا.
    """

    value = os.getenv(
        name,
        "",
    ).strip()

    if not value:
        return {}

    try:
        parsed = json.loads(
            value
        )

    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            f"{name} must be a JSON object."
        ) from exc

    if not isinstance(
        parsed,
        dict,
    ):
        raise ImproperlyConfigured(
            f"{name} must be a JSON object."
        )

    return parsed


def env_csv(
    name: str,
    default: str = "",
) -> list[str]:
    return [
        value.strip()
        for value in os.getenv(
            name,
            default,
        ).split(",")
        if value.strip()
    ]


def normalize_hostname(
    value: str,
) -> str:
    parsed = urlsplit(
        value if "://" in value else f"//{value}"
    )
    return parsed.hostname or ""


# ============================================================
# Security
# ============================================================

DEBUG = env_bool(
    "DJANGO_DEBUG",
    True,
)

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "",
).strip()

if (
    not SECRET_KEY
    and DEBUG
):
    SECRET_KEY = (
        get_random_secret_key()
    )

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set "
        "when DJANGO_DEBUG is false."
    )


configured_hosts = env_csv(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost" if DEBUG else "",
)
render_hostname = normalize_hostname(
    os.getenv(
        "RENDER_EXTERNAL_HOSTNAME",
        "",
    ).strip()
)

ALLOWED_HOSTS = list(
    dict.fromkeys(
        [
            normalize_hostname(host)
            for host in configured_hosts
        ]
        + [
            "princesahmad.onrender.com",
            render_hostname,
        ]
    )
)
ALLOWED_HOSTS = [host for host in ALLOWED_HOSTS if host]


# ============================================================
# Doors Configuration
# ============================================================

TOTAL_DOORS_COUNT = 41


# ============================================================
# Application Definition
# ============================================================

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

    # Audit
    "apps.audit.apps.AuditConfig",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.OperationalSectionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = (
    "princesahmad.urls"
)


# ============================================================
# Templates
# ============================================================

TEMPLATES = [
    {
        "BACKEND": (
            "django.template.backends."
            "django.DjangoTemplates"
        ),
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                (
                    "django.template."
                    "context_processors.debug"
                ),
                (
                    "django.template."
                    "context_processors.request"
                ),
                (
                    "django.contrib.auth."
                    "context_processors.auth"
                ),
                (
                    "django.contrib.messages."
                    "context_processors.messages"
                ),

                (
                    "apps.core.context_processors."
                    "operational_section_filter"
                ),

                (
                    "apps.roles.context_processors."
                    "platform_access"
                ),

                (
                    "apps.ops.context_processors."
                    "maintenance_badge"
                ),

                (
                    "apps.notifications."
                    "context_processors."
                    "notifications_badge"
                ),
            ],
        },
    },
]


WSGI_APPLICATION = (
    "princesahmad.wsgi.application"
)


# ============================================================
# Database
# ============================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
).strip()

DB_ENGINE = os.getenv(
    "DJANGO_DB_ENGINE",
    "sqlite",
).strip().lower()


if DATABASE_URL:
    DATABASES = {
        "default": (
            dj_database_url.config(
                default=DATABASE_URL,
                conn_max_age=env_int(
                    "POSTGRES_CONN_MAX_AGE",
                    60,
                    minimum=0,
                ),
                conn_health_checks=True,
                ssl_require=not DEBUG,
            )
        ),
    }

elif DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": (
                "django.db.backends."
                "postgresql"
            ),
            "NAME": os.getenv(
                "POSTGRES_DB",
                "princesahmad",
            ),
            "USER": os.getenv(
                "POSTGRES_USER",
                "princesahmad",
            ),
            "PASSWORD": os.getenv(
                "POSTGRES_PASSWORD",
                "",
            ),
            "HOST": os.getenv(
                "POSTGRES_HOST",
                "127.0.0.1",
            ),
            "PORT": os.getenv(
                "POSTGRES_PORT",
                "5432",
            ),
            "CONN_MAX_AGE": env_int(
                "POSTGRES_CONN_MAX_AGE",
                60,
                minimum=0,
            ),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "sslmode": os.getenv(
                    "POSTGRES_SSLMODE",
                    "require" if not DEBUG else "prefer",
                ),
            },
        },
    }

elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": (
                "django.db.backends.sqlite3"
            ),
            "NAME": (
                BASE_DIR
                / "db.sqlite3"
            ),
        },
    }

else:
    raise ImproperlyConfigured(
        "DJANGO_DB_ENGINE must be "
        "sqlite or postgresql."
    )


if not DEBUG and DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    database_password_present = (
        bool(urlsplit(DATABASE_URL).password)
        if DATABASE_URL
        else bool(DATABASES["default"]["PASSWORD"])
    )
    if not database_password_present:
        raise ImproperlyConfigured(
            "PostgreSQL password is required in production; set "
            "POSTGRES_PASSWORD or a password-bearing DATABASE_URL."
        )


# ============================================================
# Password Validation
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth."
            "password_validation."
            "NumericPasswordValidator"
        ),
    },
]


if "test" in sys.argv:
    PASSWORD_HASHERS = [
        (
            "django.contrib.auth."
            "hashers.MD5PasswordHasher"
        ),
    ]


# ============================================================
# Authentication Redirects
# ============================================================

LOGIN_URL = (
    "accounts:login"
)

LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = (
    "accounts:login"
)


# ============================================================
# Internationalization
# ============================================================

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


# ============================================================
# CSRF
# ============================================================

configured_csrf_origins = env_csv(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    (
        "http://127.0.0.1:8000,"
        "http://localhost:8000"
    ) if DEBUG else "",
)
render_csrf_origins = [
    f"https://{hostname}"
    for hostname in (
        "princesahmad.onrender.com",
        render_hostname,
    )
    if hostname
]

CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        configured_csrf_origins + render_csrf_origins
    )
)


# ============================================================
# Static Files
# ============================================================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = (
    BASE_DIR / "staticfiles"
)


WHITENOISE_AUTOREFRESH = (
    DEBUG
)

WHITENOISE_USE_FINDERS = (
    DEBUG
)

WHITENOISE_MAX_AGE = env_int(
    "WHITENOISE_MAX_AGE",
    31536000,
    minimum=0,
)


# ============================================================
# Media Files
# ============================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = (
    BASE_DIR / "media"
)


STORAGES = {
    "default": {
        "BACKEND": (
            "django.core.files.storage."
            "FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles."
            "storage.StaticFilesStorage"
        ),
    },
}


# ============================================================
# Default Primary Key
# ============================================================

DEFAULT_AUTO_FIELD = (
    "django.db.models.BigAutoField"
)


# ============================================================
# Security Defaults
# ============================================================

SECURE_CONTENT_TYPE_NOSNIFF = (
    True
)

X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SAMESITE = "Lax"


SESSION_COOKIE_AGE = env_int(
    "DJANGO_SESSION_COOKIE_AGE",
    28800,
    minimum=60,
)

SESSION_SAVE_EVERY_REQUEST = (
    True
)


LOGIN_RATE_LIMIT_ATTEMPTS = env_int(
    "LOGIN_RATE_LIMIT_ATTEMPTS",
    5,
    minimum=1,
)

LOGIN_RATE_LIMIT_WINDOW = env_int(
    "LOGIN_RATE_LIMIT_WINDOW",
    900,
    minimum=1,
)


ALLOW_PUBLIC_REGISTRATION = env_bool(
    "ALLOW_PUBLIC_REGISTRATION",
    DEBUG,
)


SECURE_REFERRER_POLICY = (
    "strict-origin-when-cross-origin"
)

SECURE_CROSS_ORIGIN_OPENER_POLICY = (
    "same-origin"
)


TRUST_PROXY_HEADERS = env_bool(
    "DJANGO_TRUST_PROXY_HEADERS",
    False,
)


if TRUST_PROXY_HEADERS:
    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )

    USE_X_FORWARDED_HOST = True


# ============================================================
# Cache
# ============================================================

CACHE_BACKEND = os.getenv(
    "DJANGO_CACHE_BACKEND",
    "",
).strip()

REDIS_URL = os.getenv(
    "REDIS_URL",
    "",
).strip()


CACHES = {
    "default": {
        "BACKEND": (
            CACHE_BACKEND
            or (
                "django.core.cache.backends."
                "redis.RedisCache"
                if REDIS_URL
                else (
                    "django.core.cache.backends."
                    "locmem.LocMemCache"
                )
            )
        ),
        "LOCATION": (
            REDIS_URL
            or os.getenv(
                "DJANGO_CACHE_LOCATION",
                "abwaab-platform",
            )
        ),
    },
}


# ============================================================
# Celery
# ============================================================

CELERY_BROKER_URL = (
    os.getenv(
        "CELERY_BROKER_URL",
        "",
    ).strip()
    or REDIS_URL
)


CELERY_RESULT_BACKEND = (
    os.getenv(
        "CELERY_RESULT_BACKEND",
        "",
    ).strip()
    or CELERY_BROKER_URL
)


CELERY_TASK_ALWAYS_EAGER = env_bool(
    "CELERY_TASK_ALWAYS_EAGER",
    DEBUG,
)

CELERY_TASK_EAGER_PROPAGATES = (
    True
)

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_ACCEPT_CONTENT = [
    "json",
]

CELERY_TIMEZONE = (
    TIME_ZONE
)

CELERY_TASK_TRACK_STARTED = (
    True
)


ASYNC_EXPORTS_ENABLED = env_bool(
    "ASYNC_EXPORTS_ENABLED",
    not DEBUG,
)


CELERY_TASK_DEFAULT_QUEUE = os.getenv(
    "CELERY_TASK_DEFAULT_QUEUE",
    "celery",
).strip() or "celery"


CELERY_BEAT_SCHEDULE = {
    "monitor-platform-every-five-minutes": {
        "task": (
            "apps.core.tasks."
            "monitor_platform_task"
        ),
        "schedule": 300.0,
    },
}


# ============================================================
# Monitoring
# ============================================================

MONITOR_DB_MAX_LATENCY_MS = env_float(
    "MONITOR_DB_MAX_LATENCY_MS",
    250.0,
    minimum=0,
)

MONITOR_QUEUE_BACKLOG_MAX = env_int(
    "MONITOR_QUEUE_BACKLOG_MAX",
    100,
    minimum=0,
)

MONITOR_FAILED_EXPORTS_MAX = env_int(
    "MONITOR_FAILED_EXPORTS_MAX",
    0,
    minimum=0,
)

MONITOR_STALE_EXPORTS_MAX = env_int(
    "MONITOR_STALE_EXPORTS_MAX",
    0,
    minimum=0,
)

MONITOR_EXPORT_STALE_MINUTES = env_int(
    "MONITOR_EXPORT_STALE_MINUTES",
    15,
    minimum=1,
)

MONITOR_HTTP_500_MAX = env_int(
    "MONITOR_HTTP_500_MAX",
    0,
    minimum=0,
)

MONITOR_HTTP_403_MAX = env_int(
    "MONITOR_HTTP_403_MAX",
    25,
    minimum=0,
)

MONITOR_EMAIL_ALERTS = env_bool(
    "MONITOR_EMAIL_ALERTS",
    False,
)


PRODUCTION_DATA_VALIDATED = env_bool(
    "PRODUCTION_DATA_VALIDATED",
    False,
)


PRODUCTION_BACKUP_VALIDATED = env_bool(
    "PRODUCTION_BACKUP_VALIDATED",
    False,
)


# ============================================================
# Logging
# ============================================================

LOG_LEVEL = os.getenv(
    "DJANGO_LOG_LEVEL",
    "INFO",
).strip().upper() or "INFO"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "structured": {
            "()": (
                "apps.core.logging."
                "JsonFormatter"
            ),
        },
    },

    "filters": {
        "sensitive_data": {
            "()": (
                "apps.core.logging."
                "SensitiveDataFilter"
            ),
        },
    },

    "handlers": {
        "console": {
            "class": (
                "logging.StreamHandler"
            ),
            "formatter": "structured",
            "filters": [
                "sensitive_data",
            ],
        },
    },

    "root": {
        "handlers": [
            "console",
        ],
        "level": LOG_LEVEL,
    },

    "loggers": {
        "platform.security": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
            "propagate": False,
        },

        "platform.exports": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
            "propagate": False,
        },

        "platform.tasks": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
            "propagate": False,
        },

        "platform.monitoring": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
            "propagate": False,
        },

        "communications": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
            "propagate": False,
        },

        "django.security": {
            "handlers": [
                "console",
            ],
            "level": "WARNING",
            "propagate": False,
        },
    },
}


# ============================================================
# Production Security
# ============================================================

if not DEBUG:
    SECURE_REFERRER_POLICY = "same-origin"

    SESSION_COOKIE_SECURE = True

    CSRF_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = env_bool(
        "DJANGO_SECURE_SSL_REDIRECT",
        True,
    )

    SECURE_HSTS_SECONDS = env_int(
        "DJANGO_SECURE_HSTS_SECONDS",
        0,
        minimum=0,
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
        False,
    )

    SECURE_HSTS_PRELOAD = env_bool(
        "DJANGO_SECURE_HSTS_PRELOAD",
        False,
    )

    if not SECURE_SSL_REDIRECT:
        raise ImproperlyConfigured(
            "DJANGO_SECURE_SSL_REDIRECT "
            "must be true in production."
        )

    insecure_csrf_origins = [
        origin
        for origin in CSRF_TRUSTED_ORIGINS
        if (
            not origin.startswith(
                "https://"
            )
            or "localhost" in origin
            or "127.0.0.1" in origin
        )
    ]

    if insecure_csrf_origins:
        raise ImproperlyConfigured(
            "CSRF_TRUSTED_ORIGINS must "
            "use production HTTPS "
            "origins only."
        )

    if (
        DATABASES[
            "default"
        ]["ENGINE"]
        == "django.db.backends.sqlite3"
    ):
        raise ImproperlyConfigured(
            "Production requires "
            "PostgreSQL; set DATABASE_URL."
        )

    if (
        not ALLOWED_HOSTS
        or any(
            host in {
                "*",
                "localhost",
                "127.0.0.1",
            }
            for host in ALLOWED_HOSTS
        )
    ):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must "
            "contain production "
            "hostnames only."
        )

    if (
        CACHES[
            "default"
        ]["BACKEND"].endswith(
            "LocMemCache"
        )
    ):
        raise ImproperlyConfigured(
            "Production requires a "
            "shared cache for login "
            "throttling."
        )

    if not CELERY_BROKER_URL:
        raise ImproperlyConfigured(
            "Production requires "
            "CELERY_BROKER_URL "
            "or REDIS_URL."
        )

    STORAGES[
        "staticfiles"
    ] = {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    }


# ============================================================
# Legacy SMS Configuration
# ============================================================

SMS_ENABLED = env_bool(
    "SMS_ENABLED",
    False,
)


UNIFONIC_APP_SID = os.getenv(
    "UNIFONIC_APP_SID",
    "",
).strip()


UNIFONIC_SENDER_ID = os.getenv(
    "UNIFONIC_SENDER_ID",
    "",
).strip()


# ============================================================
# Communications / Authentica
# ============================================================

COMMUNICATION_PROVIDER = (
    os.getenv(
        "COMMUNICATION_PROVIDER",
        "authentica",
    ).strip().lower()
    or "authentica"
)


COMMUNICATIONS_ENABLED = env_bool(
    "COMMUNICATIONS_ENABLED",
    False,
)


OPERATIONAL_MESSAGING_ENABLED = env_bool(
    "OPERATIONAL_MESSAGING_ENABLED",
    False,
)


ASSIGNMENT_SMS_ENABLED = env_bool(
    "ASSIGNMENT_SMS_ENABLED",
    False,
)


ASSIGNMENT_WHATSAPP_ENABLED = env_bool(
    "ASSIGNMENT_WHATSAPP_ENABLED",
    False,
)


COMMUNICATION_TIMEOUT = env_int(
    "COMMUNICATION_TIMEOUT",
    15,
    minimum=1,
)


COMMUNICATION_MAX_RETRIES = env_int(
    "COMMUNICATION_MAX_RETRIES",
    3,
    minimum=0,
)


COMMUNICATION_FALLBACK_ENABLED = (
    env_bool(
        "COMMUNICATION_FALLBACK_ENABLED",
        False,
    )
)


COMMUNICATION_FALLBACK_ORDER = [
    channel.strip().lower()
    for channel in os.getenv(
        "COMMUNICATION_FALLBACK_ORDER",
        "sms,whatsapp,email",
    ).split(",")
    if channel.strip()
]


COMMUNICATION_ASSIGNMENT_CHANNELS = [
    channel.strip().lower()
    for channel in os.getenv(
        "COMMUNICATION_ASSIGNMENT_CHANNELS",
        "sms",
    ).split(",")
    if channel.strip()
]


# ============================================================
# Authentica Core
# ============================================================

AUTHENTICA_BASE_URL = (
    os.getenv(
        "AUTHENTICA_BASE_URL",
        "https://api.authentica.sa",
    ).strip()
    or "https://api.authentica.sa"
)


AUTHENTICA_API_KEY = os.getenv(
    "AUTHENTICA_API_KEY",
    "",
).strip()


AUTHENTICA_API_SECRET = os.getenv(
    "AUTHENTICA_API_SECRET",
    "",
)


# ============================================================
# Authentica Communication Endpoints
# ============================================================

AUTHENTICA_SMS_ENDPOINT = os.getenv(
    "AUTHENTICA_SMS_ENDPOINT",
    "",
).strip()


AUTHENTICA_WHATSAPP_ENDPOINT = os.getenv(
    "AUTHENTICA_WHATSAPP_ENDPOINT",
    "",
).strip()


AUTHENTICA_SMS_SENDER = os.getenv(
    "AUTHENTICA_SMS_SENDER",
    "",
).strip()


AUTHENTICA_WHATSAPP_SENDER = os.getenv(
    "AUTHENTICA_WHATSAPP_SENDER",
    "",
).strip()


AUTHENTICA_EMAIL_ENDPOINT = os.getenv(
    "AUTHENTICA_EMAIL_ENDPOINT",
    "",
).strip()


AUTHENTICA_VOICE_ENDPOINT = os.getenv(
    "AUTHENTICA_VOICE_ENDPOINT",
    "",
).strip()


# ============================================================
# Authentica OTP
# ============================================================

AUTHENTICA_OTP_REQUEST_ENDPOINT = (
    os.getenv(
        "AUTHENTICA_OTP_REQUEST_ENDPOINT",
        "/api/v2/send-otp",
    ).strip()
    or "/api/v2/send-otp"
)


AUTHENTICA_OTP_VERIFY_ENDPOINT = (
    os.getenv(
        "AUTHENTICA_OTP_VERIFY_ENDPOINT",
        "/api/v2/verify-otp",
    ).strip()
    or "/api/v2/verify-otp"
)


AUTHENTICA_2FA_ENABLED = env_bool(
    "AUTHENTICA_2FA_ENABLED",
    False,
)

AUTHENTICA_2FA_REQUIRE_SUPERUSERS = env_bool(
    "AUTHENTICA_2FA_REQUIRE_SUPERUSERS",
    True,
)

AUTHENTICA_2FA_REQUIRE_FOR_NEW_USERS = env_bool(
    "AUTHENTICA_2FA_REQUIRE_FOR_NEW_USERS",
    False,
)

AUTHENTICA_2FA_NEW_USERS_SINCE = os.getenv(
    "AUTHENTICA_2FA_NEW_USERS_SINCE",
    "",
).strip()

AUTHENTICA_2FA_PENDING_SESSION_AGE = env_int(
    "AUTHENTICA_2FA_PENDING_SESSION_AGE",
    600,
    minimum=60,
)

AUTHENTICA_2FA_RECOVERY_CODES_ENABLED = env_bool(
    "AUTHENTICA_2FA_RECOVERY_CODES_ENABLED",
    False,
)

TWO_FACTOR_AUDIT_RETENTION_DAYS = env_int(
    "TWO_FACTOR_AUDIT_RETENTION_DAYS",
    365,
    minimum=1,
)

TEST_ACCOUNT_CLEANUP_MAX_AGE_DAYS = env_int(
    "TEST_ACCOUNT_CLEANUP_MAX_AGE_DAYS",
    60,
    minimum=1,
)


AUTHENTICA_2FA_PILOT_ENABLED = env_bool(
    "AUTHENTICA_2FA_PILOT_ENABLED",
    True,
)


AUTHENTICA_2FA_PILOT_USER_IDS = tuple(
    int(user_id)
    for user_id in os.getenv("AUTHENTICA_2FA_PILOT_USER_IDS", "").split(",")
    if user_id.strip().isdigit()
)


AUTHENTICA_2FA_PILOT_INCLUDE_STAFF = env_bool(
    "AUTHENTICA_2FA_PILOT_INCLUDE_STAFF",
    False,
)


AUTHENTICA_2FA_PILOT_INCLUDE_SUPERUSERS = env_bool(
    "AUTHENTICA_2FA_PILOT_INCLUDE_SUPERUSERS",
    False,
)


AUTHENTICA_OTP_ALLOWED_CHANNELS = tuple(
    channel.strip().lower()
    for channel in os.getenv(
        "AUTHENTICA_OTP_ALLOWED_CHANNELS",
        "sms,whatsapp,email",
    ).split(",")
    if channel.strip()
)


AUTHENTICA_OTP_TTL_SECONDS = env_int(
    "AUTHENTICA_OTP_TTL_SECONDS",
    300,
    minimum=30,
)


AUTHENTICA_OTP_MAX_ATTEMPTS = env_int(
    "AUTHENTICA_OTP_MAX_ATTEMPTS",
    5,
    minimum=1,
)


AUTHENTICA_OTP_RESEND_COOLDOWN_SECONDS = (
    env_int(
        "AUTHENTICA_OTP_RESEND_COOLDOWN_SECONDS",
        60,
        minimum=0,
    )
)


AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS = (
    env_int(
        "AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS",
        3,
        minimum=1,
    )
)


AUTHENTICA_OTP_RATE_LIMIT_WINDOW = env_int(
    "AUTHENTICA_OTP_RATE_LIMIT_WINDOW",
    600,
    minimum=1,
)


# ============================================================
# Authentica OTP Templates
# ============================================================

AUTHENTICA_SMS_OTP_TEMPLATE_ID = (
    os.getenv(
        "AUTHENTICA_SMS_OTP_TEMPLATE_ID",
        "5",
    ).strip()
    or "5"
)


AUTHENTICA_WHATSAPP_OTP_TEMPLATE_ID = (
    os.getenv(
        "AUTHENTICA_WHATSAPP_OTP_TEMPLATE_ID",
        "2",
    ).strip()
    or "2"
)


AUTHENTICA_EMAIL_OTP_TEMPLATE_ID = os.getenv(
    "AUTHENTICA_EMAIL_OTP_TEMPLATE_ID",
    "",
).strip()


# ============================================================
# Authentica Future Features
# ============================================================

AUTHENTICA_NAFATH_ENDPOINT = os.getenv(
    "AUTHENTICA_NAFATH_ENDPOINT",
    "",
).strip()


AUTHENTICA_FACE_ENDPOINT = os.getenv(
    "AUTHENTICA_FACE_ENDPOINT",
    "",
).strip()


AUTHENTICA_VOICE_ENABLED = env_bool(
    "AUTHENTICA_VOICE_ENABLED",
    False,
)


AUTHENTICA_NAFATH_ENABLED = env_bool(
    "AUTHENTICA_NAFATH_ENABLED",
    False,
)


AUTHENTICA_FACE_ENABLED = env_bool(
    "AUTHENTICA_FACE_ENABLED",
    False,
)


# ============================================================
# Authentica Senders
# ============================================================

AUTHENTICA_SMS_SENDER = os.getenv(
    "AUTHENTICA_SMS_SENDER",
    "",
).strip()


AUTHENTICA_WHATSAPP_SENDER = os.getenv(
    "AUTHENTICA_WHATSAPP_SENDER",
    "",
).strip()


AUTHENTICA_EMAIL_SENDER = os.getenv(
    "AUTHENTICA_EMAIL_SENDER",
    "",
).strip()


# ============================================================
# Authentica Payload Mappings
# ============================================================

AUTHENTICA_SMS_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_SMS_PAYLOAD_MAPPING"
    )
)


AUTHENTICA_WHATSAPP_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_WHATSAPP_PAYLOAD_MAPPING"
    )
)


AUTHENTICA_EMAIL_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_EMAIL_PAYLOAD_MAPPING"
    )
)


AUTHENTICA_VOICE_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_VOICE_PAYLOAD_MAPPING"
    )
)


AUTHENTICA_OTP_REQUEST_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_OTP_REQUEST_PAYLOAD_MAPPING"
    )
)


AUTHENTICA_OTP_VERIFY_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_OTP_VERIFY_PAYLOAD_MAPPING"
    )
)


# ============================================================
# Authentica Response Mappings
# ============================================================

AUTHENTICA_SMS_RESPONSE_MAPPING = (
    env_json_object(
        "AUTHENTICA_SMS_RESPONSE_MAPPING"
    )
)


AUTHENTICA_WHATSAPP_RESPONSE_MAPPING = (
    env_json_object(
        "AUTHENTICA_WHATSAPP_RESPONSE_MAPPING"
    )
)


AUTHENTICA_EMAIL_RESPONSE_MAPPING = (
    env_json_object(
        "AUTHENTICA_EMAIL_RESPONSE_MAPPING"
    )
)


AUTHENTICA_OTP_RESPONSE_MAPPING = (
    env_json_object(
        "AUTHENTICA_OTP_RESPONSE_MAPPING"
    )
)


# ============================================================
# Authentica Authentication Headers
# ============================================================

AUTHENTICA_AUTH_HEADERS = (
    env_json_object(
        "AUTHENTICA_AUTH_HEADERS"
    )
)


# ============================================================
# Authentica Status Mapping
# ============================================================

AUTHENTICA_STATUS_MAPPING = {
    "sent": "sent",
    "delivered": "delivered",
    "failed": "failed",
    "rejected": "rejected",
    "verified": "verified",
    "expired": "expired",

    **env_json_object(
        "AUTHENTICA_STATUS_MAPPING"
    ),
}


# ============================================================
# Authentica Webhook
# ============================================================

AUTHENTICA_WEBHOOK_SECRET = os.getenv(
    "AUTHENTICA_WEBHOOK_SECRET",
    "",
)


AUTHENTICA_WEBHOOK_SIGNATURE_HEADER = (
    os.getenv(
        "AUTHENTICA_WEBHOOK_SIGNATURE_HEADER",
        "",
    ).strip()
)


AUTHENTICA_WEBHOOK_TIMESTAMP_HEADER = (
    os.getenv(
        "AUTHENTICA_WEBHOOK_TIMESTAMP_HEADER",
        "",
    ).strip()
)


AUTHENTICA_WEBHOOK_SIGNATURE_ALGORITHM = (
    os.getenv(
        "AUTHENTICA_WEBHOOK_SIGNATURE_ALGORITHM",
        "",
    ).strip()
)


AUTHENTICA_WEBHOOK_VERIFICATION_ENABLED = (
    env_bool(
        "AUTHENTICA_WEBHOOK_VERIFICATION_ENABLED",
        False,
    )
)


AUTHENTICA_WEBHOOK_REPLAY_PROTECTION_ENABLED = (
    env_bool(
        "AUTHENTICA_WEBHOOK_REPLAY_PROTECTION_ENABLED",
        False,
    )
)


AUTHENTICA_WEBHOOK_EVENT_ID_MAPPING = (
    env_json_object(
        "AUTHENTICA_WEBHOOK_EVENT_ID_MAPPING"
    )
)


AUTHENTICA_WEBHOOK_MAPPING = (
    env_json_object(
        "AUTHENTICA_WEBHOOK_MAPPING"
    )
)


AUTHENTICA_VERIFICATION_WEBHOOK_MAPPING = (
    env_json_object(
        "AUTHENTICA_VERIFICATION_WEBHOOK_MAPPING"
    )
)


# ============================================================
# Authentica Future Payload Mappings
# ============================================================

AUTHENTICA_NAFATH_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_NAFATH_PAYLOAD_MAPPING"
    )
)


AUTHENTICA_FACE_PAYLOAD_MAPPING = (
    env_json_object(
        "AUTHENTICA_FACE_PAYLOAD_MAPPING"
    )
)


# ============================================================
# Email Configuration
# ============================================================

EMAIL_BACKEND = (
    os.getenv(
        "DJANGO_EMAIL_BACKEND",
        (
            "django.core.mail.backends."
            "console.EmailBackend"
            if DEBUG
            else (
                "django.core.mail.backends."
                "smtp.EmailBackend"
            )
        ),
    ).strip()
    or (
        "django.core.mail.backends."
        "console.EmailBackend"
        if DEBUG
        else (
            "django.core.mail.backends."
            "smtp.EmailBackend"
        )
    )
)


EMAIL_HOST = os.getenv(
    "EMAIL_HOST",
    "",
).strip()


EMAIL_PORT = env_int(
    "EMAIL_PORT",
    587,
    minimum=1,
    maximum=65535,
)


EMAIL_HOST_USER = os.getenv(
    "EMAIL_HOST_USER",
    "",
).strip()


EMAIL_HOST_PASSWORD = os.getenv(
    "EMAIL_HOST_PASSWORD",
    "",
)


EMAIL_USE_TLS = env_bool(
    "EMAIL_USE_TLS",
    True,
)


EMAIL_USE_SSL = env_bool(
    "EMAIL_USE_SSL",
    False,
)


if (
    EMAIL_USE_TLS
    and EMAIL_USE_SSL
):
    raise ImproperlyConfigured(
        "EMAIL_USE_TLS and EMAIL_USE_SSL "
        "cannot both be true."
    )


EMAIL_TIMEOUT = env_int(
    "EMAIL_TIMEOUT",
    10,
    minimum=1,
)


DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "",
).strip()


# ============================================================
# Cloudinary Configuration
# ============================================================

CLOUDINARY_CLOUD_NAME = os.getenv(
    "CLOUDINARY_CLOUD_NAME",
    "",
).strip()


CLOUDINARY_API_KEY = os.getenv(
    "CLOUDINARY_API_KEY",
    "",
).strip()


CLOUDINARY_API_SECRET = os.getenv(
    "CLOUDINARY_API_SECRET",
    "",
)


CLOUDINARY_STORAGE = {
    "CLOUD_NAME": (
        CLOUDINARY_CLOUD_NAME
    ),
    "API_KEY": (
        CLOUDINARY_API_KEY
    ),
    "API_SECRET": (
        CLOUDINARY_API_SECRET
    ),
}


if not DEBUG:
    if not all(
        (
            CLOUDINARY_CLOUD_NAME,
            CLOUDINARY_API_KEY,
            CLOUDINARY_API_SECRET,
        )
    ):
        raise ImproperlyConfigured(
            "Cloudinary credentials "
            "must be set in production."
        )

    INSTALLED_APPS += [
        "cloudinary",
        "cloudinary_storage",
    ]

    STORAGES[
        "default"
    ] = {
        "BACKEND": (
            "apps.core.storage."
            "SafeCloudinaryMediaStorage"
        ),
    }


# ============================================================
# Legacy SMS Validation
# ============================================================

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