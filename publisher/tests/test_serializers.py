# /Users/junluo/Documents/wechat_publisher_web/publisher/tests/test_serializers.py

import uuid
from unittest.mock import MagicMock
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers # To catch ValidationError

# Import serializers from your app
from publisher.serializers import (
    UploadSerializer,
    ConfirmSerializer,
    PreviewResponseSerializer,
    ConfirmResponseSerializer
)

# --- Fixtures ---

@pytest.fixture
def mock_markdown_file():
    return SimpleUploadedFile("test.md", b"## Markdown Content", content_type="text/markdown")

@pytest.fixture
def mock_cover_image():
    # Create a small dummy JPEG content
    jpeg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x03\x02\x02\x02\x02\x02\x03\x02\x02\x02\x03\x03\x03\x03\x04\x06\x04\x04\x04\x04\x04\x08\x06\x06\x05\x06\t\x08\n\n\t\x08\t\t\n\x0c\x0f\x0c\n\x0b\x0e\x0b\t\t\r\x11\r\x0e\x0f\x10\x10\x11\x10\n\x0c\x12\x13\x12\x10\x13\x0f\x10\x10\x10\xff\xc9\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xcc\x00\x06\x00\x10\x10\x05\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9'
    return SimpleUploadedFile("cover.jpg", jpeg_content, content_type="image/jpeg")

@pytest.fixture
def mock_content_image_1():
    return SimpleUploadedFile("image1.png", b"dummy png data", content_type="image/png")

@pytest.fixture
def mock_content_image_2():
    return SimpleUploadedFile("image2.jpg", b"dummy jpg data", content_type="image/jpeg")

# --- Tests for UploadSerializer ---

def test_upload_serializer_valid_minimum(mock_markdown_file, mock_cover_image):
    """Test UploadSerializer with minimum required valid data."""
    data = {
        'markdown_file': mock_markdown_file,
        'cover_image': mock_cover_image,
        # content_images field is omitted from input data
    }
    serializer = UploadSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert 'markdown_file' in serializer.validated_data
    assert 'cover_image' in serializer.validated_data
    # **CORRECTION HERE:** Check that getting 'content_images' with a default of [] results in []
    # This confirms the key is either absent or its value is [] (which isn't the case here, it's absent)
    assert serializer.validated_data.get('content_images', []) == []
    # Alternative check: Assert the key is simply not present
    # assert 'content_images' not in serializer.validated_data

def test_upload_serializer_valid_with_content_images(mock_markdown_file, mock_cover_image, mock_content_image_1, mock_content_image_2):
    """Test UploadSerializer with valid data including content images."""
    data = {
        'markdown_file': mock_markdown_file,
        'cover_image': mock_cover_image,
        'content_images': [mock_content_image_1, mock_content_image_2]
    }
    serializer = UploadSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert len(serializer.validated_data['content_images']) == 2

def test_upload_serializer_missing_markdown(mock_cover_image):
    """Test UploadSerializer missing required markdown_file."""
    data = {'cover_image': mock_cover_image}
    serializer = UploadSerializer(data=data)
    assert not serializer.is_valid()
    assert 'markdown_file' in serializer.errors

def test_upload_serializer_missing_cover(mock_markdown_file):
    """Test UploadSerializer missing required cover_image."""
    data = {'markdown_file': mock_markdown_file}
    serializer = UploadSerializer(data=data)
    assert not serializer.is_valid()
    assert 'cover_image' in serializer.errors

def test_upload_serializer_invalid_content_image_type(mock_markdown_file, mock_cover_image):
    """Test UploadSerializer with invalid data type in content_images list."""
    data = {
        'markdown_file': mock_markdown_file,
        'cover_image': mock_cover_image,
        'content_images': ["not_a_file", mock_content_image_1]
    }
    serializer = UploadSerializer(data=data)
    assert not serializer.is_valid()
    assert 'content_images' in serializer.errors


# --- Tests for ConfirmSerializer ---

def test_confirm_serializer_valid():
    """Test ConfirmSerializer with a valid UUID."""
    task_id = uuid.uuid4()
    data = {'task_id': task_id}
    serializer = ConfirmSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data['task_id'] == task_id

def test_confirm_serializer_invalid_uuid():
    """Test ConfirmSerializer with an invalid UUID format."""
    data = {'task_id': 'not-a-valid-uuid'}
    serializer = ConfirmSerializer(data=data)
    assert not serializer.is_valid()
    assert 'task_id' in serializer.errors

def test_confirm_serializer_missing_uuid():
    """Test ConfirmSerializer missing the task_id field."""
    data = {}
    serializer = ConfirmSerializer(data=data)
    assert not serializer.is_valid()
    assert 'task_id' in serializer.errors

# --- Tests for PreviewResponseSerializer ---

def test_preview_response_serializer():
    """Test PreviewResponseSerializer formats data correctly for serialization."""
    task_id = uuid.uuid4()
    input_data = {
        'task_id': task_id,
        'preview_url': f'http://test.com/media/previews/{task_id}.html'
    }
    serializer = PreviewResponseSerializer(instance=input_data)
    serialized_data = serializer.data
    assert serialized_data['task_id'] == str(task_id)
    assert serialized_data['preview_url'] == input_data['preview_url']

# --- Tests for ConfirmResponseSerializer ---

def test_confirm_response_serializer_success():
    """Test ConfirmResponseSerializer formats success data correctly for serialization."""
    task_id = uuid.uuid4()
    media_id = 'some_wechat_media_id_123'
    input_data = {
        'task_id': task_id,
        'status': 'Published',
        'message': 'Article published successfully.',
        'wechat_media_id': media_id
    }
    serializer = ConfirmResponseSerializer(instance=input_data)
    serialized_data = serializer.data
    assert serialized_data['task_id'] == str(task_id)
    assert serialized_data['status'] == 'Published'
    assert serialized_data['message'] == input_data['message']
    assert serialized_data['wechat_media_id'] == media_id

def test_confirm_response_serializer_null_media_id():
    """Test ConfirmResponseSerializer handles null wechat_media_id for serialization."""
    task_id = uuid.uuid4()
    input_data = {
        'task_id': task_id,
        'status': 'Failed',
        'message': 'Publication failed.',
        'wechat_media_id': None
    }
    serializer = ConfirmResponseSerializer(instance=input_data)
    serialized_data = serializer.data
    assert serialized_data['task_id'] == str(task_id)
    assert serialized_data['status'] == 'Failed'
    assert serialized_data['wechat_media_id'] is None