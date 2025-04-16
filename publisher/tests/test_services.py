# publisher/tests/test_services.py

import pytest
from unittest.mock import patch, MagicMock, ANY, call
from pathlib import Path
import uuid
import os  # <-- ****** ADD THIS IMPORT ******

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile

# Models and Services to test
from publisher.models import PublishingJob
from publisher.services import start_processing_job, confirm_and_publish_job
from publishing_engine.utils.hashing_checking import calculate_file_hash

# Mock Error defined in conftest - Using relative import
from .conftest import MockWeChatAPIError


# --- Tests for start_processing_job ---

@pytest.mark.django_db
def test_start_processing_job_success_cache_miss(
    dummy_markdown_file: SimpleUploadedFile,
    dummy_cover_image_file: SimpleUploadedFile,
    dummy_content_image_files: list[SimpleUploadedFile],
    mock_wechat_api: MagicMock, # Added type hints for mocks
    mock_wechat_auth: MagicMock, # This is the mock of the function itself
    mock_metadata_reader: MagicMock,
    mock_html_processor: MagicMock
):
    """
    Test successful job processing when the thumbnail media ID is NOT found in the cache.
    Verifies that the thumbnail is uploaded and the result is cached.
    """
    # Arrange: Ensure cache is empty (done by autouse fixture)

    # Act
    result = start_processing_job(
        dummy_markdown_file, dummy_cover_image_file, dummy_content_image_files
    )

    # Assert: Check returned values and job state in DB
    assert "task_id" in result, "Result should contain task_id"
    assert "preview_url" in result, "Result should contain preview_url"
    task_id = uuid.UUID(result["task_id"])
    job = PublishingJob.objects.get(pk=task_id)

    assert job.status == PublishingJob.Status.PREVIEW_READY, "Job status should be PREVIEW_READY"
    assert job.error_message is None, "Error message should be None on success"
    assert job.original_markdown_path is not None
    assert job.original_cover_image_path is not None
    assert job.thumb_media_id == "mock_thumb_media_id_from_upload", "Thumb media ID should be from the mock upload"
    assert job.metadata == {"title": "Mock Title", "author": "Test Author"}, "Metadata should match mock"
    assert job.preview_html_path is not None, "Preview HTML path should be set"
    assert job.preview_html_path.endswith(f"{task_id}.html"), "Preview path should use task_id"
    # Ensure preview URL construction is plausible
    assert result["preview_url"].startswith(settings.MEDIA_URL)
    # ** CORRECTION: Use os.path.sep **
    assert result["preview_url"].endswith(job.preview_html_path.replace(os.path.sep, '/')), "Preview URL should match saved path"


    # Assert: Verify external calls (API, utils)
    mock_wechat_auth.assert_called_once()
    mock_metadata_reader.extract_metadata_and_content.assert_called_once()
    # Thumbnail upload *was* called because it was a cache miss
    mock_wechat_api.upload_thumb_media.assert_called_once()
    mock_html_processor.process_html_content.assert_called_once()
    # Content image upload API was called (at least once) by the callback
    mock_wechat_api.upload_content_image.assert_called()

    # Assert: Verify cache interaction (cache was SET)
    cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
    # Re-calculate hash here for verification
    cover_hash = calculate_file_hash(cover_path_abs)
    cache_key = f"wechat_thumb_sha256_{cover_hash}"
    assert cache.get(cache_key) == "mock_thumb_media_id_from_upload", "Cache should contain the uploaded thumb ID"


