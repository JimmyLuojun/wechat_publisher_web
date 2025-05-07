# /Users/junluo/Documents/wechat_publisher_web/wechat_publisher_web/urls.py
"""
URL configuration for wechat_publisher_web project.
"""
from django.contrib import admin
from django.urls import path, include # Make sure include is imported
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    # This includes your publisher app's URLs starting from the root path ""
    path("", include("publisher.urls", namespace="publisher")),
]

# This part is for serving static and media files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
