# wechat_publisher_web/settings.py

from pathlib import Path
import os
from dotenv import load_dotenv
import logging # Import logging
import logging.config # Import logging config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Load .env file ---
dotenv_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=dotenv_path)
logger_for_settings = logging.getLogger(__name__)

# --- Create cache and log directories if they don't exist ---
CACHE_DIR = BASE_DIR / 'cache'
LOG_DIR = BASE_DIR / 'logs' # Define LOG_DIR before using it in LOGGING
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


DATABASES = {
    "default": {
        "ENGINE": os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        "NAME": os.getenv('DB_NAME', BASE_DIR / "db.sqlite3"),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles" # Adjust to your timezone
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- WeChat API Settings ---
WECHAT_APP_ID = os.getenv('WECHAT_APP_ID')
WECHAT_SECRET = os.getenv('WECHAT_SECRET')
WECHAT_BASE_URL = os.getenv('WECHAT_BASE_URL', 'https://api.weixin.qq.com')
WECHAT_DRAFT_PLACEHOLDER_CONTENT = os.getenv(
    'WECHAT_DRAFT_PLACEHOLDER_CONTENT',
    '<p>Content is being prepared...</p>'
)
WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT = None

# --- Django Cache Configuration ---
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(CACHE_DIR),
        'TIMEOUT': WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT,
        'OPTIONS': { 'MAX_ENTRIES': 1000 }
    }
}

# --- Google Cloud Storage Settings ---
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
GS_BUCKET_NAME = os.getenv('GS_BUCKET_NAME')
GS_PROJECT_ID = os.getenv('GS_PROJECT_ID')

# --- Django Storages Configuration ---
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# --- Validation for essential settings ---
if not all([WECHAT_APP_ID, WECHAT_SECRET]):
    logger_for_settings.warning("WeChat APP_ID or SECRET not configured in environment variables.")
# ... Add other validation if needed ...

# --- Path to the CSS file for HTML previews ---
PREVIEW_CSS_FILE_PATH = BASE_DIR / 'publisher/static/publisher/css/style.css'
if not Path(PREVIEW_CSS_FILE_PATH).is_file():
     logger_for_settings.warning(f"Preview CSS file not found at: {PREVIEW_CSS_FILE_PATH}")


# --- Logging Configuration ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False, # Keep existing loggers active
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        # Handler for console output (for development)
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO', # Show DEBUG logs on console if DEBUG=True
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        # Handler for general Django logs -> logs/django.log
        'django_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'django.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5, # Keep 5 backup files
            'formatter': 'verbose',
        },
        # Handler specifically for publisher app -> logs/publisher.log
        'publisher_file': {
            'level': 'DEBUG', # Capture DEBUG, INFO, WARNING, ERROR, CRITICAL from publisher app
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'publisher.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # Root logger for Django related messages
        'django': {
            'handlers': ['console', 'django_file'], # Send to console and django.log
            'level': 'INFO', # Process INFO level and above
            'propagate': False, # Don't pass to root logger
        },
        # Logger for your 'publisher' application
        'publisher': {
            'handlers': ['console', 'publisher_file'], # Send to console and publisher.log
            'level': 'DEBUG', # Process DEBUG level and above for this logger
            'propagate': False, # Don't pass messages up to the 'django' logger
        },
        # Example: Catch logs from other specific libraries if needed
        # 'storages': {
        #     'handlers': ['console', 'django_file'],
        #     'level': 'INFO',
        #     'propagate': False,
        # },
    },
}

# Apply the logging configuration
logging.config.dictConfig(LOGGING)