# (Rest of test_services.py remains the same as the previous corrected version)
# ... include all other test functions ...
@pytest.mark.django_db
def test_start_processing_job_success_cache_hit(
    dummy_markdown_file: SimpleUploadedFile,
    dummy_cover_image_file: SimpleUploadedFile,
    dummy_content_image_files: list[SimpleUploadedFile],
    mock_wechat_api: MagicMock,
    mock_wechat_auth: MagicMock, # This is the mock of the function itself
    mock_metadata_reader: MagicMock,
    mock_html_processor: MagicMock
):
    """
    Test successful job processing when the thumbnail media ID IS found in the cache.
    Verifies that the thumbnail is NOT re-uploaded and the cached ID is used.
    """
    # Arrange: Pre-populate cache
    # Save a temporary file to calculate its hash for the cache key
    # Need to use the actual file content used in the test run
    temp_cover_path = Path(settings.MEDIA_ROOT) / "uploads/cover_images/temp_cover_for_cache_hit.jpg"
    temp_cover_path.parent.mkdir(parents=True, exist_ok=True)
    file_content = dummy_cover_image_file.read() # Read content
    temp_cover_path.write_bytes(file_content)
    dummy_cover_image_file.seek(0) # Reset file pointer after read

    cover_hash = calculate_file_hash(temp_cover_path)
    cache_key = f"wechat_thumb_sha256_{cover_hash}"
    cached_media_id = "cached_thumb_media_id_xyz"
    cache.set(cache_key, cached_media_id, timeout=None) # Cache indefinitely for the test
    assert cache.get(cache_key) == cached_media_id, "Cache pre-population failed"
    # No need to clean up temp_cover_path, tmp_path fixture handles it

    # Act
    result = start_processing_job(
        dummy_markdown_file, dummy_cover_image_file, dummy_content_image_files
    )

    # Assert: Check returned values and job state in DB
    assert "task_id" in result
    task_id = uuid.UUID(result["task_id"])
    job = PublishingJob.objects.get(pk=task_id)

    assert job.status == PublishingJob.Status.PREVIEW_READY, "Job status should be PREVIEW_READY"
    # Verify the cached media ID was used for the job record
    assert job.thumb_media_id == cached_media_id, "Job should use the cached thumb ID"
    assert job.error_message is None
    assert result["preview_url"] is not None

    # Assert: Verify external calls
    # Thumbnail upload API was *NOT* called due to cache hit
    mock_wechat_api.upload_thumb_media.assert_not_called()
    # Other essential calls should still happen
    mock_wechat_auth.assert_called_once()
    mock_metadata_reader.extract_metadata_and_content.assert_called_once()
    mock_html_processor.process_html_content.assert_called_once()


@pytest.mark.django_db
def test_start_processing_job_hash_calculation_fails(
    dummy_markdown_file: SimpleUploadedFile,
    dummy_cover_image_file: SimpleUploadedFile,
    dummy_content_image_files: list[SimpleUploadedFile],
    mock_wechat_api: MagicMock,
    mock_wechat_auth: MagicMock,
    mock_metadata_reader: MagicMock,
    mock_html_processor: MagicMock
):
    """
    Test job processing when cover image hash calculation fails.
    Verifies that the thumbnail is still uploaded directly (cache skipped)
    and the cache is NOT set for the thumbnail.
    """
    # Arrange: Mock calculate_file_hash to return None for the cover image
    # Patch the function specifically where it's imported in services.py
    with patch("publisher.services.calculate_file_hash") as mock_calculate_hash:
        # Configure mock: Return None when called for the cover image path
        # We need to know the path it will be called with. Let's mock based on Path object.
        def hash_side_effect(path_obj, algorithm='sha256'):
             # Simplest approach: return None for all calls in this test scope
            return None
        mock_calculate_hash.side_effect = hash_side_effect


        # Act
        result = start_processing_job(
            dummy_markdown_file, dummy_cover_image_file, dummy_content_image_files
        )

        # Assert: Check results and job state
        assert "task_id" in result
        task_id = uuid.UUID(result["task_id"])
        job = PublishingJob.objects.get(pk=task_id)

        assert job.status == PublishingJob.Status.PREVIEW_READY, "Job should still complete successfully"
        # Thumbnail ID should be from the direct upload, as cache was skipped
        assert job.thumb_media_id == "mock_thumb_media_id_from_upload"

        # Assert: Verify external calls
        # calculate_file_hash was called (at least for the cover image)
        assert mock_calculate_hash.call_count >= 1 # Called for cover, maybe content images
        # upload_thumb_media *was* called because hashing failed (cache skipped)
        mock_wechat_api.upload_thumb_media.assert_called_once()

        # Assert: Verify Cache Interaction (Cache should NOT have been set for thumb)
        # Check that cache.set was not called for a thumb key
        found_thumb_key = any(isinstance(k, str) and k.startswith("wechat_thumb_sha256_") for k in cache._cache.keys())
        assert not found_thumb_key, "No thumbnail key should be in the cache"


