# /Users/junluo/Documents/wechat_publisher_web/publisher/tests/test_services.py

import uuid
import pytest
from unittest.mock import patch, MagicMock, ANY
from pathlib import Path # Import Path for use in assertions
import yaml
import json # Import json for checking serializable mock returns

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage # Keep for mocking save

from publisher.services import start_processing_job, confirm_and_publish_job
from publisher.models import PublishingJob

# --- Fixtures ---

@pytest.fixture
def mock_job_data():
    job_id = uuid.uuid4()
    return {
        'task_id': job_id,
        'status': PublishingJob.Status.PENDING,
        'original_markdown_path': 'uploads/markdown/test.md',
        'original_cover_image_path': 'uploads/cover_images/cover.jpg',
        'thumb_media_id': 'initial_thumb_id_123', # Potentially expired ID
        'metadata': {'title': 'Test Title', 'author': 'Test Author'},
        'preview_html_path': f'previews/{job_id}.html',
        'wechat_media_id': None,
        'error_message': None,
    }

@pytest.fixture
def mock_markdown_file_obj():
    file = MagicMock(spec=ContentFile)
    file.name = 'test.md'
    return file

@pytest.fixture
def mock_cover_image_obj():
    file = MagicMock(spec=ContentFile)
    file.name = 'cover.jpg'
    return file

@pytest.fixture
def mock_content_images_dir(tmp_path):
    d = tmp_path / "content_images"
    d.mkdir()
    return d

MODULE_PATH = 'publisher.services'

# --- Tests for start_processing_job ---

@patch(f'{MODULE_PATH}.uuid.uuid4')
@patch(f'{MODULE_PATH}.default_storage.save')
@patch(f'{MODULE_PATH}.auth.get_access_token')
@patch(f'{MODULE_PATH}.wechat_api.upload_thumb_media')
@patch(f'{MODULE_PATH}.MediaManager')
@patch(f'{MODULE_PATH}.metadata_reader.extract_metadata_and_content')
@patch(f'{MODULE_PATH}.html_processor.process_html_content')
@patch(f'{MODULE_PATH}._generate_preview_file')
@patch(f'{MODULE_PATH}.PublishingJob.objects.create')
def test_start_processing_job_success(
    mock_job_create, mock_generate_preview, mock_process_html,
    mock_extract_meta, mock_media_manager_cls, mock_upload_thumb,
    mock_get_token, mock_storage_save,
    mock_uuid4,
    mock_markdown_file_obj, mock_cover_image_obj, mock_content_images_dir, settings
    ):
    """Test the happy path for start_processing_job."""
    # --- Arrange ---
    task_id = uuid.UUID('11111111-1111-1111-1111-111111111111')
    mock_uuid4.return_value = task_id

    mock_job_instance = MagicMock(spec=PublishingJob)
    mock_job_instance.task_id = task_id
    mock_job_create.return_value = mock_job_instance

    mock_storage_save.side_effect = ['uploads/markdown/saved.md', 'uploads/cover_images/saved.jpg']
    mock_get_token.return_value = 'fake_access_token'
    mock_upload_thumb.return_value = 'permanent_thumb_id_789'

    mock_manager_instance = MagicMock()
    mock_manager_instance.get_or_upload_content_image_url.return_value = 'http://wechat.image/url'
    mock_media_manager_cls.return_value = mock_manager_instance

    mock_extract_meta.return_value = ({'title': 'Extracted Title'}, '# Body')
    mock_process_html.return_value = '<html>Processed HTML</html>'
    mock_generate_preview.return_value = f'previews/{task_id}.html'

    settings.WECHAT_APP_ID = 'test_app_id'
    settings.WECHAT_SECRET = 'test_secret'
    settings.WECHAT_BASE_URL = 'http://fake.wechat.com'
    settings.MEDIA_ROOT = '/fake/media/root'
    settings.MEDIA_URL = '/media/'
    settings.PREVIEW_CSS_FILE_PATH = '/path/to/style.css'
    settings.WECHAT_MEDIA_CACHE_PATH = '/tmp/test_cache.json'

    # --- Act ---
    result = start_processing_job(
        markdown_file=mock_markdown_file_obj,
        cover_image=mock_cover_image_obj,
        content_images_dir_abs=mock_content_images_dir
    )

    # --- Assert ---
    mock_job_create.assert_called_once_with(task_id=task_id, status=PublishingJob.Status.PENDING)
    assert mock_job_instance.save.call_count >= 4 # Initial, status, paths, thumb_id, preview

    assert mock_storage_save.call_count == 2
    mock_get_token.assert_called_once()

    expected_cover_path = Path(settings.MEDIA_ROOT) / 'uploads/cover_images/saved.jpg'
    mock_upload_thumb.assert_called_once_with(
        access_token='fake_access_token',
        thumb_path=expected_cover_path,
        base_url=settings.WECHAT_BASE_URL
    )
    mock_media_manager_cls.assert_called_with(cache_file_path=settings.WECHAT_MEDIA_CACHE_PATH)
    mock_manager_instance.get_or_upload_thumb_media.assert_not_called()

    mock_extract_meta.assert_called_once_with(Path(settings.MEDIA_ROOT) / 'uploads/markdown/saved.md')
    mock_process_html.assert_called_once_with(
        md_content='# Body',
        css_path=str(settings.PREVIEW_CSS_FILE_PATH),
        content_images_dir=mock_content_images_dir,
        image_uploader=ANY
    )

    mock_generate_preview.assert_called_once_with('<html>Processed HTML</html>', task_id)

    thumb_save_call = next(c for c in mock_job_instance.save.call_args_list if 'thumb_media_id' in c.kwargs.get('update_fields', []))
    assert mock_job_instance.thumb_media_id == 'permanent_thumb_id_789'
    assert 'thumb_media_id' in thumb_save_call.kwargs['update_fields']

    preview_save_call = next(c for c in mock_job_instance.save.call_args_list if 'preview_html_path' in c.kwargs.get('update_fields', []))
    assert mock_job_instance.preview_html_path == f'previews/{task_id}.html'
    assert mock_job_instance.status == PublishingJob.Status.PREVIEW_READY
    assert 'status' in preview_save_call.kwargs['update_fields']
    assert 'preview_html_path' in preview_save_call.kwargs['update_fields']

    assert result['task_id'] == task_id
    assert result['preview_url'] == f'/media/previews/{task_id}.html'


