# /Users/junluo/Documents/wechat_publisher_web/wechat_publisher_web/asgi.py
"""
ASGI config for the wechat_publisher_web project.

It exposes the ASGI callable as a module-level variable named ``application``.
This is used by ASGI-compatible web servers (like Daphne, Uvicorn) to serve
your application asynchronously.

For more information on this file, see
https://docs.djangoproject.com/en/stable/howto/deployment/asgi/
"""
import os
from django.core.asgi import get_asgi_application

# Set the default Django settings module for the 'asgi' application.
# Adjust 'wechat_publisher_web.settings' if your settings file is named differently
# or located elsewhere relative to the manage.py directory.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wechat_publisher_web.settings')

# Get the ASGI application instance for the Django project.
application = get_asgi_application()

# You might add more ASGI middleware here later for things like WebSockets (Channels)
# For example:
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# import myapp.routing
#
# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AuthMiddlewareStack(
#         URLRouter(
#             myapp.routing.websocket_urlpatterns
#         )
#     ),
# })