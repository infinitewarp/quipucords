"""
Django settings for quipucords project.

Generated by 'django-admin startproject' using Django 1.11.5.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""

import logging
import os
import random
import string
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from .featureflag import FeatureFlag

# Get an instance of a logger
logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

env = environ.Env()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = Path(__file__).absolute().parent.parent

PRODUCTION = env.bool("PRODUCTION", False)

QPC_DISABLE_THREADED_SCAN_MANAGER = env.bool("QPC_DISABLE_THREADED_SCAN_MANAGER", False)


def create_random_key():
    """Create a randomized string."""
    return "".join(
        [
            random.SystemRandom().choice(
                string.ascii_letters + string.digits + string.punctuation
            )
            for _ in range(50)
        ]
    )


QPC_SSH_CONNECT_TIMEOUT = env.int("QPC_SSH_CONNECT_TIMEOUT", 60)
QPC_SSH_INSPECT_TIMEOUT = env.int("QPC_SSH_INSPECT_TIMEOUT", 120)

NETWORK_INSPECT_JOB_TIMEOUT = env.int("NETWORK_INSPECT_JOB_TIMEOUT", 10800)  # 3 hours
NETWORK_CONNECT_JOB_TIMEOUT = env.int("NETWORK_CONNECT_JOB_TIMEOUT", 600)  # 10 minutes

QPC_CONNECT_TASK_TIMEOUT = env.int("QPC_CONNECT_TASK_TIMEOUT", 30)
QPC_INSPECT_TASK_TIMEOUT = env.int("QPC_INSPECT_TASK_TIMEOUT", 600)

ANSIBLE_LOG_LEVEL = env.int("ANSIBLE_LOG_LEVEL", 0)

if PRODUCTION:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SESSION_EXPIRE_AT_BROWSER_CLOSE = True

DJANGO_SECRET_PATH = Path(env.str("DJANGO_SECRET_PATH", str(BASE_DIR / "secret.txt")))
if not DJANGO_SECRET_PATH.exists():
    SECRET_KEY = create_random_key()
    DJANGO_SECRET_PATH.write_text(SECRET_KEY, encoding="utf-8")
else:
    SECRET_KEY = DJANGO_SECRET_PATH.read_text(encoding="utf-8").strip()

# SECURITY WARNING: Running with DEBUG=True is a *BAD IDEA*, but this is unfortunately
# necessary because in some cases we still need to serve static files through Django.
# Please consider this note from the official Django docs:
# > This view will only work if DEBUG is True.
# > That’s because this view is grossly inefficient and probably insecure. This is only
# > intended for local development, and should never be used in production.
# TODO FIXME Remove this dangerous default.  # pylint: disable=fixme
DEBUG = env.bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOST_LIST", default=["*"])

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "api",
]

if not PRODUCTION:
    INSTALLED_APPS.append("coverage")


MIDDLEWARE = [
    "api.common.middleware.ServerVersionMiddle",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]

ROOT_URLCONF = "quipucords.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(os.path.dirname(__file__), "templates").replace("\\", "/"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

LOGIN_REDIRECT_URL = "/client/"

WSGI_APPLICATION = "quipucords.wsgi.application"

DEFAULT_PAGINATION_CLASS = "api.common.pagination.StandardResultsSetPagination"

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": DEFAULT_PAGINATION_CLASS,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "api.user.authentication.QuipucordsExpiringTokenAuthentication",
    ),
}

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

# Database Management System could be 'sqlite' or 'postgresql'
QPC_DBMS = env.str("QPC_DBMS", "postgres").lower()
allowed_db_engines = ["sqlite", "postgres"]
if QPC_DBMS not in allowed_db_engines:
    raise ImproperlyConfigured(f"QPC_DBMS must be one of {allowed_db_engines}")

if QPC_DBMS == "sqlite":
    # If user enters an invalid QPC_DBMS, use default postgresql
    DEV_DB = os.path.join(BASE_DIR, "db.sqlite3")
    PROD_DB = os.path.join(env.str("DJANGO_DB_PATH", str(BASE_DIR)), "db.sqlite3")
    DB_PATH = PROD_DB if PRODUCTION else DEV_DB
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DB_PATH,
            "TEST": {"NAME": ":memory:"},
        }
    }
elif QPC_DBMS == "postgres":
    # The following variables are only relevant when using a postgres database:
    QPC_DBMS_DATABASE = env.str("QPC_DBMS_DATABASE", "qpc")
    QPC_DBMS_USER = env.str("QPC_DBMS_USER", "qpc")
    QPC_DBMS_PASSWORD = env.str("QPC_DBMS_PASSWORD", "qpc")
    QPC_DBMS_HOST = env.str("QPC_DBMS_HOST", "localhost")
    QPC_DBMS_PORT = env.int("QPC_DBMS_PORT", 54321)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": QPC_DBMS_DATABASE,
            "USER": QPC_DBMS_USER,
            "PASSWORD": QPC_DBMS_PASSWORD,
            "HOST": QPC_DBMS_HOST,
            "PORT": QPC_DBMS_PORT,
        }
    }

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators
NAME = "NAME"
USER_ATTRIBUTE_SIMILARITY_VALIDATOR = (
    "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
)
MINIMUM_LENGTH_VALIDATOR = (
    "django.contrib.auth.password_validation.MinimumLengthValidator"
)
COMMON_PASSWORD_VALIDATOR = (
    "django.contrib.auth.password_validation.CommonPasswordValidator"
)
NUMERIC_PASSWORD_VALIDATOR = (
    "django.contrib.auth.password_validation.NumericPasswordValidator"
)
AUTH_PASSWORD_VALIDATORS = [
    {
        NAME: USER_ATTRIBUTE_SIMILARITY_VALIDATOR,
    },
    {
        NAME: MINIMUM_LENGTH_VALIDATOR,
    },
    {
        NAME: COMMON_PASSWORD_VALIDATOR,
    },
    {
        NAME: NUMERIC_PASSWORD_VALIDATOR,
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATIC_URL = "/client/"

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "client"),
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

LOGGING_FORMATTER = env.str("DJANGO_LOG_FORMATTER", "simple")
DJANGO_LOGGING_LEVEL = env.str("DJANGO_LOG_LEVEL", "INFO")
QUIPUCORDS_LOGGING_LEVEL = env.str("QUIPUCORDS_LOG_LEVEL", "INFO")
LOGGING_HANDLERS = env.list("DJANGO_LOG_HANDLERS", default=["console"])
VERBOSE_FORMATTING = (
    "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"
)

LOG_DIRECTORY = Path(env.str("LOG_DIRECTORY", str(BASE_DIR)))
DEFAULT_LOG_FILE = LOG_DIRECTORY / "app.log"
LOGGING_FILE = Path(env.str("DJANGO_LOG_FILE", str(DEFAULT_LOG_FILE)))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": VERBOSE_FORMATTING},
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": LOGGING_FORMATTER},
        "file": {
            "level": QUIPUCORDS_LOGGING_LEVEL,
            "class": "logging.FileHandler",
            "filename": LOGGING_FILE,
            "formatter": LOGGING_FORMATTER,
        },
    },
    "loggers": {
        "django": {
            "handlers": LOGGING_HANDLERS,
            "level": DJANGO_LOGGING_LEVEL,
        },
        "api.details_report": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "api.deployments_report": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "api.scan": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "api.scantask": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "api.scanjob": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "api.status": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "fingerprinter": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "api.signal.scanjob_signal": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.callback": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.manager": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.job": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.task": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.network": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.vcenter": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "scanner.satellite": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
        "quipucords.environment": {
            "handlers": LOGGING_HANDLERS,
            "level": QUIPUCORDS_LOGGING_LEVEL,
        },
    },
}

# Reverse default behavior to avoid host key checking
os.environ.setdefault("ANSIBLE_HOST_KEY_CHECKING", "False")

QPC_EXCLUDE_INTERNAL_FACTS = env.bool("QPC_EXCLUDE_INTERNAL_FACTS", True)
QPC_TOKEN_EXPIRE_HOURS = env.int("QPC_TOKEN_EXPIRE_HOURS", 24)
QPC_INSIGHTS_REPORT_SLICE_SIZE = env.int("QPC_INSIGHTS_REPORT_SLICE_SIZE", 10000)
QPC_INSIGHTS_DATA_COLLECTOR_LABEL = env.str("QPC_INSIGHTS_DATA_COLLECTOR_LABEL", "qpc")

# Load Feature Flags
QPC_FEATURE_FLAGS = FeatureFlag()
