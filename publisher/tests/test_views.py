# /Users/junluo/Documents/wechat_publisher_web/publisher/tests/test_views.py

import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock, ANY
import uuid
from pathlib import Path
import yaml

from publisher.models import PublishingJob

# --- Fixtures ---

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def mock_markdown_file_upload():
    return SimpleUploadedFile(
        name='test.md',
        content=b"## Markdown Content",
        content_type='text/markdown'
    )

@pytest.fixture
def mock_cover_image_upload():
    jpeg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc9\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xcc\x00\x06\x00\x10\x10\x05\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9'
    return SimpleUploadedFile(
        name='cover.jpg',
        content=jpeg_content,
        content_type='image/jpeg'
    )

@pytest.fixture
def mock_content_image_upload():
     png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xfc\xff?\x03\x00\x01\xfa`\x05\xe0\x00\x00\x00\x00IEND\xaeB`\x82'
     return SimpleUploadedFile(
         name='content.png',
         content=png_content,
         content_type='image/png'
     )

VIEWS_MODULE_PATH = 'publisher.views'

# --- Test UploadFormView ---

@pytest.mark.django_db
# *** ADDED: Explicitly set urlconf for this test ***
@pytest.mark.urls('wechat_publisher_web.urls')
def test_upload_form_view_get(api_client):
    """Test GET request for the upload form page."""
    # This should now resolve correctly with the urls marker
    url = reverse('publisher:upload_form')
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert 'publisher/upload_form.html' in [t.name for t in response.templates]

# --- Test ProcessPreviewAPIView ---

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls') # Add marker here too for consistency
@patch(f'{VIEWS_MODULE_PATH}.default_storage.save')
@patch(f'{VIEWS_MODULE_PATH}.start_processing_job')
def test_process_preview_api_success(
    mock_start_job, mock_storage_save, api_client,
    mock_markdown_file_upload, mock_cover_image_upload, mock_content_image_upload,
    settings, tmp_path # *** ADDED tmp_path fixture ***
    ):
    """Test successful POST request to process/preview endpoint."""
    # --- Arrange ---
    task_id = uuid.uuid4()
    preview_url_path = f"previews/{task_id}.html"
    settings.MEDIA_URL = '/media/'
    # *** CORRECTED: Use tmp_path for MEDIA_ROOT ***
    settings.MEDIA_ROOT = str(tmp_path / "media_root")
    settings.CONTENT_IMAGES_SUBDIR = 'test_content_images'
    # Calculate expected path based on tmp_path
    expected_content_dir = tmp_path / "media_root" / settings.CONTENT_IMAGES_SUBDIR

    mock_start_job.return_value = {
        'task_id': task_id,
        'preview_url': f"{settings.MEDIA_URL}{preview_url_path}"
    }
    # Relative path for storage save doesn't need tmp_path prefix
    mock_storage_save.return_value = f"{settings.CONTENT_IMAGES_SUBDIR}/content.png"

    url = reverse('publisher:process_preview_api')
    data = {
        'markdown_file': mock_markdown_file_upload,
        'cover_image': mock_cover_image_upload,
        'content_images': [mock_content_image_upload]
    }

    # --- Act ---
    response = api_client.post(url, data, format='multipart')

    # --- Assert ---
    # mkdir should now succeed inside tmp_path, allowing the view to proceed
    assert response.status_code == status.HTTP_200_OK, f"Expected 200, got {response.status_code}. Response data: {response.data}"
    assert response.data['task_id'] == str(task_id)
    assert response.data['preview_url'] == f"/media/{preview_url_path}"

    mock_start_job.assert_called_once()
    call_args, call_kwargs = mock_start_job.call_args
    # Assert the absolute path passed to the service uses tmp_path
    assert call_kwargs['content_images_dir_abs'] == expected_content_dir
    assert mock_storage_save.call_count == 1


@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
def test_process_preview_api_invalid_data(api_client, mock_cover_image_upload):
    """Test POST with missing required data."""
    url = reverse('publisher:process_preview_api')
    data = {'cover_image': mock_cover_image_upload}
    response = api_client.post(url, data, format='multipart')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'markdown_file' in response.data