@pytest.mark.django_db
def test_start_processing_job_metadata_error(
    dummy_markdown_file: SimpleUploadedFile,
    dummy_cover_image_file: SimpleUploadedFile,
    dummy_content_image_files: list[SimpleUploadedFile],
    mock_wechat_api: MagicMock, # Need API mock even if error is earlier
    mock_wechat_auth: MagicMock,
    mock_metadata_reader: MagicMock
):
    """Test job failure when metadata extraction raises a ValueError."""
    # Arrange: Configure metadata reader mock to raise an error
    mock_metadata_reader.extract_metadata_and_content.side_effect = ValueError("Invalid YAML in test")

    # Act & Assert: Check that the specific error is raised
    with pytest.raises(ValueError, match="Invalid YAML in test"):
        start_processing_job(
            dummy_markdown_file, dummy_cover_image_file, dummy_content_image_files
        )

    # Assert: Verify job status is FAILED in the database
    # Need to get the job using some predictable aspect if task_id isn't returned
    # Or, query all jobs assuming only one is created per test run.
    jobs = PublishingJob.objects.all()
    assert len(jobs) == 1, "One job should have been created"
    job = jobs[0]
    assert job.status == PublishingJob.Status.FAILED, "Job status should be FAILED"
    assert "Invalid YAML in test" in job.error_message, "Error message should reflect the cause"


@pytest.mark.django_db
def test_start_processing_job_thumb_upload_error(
    dummy_markdown_file: SimpleUploadedFile,
    dummy_cover_image_file: SimpleUploadedFile,
    dummy_content_image_files: list[SimpleUploadedFile],
    mock_wechat_api: MagicMock,
    mock_wechat_auth: MagicMock,
    mock_metadata_reader: MagicMock # Need metadata mock even if error is later
):
    """Test job failure when thumbnail upload raises a RuntimeError."""
    # Arrange: Configure thumb upload mock to raise an error
    mock_wechat_api.upload_thumb_media.side_effect = RuntimeError("WeChat API Timeout during test")

    # Act & Assert: Check that the specific error is raised
    with pytest.raises(RuntimeError, match="WeChat API Timeout during test"):
        start_processing_job(
            dummy_markdown_file, dummy_cover_image_file, dummy_content_image_files
        )

    # Assert: Verify job status is FAILED in the database
    jobs = PublishingJob.objects.all()
    assert len(jobs) == 1, "One job should have been created"
    job = jobs[0]
    assert job.status == PublishingJob.Status.FAILED, "Job status should be FAILED"
    assert "WeChat API Timeout during test" in job.error_message, "Error message should reflect the cause"


# --- Tests for confirm_and_publish_job ---

