# tests/publisher/test_services.py

import pytest
import uuid
from pathlib import Path
import builtins
from datetime import datetime, timezone as dt_timezone
from typing import Callable, List, Dict, Any, Optional, Tuple
from unittest.mock import MagicMock, call, patch, ANY
import logging
import re # Import re

from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.text import slugify
from django.utils import timezone

# Assuming PublishingJob, services, etc are correctly importable
from publisher.models import PublishingJob
from publisher import services
# Import constants - adjust path if they live elsewhere or define directly
try:
    from publisher.services import (
        COVER_IMAGE_SIZE_LIMIT_KB,
        CONTENT_IMAGE_SIZE_LIMIT_KB,
        JOB_ERROR_UPDATE_FIELDS,
        JOB_PUBLISH_SUCCESS_FIELDS,
        JOB_STATUS_UPDATE_FIELDS,
        JOB_PATHS_UPDATE_FIELDS,
        JOB_THUMB_UPDATE_FIELDS,
        JOB_METADATA_UPDATE_FIELDS,
        JOB_PREVIEW_UPDATE_FIELDS,
        JOB_ERROR_MSG_UPDATE_FIELDS
    )
except ImportError:
    # Define defaults if not importable (adjust values as needed)
    logging.Logger.warning("Could not import constants from publisher.services, using defaults.")
    COVER_IMAGE_SIZE_LIMIT_KB = 64
    CONTENT_IMAGE_SIZE_LIMIT_KB = 1024
    JOB_ERROR_UPDATE_FIELDS = ['status', 'error_message', 'published_at']
    JOB_PUBLISH_SUCCESS_FIELDS = ['status', 'wechat_media_id', 'error_message', 'published_at']
    JOB_STATUS_UPDATE_FIELDS = ['status']
    JOB_PATHS_UPDATE_FIELDS = ['original_markdown_path', 'original_cover_image_path']
    JOB_THUMB_UPDATE_FIELDS = ['thumb_media_id']
    JOB_METADATA_UPDATE_FIELDS = ['metadata']
    JOB_PREVIEW_UPDATE_FIELDS = ['status', 'preview_html_path']
    JOB_ERROR_MSG_UPDATE_FIELDS = ['error_message']


# Configure logging for tests if needed (optional, helps debugging)
# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# --- Fixtures ---

@pytest.fixture
def mock_uploaded_file_factory() -> Callable[..., UploadedFile]:
    """Factory to create mock UploadedFile objects using SimpleUploadedFile."""
    def _create_mock_file(filename="test.txt", content=b"content") -> UploadedFile:
        filename_str = str(filename)
        mock_file = SimpleUploadedFile(filename_str, content, content_type='text/plain')
        if not hasattr(mock_file, 'name'):
             mock_file.name = filename_str
        if not hasattr(mock_file, 'size'):
             mock_file.size = len(content)
        return mock_file
    return _create_mock_file

@pytest.fixture
def mock_job() -> MagicMock:
    """Fixture for a reusable mock PublishingJob instance."""
    job_instance = MagicMock(spec=PublishingJob)
    job_instance.task_id = uuid.uuid4()
    job_instance.status = PublishingJob.Status.PENDING
    job_instance.metadata = {}
    job_instance.original_cover_image_path = f"uploads/cover_images/original_cover_{job_instance.task_id.hex[:8]}.jpg"
    job_instance.original_markdown_path = f"uploads/markdown/original_article_{job_instance.task_id.hex[:8]}.md"
    job_instance.thumb_media_id = None
    job_instance.wechat_media_id = None
    job_instance.preview_html_path = None
    job_instance.error_message = None
    job_instance.published_at = None
    job_instance.save = MagicMock()
    job_instance.get_status_display = MagicMock(side_effect=lambda: getattr(getattr(job_instance.status, 'label', job_instance.status), 'value', str(job_instance.status)))
    return job_instance

# --- Global Mock Cache Instance ---
mock_cache_instance = MagicMock()
mock_cache_instance.get = MagicMock(return_value=None)
mock_cache_instance.set = MagicMock()