@patch(f'{MODULE_PATH}.PublishingJob.objects.create')
@patch(f'{MODULE_PATH}._save_uploaded_file', side_effect=FileNotFoundError("Mock save failed"))
def test_start_processing_job_save_fails(mock_save_file, mock_job_create, mock_markdown_file_obj, mock_cover_image_obj, mock_content_images_dir):
    """Test start_processing_job when saving a file fails."""
    mock_job_instance = MagicMock(spec=PublishingJob)
    mock_job_instance.status = PublishingJob.Status.PENDING
    mock_job_create.return_value = mock_job_instance

    with pytest.raises(FileNotFoundError, match="Mock save failed"):
        start_processing_job(
            markdown_file=mock_markdown_file_obj,
            cover_image=mock_cover_image_obj,
            content_images_dir_abs=mock_content_images_dir
        )

    mock_job_instance.save.assert_called()
    fail_save_call = next((c for c in reversed(mock_job_instance.save.call_args_list) if c.kwargs.get('update_fields') and 'status' in c.kwargs['update_fields']), None)
    assert fail_save_call is not None, "Job save with FAILED status not found"
    assert mock_job_instance.status == PublishingJob.Status.FAILED
    assert 'status' in fail_save_call.kwargs['update_fields']
    assert 'error_message' in fail_save_call.kwargs['update_fields']
    assert "File Not Found Error: Mock save failed" in mock_job_instance.error_message