@pytest.fixture
def preview_ready_job(db):
    """
    Fixture to create a PublishingJob instance in PREVIEW_READY state,
    including creating a dummy cover file needed for potential retries.
    """
    task_id = uuid.uuid4()
    # Create dummy paths relative to MEDIA_ROOT for the job record
    media_root = Path(settings.MEDIA_ROOT)
    # Ensure consistent naming for easier lookup if needed (though direct object return is better)
    cover_filename = f"confirm_cover_{task_id.hex[:8]}.jpg"
    # Ensure path is stored as string, using OS-agnostic separator for consistency if needed
    cover_rel_path_str = (Path("uploads/cover_images") / cover_filename).as_posix()
    cover_abs_path = media_root / cover_rel_path_str # Reconstruct using '/'
    cover_abs_path.parent.mkdir(parents=True, exist_ok=True)
    cover_abs_path.write_bytes(b"confirm test image data for retry") # Unique content

    job = PublishingJob.objects.create(
        task_id=task_id,
        status=PublishingJob.Status.PREVIEW_READY,
        original_markdown_path=f"uploads/markdown/confirm_md_{task_id.hex[:8]}.md",
        original_cover_image_path=cover_rel_path_str, # Store posix path string
        thumb_media_id="initial_thumb_media_id_for_confirm",
        metadata={"title": "Confirm Test Title", "author": "Confirm Test Author"},
        preview_html_path=f"previews/{task_id}.html"
    )
    return job


@pytest.mark.django_db
def test_confirm_and_publish_job_success(
    preview_ready_job: PublishingJob, # Added type hint
    mock_wechat_api: MagicMock,
    mock_wechat_auth: MagicMock, # Mock of function
    mock_payload_builder: MagicMock
):
    """Test successful confirmation and publishing (happy path)."""
    # Arrange
    task_id = preview_ready_job.task_id
    initial_thumb_id = preview_ready_job.thumb_media_id
    job_metadata = preview_ready_job.metadata

    # Act
    result = confirm_and_publish_job(task_id)

    # Assert: Check returned dictionary
    assert result["status"] == PublishingJob.Status.PUBLISHED.label, "Result status label should be PUBLISHED"
    assert result["message"] is not None, "Success message should be present"
    assert result["wechat_media_id"] == "mock_draft_media_id_success", "Result should contain correct draft ID"

    # Assert: Verify job state in DB
    job = PublishingJob.objects.get(pk=task_id) # Re-fetch job after changes
    assert job.status == PublishingJob.Status.PUBLISHED, "DB status should be PUBLISHED"
    assert job.wechat_media_id == "mock_draft_media_id_success", "DB should store correct draft ID"
    assert job.published_at is not None, "Published timestamp should be set"
    assert job.error_message is None, "Error message should be None"

    # Assert: Verify external API calls
    mock_wechat_auth.assert_called_once() # Assert directly on function mock
    # Verify payload builder was called with the correct arguments from the job
    mock_payload_builder.build_draft_payload.assert_called_once_with(
        metadata=job_metadata, # Use metadata fetched before call
        html_content=settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT,
        thumb_media_id=initial_thumb_id # Check it used the initial thumb id
    )
    # Verify add_draft was called with the built payload
    expected_draft_payload = {"articles": [mock_payload_builder.build_draft_payload.return_value]}
    mock_wechat_api.add_draft.assert_called_once_with(
        access_token=mock_wechat_auth.return_value, # Use the return value of the mock
        draft_payload=expected_draft_payload,
        base_url=settings.WECHAT_BASE_URL
    )