@pytest.fixture(autouse=True) # Apply mocking automatically to relevant tests
def mock_dependencies(mocker) -> None:
    """Mock external dependencies used across service functions."""
    # Reset the mock cache calls for each test
    mock_cache_instance.reset_mock()
    mock_cache_instance.get.return_value = None

    # Mock Django ORM
    mocker.patch('publisher.models.PublishingJob.objects.create', return_value=MagicMock(spec=PublishingJob))
    mocker.patch('publisher.models.PublishingJob.objects.get', side_effect=ObjectDoesNotExist("Default mock"))

    # Mock external libraries/utils
    mocker.patch('publisher.services.auth.get_access_token', return_value="DUMMY_ACCESS_TOKEN")
    mocker.patch('publisher.services.wechat_api.upload_thumb_media', return_value="DUMMY_THUMB_MEDIA_ID")
    mocker.patch('publisher.services.wechat_api.upload_content_image', return_value="http://wechat.example.com/content_img.jpg")
    mocker.patch('publisher.services.wechat_api.add_draft', return_value="DUMMY_DRAFT_MEDIA_ID")
    mocker.patch('publisher.services.metadata_reader.extract_metadata_and_content', return_value=({}, "Markdown Body Content"))
    mocker.patch('publisher.services.payload_builder.build_draft_payload', return_value={"articles": [{"title": "Mock Title"}]})
    mocker.patch('publisher.services.calculate_file_hash', return_value="dummy_hash_123")
    mocker.patch('publisher.services.ensure_image_size', side_effect=lambda p, limit: p)
    mocker.patch('django.utils.timezone.now', return_value=datetime(2025, 4, 19, 18, 0, 0, tzinfo=dt_timezone.utc))

    # --- Mock Django Cache Object Itself ---
    mocker.patch('publisher.services.cache', mock_cache_instance)

    # Mock settings needed
    mocker.patch('django.conf.settings.MEDIA_ROOT', '/fake/media/root')
    mocker.patch('django.conf.settings.MEDIA_URL', '/media/')
    mocker.patch('django.conf.settings.WECHAT_APP_ID', 'fake_app_id')
    mocker.patch('django.conf.settings.WECHAT_SECRET', 'fake_secret')
    mocker.patch('django.conf.settings.WECHAT_BASE_URL', 'https://api.weixin.qq.com')
    mocker.patch('django.conf.settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT', 3 * 24 * 60 * 60)
    mocker.patch('django.conf.settings.PREVIEW_CSS_FILE_PATH', getattr(settings, 'PREVIEW_CSS_FILE_PATH', None))
    mocker.patch('django.conf.settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT', getattr(settings, 'WECHAT_DRAFT_PLACEHOLDER_CONTENT', '<p>Content pending update.</p>'))


# --- Tests for Helper Functions in services.py ---

@pytest.mark.django_db
def test_save_uploaded_file_locally_success(tmp_path: Path, mock_uploaded_file_factory: Callable, mocker):
    """Test successful local saving of an uploaded file using tmp_path."""
    # Arrange
    original_filename = "test doc.txt"
    mock_file = mock_uploaded_file_factory(filename=original_filename, content=b"file data")
    mock_media_root = tmp_path / "media"
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(mock_media_root))

    # Act
    result_path = services._save_uploaded_file_locally(mock_file, subfolder="test_uploads")

    # Assert
    assert isinstance(result_path, Path)
    assert result_path.is_absolute()
    assert result_path.exists(), f"Saved file not found at {result_path}"

    # Check directory structure
    target_dir = mock_media_root / "test_uploads"
    assert target_dir.is_dir()
    assert result_path.parent == target_dir

    # Check filename pattern (slugified + uuid hex + suffix)
    # Original stem: "test doc" -> slugify -> "test-doc"
    # Service seems to save as "test_doc_..." (underscore)
    stem_from_filename = Path(original_filename).stem # "test doc"
    service_expected_stem = slugify(stem_from_filename).replace('-', '_') # "test_doc"
    expected_suffix = Path(original_filename).suffix # ".txt"
    # Regex to match: service_expected_stem + "_" + hex chars + suffix + end-of-string
    filename_pattern = rf"^{re.escape(service_expected_stem)}_[a-f0-9]+{re.escape(expected_suffix)}$"
    assert re.match(filename_pattern, result_path.name), \
        f"Filename '{result_path.name}' does not match expected pattern '{filename_pattern}' (derived from stem '{service_expected_stem}')"

    # Check content
    assert result_path.read_bytes() == b"file data"


