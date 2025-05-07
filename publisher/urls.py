# /Users/junluo/Documents/wechat_publisher_web/publisher/urls.py
"""
URL configuration for the publisher app.
"""
from django.urls import path
from . import views # Import views from the current app

app_name = 'publisher' # Namespace for URLs

urlpatterns = [
    # This maps the root path (relative to where these URLs are included)
    # to your UploadFormView. Since the main urls.py includes this at "",
    # this view will handle requests to the site's root (e.g., http://127.0.0.1:8000/).
    path('', views.UploadFormView.as_view(), name='upload_form'),

    # These API endpoints will be accessible at /api/process/ and /api/confirm/
    path('api/process/', views.ProcessPreviewAPIView.as_view(), name='process_preview_api'),
    path('api/confirm/', views.ConfirmPublishAPIView.as_view(), name='confirm_publish_api'),
]