@pytest.mark.django_db
def test_confirm_and_publish_job_retry_40007_success(
    preview_ready_job: PublishingJob,
    mock_wechat_api: MagicMock,
    mock_wechat_auth: MagicMock, # Mock of function
    mock_payload_builder: MagicMock,
    mock_wechat_api_error_cls: type[MockWeChatAPIError] # Use fixture for error class
):
    """
    Test successful publish after automatically retrying due to a 40007 error
    (invalid media_id) from the initial add_draft call.
    Verifies thumbnail re-upload, cache update, and final success.
    """
    # Arrange
    task_id = preview_ready_job.task_id
    initial_thumb_id = preview_ready_job.thumb_media_id
    job_metadata = preview_ready_job.metadata
    new_thumb_id_on_retry = "new_thumb_media_id_after_retry_abc"

    # Configure mock API calls for the retry scenario:
    # 1. add_draft fails first time with 40007
    # 2. upload_thumb_media succeeds during retry, returning a new ID
    # 3. add_draft succeeds second time
    mock_wechat_api.add_draft.side_effect = [
        mock_wechat_api_error_cls("Invalid media_id test", errcode=40007), # First call fails
        "mock_draft_media_id_retry_success"                        # Second call succeeds
    ]
    mock_wechat_api.upload_thumb_media.return_value = new_thumb_id_on_retry

    # Re-configure payload builder mock to return distinct payloads if needed for checking calls
    payload_attempt_1 = {"title": "Attempt 1", "content": settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT, "thumb_media_id": initial_thumb_id}
    payload_attempt_2 = {"title": "Attempt 2", "content": settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT, "thumb_media_id": new_thumb_id_on_retry}
    mock_payload_builder.build_draft_payload.side_effect = [payload_attempt_1, payload_attempt_2]


    # Act
    result = confirm_and_publish_job(task_id)

    # Assert: Final success state
    assert result["status"] == PublishingJob.Status.PUBLISHED.label, "Result status label should be PUBLISHED after retry"
    assert result["wechat_media_id"] == "mock_draft_media_id_retry_success", "Result should contain the final draft ID"

    # Assert: Verify job state in DB
    job = PublishingJob.objects.get(pk=task_id) # Re-fetch job
    assert job.status == PublishingJob.Status.PUBLISHED, "DB status should be PUBLISHED"
    # Check that the thumb_media_id in the DB was updated during the retry
    assert job.thumb_media_id == new_thumb_id_on_retry, "DB thumb_media_id should be updated"
    assert job.wechat_media_id == "mock_draft_media_id_retry_success", "DB should store the final draft ID"

    # Assert: Verify sequence of external API calls
    # Assert call count directly on function mock
    assert mock_wechat_auth.call_count == 2, "get_access_token called twice (initial + retry)"

    # Payload builder called twice (initial attempt, after re-upload)
    assert mock_payload_builder.build_draft_payload.call_count == 2
    # Check arguments passed to payload builder
    mock_payload_builder.build_draft_payload.assert_has_calls([
        call(metadata=job_metadata, html_content=settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT, thumb_media_id=initial_thumb_id), # First attempt
        call(metadata=job_metadata, html_content=settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT, thumb_media_id=new_thumb_id_on_retry) # Second attempt
    ])
    # add_draft called twice (failed, succeeded)
    assert mock_wechat_api.add_draft.call_count == 2
    # Check arguments for add_draft calls
    expected_draft_payload_1 = {"articles": [payload_attempt_1]}
    expected_draft_payload_2 = {"articles": [payload_attempt_2]}
    mock_wechat_api.add_draft.assert_has_calls([
        call(access_token=ANY, draft_payload=expected_draft_payload_1, base_url=ANY),
        call(access_token=ANY, draft_payload=expected_draft_payload_2, base_url=ANY)
    ])

    # upload_thumb_media called exactly ONCE during the retry logic
    mock_wechat_api.upload_thumb_media.assert_called_once()
    # Verify the path used for re-upload
    expected_cover_path = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
    mock_wechat_api.upload_thumb_media.assert_called_once_with(
        access_token=ANY, # Token might have been refreshed
        thumb_path=expected_cover_path,
        base_url=settings.WECHAT_BASE_URL
    )

    # Assert: ** Verify Cache Update during Retry **
    cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
    cover_hash = calculate_file_hash(cover_path_abs) # Calculate hash of the original file
    cache_key = f"wechat_thumb_sha256_{cover_hash}"
    # Check that the cache now holds the NEW, valid thumb media ID after the retry
    assert cache.get(cache_key) == new_thumb_id_on_retry, "Cache should be updated with the new thumb ID after retry"


