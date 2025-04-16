import pytest
import json
import uuid
import yaml
from unittest.mock import patch, MagicMock

# from django.urls import reverse # Using hardcoded URLs for now
from django.core.files.uploadedfile import SimpleUploadedFile # Need this again
from rest_framework import status

# Import the model needed for DoesNotExist exception
from publisher.models import PublishingJob

# Use pytest-django's db marker and client fixture
pytestmark = pytest.mark.django_db

# --- Constants for URLs (Using hardcoded paths as a workaround) ---
# !!! Recommended: Fix urls.py and use reverse('publisher:...') instead !!!
UPLOAD_FORM_URL = '/publisher/upload/'
PROCESS_API_URL = '/publisher/api/process/'
CONFIRM_API_URL = '/publisher/api/confirm/'

# NOTE: Fixtures like sample_md_file_fixture, sample_cover_file_fixture,
#       sample_content_files_fixture are now defined in conftest.py
#       and automatically injected by pytest when listed as test function arguments.

# --- Tests for UploadFormView ---

def test_upload_form_view_get(client):
    """Test GET request to the upload form view."""
    response = client.get(UPLOAD_FORM_URL)
    assert response.status_code == status.HTTP_200_OK
    # Check if the correct template was used (requires template name in view)
    assert 'publisher/upload_form.html' in [t.name for t in response.templates]
    # Check for some expected content in the response
    assert b'<form' in response.content # Check if form tag exists


# --- Tests for ProcessPreviewAPIView ---

@patch('publisher.views.start_processing_job') # Target where it's imported in views.py
def test_process_preview_success(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture, sample_content_files_fixture):
    """Test successful POST request to process files using conftest fixtures."""
    task_id = uuid.uuid4()
    preview_url = "/media/previews/some_preview.html"
    # Configure the mock service function return value
    mock_start_job.return_value = {"task_id": task_id, "preview_url": preview_url}

    # Prepare multipart form data using fixtures from conftest.py
    # NOTE: Conftest fixtures provide SimpleUploadedFile objects directly
    data = {
        'markdown_file': sample_md_file_fixture,
        'cover_image': sample_cover_file_fixture,
        'content_images': sample_content_files_fixture # Pass the list from the fixture
    }

    response = client.post(PROCESS_API_URL, data=data, format='multipart') # Use format='multipart'

    # Assertions
    assert response.status_code == status.HTTP_200_OK
    expected_response_data = {"task_id": str(task_id), "preview_url": preview_url}
    assert response.json() == expected_response_data

    # Assert service function was called correctly
    mock_start_job.assert_called_once()
    call_args, call_kwargs = mock_start_job.call_args
    # Check names to ensure the correct fixture files were passed
    assert call_kwargs['markdown_file'].name == 'fixture.md'
    assert call_kwargs['cover_image'].name == 'fixture_cover.gif' # Matches conftest fixture
    assert len(call_kwargs['content_images']) == 2
    assert call_kwargs['content_images'][0].name == 'image1.gif' # Matches conftest fixture
    assert call_kwargs['content_images'][1].name == 'image2.gif' # Matches conftest fixture

