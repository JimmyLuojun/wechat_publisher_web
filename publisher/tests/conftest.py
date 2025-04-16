# tests/conftest.py

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path
import uuid
import logging # Added for side_effect logging

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.core.cache import cache

# --- Mock WeChat API Error ---
# Define a simple exception class to simulate WeChat API errors with errcode
class MockWeChatAPIError(Exception):
    """Custom exception to simulate WeChat API errors in tests."""
    def __init__(self, message="Mock WeChat API Error", errcode=None, errmsg=None):
        super().__init__(message)
        self.errcode = errcode
        self.errmsg = errmsg or message

# --- Fixtures ---

@pytest.fixture(autouse=True)
def setup_django_settings(settings, tmp_path):
    """
    Automatically configure Django settings for each test.
    - Uses pytest's tmp_path for MEDIA_ROOT to isolate test file artifacts.
    - Configures a unique in-memory cache (LocMemCache) for test isolation.
    - Sets dummy WeChat credentials required by the services.
    """
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_URL = "/media/"
    settings.PREVIEW_CSS_FILE_PATH = None
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': f'wechat-test-cache-{uuid.uuid4()}',
        }
    }
    settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT = None
    settings.WECHAT_APP_ID = "test_app_id"
    settings.WECHAT_SECRET = "test_secret"
    settings.WECHAT_BASE_URL = "https://api.example.com" # Mock base URL
    settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT = "<p>Test Placeholder Content</p>"
    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)

@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """
    Ensures the Django cache is explicitly cleared before each test runs.
    """
    cache.clear()

@pytest.fixture
def mock_wechat_api():
    """
    Mocks the publishing_engine.wechat.api module as used within publisher.services.
    Provides MagicMock objects for API functions with default return values.
    """
    with patch("publisher.services.wechat_api", autospec=True) as mock_api:
        mock_api.upload_thumb_media.return_value = "mock_thumb_media_id_from_upload"
        mock_api.upload_content_image.return_value = "http://mock.url/content_image.jpg"
        mock_api.add_draft.return_value = "mock_draft_media_id_success"
        yield mock_api

@pytest.fixture
def mock_wechat_auth():
    """
    Mocks the get_access_token function as used within publisher.services.
    """
    with patch("publisher.services.auth.get_access_token", autospec=True) as mock_auth:
        mock_auth.return_value = "mock_access_token_xyz" # Provide a mock token
        yield mock_auth

@pytest.fixture
def mock_metadata_reader():
    """
    Mocks the publishing_engine.core.metadata_reader module as used within publisher.services.
    Provides default return values for metadata extraction.
    """
    with patch("publisher.services.metadata_reader", autospec=True) as mock_reader:
        mock_reader.extract_metadata_and_content.return_value = (
            {"title": "Mock Title", "author": "Test Author"}, # metadata_dict
            "## Mock Markdown Body\n\nThis is mock content with ![Image](content_fixture.png)." # markdown_body_content (ensure it has an image reference for the processor mock)
        )
        yield mock_reader

