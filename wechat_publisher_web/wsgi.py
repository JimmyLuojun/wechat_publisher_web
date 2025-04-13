# /Users/junluo/Documents/wechat_publisher_web/wechat_publisher_web/wsgi.py
"""
WSGI config for the wechat_publisher_web project.

It exposes the WSGI callable as a module-level variable named ``application``.
This is used by WSGI-compatible web servers (like Gunicorn, uWSGI) to serve
your application synchronously.

For more information on this file, see
https://docs.djangoproject.com/en/stable/howto/deployment/wsgi/
"""
import os
from django.core.wsgi import get_wsgi_application

# Set the default Django settings module for the 'wsgi' application.
# Adjust 'wechat_publisher_web.settings' if your settings file is named differently
# or located elsewhere relative to the manage.py directory.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wechat_publisher_web.settings')

# Get the WSGI application instance for the Django project.
application = get_wsgi_application()