@pytest.mark.django_db
def test_save_uploaded_file_locally_io_error(tmp_path: Path, mock_uploaded_file_factory: Callable, mocker):
    """Test handling of IOError during file saving by mocking open locally."""
    # Arrange
    mock_file = mock_uploaded_file_factory(filename="fail_io.txt") # Give specific name for targeting
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(tmp_path))

    original_open = builtins.open
    def faulty_open(*args, **kwargs):
        path_arg_str = str(args[0]) if args else ""
        mode_arg_str = str(args[1]) if len(args) > 1 else ""

        # Only fail on write/append modes for the specific target file
        if ('w' in mode_arg_str or 'a' in mode_arg_str or '+' in mode_arg_str) and 'fail_io_' in path_arg_str:
            logger.debug(f"faulty_open: Simulating IOError for args: {args}")
            raise IOError("Disk full simulation")
        logger.debug(f"faulty_open: Allowing open: {args}")
        return original_open(*args, **kwargs)

    mocker.patch('builtins.open', side_effect=faulty_open)

    # Act & Assert
    # Use the subfolder that will appear in the path passed to open
    with pytest.raises(RuntimeError, match="Failed to save .* locally due to file system error"):
        services._save_uploaded_file_locally(mock_file, subfolder="io_test")


@pytest.mark.django_db
def test_generate_preview_file_success(tmp_path: Path, mocker):
    # ... (Keep previous corrected version - was passing) ...
    """Test successful generation of a preview HTML file using tmp_path."""
    # Arrange
    task_id = uuid.uuid4()
    html_content = "<!DOCTYPE html><html><body>Preview</body></html>"
    mock_media_root = tmp_path / "media"
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(mock_media_root))

    # Act
    relative_path_str = services._generate_preview_file(html_content, task_id)

    # Assert
    relative_path = Path(relative_path_str)
    expected_abs_path = mock_media_root / relative_path
    assert relative_path.parent == Path("previews")
    assert relative_path.name == f"{task_id}.html"
    assert (mock_media_root / "previews").is_dir()
    assert expected_abs_path.is_file()
    assert expected_abs_path.read_text(encoding='utf-8') == html_content


# --- Tests for start_processing_job ---

def find_file_by_pattern(directory: Path, pattern: str) -> Optional[Path]:
    """Helper to find a file in a directory using regex"""
    if not directory.is_dir():
        return None
    for item in directory.iterdir():
        if item.is_file() and re.match(pattern, item.name):
            return item
    return None

