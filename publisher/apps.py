# /Users/junluo/Documents/wechat_publisher_web/publisher/apps.py
"""
App configuration for the 'publisher' Django app.
"""
from django.apps import AppConfig

class PublisherConfig(AppConfig):
    """
    Configuration class for the 'publisher' app.
    """
    # Use BigAutoField for primary keys by default if not overridden elsewhere
    default_auto_field = 'django.db.models.BigAutoField'
    # The name of the app package
    name = 'publisher'
    # Optional: A human-readable name for the admin site
    # verbose_name = "WeChat Publishing Tools"

    # def ready(self):
    #     """
    #     Optional: Code to run when the app is ready.
    #     For example, import signals here.
    #     """
    #     # import publisher.signals
    #     pass