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
logger_for_settings = logging.getLogger(__name__) # Logger for messages during settings load

# --- Create cache and log directories if they don't exist ---
CACHE_DIR = BASE_DIR / 'cache'
LOG_DIR = BASE_DIR / 'logs' # Define LOG_DIR before using it in LOGGING
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-default-key-for-dev')
# Determine DEBUG status from environment variable
DEBUG_FLAG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

logger_for_settings.info(f"Django DEBUG mode is set to: {DEBUG_FLAG}")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "publisher.apps.PublisherConfig", # Your app
    # Assuming publishing_engine is used by publisher but not a separate Django app
    # If publishing_engine IS a Django app, add it here too.
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
# Use current date to set timezone. America/Los_Angeles is current timezone.
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / 'staticfiles' # For collectstatic
STATICFILES_DIRS = [BASE_DIR / 'static'] # For development server finding static files

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media' # User uploaded files

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- WeChat API Settings ---
WECHAT_APP_ID = os.getenv('WECHAT_APP_ID')
WECHAT_SECRET = os.getenv('WECHAT_SECRET')
WECHAT_BASE_URL = os.getenv('WECHAT_BASE_URL', 'https://api.weixin.qq.com')
WECHAT_DRAFT_PLACEHOLDER_CONTENT = os.getenv(
    'WECHAT_DRAFT_PLACEHOLDER_CONTENT',
    '<p>Please copy and paste your preview content opened in your browser here...</p>'
)
# Cache timeout for permanent media (None means cache forever)
WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT = None

# --- Django Cache Configuration ---
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(CACHE_DIR),
        'TIMEOUT': WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT, # Use the setting from above
        'OPTIONS': { 'MAX_ENTRIES': 1000 }
    }
}

# --- Google Cloud Storage Settings (Optional - if used) ---
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
GS_BUCKET_NAME = os.getenv('GS_BUCKET_NAME')
GS_PROJECT_ID = os.getenv('GS_PROJECT_ID')


# --- Django Storages Configuration (Corrected) ---
# Use the modern STORAGES setting. DEFAULT_FILE_STORAGE is deprecated when using STORAGES.

# Determine the backend based on GS_BUCKET_NAME
if GS_BUCKET_NAME:
    default_storage_backend = 'storages.backends.gcloud.GoogleCloudStorage'
    logger_for_settings.info(f"Using GoogleCloudStorage backend for default storage (Bucket: {GS_BUCKET_NAME}).")
else:
    default_storage_backend = 'django.core.files.storage.FileSystemStorage'
    logger_for_settings.info("Using FileSystemStorage backend for default storage.")

# Define the STORAGES dictionary (preferred method)
STORAGES = {
    "default": {
        "BACKEND": default_storage_backend,
        # You might need to specify options for GCS if using it:
        # "OPTIONS": {
        #     "bucket_name": GS_BUCKET_NAME,
        # }
    },
    "staticfiles": {
        # Typically keep this as standard StaticFilesStorage unless deploying static files to GCS too
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# --- REMOVED deprecated setting ---
# DEFAULT_FILE_STORAGE = ... # DO NOT DEFINE THIS IF USING STORAGES


# --- Validation for essential settings ---
if not all([WECHAT_APP_ID, WECHAT_SECRET]):
    logger_for_settings.warning("WeChat APP_ID or SECRET not configured in environment variables.")
# Corrected validation check: Check the determined backend in STORAGES
if STORAGES['default']['BACKEND'] == 'storages.backends.gcloud.GoogleCloudStorage' and not GS_BUCKET_NAME:
     logger_for_settings.error("GoogleCloudStorage is set as default storage backend, but GS_BUCKET_NAME is missing!")

# --- Path to the CSS file for HTML previews ---
PREVIEW_CSS_FILE_PATH = BASE_DIR / 'publisher/static/publisher/css/style.css'
if not Path(PREVIEW_CSS_FILE_PATH).is_file():
     logger_for_settings.warning(f"Preview CSS file not found at: {PREVIEW_CSS_FILE_PATH}")


# --- Logging Configuration ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False, # Keep existing loggers active (like Django's)
    'formatters': {
        'verbose': {
            # Example: Include process/thread IDs, good for server logs
            'format': '{levelname} {asctime} {module} P{process:d} T{thread:d} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            # Format used in your previous console output
            'format': '{levelname} {asctime} {name}: {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S,%f', # Add milliseconds if needed
        },
    },
    'handlers': {
        # Handler for console output (for development/debugging)
        'console': {
            # Ensure console always shows DEBUG level messages during development
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple', # Use the format matching previous logs
        },
        # Handler for general Django logs -> logs/django.log
        'django_file': {
            'level': 'INFO', # Log INFO and above for Django core
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'django.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5, # Keep 5 backup files
            'formatter': 'verbose',
            'encoding': 'utf-8', # Explicitly set encoding
        },
        # Handler specifically for publisher app -> logs/publisher.log
        'publisher_file': {
            'level': 'DEBUG', # Capture DEBUG and above from publisher app
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'publisher.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose', # Use detailed format for file logs
            'encoding': 'utf-8', # Explicitly set encoding
        },
    },
    'loggers': {
        # Root logger for Django related messages
        'django': {
            'handlers': ['console', 'django_file'], # Send to console and django.log
            'level': 'INFO', # Process INFO level and above for Django itself
            'propagate': False, # Don't pass Django messages to higher level loggers
        },
        # Logger for your 'publisher' application and its submodules
        'publisher': {
            'handlers': ['console', 'publisher_file'], # Send to console and publisher.log
            'level': 'DEBUG', # Process DEBUG level and above for this logger and its children
            'propagate': False, # Prevents duplication if root logger is configured
        },
        # --- ADDED THIS SECTION ---
        # Logger specifically for the 'publishing_engine' module and its children
        'publishing_engine': {
            'handlers': ['console', 'publisher_file'], # Send logs to the same handlers
            'level': 'DEBUG',                         # Process DEBUG level and above
            'propagate': False,                       # Prevent passing messages up further
        },
        # --------------------------
        # Logger for Django server messages (if you want to control them separately)
        'django.server': {
             'handlers': ['console', 'django_file'],
             'level': 'INFO', # Typically INFO is sufficient
             'propagate': False,
        },
    },
}

# Apply the logging configuration from the dictionary
logging.config.dictConfig(LOGGING)

# --- Django DEBUG setting ---
# Controls Django's internal debug features (like error pages)
DEBUG = DEBUG_FLAG

# --- Final check after all settings ---
logger_for_settings.info("Django settings loaded successfully.")