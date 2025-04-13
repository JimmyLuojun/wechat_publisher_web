# /Users/junluo/Documents/wechat_publisher_web/publisher/urls.py
"""
URL configuration for the publisher app.

Maps URL paths to their corresponding API views.
"""
from django.urls import path
from . import views # Import views from the current app

app_name = 'publisher' # Namespace for URLs (optional but recommended)

urlpatterns = [
    # Endpoint for Request 1: Process Upload and Generate Preview
    path('api/process/', views.ProcessPreviewAPIView.as_view(), name='process_preview_api'),

    # Endpoint for Request 2: Confirm and Publish to WeChat Drafts
    # Consider if task_id should be in the URL or just the POST body.
    # Keeping it simpler here by expecting it in the POST body.
    path('api/confirm/', views.ConfirmPublishAPIView.as_view(), name='confirm_publish_api'),

    # Add path for the frontend upload page (if not serving from root)
    # Example: If you want the upload page at /publisher/upload/
    # path('upload/', views.upload_page_view, name='upload_page'), # Needs a standard Django view
]

# Note: You'll also need to include these URLs in your main project's urls.py
# Example in wechat_publisher_web/urls.py:
# from django.urls import path, include
#
# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path('publisher/', include('publisher.urls', namespace='publisher')), # Include app URLs
#     # ... other project urls
# ]
# Also configure MEDIA_URL serving in project urls.py for development previews.