@patch('publisher.views.start_processing_job')
def test_process_preview_serializer_invalid(mock_start_job, client, sample_cover_file_fixture):
    """Test POST request with missing required fields using conftest fixture."""
    data = {
        # Missing markdown_file
        'cover_image': sample_cover_file_fixture, # Use fixture directly
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'markdown_file' in response.json() # Check that the error is about the missing field
    assert 'No file was submitted.' in response.json()['markdown_file'][0]
    mock_start_job.assert_not_called() # Service should not be called

@patch('publisher.views.start_processing_job', side_effect=FileNotFoundError("CSS file missing"))
def test_process_preview_service_file_not_found(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture):
    """Test handling FileNotFoundError from the service using conftest fixtures."""
    data = {
        'markdown_file': sample_md_file_fixture, # Use fixture
        'cover_image': sample_cover_file_fixture, # Use fixture
        # No content images needed for this error case
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.json()
    assert "Processing failed: CSS file missing" in response.json()['error'] # Check specific message handling
    mock_start_job.assert_called_once()

@patch('publisher.views.start_processing_job', side_effect=ValueError("Invalid metadata format"))
def test_process_preview_service_value_error(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture):
    """Test handling ValueError from the service using conftest fixtures."""
    data = {
        'markdown_file': sample_md_file_fixture, # Use fixture
        'cover_image': sample_cover_file_fixture, # Use fixture
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.json()
    assert "Processing failed due to invalid input or format. Details: Invalid metadata format" in response.json()['error']
    mock_start_job.assert_called_once()

@patch('publisher.views.start_processing_job', side_effect=yaml.YAMLError("Bad YAML structure"))
def test_process_preview_service_yaml_error(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture):
    """Test handling YAMLError from the service using conftest fixtures."""
    data = {
        'markdown_file': sample_md_file_fixture, # Use fixture
        'cover_image': sample_cover_file_fixture, # Use fixture
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.json()
    assert "Processing failed due to invalid input or format. Details: Bad YAML structure" in response.json()['error']
    mock_start_job.assert_called_once()

@patch('publisher.views.start_processing_job', side_effect=RuntimeError("GCS upload failed"))
def test_process_preview_service_runtime_error_gcs(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture):
    """Test handling RuntimeError suggesting GCS issue using conftest fixtures."""
    data = {
        'markdown_file': sample_md_file_fixture, # Use fixture
        'cover_image': sample_cover_file_fixture, # Use fixture
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_502_BAD_GATEWAY # Expecting 502 due to "GCS" in error
    assert "error" in response.json()
    assert "Processing failed due to a runtime error: GCS upload failed" in response.json()['error']
    mock_start_job.assert_called_once()

@patch('publisher.views.start_processing_job', side_effect=RuntimeError("Something else broke"))
def test_process_preview_service_runtime_error_other(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture):
    """Test handling generic RuntimeError using conftest fixtures."""
    data = {
        'markdown_file': sample_md_file_fixture, # Use fixture
        'cover_image': sample_cover_file_fixture, # Use fixture
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR # Expecting 500
    assert "error" in response.json()
    assert "Processing failed due to a runtime error: Something else broke" in response.json()['error']
    mock_start_job.assert_called_once()

@patch('publisher.views.start_processing_job', side_effect=ImportError("Missing engine module"))
def test_process_preview_service_import_error(mock_start_job, client, sample_md_file_fixture, sample_cover_file_fixture):
    """Test handling ImportError from the service using conftest fixtures."""
    data = {
        'markdown_file': sample_md_file_fixture, # Use fixture
        'cover_image': sample_cover_file_fixture, # Use fixture
    }
    response = client.post(PROCESS_API_URL, data=data, format='multipart')

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "error" in response.json()
    assert "Server configuration error: Required processing module not found." in response.json()['error']
    mock_start_job.assert_called_once()


# --- Tests for ConfirmPublishAPIView ---
# (These tests do not need the file fixtures from conftest.py)

@patch('publisher.views.confirm_and_publish_job') # Target where it's imported in views.py
def test_confirm_publish_success(mock_confirm_job, client):
    """Test successful POST request to confirm and publish."""
    task_id = uuid.uuid4()
    wechat_id = "wechat_draft_123"
    # Configure mock service return value
    mock_confirm_job.return_value = {
        "task_id": task_id,
        "status": "Published Successfully", # Match the status string from service/model
        "message": "Article published to WeChat drafts successfully.",
        "wechat_media_id": wechat_id
    }

    # Prepare JSON data
    data = {"task_id": str(task_id)}

    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_200_OK
    expected_response_data = {
        "task_id": str(task_id),
        "status": "Published Successfully",
        "message": "Article published to WeChat drafts successfully.",
        "wechat_media_id": wechat_id
    }
    assert response.json() == expected_response_data
    mock_confirm_job.assert_called_once_with(task_id) # Check service called with UUID


@patch('publisher.views.confirm_and_publish_job')
def test_confirm_publish_serializer_invalid_uuid(mock_confirm_job, client):
    """Test POST request with invalid UUID format."""
    data = {"task_id": "not-a-uuid"}
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'task_id' in response.json()
    assert "Must be a valid UUID." in response.json()['task_id'][0]
    mock_confirm_job.assert_not_called()

@patch('publisher.views.confirm_and_publish_job')
def test_confirm_publish_serializer_missing_field(mock_confirm_job, client):
    """Test POST request with missing task_id field."""
    data = {} # Missing task_id
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'task_id' in response.json()
    assert "This field is required." in response.json()['task_id'][0]
    mock_confirm_job.assert_not_called()

@patch('publisher.views.confirm_and_publish_job', side_effect=PublishingJob.DoesNotExist)
def test_confirm_publish_job_not_found(mock_confirm_job, client):
    """Test handling when the PublishingJob does not exist."""
    task_id = uuid.uuid4()
    data = {"task_id": str(task_id)}
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "error" in response.json()
    assert "Publishing job not found." in response.json()['error']
    mock_confirm_job.assert_called_once_with(task_id)

@patch('publisher.views.confirm_and_publish_job', side_effect=ValueError("Job not ready"))
def test_confirm_publish_value_error(mock_confirm_job, client):
    """Test handling ValueError from the service (e.g., job state error)."""
    task_id = uuid.uuid4()
    data = {"task_id": str(task_id)}
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.json()
    assert "Publishing failed: Job not ready" in response.json()['error']
    mock_confirm_job.assert_called_once_with(task_id)

@patch('publisher.views.confirm_and_publish_job', side_effect=RuntimeError("WeChat API timeout"))
def test_confirm_publish_runtime_error_wechat(mock_confirm_job, client):
    """Test handling RuntimeError suggesting WeChat issue."""
    task_id = uuid.uuid4()
    data = {"task_id": str(task_id)}
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_502_BAD_GATEWAY # Expect 502
    assert "error" in response.json()
    assert "Publishing failed due to API or runtime issue: WeChat API timeout" in response.json()['error']
    mock_confirm_job.assert_called_once_with(task_id)

@patch('publisher.views.confirm_and_publish_job', side_effect=RuntimeError("Something else broke"))
def test_confirm_publish_runtime_error_other(mock_confirm_job, client):
    """Test handling generic RuntimeError."""
    task_id = uuid.uuid4()
    data = {"task_id": str(task_id)}
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR # Expect 500
    assert "error" in response.json()
    assert "Publishing failed due to API or runtime issue: Something else broke" in response.json()['error']
    mock_confirm_job.assert_called_once_with(task_id)

@patch('publisher.views.confirm_and_publish_job', side_effect=ImportError("Missing engine module"))
def test_confirm_publish_import_error(mock_confirm_job, client):
    """Test handling ImportError during publish."""
    task_id = uuid.uuid4()
    data = {"task_id": str(task_id)}
    response = client.post(CONFIRM_API_URL, data=json.dumps(data), content_type='application/json')

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "error" in response.json()
    assert "Server configuration error: Required publishing module not found." in response.json()['error']
    mock_confirm_job.assert_called_once_with(task_id)