@pytest.mark.django_db
def test_start_processing_job_success_flow(tmp_path: Path, mock_uploaded_file_factory: Callable, mock_job: MagicMock, mocker):
    """
    Test the main success path of start_processing_job, using tmp_path
    and letting the actual file saving and html_processor run.
    """
    # Arrange
    md_filename = "article with space.md"
    cover_filename = "cover image.jpg"
    content_image_filename = "img_side.png"
    referenced_image_filename = "ref image.png"

    md_body_content = f"# Title ![alt text]({referenced_image_filename})"
    markdown_file = mock_uploaded_file_factory(md_filename, md_body_content.encode('utf-8'))
    cover_image = mock_uploaded_file_factory(cover_filename, b"jpg_data")
    content_image_side = mock_uploaded_file_factory(content_image_filename, b"png_data_side")
    referenced_image_content = b"dummy png data ref"

    mock_media_root = tmp_path / "media"
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(mock_media_root))

    # Mock the job creation and retrieval
    test_task_id = mock_job.task_id
    mock_create = mocker.patch('publisher.models.PublishingJob.objects.create', return_value=mock_job)
    mocker.patch('publisher.models.PublishingJob.objects.get', return_value=mock_job)

    # --- Let _save_uploaded_file_locally run ---
    uploads_markdown_dir = mock_media_root / "uploads/markdown"
    uploads_cover_dir = mock_media_root / "uploads/cover_images"

    # Manually create referenced image relative to MD save dir
    uploads_markdown_dir.mkdir(parents=True, exist_ok=True)
    referenced_content_original_path = uploads_markdown_dir / referenced_image_filename
    referenced_content_original_path.write_bytes(referenced_image_content)

    # Simulate optimization paths - these MUST exist if ensure_image_size returns them
    optimized_cover_path = uploads_cover_dir / "cover-image-optimized.jpg"
    optimized_content_path = uploads_markdown_dir / "ref-image-optimized.png"

    mock_ensure_image_size = mocker.patch('publisher.services.ensure_image_size', side_effect=[
        optimized_cover_path, optimized_content_path
    ])

    # Ensure optimized files exist
    uploads_cover_dir.mkdir(parents=True, exist_ok=True)
    optimized_cover_path.write_bytes(b"optimized jpg data")
    optimized_content_path.write_bytes(b"optimized png data")

    # Mock hashing for *optimized* paths
    mock_hash = mocker.patch('publisher.services.calculate_file_hash', side_effect=[
        "optimized_cover_hash", "optimized_content_hash"
    ])

    # Mock external calls
    global mock_cache_instance # Use the global mock cache
    mock_upload_thumb = mocker.patch('publisher.services.wechat_api.upload_thumb_media', return_value="NEW_THUMB_ID")
    mock_extract_meta = mocker.patch('publisher.services.metadata_reader.extract_metadata_and_content', return_value=(
        {"title": "Test Article", "author": "Tester"}, md_body_content
    ))
    mock_upload_content = mocker.patch('publisher.services.wechat_api.upload_content_image', return_value="http://wechat.example.com/ref_optimized.png")
    mock_gen_preview = mocker.patch('publisher.services._generate_preview_file', return_value=f"previews/{test_task_id}.html")
    mocker.patch('publisher.services.html_processor._read_file', return_value="body { color: red; }")

    # --- Act ---
    result = services.start_processing_job(markdown_file, cover_image, [content_image_side])

    # --- Assertions ---
    mock_create.assert_called_once()
    assert mock_create.call_args[1]['task_id'] is not None
    assert mock_create.call_args[1]['status'] == PublishingJob.Status.PENDING

    # Find actual saved paths using regex matching on filenames
    # Pattern expecting underscores after slugify+replace
    md_stem = slugify(Path(md_filename).stem).replace('-', '_') # article_with_space
    md_pattern = rf"^{re.escape(md_stem)}_[a-f0-9]+\.md$"
    actual_saved_md_path = find_file_by_pattern(uploads_markdown_dir, md_pattern)
    assert actual_saved_md_path, f"Markdown file matching pattern '{md_pattern}' not found in {uploads_markdown_dir}"

    cover_stem = slugify(Path(cover_filename).stem).replace('-', '_') # cover_image
    cover_pattern = rf"^{re.escape(cover_stem)}_[a-f0-9]+\.jpg$"
    actual_saved_cover_path = find_file_by_pattern(uploads_cover_dir, cover_pattern)
    assert actual_saved_cover_path, f"Cover file matching pattern '{cover_pattern}' not found in {uploads_cover_dir}"

    # Check ensure_image_size calls
    assert mock_ensure_image_size.call_count == 2
    mock_ensure_image_size.assert_any_call(actual_saved_cover_path, COVER_IMAGE_SIZE_LIMIT_KB)
    assert referenced_content_original_path.exists()
    mock_ensure_image_size.assert_any_call(referenced_content_original_path, CONTENT_IMAGE_SIZE_LIMIT_KB)

    # Check hashing calls
    mock_hash.assert_any_call(optimized_cover_path, algorithm='sha256')
    mock_hash.assert_any_call(optimized_content_path, algorithm='sha256')
    assert mock_hash.call_count == 2

    # Check cache lookups
    mock_cache_instance.get.assert_any_call(f"wechat_thumb_sha256_optimized_cover_hash")
    mock_cache_instance.get.assert_any_call(f"wechat_content_url_sha256_optimized_content_hash")

    # Check uploads
    mock_upload_thumb.assert_called_once_with(access_token="DUMMY_ACCESS_TOKEN", thumb_path=optimized_cover_path, base_url=ANY)
    mock_upload_content.assert_called_once_with(access_token="DUMMY_ACCESS_TOKEN", image_path=optimized_content_path, base_url=ANY)
    mock_extract_meta.assert_called_once_with(actual_saved_md_path)
    mock_gen_preview.assert_called_once()

    # Check final job state
    mock_job.save.assert_called()
    assert mock_job.status == PublishingJob.Status.PREVIEW_READY
    assert mock_job.thumb_media_id == "NEW_THUMB_ID"
    assert mock_job.metadata["title"] == "Test Article"
    assert mock_job.preview_html_path == f"previews/{test_task_id}.html"
    assert mock_job.error_message is None

    # Check stored relative paths
    assert mock_job.original_markdown_path == actual_saved_md_path.relative_to(mock_media_root).as_posix()
    assert mock_job.original_cover_image_path == actual_saved_cover_path.relative_to(mock_media_root).as_posix()

    # Check result
    assert result["task_id"] == str(test_task_id)
    assert result["preview_url"] == f"/media/previews/{test_task_id}.html"
    assert "warnings" not in result


