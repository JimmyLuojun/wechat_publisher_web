# tests/publisher/test_cloudinary_client.py

import pytest
from unittest.mock import patch, MagicMock
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

# --- Import the actual Cloudinary exception class ---
import cloudinary # Import the base library
# Or be more specific:
# from cloudinary.exceptions import Error as CloudinaryError

# Import the client module we want to test
from publisher import cloudinary_client

# --- Fixtures ---

@pytest.fixture
def mock_cloudinary_sdk(mocker):
    """Mocks the cloudinary library modules."""
    # Mock the config function
    mock_config = mocker.patch('cloudinary.config', return_value=None)
    # Mock the uploader function
    mock_upload = mocker.patch('cloudinary.uploader.upload', return_value={
        'public_id': 'test_public_id',
        'version': 12345,
        'signature': 'test_sig',
        'width': 100,
        'height': 100,
        'format': 'jpg',
        'resource_type': 'image',
        'created_at': '2025-04-14T00:00:00Z',
        'tags': [],
        'bytes': 12345,
        'type': 'upload',
        'etag': 'test_etag',
        'placeholder': False,
        'url': 'http://res.cloudinary.com/test-cloud/image/upload/v12345/test_public_id.jpg',
        'secure_url': 'https://res.cloudinary.com/test-cloud/image/upload/v12345/test_public_id.jpg', # Important part
        'original_filename': 'test_image'
    })
    return {
        'config': mock_config,
        'upload': mock_upload
    }

@pytest.fixture
def sample_image_file():
    """Creates a sample image file for testing uploads."""
    return SimpleUploadedFile("test_image.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", content_type="image/jpeg")

@pytest.fixture
def sample_image_file_list(sample_image_file):
    """Creates a list of sample image files."""
    img2 = SimpleUploadedFile("test_image2.png", b"pngcontent", content_type="image/png")
    return [sample_image_file, img2]

# --- Test Functions ---

def test_configure_cloudinary_success(mock_cloudinary_sdk, settings):
    """Test successful configuration when settings are present."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    settings.CLOUDINARY_API_KEY = "test-key"
    settings.CLOUDINARY_API_SECRET = "test-secret"
    cloudinary_client._cloudinary_configured = False # Reset flag

    assert cloudinary_client.configure_cloudinary() is True
    mock_cloudinary_sdk['config'].assert_called_once_with(
        cloud_name="test-cloud",
        api_key="test-key",
        api_secret="test-secret",
        secure=True
    )
    assert cloudinary_client._cloudinary_configured is True

    # Test idempotency
    mock_cloudinary_sdk['config'].reset_mock()
    assert cloudinary_client.configure_cloudinary() is True
    mock_cloudinary_sdk['config'].assert_not_called()


def test_configure_cloudinary_missing_settings(mock_cloudinary_sdk, settings):
    """Test configuration failure when settings are missing."""
    settings.CLOUDINARY_CLOUD_NAME = None
    settings.CLOUDINARY_API_KEY = "test-key"
    settings.CLOUDINARY_API_SECRET = "test-secret"
    cloudinary_client._cloudinary_configured = False

    assert cloudinary_client.configure_cloudinary() is False
    mock_cloudinary_sdk['config'].assert_not_called()
    assert cloudinary_client._cloudinary_configured is False


def test_upload_image_success(mock_cloudinary_sdk, sample_image_file, settings):
    """Test successful single image upload."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    settings.CLOUDINARY_API_KEY = "test-key"
    settings.CLOUDINARY_API_SECRET = "test-secret"
    cloudinary_client._cloudinary_configured = True # Assume pre-configured

    result = cloudinary_client.upload_image(sample_image_file)

    assert result is not None
    assert 'secure_url' in result
    assert result['secure_url'] == 'https://res.cloudinary.com/test-cloud/image/upload/v12345/test_public_id.jpg'
    mock_cloudinary_sdk['upload'].assert_called_once()
    call_args, call_kwargs = mock_cloudinary_sdk['upload'].call_args
    assert call_args[0] == sample_image_file
    assert call_kwargs['folder'] == settings.CLOUDINARY_UPLOAD_FOLDER
    assert call_kwargs['resource_type'] == 'image'