@patch(f'{MODULE_PATH}.PublishingJob.objects.create')
@patch(f'{MODULE_PATH}._save_uploaded_file')
@patch(f'{MODULE_PATH}.auth.get_access_token')
@patch(f'{MODULE_PATH}.wechat_api.upload_thumb_media')
@patch(f'{MODULE_PATH}.MediaManager')
@patch(f'{MODULE_PATH}.metadata_reader.extract_metadata_and_content', side_effect=yaml.YAMLError("Bad YAML"))
def test_start_processing_job_metadata_fails(
    mock_extract_meta, mock_mm_cls, mock_upload_thumb, mock_get_token, mock_save, mock_job_create,
    mock_markdown_file_obj, mock_cover_image_obj, mock_content_images_dir, settings):
    """Test start_processing_job when metadata extraction fails."""
    mock_job_instance = MagicMock(spec=PublishingJob)
    mock_job_create.return_value = mock_job_instance
    mock_job_instance.status = PublishingJob.Status.PENDING

    mock_save.side_effect = ['uploads/markdown/meta_fail.md', 'uploads/cover_images/meta_fail.jpg']
    mock_get_token.return_value = 'fake_token_meta_fail'
    mock_upload_thumb.return_value = 'thumb_id_meta_fail'

    settings.WECHAT_APP_ID = 'id'
    settings.WECHAT_SECRET = 'secret'
    settings.MEDIA_ROOT = '/fake/media'
    settings.WECHAT_BASE_URL = 'http://fake.wechat.com'

    with pytest.raises(ValueError, match="Metadata/Format Error in Markdown: Bad YAML"):
         start_processing_job(
            markdown_file=mock_markdown_file_obj,
            cover_image=mock_cover_image_obj,
            content_images_dir_abs=mock_content_images_dir
        )

    mock_upload_thumb.assert_called_once()
    mock_extract_meta.assert_called_once()

    fail_save_call = next((c for c in reversed(mock_job_instance.save.call_args_list) if c.kwargs.get('update_fields') and 'status' in c.kwargs['update_fields']), None)
    assert fail_save_call is not None, "Job save with FAILED status not found"
    assert mock_job_instance.status == PublishingJob.Status.FAILED
    assert 'status' in fail_save_call.kwargs['update_fields']
    assert 'error_message' in fail_save_call.kwargs['update_fields']
    assert "Metadata/Format Error in Markdown: Bad YAML" in mock_job_instance.error_message


# --- Tests for confirm_and_publish_job ---

@patch(f'{MODULE_PATH}.PublishingJob.objects.get')
@patch(f'{MODULE_PATH}.auth.get_access_token')
@patch(f'{MODULE_PATH}.payload_builder.build_draft_payload')
@patch(f'{MODULE_PATH}.wechat_api.add_draft')
@patch(f'{MODULE_PATH}.wechat_api.upload_thumb_media')
def test_confirm_publish_job_success_first_try(
    mock_upload_thumb, mock_add_draft, mock_build_payload, mock_get_token, mock_job_get,
    mock_job_data, settings):
    """Test confirm_and_publish_job success on the first attempt."""
    # --- Arrange ---
    mock_job_object = MagicMock(spec=PublishingJob) # Use mock_job_object consistently
    mock_job_object.task_id = mock_job_data['task_id']
    mock_job_object.status = PublishingJob.Status.PREVIEW_READY
    mock_job_object.metadata = mock_job_data['metadata']
    mock_job_object.thumb_media_id = mock_job_data['thumb_media_id']
    mock_job_object.original_cover_image_path = mock_job_data['original_cover_image_path']
    mock_job_object.get_status_display.return_value = "Published"

    mock_job_get.return_value = mock_job_object

    mock_get_token.return_value = 'confirm_token'
    mock_build_payload.return_value = {'title': 'Test Payload', 'thumb_media_id': mock_job_data['thumb_media_id']}
    mock_add_draft.return_value = 'final_draft_media_id_789'

    settings.WECHAT_APP_ID = 'id'
    settings.WECHAT_SECRET = 'secret'
    settings.WECHAT_BASE_URL = 'http://fake-wechat.com'
    settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT = '<p>Placeholder</p>'
    settings.MEDIA_ROOT = '/fake/media/root'

    # --- Act ---
    result = confirm_and_publish_job(mock_job_data['task_id'])

    # --- Assert ---
    mock_job_get.assert_called_once_with(pk=mock_job_data['task_id'])
    mock_get_token.assert_called_once()
    mock_build_payload.assert_called_once_with(
        metadata=mock_job_object.metadata,
        html_content='<p>Placeholder</p>',
        thumb_media_id=mock_job_object.thumb_media_id
    )
    mock_add_draft.assert_called_once_with(
        access_token='confirm_token',
        draft_payload={'articles': [{'title': 'Test Payload', 'thumb_media_id': mock_job_data['thumb_media_id']}]},
        base_url=settings.WECHAT_BASE_URL
    )
    mock_upload_thumb.assert_not_called()

    assert mock_job_object.save.call_count >= 2
    # *** CORRECTED VARIABLE NAME HERE ***
    final_save_call = next((c for c in reversed(mock_job_object.save.call_args_list) if c.kwargs.get('update_fields') and 'status' in c.kwargs['update_fields']), None)

    assert final_save_call is not None, "Final job save call not found"

    assert mock_job_object.status == PublishingJob.Status.PUBLISHED
    assert mock_job_object.wechat_media_id == 'final_draft_media_id_789'
    assert mock_job_object.error_message is None
    assert 'status' in final_save_call.kwargs['update_fields']
    assert 'wechat_media_id' in final_save_call.kwargs['update_fields']
    assert 'error_message' in final_save_call.kwargs['update_fields']

    assert result['task_id'] == mock_job_object.task_id
    assert result['status'] == "Published"
    assert result['wechat_media_id'] == 'final_draft_media_id_789'


