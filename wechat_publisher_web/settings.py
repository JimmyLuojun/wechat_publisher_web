# /Users/junluo/Documents/wechat_publisher_web/wechat_publisher_web/settings.py
"""
Django settings for wechat_publisher_web project.
... (other imports remain the same) ...
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(Path(__file__).resolve().parent.parent, '.env'))

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Create cache directory if it doesn't exist ---
CACHE_DIR = BASE_DIR / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
# ---

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-default-key-for-dev')

# SECURITY WARNING: don't run with debug turned on in production!
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
    "publisher.apps.PublisherConfig", # Ensure your app name is correct
    "rest_framework",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", # Consider if needed for API views if using sessions
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "wechat_publisher_web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / 'templates'],
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
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        "NAME": os.getenv('DB_NAME', BASE_DIR / "db.sqlite3"),
        "USER": os.getenv('DB_USER', ''),
        "PASSWORD": os.getenv('DB_PASSWORD', ''),
        "HOST": os.getenv('DB_HOST', ''),
        "PORT": os.getenv('DB_PORT', ''),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles" # Example: Use your actual timezone
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / 'staticfiles' # Directory for collectstatic
STATICFILES_DIRS = [BASE_DIR / 'static'] # Directories to find static files


# Media files (User uploaded files)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Subdirectory within MEDIA_ROOT for content images used in articles
# Ensure this path component is URL-safe if needed elsewhere
CONTENT_IMAGES_SUBDIR = os.getenv('CONTENT_IMAGES_SUBDIR', 'uploads/content_images')


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# WeChat API Settings
WECHAT_APP_ID = os.getenv('WECHAT_APP_ID')
WECHAT_SECRET = os.getenv('WECHAT_APP_SECRET')
WECHAT_BASE_URL = os.getenv('WECHAT_BASE_URL', 'https://api.weixin.qq.com') # Default base URL

WECHAT_DRAFT_PLACEHOLDER_CONTENT = os.getenv(
    'WECHAT_DRAFT_PLACEHOLDER_CONTENT',
    '<p>Content is being prepared. Please edit in WeChat backend.</p>'
)

# --- Path to the Media Manager Cache ---
# Use the CACHE_DIR defined earlier
WECHAT_MEDIA_CACHE_PATH = os.getenv('WECHAT_MEDIA_CACHE_PATH', str(CACHE_DIR / 'wechat_media_cache.json'))

# Path to the CSS file for HTML previews (adjust path as needed)
PREVIEW_CSS_FILE_PATH = BASE_DIR / 'publisher/static/publisher/css/style.css' # Assuming CSS is in static

# Email Settings (Example, configure as needed)
# ... (email settings remain the same) ...

# Security Settings (Adjust for production!)
CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', 'False') == 'True'
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False') == 'True'
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False') == 'True'
# SECURE_HSTS_SECONDS = 31536000 # Example: Enable HSTS in production
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

# File Upload Settings (Example, configure as needed)
MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 5242880))  # Default 5MB
# ALLOWED_UPLOAD_EXTENSIONS are often better handled during form/serializer validation

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module}:{lineno} {process:d} {thread:d} {message}', # Added lineno
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
            'level': 'DEBUG' if DEBUG else 'INFO', # Console level based on DEBUG
        },
        'file': {
            'level': 'INFO', # Log INFO and above to file
            'class': 'logging.handlers.RotatingFileHandler', # Use rotating file handler
            'filename': BASE_DIR / 'logs/django.log',
            'maxBytes': 1024*1024*5, # 5 MB
            'backupCount': 5, # Keep 5 backup files
            'formatter': 'verbose',
        },
        # Example: Handler for publisher app specifically
        'publisher_file': {
             'level': 'DEBUG', # Log DEBUG and above for publisher app
             'class': 'logging.handlers.RotatingFileHandler',
             'filename': BASE_DIR / 'logs/publisher.log',
             'maxBytes': 1024*1024*5, # 5 MB
             'backupCount': 3,
             'formatter': 'verbose',
         },
    },
    'root': {
        # Default handler if not specified by logger
        'handlers': ['console', 'file'],
        'level': 'INFO', # Root level
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False, # Don't pass to root logger
        },
        'django.request': { # Capture request errors
             'handlers': ['file'],
             'level': 'ERROR',
             'propagate': False,
         },
        'publisher': { # Logger for your app
            'handlers': ['console', 'publisher_file'], # Use specific handler
            'level': 'DEBUG' if DEBUG else 'INFO', # Level based on DEBUG
            'propagate': False, # Don't pass to root logger
        },
        # Add other third-party library loggers if needed
         'publishing_engine': { # Example for the engine
             'handlers': ['console', 'publisher_file'], # Log to same file as publisher
             'level': 'INFO',
             'propagate': False,
         },
    },
}