def test_upload_image_cloudinary_error(mock_cloudinary_sdk, sample_image_file, settings):
    """Test handling of an upload error from the Cloudinary SDK."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    settings.CLOUDINARY_API_KEY = "test-key"
    settings.CLOUDINARY_API_SECRET = "test-secret"
    cloudinary_client._cloudinary_configured = True

    # --- CORRECTED LINE ---
    # Simulate an error using the actual Cloudinary exception class
    mock_cloudinary_sdk['upload'].side_effect = cloudinary.exceptions.Error("Simulated upload failed")
    # Or use the alias if you imported it:
    # mock_cloudinary_sdk['upload'].side_effect = CloudinaryError("Simulated upload failed")

    result = cloudinary_client.upload_image(sample_image_file)

    assert result is None
    mock_cloudinary_sdk['upload'].assert_called_once()


def test_upload_image_not_configured(mock_cloudinary_sdk, sample_image_file, settings):
    """Test upload attempt when Cloudinary is not configured."""
    settings.CLOUDINARY_CLOUD_NAME = None
    cloudinary_client._cloudinary_configured = False

    result = cloudinary_client.upload_image(sample_image_file)

    assert result is None
    mock_cloudinary_sdk['upload'].assert_not_called()


def test_upload_content_images_success(mock_cloudinary_sdk, sample_image_file_list, settings):
    """Test uploading a list of content images successfully."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    settings.CLOUDINARY_API_KEY = "test-key"
    settings.CLOUDINARY_API_SECRET = "test-secret"
    cloudinary_client._cloudinary_configured = True

    mock_cloudinary_sdk['upload'].side_effect = [
        {'secure_url': 'https://.../test_image.jpg', 'public_id': 'id1'},
        {'secure_url': 'https://.../test_image2.png', 'public_id': 'id2'}
    ]

    result_map = cloudinary_client.upload_content_images(sample_image_file_list)

    assert len(result_map) == 2
    assert result_map['test_image.jpg'] == 'https://.../test_image.jpg'
    assert result_map['test_image2.png'] == 'https://.../test_image2.png'
    assert mock_cloudinary_sdk['upload'].call_count == 2


def test_upload_content_images_partial_failure(mock_cloudinary_sdk, sample_image_file_list, settings):
    """Test uploading multiple images where one fails."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    settings.CLOUDINARY_API_KEY = "test-key"
    settings.CLOUDINARY_API_SECRET = "test-secret"
    cloudinary_client._cloudinary_configured = True

    # --- CORRECTED LINE ---
    # First upload succeeds, second fails using the actual Cloudinary exception
    mock_cloudinary_sdk['upload'].side_effect = [
        {'secure_url': 'https://.../test_image.jpg', 'public_id': 'id1'},
        cloudinary.exceptions.Error("Upload failed for image 2")
        # Or use the alias if imported:
        # CloudinaryError("Upload failed for image 2")
    ]

    result_map = cloudinary_client.upload_content_images(sample_image_file_list)

    assert len(result_map) == 2
    assert result_map['test_image.jpg'] == 'https://.../test_image.jpg'
    assert result_map['test_image2.png'] is None # Failed upload results in None
    assert mock_cloudinary_sdk['upload'].call_count == 2


def test_upload_content_images_not_configured(mock_cloudinary_sdk, sample_image_file_list, settings):
    """Test content image upload when not configured."""
    settings.CLOUDINARY_CLOUD_NAME = None
    cloudinary_client._cloudinary_configured = False

    result_map = cloudinary_client.upload_content_images(sample_image_file_list)

    assert len(result_map) == 2
    assert result_map['test_image.jpg'] is None
    assert result_map['test_image2.png'] is None
    mock_cloudinary_sdk['upload'].assert_not_called()