@patch('pathlib.Path.is_file')
@patch(f'{MODULE_PATH}.PublishingJob.objects.get')
@patch(f'{MODULE_PATH}.auth.get_access_token')
@patch(f'{MODULE_PATH}.payload_builder.build_draft_payload')
@patch(f'{MODULE_PATH}.wechat_api.add_draft')
@patch(f'{MODULE_PATH}.wechat_api.upload_thumb_media')
def test_confirm_publish_job_retry_success(
    mock_upload_thumb, mock_add_draft, mock_build_payload, mock_get_token, mock_job_get,
    mock_is_file,
    mock_job_data, settings):
    """Test confirm_and_publish_job success after retry due to invalid media ID."""
     # --- Arrange ---
    mock_job_object = MagicMock(spec=PublishingJob)
    mock_job_object.task_id = mock_job_data['task_id']
    mock_job_object.status = PublishingJob.Status.PREVIEW_READY
    mock_job_object.metadata = mock_job_data['metadata']
    mock_job_object.thumb_media_id = mock_job_data['thumb_media_id']
    mock_job_object.original_cover_image_path = mock_job_data['original_cover_image_path']
    mock_job_object.get_status_display.return_value = "Published"

    mock_job_get.return_value = mock_job_object

    mock_get_token.return_value = 'confirm_token_retry'
    mock_build_payload.side_effect = [
        {'payload': 'first try', 'thumb_media_id': mock_job_data['thumb_media_id']},
        {'payload': 'second try', 'thumb_media_id': 'new_valid_thumb_id_abc'}
    ]

    mock_add_draft.side_effect = [
        RuntimeError("API Error: 40007 invalid media_id some extra text"),
        'final_draft_media_id_RETRY'
    ]
    mock_upload_thumb.return_value = 'new_valid_thumb_id_abc'
    mock_is_file.return_value = True

    settings.WECHAT_APP_ID = 'id'
    settings.WECHAT_SECRET = 'secret'
    settings.MEDIA_ROOT = '/fake/media/root'
    settings.WECHAT_BASE_URL = 'http://fake-wechat.com'
    settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT = '<p>Placeholder</p>'

    expected_thumb_path = Path(settings.MEDIA_ROOT) / mock_job_data['original_cover_image_path']

    # --- Act ---
    result = confirm_and_publish_job(mock_job_data['task_id'])

     # --- Assert ---
    mock_job_get.assert_called_once_with(pk=mock_job_data['task_id'])
    mock_get_token.assert_called_once()

    assert mock_build_payload.call_count == 2
    assert mock_build_payload.call_args_list[0][1]['thumb_media_id'] == mock_job_data['thumb_media_id']
    assert mock_build_payload.call_args_list[1][1]['thumb_media_id'] == 'new_valid_thumb_id_abc'

    assert mock_add_draft.call_count == 2
    assert mock_add_draft.call_args_list[0][1]['draft_payload'] == {'articles': [{'payload': 'first try', 'thumb_media_id': mock_job_data['thumb_media_id']}]}
    assert mock_add_draft.call_args_list[1][1]['draft_payload'] == {'articles': [{'payload': 'second try', 'thumb_media_id': 'new_valid_thumb_id_abc'}]}

    mock_is_file.assert_called_once()
    mock_upload_thumb.assert_called_once_with(
        access_token='confirm_token_retry',
        thumb_path=expected_thumb_path,
        base_url=settings.WECHAT_BASE_URL
    )

    assert mock_job_object.thumb_media_id == 'new_valid_thumb_id_abc'
    thumb_update_save_call = next((c for c in mock_job_object.save.call_args_list if c.kwargs.get('update_fields') == ['thumb_media_id', 'updated_at']), None)
    assert thumb_update_save_call is not None, "Job save call updating thumb_media_id not found"

    final_save_call = next((c for c in reversed(mock_job_object.save.call_args_list) if 'wechat_media_id' in c.kwargs.get('update_fields', [])), None)
    assert final_save_call is not None, "Final job save call not found"
    assert mock_job_object.status == PublishingJob.Status.PUBLISHED
    assert mock_job_object.wechat_media_id == 'final_draft_media_id_RETRY'
    assert 'status' in final_save_call.kwargs['update_fields']
    assert 'wechat_media_id' in final_save_call.kwargs['update_fields']

    assert result['wechat_media_id'] == 'final_draft_media_id_RETRY'