@pytest.mark.django_db
def test_confirm_and_publish_job_retry_40007_fails_again(
    preview_ready_job: PublishingJob,
    mock_wechat_api: MagicMock,
    mock_wechat_auth: MagicMock, # Mock of function
    mock_payload_builder: MagicMock,
    mock_wechat_api_error_cls: type[MockWeChatAPIError]
):
    """Test failure when add_draft fails with 40007, retries, but fails again."""
    # Arrange
    task_id = preview_ready_job.task_id
    initial_thumb_id = preview_ready_job.thumb_media_id
    job_metadata = preview_ready_job.metadata
    new_thumb_id_on_retry = "new_thumb_id_during_failed_retry_def"
    # Configure mocks:
    # 1. add_draft fails first time (40007)
    # 2. upload_thumb_media succeeds during retry
    # 3. add_draft fails second time with a different error
    mock_wechat_api.add_draft.side_effect = [
        mock_wechat_api_error_cls("Invalid media_id test", errcode=40007),
        RuntimeError("WeChat API down on second attempt")
    ]
    mock_wechat_api.upload_thumb_media.return_value = new_thumb_id_on_retry
    # Make payload builder work for both calls
    mock_payload_builder.build_draft_payload.side_effect = [
        {"title": "Attempt 1", "content": settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT, "thumb_media_id": initial_thumb_id},
        {"title": "Attempt 2", "content": settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT, "thumb_media_id": new_thumb_id_on_retry}
    ]


    # Act & Assert: Check that the final error is raised
    with pytest.raises(RuntimeError, match="Failed to publish draft to WeChat after 2 attempt"): # Match the raised error message
        confirm_and_publish_job(task_id)

    # Assert: Verify job state in DB
    job = PublishingJob.objects.get(pk=task_id) # Re-fetch
    assert job.status == PublishingJob.Status.FAILED, "DB status should be FAILED"
    # Check the specific error message stored from the *final* failure
    assert "Failed to publish draft to WeChat after 2 attempt(s). Last error: WeChat API down on second attempt" in job.error_message, "Error message should reflect the final error"

    # Thumb ID *should* be updated in the DB because the re-upload happened before the second failure
    assert job.thumb_media_id == new_thumb_id_on_retry, "DB thumb_media_id should be updated from retry"
    assert job.wechat_media_id is None, "No final draft ID should be stored"

    # Assert: Verify Cache Update (cache *should* have been updated during retry)
    cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
    cover_hash = calculate_file_hash(cover_path_abs)
    cache_key = f"wechat_thumb_sha256_{cover_hash}"
    assert cache.get(cache_key) == new_thumb_id_on_retry, "Cache should still be updated with the new thumb ID from the retry attempt"


@pytest.mark.django_db
def test_confirm_and_publish_job_not_ready(preview_ready_job: PublishingJob):
    """Test attempting to publish a job that is not in PREVIEW_READY state."""
    # Arrange: Change the job status
    preview_ready_job.status = PublishingJob.Status.PROCESSING
    preview_ready_job.save()
    task_id = preview_ready_job.task_id

    # Act & Assert: Check for ValueError
    with pytest.raises(ValueError, match="Job not ready for publishing"):
        confirm_and_publish_job(task_id)

    # Assert: Verify DB state unchanged (still PROCESSING)
    job = PublishingJob.objects.get(pk=task_id) # Re-fetch job
    # Assert that the status is now FAILED due to the error handling in confirm_and_publish_job
    assert job.status == PublishingJob.Status.FAILED, "Job status should be FAILED after caught error"
    assert "Job not ready for publishing" in job.error_message, "Error message should be set"



@pytest.mark.django_db
def test_confirm_and_publish_job_not_found():
    """Test attempting to publish a job ID that doesn't exist in the database."""
    # Arrange
    non_existent_task_id = uuid.uuid4()

    # Act & Assert: Check for Django's ObjectDoesNotExist
    with pytest.raises(ObjectDoesNotExist):
        confirm_and_publish_job(non_existent_task_id)