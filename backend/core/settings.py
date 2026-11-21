"""
Django settings for Siora One.

Every deployment-specific value comes from environment variables, so the same
settings module runs locally (values from backend/.env) and on Vercel (values
from the project's Environment Variables). See backend/.env.example.
"""

import os
import warnings
from pathlib import Path
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Only backend/.env is loaded. Never put production credentials there: the
# local dev server would then read and write the live database.
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None or value == '':
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name):
    return [item.strip() for item in os.getenv(name, '').split(',') if item.strip()]


# Set automatically by Vercel at build and run time.
IS_VERCEL = bool(os.getenv('VERCEL'))

# Matplotlib (pulled in by insightface) needs a writable cache dir; only /tmp is
# writable on Vercel and on the hardened VPS.
os.environ.setdefault('MPLCONFIGDIR', os.path.join('/tmp', 'matplotlib'))

# Suppress deprecation warnings from third-party libraries (insightface)
warnings.filterwarnings("ignore", category=FutureWarning, module="insightface")
warnings.filterwarnings("ignore", category=FutureWarning, module="skimage")


# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------

# Local development defaults to DEBUG on; Vercel defaults to DEBUG off.
DEBUG = env_bool('DEBUG', default=not IS_VERCEL)

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY must be set when DEBUG is off.')
    SECRET_KEY = 'django-insecure-local-development-only'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS') + ['localhost', '127.0.0.1']
if IS_VERCEL:
    ALLOWED_HOSTS.append('.vercel.app')
if DEBUG:
    # Lets phones on the same Wi-Fi reach the dev server by LAN IP / tunnel.
    ALLOWED_HOSTS.append('*')

# Public URL of the web app, e.g. https://siora-one.vercel.app
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')

# Browsers only. Native mobile apps don't send an Origin header, so CORS never
# blocks them; they authenticate with JWT Bearer tokens.
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(env_list('CORS_ALLOWED_ORIGINS') + [FRONTEND_URL]))
# Optional, e.g. ^https://siora-one-[a-z0-9-]+\.vercel\.app$ for preview deployments
CORS_ALLOWED_ORIGIN_REGEXES = env_list('CORS_ALLOWED_ORIGIN_REGEXES')

CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
    env_list('CSRF_TRUSTED_ORIGINS')
    + CORS_ALLOWED_ORIGINS
    + ['http://localhost:5173', 'http://127.0.0.1:5173']
))

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '3600'))
    X_FRAME_OPTIONS = 'DENY'


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# On Vercel the Neon integration sets DATABASE_URL (pooled). Locally, either set
# DATABASE_URL or the individual DB_* variables.

if os.getenv('DATABASE_URL'):
    import dj_database_url

    DATABASES = {
        'default': dj_database_url.config(
            env='DATABASE_URL',
            # Serverless: don't hold connections across invocations.
            conn_max_age=0 if IS_VERCEL else 600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'attendance_db_local'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# REST API (shared by the web app and the mobile app)
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '60'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '30'))),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Siora One API',
    'DESCRIPTION': (
        'REST API for the Siora One web and mobile apps. Authenticate with '
        'POST /api/auth/login/ and send the access token as "Authorization: Bearer <token>".'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# Trailing slashes are optional on API routes (see api/urls.py), so mobile
# clients never hit a redirect on POST.
APPEND_SLASH = True


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = 'api.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.getenv('TIME_ZONE', 'Asia/Kolkata')
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------

# Vercel runs collectstatic automatically when STATIC_ROOT is set and serves the
# result from its CDN (Django admin CSS/JS).
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Uploaded files (profile pictures). On Vercel the filesystem is read-only, so
# uploads go to Vercel Blob whenever BLOB_READ_WRITE_TOKEN is present.
# Locally they go to backend/media/.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

USE_VERCEL_BLOB = bool(os.getenv('BLOB_READ_WRITE_TOKEN'))

STORAGES = {
    'default': {
        'BACKEND': (
            'core.storage.VercelBlobStorage' if USE_VERCEL_BLOB
            else 'django.core.files.storage.FileSystemStorage'
        ),
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

if IS_VERCEL and not USE_VERCEL_BLOB:
    warnings.warn('BLOB_READ_WRITE_TOKEN is not set: uploaded files will be lost on Vercel.')


# ---------------------------------------------------------------------------
# Face recognition (InsightFace buffalo_l: detection + recognition only)
# ---------------------------------------------------------------------------
# FACE_MODEL_ROOT: directory that contains models/buffalo_l/*.onnx.
# FACE_MODEL_BASE_URL: where to download det_10g.onnx and w600k_r50.onnx from on
# a cold start when they aren't present (required on Vercel, optional locally,
# where insightface downloads the full pack into ~/.insightface itself).

FACE_MODEL_ROOT = os.getenv(
    'FACE_MODEL_ROOT',
    '/tmp/insightface' if IS_VERCEL else os.path.join(Path.home(), '.insightface'),
)
FACE_MODEL_BASE_URL = os.getenv('FACE_MODEL_BASE_URL', '').rstrip('/')


# ---------------------------------------------------------------------------
# Logging (console only: Vercel collects stdout/stderr)
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "api": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": True,
        },
        "api.face_recognition": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "api.views": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
