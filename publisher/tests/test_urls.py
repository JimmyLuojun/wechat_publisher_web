# /Users/junluo/Documents/wechat_publisher_web/publisher/tests/test_urls.py
"""
Tests for the URL configuration of the publisher app.
"""
from django.urls import reverse, resolve
from django.test import SimpleTestCase

# Import the views referenced in urls.py
from ..views import ProcessPreviewAPIView, ConfirmPublishAPIView # Add upload_page_view if used

class PublisherURLTests(SimpleTestCase):
    """Test URL patterns resolve to the correct views."""

    def test_process_preview_url_resolves(self):
        """Test that the process API URL resolves to the correct view."""
        url = reverse('publisher:process_preview_api') # Use namespaced name
        self.assertEqual(resolve(url).func.view_class, ProcessPreviewAPIView)

    def test_confirm_publish_url_resolves(self):
        """Test that the confirm API URL resolves to the correct view."""
        url = reverse('publisher:confirm_publish_api')
        self.assertEqual(resolve(url).func.view_class, ConfirmPublishAPIView)

    # Add test for upload_page_view if you added that URL pattern
    # def test_upload_page_url_resolves(self):
    #     """Test that the upload page URL resolves to the correct view."""
    #     url = reverse('publisher:upload_page')
    #     self.assertEqual(resolve(url).func, upload_page_view)