@pytest.mark.django_db
def test_start_processing_job_content_image_processing_warning(tmp_path: Path, mock_uploaded_file_factory: Callable, mock_job: MagicMock, mocker):
    # ... (Keep previous corrected version - was passing) ...
    """
    Test warning collection when content image processing fails, letting html_processor run.
    """
    # Arrange
    md_filename = "article_warn.md"
    cover_filename = "cover_warn.jpg"
    referenced_bad_image_filename = "bad_image.png"

    md_body_content = f"![img]({referenced_bad_image_filename})"
    markdown_file = mock_uploaded_file_factory(md_filename, md_body_content.encode('utf-8'))
    cover_image = mock_uploaded_file_factory(cover_filename, b"jpg_data_warn")

    mock_media_root = tmp_path / "media"
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(mock_media_root))

    # Mock job creation/retrieval
    test_task_id = mock_job.task_id
    mock_create = mocker.patch('publisher.models.PublishingJob.objects.create', return_value=mock_job) # Assign mock
    mocker.patch('publisher.models.PublishingJob.objects.get', return_value=mock_job)

    # --- Let _save_uploaded_file_locally run ---
    uploads_markdown_dir = mock_media_root / "uploads/markdown"
    uploads_cover_dir = mock_media_root / "uploads/cover_images"

    # Create referenced bad image file
    uploads_markdown_dir.mkdir(parents=True, exist_ok=True)
    referenced_content_path = uploads_markdown_dir / referenced_bad_image_filename
    referenced_content_path.write_bytes(b"large data perhaps")

    # Mock ensure_image_size
    mock_ensure_image_size = mocker.patch('publisher.services.ensure_image_size')
    actual_saved_cover_path_holder = {} # Use dict to allow modification in closure
    def ensure_image_side_effect(path: Path, limit_kb: int):
        # Check if this is the cover image call (based on expected name stem)
        # Correct stem check: slugify and replace hyphen with underscore
        cover_stem = slugify(Path(cover_filename).stem).replace('-', '_')
        if path.name.startswith(cover_stem):
            actual_saved_cover_path_holder['path'] = path
            logger.debug(f"Mock ensure_image_size: Cover call for {path}, returning original.")
            return path
        elif path.name == referenced_bad_image_filename:
            logger.debug(f"Mock ensure_image_size: Content call for {path}, raising ValueError.")
            raise ValueError("Processing failed test error")
        else:
            logger.warning(f"Mock ensure_image_size: Unexpected call for {path}, returning original.")
            return path

    mock_ensure_image_size.side_effect = ensure_image_side_effect

    # Mock other calls
    mock_extract_meta = mocker.patch('publisher.services.metadata_reader.extract_metadata_and_content', return_value=({}, md_body_content))
    mock_gen_preview = mocker.patch('publisher.services._generate_preview_file', return_value=f"previews/{test_task_id}_warn.html")
    mocker.patch('publisher.services.html_processor._read_file', return_value="")
    mock_upload_thumb = mocker.patch('publisher.services.wechat_api.upload_thumb_media', return_value="WARN_THUMB_ID")
    mock_upload_content = mocker.patch('publisher.services.wechat_api.upload_content_image')
    mock_hash = mocker.patch('publisher.services.calculate_file_hash', return_value="warn_hash")
    # Access global mock cache for assertions
    global mock_cache_instance
    mock_cache_instance.get.return_value = None # Ensure cache miss

    # --- Act ---
    result = services.start_processing_job(markdown_file, cover_image, [])

    # --- Assertions ---
    mock_create.assert_called_once() # Check create was called

    # Find actual saved MD path
    md_stem = slugify(Path(md_filename).stem).replace('-', '_')
    md_pattern = rf"^{re.escape(md_stem)}_[a-f0-9]+\.md$"
    actual_saved_md_path = find_file_by_pattern(uploads_markdown_dir, md_pattern)
    assert actual_saved_md_path, f"Markdown file matching pattern '{md_pattern}' not found"

    # Get the actual saved cover path found during the side effect
    assert 'path' in actual_saved_cover_path_holder, "Side effect did not capture cover path"
    actual_saved_cover_path = actual_saved_cover_path_holder['path']
    assert actual_saved_cover_path.exists(), f"Captured cover path {actual_saved_cover_path} does not exist"

    # Check ensure_image_size calls
    assert mock_ensure_image_size.call_count == 2
    mock_ensure_image_size.assert_any_call(actual_saved_cover_path, COVER_IMAGE_SIZE_LIMIT_KB)
    assert referenced_content_path.exists()
    mock_ensure_image_size.assert_any_call(referenced_content_path, CONTENT_IMAGE_SIZE_LIMIT_KB)

    # Check thumb upload happened
    mock_upload_thumb.assert_called_once_with(access_token=ANY, thumb_path=actual_saved_cover_path, base_url=ANY)
    mock_upload_content.assert_not_called() # Content upload didn't happen

    # Check metadata and preview
    mock_extract_meta.assert_called_once_with(actual_saved_md_path)
    mock_gen_preview.assert_called_once()

    # Check warnings
    assert "warnings" in result
    assert len(result["warnings"]) == 1
    assert f"Image processing failed: {referenced_bad_image_filename}" in result["warnings"][0]
    assert "(ValueError)" in result["warnings"][0]

    # Check final job state
    mock_job.save.assert_called()
    assert mock_job.status == PublishingJob.Status.PREVIEW_READY
    assert mock_job.thumb_media_id == "WARN_THUMB_ID"
    assert mock_job.preview_html_path == f"previews/{test_task_id}_warn.html"
    assert mock_job.error_message is not None
    assert f"Image processing failed: {referenced_bad_image_filename}" in mock_job.error_message
    assert "(ValueError)" in mock_job.error_message

    # Check result structure
    assert result["task_id"] == str(test_task_id)
    assert result["preview_url"] == f"/media/previews/{test_task_id}_warn.html"