# !!!!!!!!!! START OF CORRECTION !!!!!!!!!!
@pytest.fixture
def mock_html_processor(dummy_content_image_file): # Inject the dummy file fixture
    """
    Mocks the publishing_engine.core.html_processor module as used within publisher.services.
    Simulates calling the image_uploader callback.
    """
    logger = logging.getLogger("mock_html_processor_fixture")

    def process_html_side_effect(md_content, css_path, markdown_file_path, image_uploader):
        """
        This side effect function simulates the real process_html_content:
        1. It takes the arguments the real function would.
        2. It calls the image_uploader callback function passed to it.
        3. It returns a dummy HTML fragment.
        """
        logger.info("Mock process_html_content called.")
        # Simulate finding an image and needing to upload it.
        # We need a valid Path object for the image_uploader callback.
        # Let's create a dummy file path based on the injected fixture.
        # Note: The real processor would resolve paths relative to markdown_file_path.
        # For simplicity, we use the path from the fixture, assuming it represents
        # an image linked in the markdown. Ensure the callback can handle this path.

        # Create the dummy content image file physically in the temp dir if needed by callback
        # Or ensure the path passed to callback exists. Let's assume the callback
        # needs an existing file path. We can use the path from the fixture
        # if the fixture creates the file, or create one here.

        # Simplest approach: Assume the callback needs *a* Path object.
        # Let's construct a plausible path relative to the test's MEDIA_ROOT.
        # We need to ensure this path exists for the callback's hashing/upload logic.
        # The dummy_content_image_file fixture creates a file in tmp_path.
        # Let's find its absolute path within the test's MEDIA_ROOT.
        # We need the actual path where _save_uploaded_file_locally would save it.
        # This is getting complex. Let's simplify:
        # Assume the callback is robust enough to handle a Path object.
        # We'll just call it with a dummy path *name* relative to the markdown.
        # The callback in services.py actually resolves the path, so it needs to exist.

        # Let's try calling the callback with the *absolute* path of the dummy file fixture.
        # This assumes the fixture provides a file object with a resolvable path.
        try:
            # Create the dummy file in the expected location for the callback to find
            # The callback resolves relative to the *markdown file path* if relative.
            # Let's assume markdown_file_path is the parent of where content images are.
            # md_path = Path(markdown_file_path) # services.py passes this
            # dummy_image_name = "content_fixture.png" # From dummy markdown
            # dummy_image_path_for_callback = md_path.parent / dummy_image_name
            # dummy_image_path_for_callback.write_bytes(dummy_content_image_file.read())
            # dummy_content_image_file.seek(0)

            # ---- Simplified Approach: Create file in known test location ----
            # The callback in services.py will try to resolve it. Let's make it easy.
            # Assume the callback looks relative to the MD file's parent.
            # The MD file is saved in MEDIA_ROOT / 'uploads/markdown'
            # The content images are saved in MEDIA_ROOT / 'uploads/content_images'
            # Let's assume the markdown refers to "../content_images/content_fixture.png"
            # This is tricky because the mock doesn't know the *exact* path structure.

            # --- Easiest Mocking: Call with a path we know exists ---
            # The callback itself will save content images via _save_uploaded_file_locally
            # Let's find one of those saved files if possible, or just use the fixture path.
            # The fixture `dummy_content_image_file` provides a SimpleUploadedFile.
            # Its 'name' attribute might be just the filename.
            # Let's write it to a predictable place for the callback.
            content_img_dir = Path(settings.MEDIA_ROOT) / "uploads/content_images"
            content_img_dir.mkdir(parents=True, exist_ok=True)
            saved_content_image_path = content_img_dir / dummy_content_image_file.name
            saved_content_image_path.write_bytes(dummy_content_image_file.read())
            dummy_content_image_file.seek(0)

            logger.info(f"Mock simulating image found, calling image_uploader callback with path: {saved_content_image_path}")
            # Call the provided callback
            uploaded_url = image_uploader(saved_content_image_path)
            logger.info(f"Mock received URL from callback: {uploaded_url}")

        except Exception as e:
            logger.error(f"Error in mock_html_processor side_effect trying to call callback: {e}", exc_info=True)
            # Don't raise here, just log, so the test can proceed and potentially fail elsewhere if needed

        # Return the standard dummy HTML fragment
        return "<p>Mock Processed HTML Fragment with Image</p>"

    # Patch where html_processor is looked up
    with patch("publisher.services.html_processor", autospec=True) as mock_processor:
        # Set the side_effect
        mock_processor.process_html_content.side_effect = process_html_side_effect
        yield mock_processor

# !!!!!!!!!! END OF CORRECTION !!!!!!!!!!

@pytest.fixture
def mock_payload_builder():
    """
    Mocks the publishing_engine.core.payload_builder module as used within publisher.services.
    Provides a default return value for payload building.
    """
    with patch("publisher.services.payload_builder", autospec=True) as mock_builder:
        # Return a dictionary simulating the structure expected by wechat_api.add_draft
        mock_builder.build_draft_payload.return_value = {
            "title": "Mock Built Title",
            "content": "<p>Test Placeholder Content</p>", # Match setting
            "thumb_media_id": "mock_built_thumb_id",
            "author": "Mock Built Author", # Add fields matching real function if needed
            # Add other fields returned by your actual builder if needed by tests
        }
        yield mock_builder


@pytest.fixture
def dummy_markdown_file(tmp_path):
    """Creates a dummy markdown file in the temp directory for testing uploads."""
    content = """---
title: Test Article Title Fixture
author: Pytest Fixture Author
tags: [fixture, markdown]
---

# Fixture Heading

Content generated by fixture.

![Fixture Image](content_fixture.png)
""" # Ensure this matches the image name used in mock_html_processor side_effect if needed
    file_path = tmp_path / "test_article_fixture.md"
    file_path.write_text(content, encoding='utf-8')
    return SimpleUploadedFile(
        name=file_path.name,
        content=file_path.read_bytes(),
        content_type="text/markdown"
    )

@pytest.fixture
def dummy_cover_image_file(tmp_path):
    """Creates a dummy JPEG image file in the temp directory for testing uploads."""
    file_path = tmp_path / "cover_fixture.jpg"
    file_path.write_bytes(b"\xFF\xD8\xFF\xE0 dummy jpeg cover fixture data")
    return SimpleUploadedFile(
        name=file_path.name,
        content=file_path.read_bytes(),
        content_type="image/jpeg"
    )

@pytest.fixture
def dummy_content_image_file(tmp_path):
    """Creates a dummy PNG image file in the temp directory for testing uploads."""
    # Use a consistent name that might be referenced in markdown/side_effect
    file_name = "content_fixture.png"
    file_path = tmp_path / file_name
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n dummy png content fixture data")
    return SimpleUploadedFile(
        name=file_name, # Return consistent name
        content=file_path.read_bytes(),
        content_type="image/png"
    )

@pytest.fixture
def dummy_content_image_files(dummy_content_image_file):
    """Provides a list containing one dummy content image file fixture."""
    return [dummy_content_image_file]

# --- Fixture to Provide Mock Error Class ---
@pytest.fixture
def mock_wechat_api_error_cls():
    """Provides the MockWeChatAPIError class via a fixture, avoiding direct imports in tests."""
    return MockWeChatAPIError
# --- End Fixture ---