@patch('pathlib.Path.is_file')
@patch(f'{MODULE_PATH}.PublishingJob.objects.get')
@patch(f'{MODULE_PATH}.auth.get_access_token')
@patch(f'{MODULE_PATH}.payload_builder.build_draft_payload')
@patch(f'{MODULE_PATH}.wechat_api.add_draft', side_effect=RuntimeError("API Error: 40007 invalid media_id"))
@patch(f'{MODULE_PATH}.wechat_api.upload_thumb_media', side_effect=RuntimeError("Upload failed badly"))
def test_confirm_publish_job_retry_reupload_fails(
    mock_upload_thumb, mock_add_draft, mock_build_payload, mock_get_token, mock_job_get,
    mock_is_file,
    mock_job_data, settings):
    """Test confirm_and_publish_job when re-upload fails during retry."""
    # --- Arrange ---
    mock_job_object = MagicMock(spec=PublishingJob)
    mock_job_object.task_id = mock_job_data['task_id']
    mock_job_object.status = PublishingJob.Status.PREVIEW_READY
    mock_job_object.metadata = mock_job_data['metadata']
    mock_job_object.thumb_media_id = mock_job_data['thumb_media_id']
    mock_job_object.original_cover_image_path = mock_job_data['original_cover_image_path']

    mock_job_get.return_value = mock_job_object

    mock_get_token.return_value = 'confirm_token_reupload_fail'
    mock_build_payload.return_value = {'payload': 'first try', 'thumb_media_id': mock_job_data['thumb_media_id']}
    mock_is_file.return_value = True

    settings.WECHAT_APP_ID = 'id'; settings.WECHAT_SECRET = 'secret'
    settings.MEDIA_ROOT = '/fake/media/root'
    settings.WECHAT_BASE_URL = 'http://fake-wechat.com'

    expected_thumb_path = Path(settings.MEDIA_ROOT) / mock_job_data['original_cover_image_path']

    # --- Act & Assert ---
    # *** CORRECTED expected error message regex ***
    with pytest.raises(RuntimeError, match="Publishing failed on retry attempt: Upload failed badly"):
        confirm_and_publish_job(mock_job_data['task_id'])

    # Verify calls
    mock_add_draft.assert_called_once()
    mock_is_file.assert_called_once()
    mock_upload_thumb.assert_called_once_with(
         access_token='confirm_token_reupload_fail',
         thumb_path=expected_thumb_path,
         base_url=settings.WECHAT_BASE_URL
    )
    mock_build_payload.assert_called_once()

    # Check final job state
    fail_save_call = next((c for c in reversed(mock_job_object.save.call_args_list) if c.kwargs.get('update_fields') and 'status' in c.kwargs['update_fields']), None)
    assert fail_save_call is not None, "Job save with FAILED status not found"
    assert mock_job_object.status == PublishingJob.Status.FAILED
    assert 'status' in fail_save_call.kwargs['update_fields']
    assert 'error_message' in fail_save_call.kwargs['update_fields']
    # Check the error message set by the service
    assert "Publishing Retry Failed: RuntimeError: Upload failed badly" in mock_job_object.error_message


@patch(f'{MODULE_PATH}.PublishingJob.objects.get')
def test_confirm_publish_job_wrong_initial_state(mock_job_get, mock_job_data):
    """Test confirm_and_publish_job when job is not in PREVIEW_READY state."""
    mock_job_object = MagicMock(spec=PublishingJob)
    mock_job_object.task_id = mock_job_data['task_id']
    mock_job_object.status = PublishingJob.Status.PROCESSING
    mock_job_object.get_status_display.return_value = "Processing"

    mock_job_get.return_value = mock_job_object

    with pytest.raises(ValueError, match="Job not ready. Current status: Processing"):
        confirm_and_publish_job(mock_job_data['task_id'])

    mock_job_object.save.assert_not_called()


@patch(f'{MODULE_PATH}.PublishingJob.objects.get', side_effect=PublishingJob.DoesNotExist)
def test_confirm_publish_job_does_not_exist(mock_job_get):
    """Test confirm_and_publish_job when the job ID does not exist."""
    task_id = uuid.uuid4()
    with pytest.raises(PublishingJob.DoesNotExist):
        confirm_and_publish_job(task_id)
    mock_job_get.assert_called_once_with(pk=task_id)