# --- Tests for confirm_and_publish_job ---
# (Assume previous passing tests remain okay)

@pytest.mark.django_db
def test_confirm_publish_thumb_error_40007_failed_retry_upload(tmp_path: Path, mock_job: MagicMock, mocker):
    # ... (Keep previous structure, update assertion) ...
    """Test when the thumbnail re-upload during retry also fails."""
    # Arrange
    task_id = mock_job.task_id
    mock_job.status = PublishingJob.Status.PREVIEW_READY
    mock_job.metadata = {"title": "Retry Fail Upload Test"}
    mock_job.thumb_media_id = "OLD_INVALID_THUMB_ID"
    original_cover_rel_path = "uploads/cover/original_retry_fail.jpg"
    mock_job.original_cover_image_path = original_cover_rel_path

    mock_media_root = tmp_path / "media"
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(mock_media_root))
    mock_get = mocker.patch('publisher.models.PublishingJob.objects.get', return_value=mock_job)
    mock_job.preview_html_path = f"previews/{task_id}.html"
    (mock_media_root / Path(mock_job.preview_html_path).parent).mkdir(parents=True, exist_ok=True)

    placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT
    payload1 = {"title": "Retry Fail Upload Test", "content": placeholder_content, "thumb_media_id": "OLD_INVALID_THUMB_ID"}
    mock_build_payload = mocker.patch('publisher.services.payload_builder.build_draft_payload', return_value=payload1)
    api_payload1 = {"articles": [payload1]}

    mock_add_draft = mocker.patch('publisher.services.wechat_api.add_draft', side_effect=RuntimeError("API Error - 40007 invalid media_id"))

    original_cover_path_abs = mock_media_root / original_cover_rel_path
    original_cover_path_abs.parent.mkdir(parents=True, exist_ok=True)
    original_cover_path_abs.write_bytes(b"original retry fail data")

    processed_cover_path_retry = original_cover_path_abs.parent / "original_retry_fail_optimized.jpg"
    mocker.patch('publisher.services.ensure_image_size', return_value=processed_cover_path_retry)
    processed_cover_path_retry.write_bytes(b"reprocessed fail data")

    mock_upload_retry = mocker.patch('publisher.services.wechat_api.upload_thumb_media', side_effect=RuntimeError("Re-upload failed test"))
    mocker.patch('publisher.services.calculate_file_hash', return_value="retry_fail_hash")
    global mock_cache_instance

    # Act & Assert
    with pytest.raises(RuntimeError, match="Failed during thumbnail re-upload attempt"):
        services.confirm_and_publish_job(task_id)

    mock_get.assert_called_once_with(pk=task_id)
    mock_build_payload.assert_called_once()
    mock_add_draft.assert_called_once_with(access_token=ANY, draft_payload=api_payload1, base_url=ANY)
    mock_upload_retry.assert_called_once()
    mock_cache_instance.set.assert_not_called()

    # Check final job state
    assert mock_job.status == PublishingJob.Status.FAILED
    assert mock_job.error_message is not None
    # Check the specific error message saved from the retry block
    assert mock_job.error_message == "Failed during thumbnail re-upload attempt: Re-upload failed test"
    # Check save call updates error fields
    mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)


