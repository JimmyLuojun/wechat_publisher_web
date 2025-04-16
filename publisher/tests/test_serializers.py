# tests/publisher/test_serializers.py

import pytest
import uuid
from django.core.files.uploadedfile import SimpleUploadedFile
from pathlib import Path # Import Path

# Import serializers to test
from publisher.serializers import UploadSerializer, ConfirmSerializer, PreviewResponseSerializer, ConfirmResponseSerializer

# --- Test UploadSerializer ---

# Use the fixtures defined in conftest.py
def test_upload_serializer_valid(sample_md_file_fixture, sample_cover_file_fixture, sample_content_files_fixture):
    """Test UploadSerializer with valid data including content images."""
    # --- CORRECTED: Pass files within the 'data' dictionary ---
    data = {
        'markdown_file': sample_md_file_fixture,
        'cover_image': sample_cover_file_fixture,
        'content_images': sample_content_files_fixture, # Pass list directly
    }
    serializer = UploadSerializer(data=data) # Initialize with only 'data'

    assert serializer.is_valid(), serializer.errors
    validated_data = serializer.validated_data
    assert validated_data['markdown_file'].name == sample_md_file_fixture.name
    assert validated_data['cover_image'].name == sample_cover_file_fixture.name
    assert len(validated_data['content_images']) == len(sample_content_files_fixture)
    assert validated_data['content_images'][0].name == sample_content_files_fixture[0].name


def test_upload_serializer_valid_no_content_images(sample_md_file_fixture, sample_cover_file_fixture):
    """Test UploadSerializer with valid data but no optional content images."""
    # --- CORRECTED: Pass files within the 'data' dictionary ---
    data = {
        'markdown_file': sample_md_file_fixture,
        'cover_image': sample_cover_file_fixture,
        # 'content_images': [] # Omit or pass empty list for optional field
    }
    serializer = UploadSerializer(data=data) # Initialize with only 'data'

    assert serializer.is_valid(), serializer.errors
    validated_data = serializer.validated_data
    # Check content_images is empty or not present in validated_data
    assert 'content_images' not in validated_data or len(validated_data['content_images']) == 0


def test_upload_serializer_missing_required_field():
    """Test UploadSerializer missing a required file."""
    # --- CORRECTED: Pass files within the 'data' dictionary ---
    data = {
        'cover_image': SimpleUploadedFile("c.jpg", b"c", content_type="image/jpeg"),
        # Missing markdown_file
    }
    serializer = UploadSerializer(data=data) # Initialize with only 'data'

    assert not serializer.is_valid()
    assert 'markdown_file' in serializer.errors
    assert 'required' in str(serializer.errors['markdown_file'])


def test_upload_serializer_invalid_cover_type():
    """Test UploadSerializer with non-image file for cover_image."""
     # --- CORRECTED: Pass files within the 'data' dictionary ---
    data = {
        'markdown_file': SimpleUploadedFile("a.md", b"m", content_type="text/markdown"),
        'cover_image': SimpleUploadedFile("c.txt", b"t", content_type="text/plain"), # Invalid
    }
    serializer = UploadSerializer(data=data) # Initialize with only 'data'

    assert not serializer.is_valid()
    assert 'cover_image' in serializer.errors
    assert 'valid image' in str(serializer.errors['cover_image'])


def test_upload_serializer_invalid_md_extension():
    """Test custom validator for markdown file extension."""
    # --- CORRECTED: Pass files within the 'data' dictionary ---
    data = {
        'markdown_file': SimpleUploadedFile("a.txt", b"m", content_type="text/plain"), # Invalid ext
        'cover_image': SimpleUploadedFile("c.jpg", b"c", content_type="image/jpeg"),
    }
    serializer = UploadSerializer(data=data) # Initialize with only 'data'

    assert not serializer.is_valid()
    assert 'markdown_file' in serializer.errors
    # Access the specific error message if needed
    assert any("Invalid file extension" in msg for msg in serializer.errors['markdown_file'])


# --- Test ConfirmSerializer ---
# These tests were passing and don't need changes related to file handling

def test_confirm_serializer_valid():
    """Test ConfirmSerializer with a valid UUID."""
    task_id = uuid.uuid4()
    data = {'task_id': str(task_id)} # Pass UUID as string
    serializer = ConfirmSerializer(data=data)

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data['task_id'] == task_id # Serializer converts to UUID object


def test_confirm_serializer_missing_task_id():
    """Test ConfirmSerializer with missing task_id."""
    data = {}
    serializer = ConfirmSerializer(data=data)

    assert not serializer.is_valid()
    assert 'task_id' in serializer.errors
    assert 'required' in str(serializer.errors['task_id'])


def test_confirm_serializer_invalid_task_id_format():
    """Test ConfirmSerializer with invalid UUID format."""
    data = {'task_id': 'this-is-not-a-uuid'}
    serializer = ConfirmSerializer(data=data)

    assert not serializer.is_valid()
    assert 'task_id' in serializer.errors
    assert 'valid UUID' in str(serializer.errors['task_id'])


# --- Test Response Serializers (usually simple data pass-through) ---
# These tests were passing and don't need changes

def test_preview_response_serializer():
    """Test PreviewResponseSerializer formatting."""
    task_id = uuid.uuid4()
    data = {
        'task_id': task_id,
        'preview_url': 'http://example.com/preview/123.html'
    }
    serializer = PreviewResponseSerializer(instance=data) # Pass data as instance for read-only

    assert serializer.data['task_id'] == str(task_id) # UUIDs are serialized to strings
    assert serializer.data['preview_url'] == 'http://example.com/preview/123.html'


def test_confirm_response_serializer():
    """Test ConfirmResponseSerializer formatting."""
    task_id = uuid.uuid4()
    data = {
        'task_id': task_id,
        'status': 'Published Successfully',
        'message': 'All good.',
        'wechat_media_id': 'wechat_123'
    }
    serializer = ConfirmResponseSerializer(instance=data)

    assert serializer.data['task_id'] == str(task_id)
    assert serializer.data['status'] == 'Published Successfully'
    assert serializer.data['message'] == 'All good.'
    assert serializer.data['wechat_media_id'] == 'wechat_123'


def test_confirm_response_serializer_no_media_id():
    """Test ConfirmResponseSerializer when wechat_media_id might be null."""
    task_id = uuid.uuid4()
    data = {
        'task_id': task_id,
        'status': 'Failed',
        'message': 'Something went wrong.',
        'wechat_media_id': None # Test null value
    }
    serializer = ConfirmResponseSerializer(instance=data)

    assert serializer.data['task_id'] == str(task_id)
    assert serializer.data['status'] == 'Failed'
    assert serializer.data['message'] == 'Something went wrong.'
    assert serializer.data['wechat_media_id'] is None

