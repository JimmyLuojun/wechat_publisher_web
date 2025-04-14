# /Users/junluo/Documents/wechat_publisher_web/publisher/urls.py
"""
URL configuration for the publisher app.

Maps URL paths to their corresponding API views.
"""
from django.urls import path
from . import views # Import views from the current app

app_name = 'publisher' # Namespace for URLs (optional but recommended)

urlpatterns = [
    # URL for the HTML form page - CHECK THIS LINE CAREFULLY
    path('upload/', views.UploadFormView.as_view(), name='upload_form'), # Make sure name='upload_form' is exact

    # URLs for the API endpoints
    path('api/process/', views.ProcessPreviewAPIView.as_view(), name='process_preview_api'),
    path('api/confirm/', views.ConfirmPublishAPIView.as_view(), name='confirm_publish_api'),
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