# publisher/tests/conftest.py

import pytest
import uuid
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

# Import the real model
# *** FIX: Remove incorrect PublishingJobStatus import ***
from publisher.models import PublishingJob

# --- Minimal valid image data (1x1 transparent GIF) ---
VALID_IMAGE_BYTES = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
# --- Minimal valid CSS data ---
VALID_CSS_BYTES = b'body { color: #333; }'


@pytest.fixture
def sample_md_content_with_image():
    """Provides sample Markdown content string with metadata and an image link."""
    return """---
title: Sample Test Article
author: Pytest Fixture
tags: [test, fixture]
---

# Main Content

This is a paragraph.

![Sample Image Alt Text](images/sample_content.gif)

Another paragraph.
"""

@pytest.fixture
def sample_markdown_file(sample_md_content_with_image):
    """Provides a sample Markdown UploadedFile object."""
    return SimpleUploadedFile(
        "article.md",
        sample_md_content_with_image.encode('utf-8'),
        content_type="text/markdown"
    )

@pytest.fixture
def sample_cover_image_file():
    """Provides a sample cover image UploadedFile object."""
    return SimpleUploadedFile(
        "cover.gif",
        VALID_IMAGE_BYTES,
        content_type="image/gif"
    )

@pytest.fixture
def sample_content_image_file():
    """Provides a sample content image UploadedFile object."""
    # Match the filename used in sample_md_content_with_image
    return SimpleUploadedFile(
        "sample_content.gif",
        VALID_IMAGE_BYTES,
        content_type="image/gif"
    )

@pytest.fixture
def sample_css_file():
    """Provides a sample CSS UploadedFile object (though not directly uploaded in services)."""
    return SimpleUploadedFile(
        "style.css",
        VALID_CSS_BYTES,
        content_type="text/css"
    )


@pytest.fixture
def preview_ready_job_in_db(db, settings, tmp_path):
    """
    Creates a PublishingJob instance in PREVIEW_READY state directly in the test DB.
    Also creates the corresponding dummy local cover file needed for retry tests.
    Requires pytest-django's `db` fixture. Tests using this MUST be marked
    with `@pytest.mark.django_db`.

    Args:
        db: pytest-django fixture for database access.
        settings: Django settings fixture.
        tmp_path: Pytest fixture for a temporary directory.

    Returns:
        PublishingJob: The persisted job instance.
    """
    # Configure MEDIA_ROOT to use tmp_path for this fixture's file creation
    settings.MEDIA_ROOT = str(tmp_path) # Ensure it's a string for Path() compatibility

    # Define relative path for the dummy cover file *within* MEDIA_ROOT
    local_cover_rel_path_str = 'uploads/cover_images/cover_for_retry_fixture.gif'
    # Create the absolute path within the temporary MEDIA_ROOT
    local_cover_abs_path = tmp_path / local_cover_rel_path_str
    # Ensure parent directory exists
    local_cover_abs_path.parent.mkdir(parents=True, exist_ok=True)
    # Create the dummy file (content doesn't matter for existence check in retry)
    local_cover_abs_path.write_bytes(VALID_IMAGE_BYTES) # Write valid bytes just in case

    # Create the job instance in the database
    # *** FIX: Use PublishingJob.Status for the status choice ***
    job = PublishingJob.objects.create(
        task_id=uuid.uuid4(),
        status=PublishingJob.Status.PREVIEW_READY, # Use the nested Status class
        metadata={'title': 'DB Fixture Article', 'author': 'Conftest'},
        thumb_media_id='fixture_thumb_id_from_db_123',
        # Store the RELATIVE path string in the model field
        original_cover_image_path=local_cover_rel_path_str,
        original_markdown_path='uploads/markdown/dummy_fixture.md', # Add dummy path
        preview_html_path='previews/dummy_fixture.html', # Add dummy path
    )
    return job