@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.start_processing_job', side_effect=ValueError("Invalid YAML in metadata"))
def test_process_preview_api_service_value_error(mock_start_job, api_client, mock_markdown_file_upload, mock_cover_image_upload, tmp_path, settings): # Add tmp_path/settings
    """Test error handling when service raises ValueError."""
    # Need MEDIA_ROOT set for directory creation attempt, even if service fails later
    settings.MEDIA_ROOT = str(tmp_path / "media_root")
    settings.CONTENT_IMAGES_SUBDIR = 'test_content_images'

    url = reverse('publisher:process_preview_api')
    data = {
        'markdown_file': mock_markdown_file_upload,
        'cover_image': mock_cover_image_upload,
    }
    response = api_client.post(url, data, format='multipart')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.data
    assert "Invalid YAML" in response.data["error"]

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.start_processing_job', side_effect=FileNotFoundError("CSS file missing"))
def test_process_preview_api_service_file_not_found(mock_start_job, api_client, mock_markdown_file_upload, mock_cover_image_upload, tmp_path, settings): # Add tmp_path/settings
    """Test error handling when service raises FileNotFoundError."""
    settings.MEDIA_ROOT = str(tmp_path / "media_root")
    settings.CONTENT_IMAGES_SUBDIR = 'test_content_images'

    url = reverse('publisher:process_preview_api')
    data = {
        'markdown_file': mock_markdown_file_upload,
        'cover_image': mock_cover_image_upload,
    }
    response = api_client.post(url, data, format='multipart')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.data
    assert "Required file not found" in response.data["error"]


@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.start_processing_job', side_effect=RuntimeError("WeChat API failed"))
def test_process_preview_api_service_runtime_error(mock_start_job, api_client, mock_markdown_file_upload, mock_cover_image_upload, tmp_path, settings): # Add tmp_path/settings
    """Test error handling when service raises RuntimeError."""
    settings.MEDIA_ROOT = str(tmp_path / "media_root")
    settings.CONTENT_IMAGES_SUBDIR = 'test_content_images'

    url = reverse('publisher:process_preview_api')
    data = {
        'markdown_file': mock_markdown_file_upload,
        'cover_image': mock_cover_image_upload,
    }
    response = api_client.post(url, data, format='multipart')
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "error" in response.data
    assert "runtime error" in response.data["error"]


# --- Test ConfirmPublishAPIView ---

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.confirm_and_publish_job')
def test_confirm_publish_api_success(mock_confirm_job, api_client):
    task_id = uuid.uuid4()
    mock_confirm_job.return_value = {
        'task_id': task_id, 'status': 'Published',
        'message': 'OK', 'wechat_media_id': 'final_id_confirm'
    }
    url = reverse('publisher:confirm_publish_api')
    data = {'task_id': str(task_id)}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['task_id'] == str(task_id)
    mock_confirm_job.assert_called_once_with(task_id)

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
def test_confirm_publish_api_invalid_uuid(api_client):
    url = reverse('publisher:confirm_publish_api')
    data = {'task_id': 'not-a-uuid'}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'task_id' in response.data

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.confirm_and_publish_job', side_effect=PublishingJob.DoesNotExist)
def test_confirm_publish_api_job_not_found(mock_confirm_job, api_client):
    task_id = uuid.uuid4()
    url = reverse('publisher:confirm_publish_api')
    data = {'task_id': str(task_id)}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "error" in response.data

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.confirm_and_publish_job', side_effect=ValueError("Job not ready"))
def test_confirm_publish_api_service_value_error(mock_confirm_job, api_client):
    task_id = uuid.uuid4()
    url = reverse('publisher:confirm_publish_api')
    data = {'task_id': str(task_id)}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.data

@pytest.mark.django_db
@pytest.mark.urls('wechat_publisher_web.urls')
@patch(f'{VIEWS_MODULE_PATH}.confirm_and_publish_job', side_effect=RuntimeError("WeChat API publish failed"))
def test_confirm_publish_api_service_runtime_error(mock_confirm_job, api_client):
    task_id = uuid.uuid4()
    url = reverse('publisher:confirm_publish_api')
    data = {'task_id': str(task_id)}
    response = api_client.post(url, data, format='json')
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert "error" in response.data