@pytest.mark.django_db
def test_confirm_publish_thumb_error_40007_failed_retry_processing(tmp_path: Path, mock_job: MagicMock, mocker):
    # ... (Keep previous structure, update assertion) ...
    """Test when the image re-processing during retry fails."""
    # Arrange
    task_id = mock_job.task_id
    mock_job.status = PublishingJob.Status.PREVIEW_READY
    mock_job.metadata = {"title": "Retry Fail Processing Test"}
    mock_job.thumb_media_id = "OLD_INVALID_THUMB_ID"
    original_cover_rel_path = "uploads/cover/original_retry_process_fail.jpg"
    mock_job.original_cover_image_path = original_cover_rel_path

    mock_media_root = tmp_path / "media"
    mocker.patch('django.conf.settings.MEDIA_ROOT', str(mock_media_root))
    mock_get = mocker.patch('publisher.models.PublishingJob.objects.get', return_value=mock_job)
    mock_job.preview_html_path = f"previews/{task_id}.html"
    (mock_media_root / Path(mock_job.preview_html_path).parent).mkdir(parents=True, exist_ok=True)

    placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT
    payload1 = {"title": "Retry Fail Processing Test", "content": placeholder_content, "thumb_media_id": "OLD_INVALID_THUMB_ID"}
    mock_build_payload = mocker.patch('publisher.services.payload_builder.build_draft_payload', return_value=payload1)
    api_payload1 = {"articles": [payload1]}

    mock_add_draft = mocker.patch('publisher.services.wechat_api.add_draft', side_effect=RuntimeError("API Error - 40007 invalid media_id"))

    original_cover_path_abs = mock_media_root / original_cover_rel_path
    original_cover_path_abs.parent.mkdir(parents=True, exist_ok=True)
    original_cover_path_abs.write_bytes(b"original retry process fail data")

    # Simulate ensure_image_size failing during retry
    mock_ensure_retry = mocker.patch('publisher.services.ensure_image_size', side_effect=ValueError("Cannot process image during retry test"))
    mock_upload_retry = mocker.patch('publisher.services.wechat_api.upload_thumb_media')
    mock_hash_retry = mocker.patch('publisher.services.calculate_file_hash')
    global mock_cache_instance

    # Act & Assert
    with pytest.raises(RuntimeError, match="Failed to re-process cover image during retry"):
        services.confirm_and_publish_job(task_id)

    mock_get.assert_called_once_with(pk=task_id)
    mock_build_payload.assert_called_once()
    mock_add_draft.assert_called_once_with(access_token=ANY, draft_payload=api_payload1, base_url=ANY)
    mock_ensure_retry.assert_called_once()
    mock_upload_retry.assert_not_called()
    mock_hash_retry.assert_not_called()
    mock_cache_instance.set.assert_not_called()

    # Check final job state
    assert mock_job.status == PublishingJob.Status.FAILED
    assert mock_job.error_message is not None
    # Check the specific error message saved from the retry block
    assert mock_job.error_message == "Failed to re-process cover image during retry: Cannot process image during retry test"
    # Check save call updates error fields
    mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)