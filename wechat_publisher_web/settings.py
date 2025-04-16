# wechat_publisher_web/settings.py

from pathlib import Path
import os
from dotenv import load_dotenv
import logging # Import logging

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Load .env file ---
# Ensure you have a .env file in the project root (same level as manage.py)
# Example .env content:
# DJANGO_SECRET_KEY='your-secret-key'
# DEBUG=True
# ALLOWED_HOSTS=127.0.0.1,localhost
# WECHAT_APP_ID='your_wechat_app_id'
# WECHAT_SECRET='your_wechat_secret'
# GOOGLE_APPLICATION_CREDENTIALS='/path/to/your/gcs-keyfile.json'
# GS_BUCKET_NAME='your-gcs-bucket-name'
# GS_PROJECT_ID='your-gcp-project-id'
# DB_ENGINE='django.db.backends.sqlite3' # or postgresql, mysql
# DB_NAME='db.sqlite3' # or your db name

dotenv_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=dotenv_path)
logger_for_settings = logging.getLogger(__name__) # Use a logger for settings validation

# --- Create cache and log directories if they don't exist ---
CACHE_DIR = BASE_DIR / 'cache'
LOG_DIR = BASE_DIR / 'logs'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-default-key-for-dev')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "publisher.apps.PublisherConfig", # Your app
    "rest_framework",                 # Django REST framework
    "storages",                       # django-storages app
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "wechat_publisher_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / 'templates'], # Project-level templates
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

WSGI_APPLICATION = "wechat_publisher_web.wsgi.application"
ASGI_APPLICATION = "wechat_publisher_web.asgi.application"


# Database
# Uses environment variables with defaults for SQLite
DATABASES = {
    "default": {
        "ENGINE": os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        "NAME": os.getenv('DB_NAME', BASE_DIR / "db.sqlite3"),
        # Add other DB settings (USER, PASSWORD, HOST, PORT) as needed from env vars
        # if not using SQLite
    }
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles" # Adjust to your timezone
USE_I18N = True
USE_TZ = True # Recommended for timezone-aware datetimes


# Static files (CSS, JavaScript, Images) served by Django in development
STATIC_URL = "/static/"
# Directory where collectstatic will gather files for deployment
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Additional locations for static files (project-level static)
STATICFILES_DIRS = [BASE_DIR / 'static']


# Media files (User uploaded files) - Handled by STORAGES['default'] (GCS)
MEDIA_URL = '/media/' # Base URL for media files (often served directly from GCS)
# MEDIA_ROOT is less relevant when using cloud storage like GCS for the default backend,
# but Django might still use it internally for some operations or if you switch backends.
MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- WeChat API Settings ---
WECHAT_APP_ID = os.getenv('WECHAT_APP_ID')
WECHAT_SECRET = os.getenv('WECHAT_SECRET')
WECHAT_BASE_URL = os.getenv('WECHAT_BASE_URL', 'https://api.weixin.qq.com')
WECHAT_DRAFT_PLACEHOLDER_CONTENT = os.getenv(
    'WECHAT_DRAFT_PLACEHOLDER_CONTENT',
    '<p>Content is being prepared...</p>'
)
# Optional: Define path for media cache if used by publishing_engine
WECHAT_MEDIA_CACHE_PATH = os.getenv('WECHAT_MEDIA_CACHE_PATH', str(CACHE_DIR / 'wechat_media_cache.json'))


# --- Google Cloud Storage Settings ---
# These settings are used by the storages backend defined below
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
GS_BUCKET_NAME = os.getenv('GS_BUCKET_NAME')
GS_PROJECT_ID = os.getenv('GS_PROJECT_ID')

# Optional: Set default ACL for new objects if needed (e.g., 'publicRead')
# GS_DEFAULT_ACL = 'projectPrivate' # Default is usually private

# --- Django Storages Configuration (Modern Method) ---
STORAGES = {
    "default": {
        # Use the GCS backend for default file storage (media files)
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        # The backend automatically picks up GOOGLE_APPLICATION_CREDENTIALS,
        # GS_BUCKET_NAME, GS_PROJECT_ID, GS_DEFAULT_ACL etc. from settings.
    },
    "staticfiles": {
        # Use Django's default static files storage for development.
        # For production, you might use WhiteNoise or configure GCS here too.
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# --- Validation for essential settings ---
if not all([WECHAT_APP_ID, WECHAT_SECRET]):
    logger_for_settings.warning("WeChat APP_ID or SECRET not configured in environment variables.")

if not all([GS_BUCKET_NAME, GS_PROJECT_ID]):
    logger_for_settings.warning("Google Cloud Storage settings (Bucket Name, Project ID) not fully configured in environment variables.")
# Note: GOOGLE_APPLICATION_CREDENTIALS might not be a file path in all environments (e.g., Cloud Run).
# This check is useful for local/VM setups using a key file.
if GOOGLE_APPLICATION_CREDENTIALS and not Path(GOOGLE_APPLICATION_CREDENTIALS).is_file():
     # Check if the path looks like it *should* be a file before warning
     if "/" in GOOGLE_APPLICATION_CREDENTIALS or "\\" in GOOGLE_APPLICATION_CREDENTIALS:
          logger_for_settings.warning(
              f"Google Cloud Storage credentials file not found at the path specified by "
              f"GOOGLE_APPLICATION_CREDENTIALS: {GOOGLE_APPLICATION_CREDENTIALS}"
          )
     # else: assume it might be non-file credentials (like workload identity)

# --- Path to the CSS file for HTML previews ---
PREVIEW_CSS_FILE_PATH = BASE_DIR / 'publisher/static/publisher/css/style.css'
if not PREVIEW_CSS_FILE_PATH.is_file():
    logger_for_settings.warning(f"Preview CSS file not found at expected location: {PREVIEW_CSS_FILE_PATH}")


# Logging Configuration (ensure logs directory exists)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False, # Keep False for pytest caplog compatibility
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module}:{lineno} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'DEBUG' if DEBUG else 'INFO',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'django.log', # Use LOG_DIR
            'maxBytes': 1024*1024*5, # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'publisher_file': {
             'level': 'DEBUG',
             'class': 'logging.handlers.RotatingFileHandler',
             'filename': LOG_DIR / 'publisher.log', # Use LOG_DIR
             'maxBytes': 1024*1024*5, # 5 MB
             'backupCount': 3,
             'formatter': 'verbose',
         },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False, # Avoid double logging with root logger
        },
         'django.request': { # Specific logger for request errors
             'handlers': ['file'], # Log request errors to file
             'level': 'ERROR',
             'propagate': False,
         },
        'publisher': { # Logger for your app (views, services, models etc)
            'handlers': ['console', 'publisher_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False, # Avoid double logging with root
        },
        'publishing_engine': { # Logger for the engine sub-package
             'handlers': ['console', 'publisher_file'],
             'level': 'DEBUG' if DEBUG else 'INFO',
             'propagate': False, # Avoid double logging with root
         },
        'google.cloud': { # Logger for Google Cloud client libraries
            'handlers': ['console', 'file'],
            'level': 'INFO', # Adjust level as needed (e.g., WARNING in production)
            'propagate': False,
        },
        'storages': { # Logger for django-storages itself
             'handlers': ['console', 'file'],
             'level': 'INFO', # Adjust level as needed
             'propagate': False,
        }
    },
}
