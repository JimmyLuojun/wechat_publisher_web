# publishing_engine/tests/test_payload_builder.py
# (Assuming you place tests within the engine package)
# Or: /Users/junluo/Documents/wechat_publisher_web/publisher/tests/test_payload_builder.py
# (If you prefer keeping all tests in the Django app test dir)

import pytest
from unittest.mock import patch, MagicMock

# Import the functions to test
from publishing_engine.core.payload_builder import generate_digest, build_draft_payload, MAX_DIGEST_LENGTH

# --- Tests for generate_digest ---

def test_generate_digest_from_metadata():
    """Test digest generation when provided in metadata."""
    metadata = {"digest": "This is the exact digest."}
    html_content = "<p>Some content</p>"
    expected_digest = "This is the exact digest."
    assert generate_digest(metadata, html_content) == expected_digest

def test_generate_digest_from_metadata_truncation():
    """Test digest truncation when metadata digest is too long."""
    long_digest = "A" * (MAX_DIGEST_LENGTH + 10)
    metadata = {"digest": long_digest}
    html_content = "<p>Some content</p>"
    expected_digest = "A" * MAX_DIGEST_LENGTH
    assert generate_digest(metadata, html_content) == expected_digest

# Mock BeautifulSoup for tests relying on HTML parsing
@patch('publishing_engine.core.payload_builder.BeautifulSoup')
def test_generate_digest_from_html(mock_bs):
    """Test digest generation from HTML content."""
    mock_soup_instance = MagicMock()
    # Configure the mock's get_text method
    mock_soup_instance.get_text.return_value = "This is the plain text extracted from HTML content."
    mock_bs.return_value = mock_soup_instance # Make BeautifulSoup() return our mock

    metadata = {} # No digest in metadata
    html_content = "<p>This is the <b>HTML</b> content.</p>" # Actual HTML passed
    expected_digest = "This is the plain text extracted from HTML content."[:MAX_DIGEST_LENGTH]

    assert generate_digest(metadata, html_content) == expected_digest
    mock_bs.assert_called_once_with(html_content, 'lxml')
    mock_soup_instance.get_text.assert_called_once_with(separator=' ', strip=True)

@patch('publishing_engine.core.payload_builder.BeautifulSoup')
def test_generate_digest_from_html_truncation(mock_bs):
    """Test digest truncation when generated from long HTML content."""
    long_text = "B" * (MAX_DIGEST_LENGTH + 20)
    mock_soup_instance = MagicMock()
    mock_soup_instance.get_text.return_value = long_text
    mock_bs.return_value = mock_soup_instance

    metadata = {}
    html_content = "<p>" + long_text + "</p>"
    expected_digest = "B" * MAX_DIGEST_LENGTH
    assert generate_digest(metadata, html_content) == expected_digest

def test_generate_digest_no_metadata_no_html():
    """Test digest generation when no metadata digest and no HTML are provided."""
    metadata = {}
    html_content = "" # Empty HTML
    expected_digest = "No summary provided."
    assert generate_digest(metadata, html_content) == expected_digest

# --- Tests for build_draft_payload ---

@patch('publishing_engine.core.payload_builder.generate_digest')
def test_build_draft_payload_success(mock_generate_digest):
    """Test successful payload building."""
    mock_generate_digest.return_value = "Generated Digest"
    metadata = {
        "title": "My Article Title",
        "author": "Test Author",
        "content_source_url": "http://example.com/source",
        "need_open_comment": 1,
        "only_fans_can_comment": 1,
        # No digest provided, will use mocked generate_digest
    }
    html_content = "<p>Article content goes here.</p>"
    thumb_media_id = "PERMANENT_MEDIA_ID_123"

    expected_payload = {
        "title": "My Article Title",
        "author": "Test Author",
        "digest": "Generated Digest", # From mocked function
        "content": "<p>Article content goes here.</p>",
        "content_source_url": "http://example.com/source",
        "thumb_media_id": "PERMANENT_MEDIA_ID_123",
        "need_open_comment": 1,
        "only_fans_can_comment": 1,
    }

    payload = build_draft_payload(metadata, html_content, thumb_media_id)
    mock_generate_digest.assert_called_once_with(metadata, html_content)
    assert payload == expected_payload

@patch('publishing_engine.core.payload_builder.generate_digest')
def test_build_draft_payload_minimal_metadata(mock_generate_digest):
    """Test payload building with only required metadata."""
    mock_generate_digest.return_value = "Generated Minimal Digest"
    metadata = {"title": "Minimal Title"} # Only title provided
    html_content = "<p>Minimal content.</p>"
    thumb_media_id = "PERM_ID_456"

    expected_payload = {
        "title": "Minimal Title",
        "author": "", # Default
        "digest": "Generated Minimal Digest",
        "content": "<p>Minimal content.</p>",
        "content_source_url": "", # Default
        "thumb_media_id": "PERM_ID_456",
        "need_open_comment": 0, # Default
        "only_fans_can_comment": 0, # Default
    }

    payload = build_draft_payload(metadata, html_content, thumb_media_id)
    mock_generate_digest.assert_called_once_with(metadata, html_content)
    assert payload == expected_payload

def test_build_draft_payload_missing_title():
    """Test payload building fails if title is missing."""
    metadata = {"author": "Some Author"} # No title
    html_content = "<p>Content</p>"
    thumb_media_id = "PERM_ID_789"
    with pytest.raises(KeyError, match="Required metadata 'title' is missing."):
        build_draft_payload(metadata, html_content, thumb_media_id)

def test_build_draft_payload_empty_thumb_id():
    """Test payload building fails if thumb_media_id is empty."""
    metadata = {"title": "A Title"}
    html_content = "<p>Content</p>"
    thumb_media_id = "" # Empty
    with pytest.raises(ValueError, match="thumb_media_id cannot be empty."):
        build_draft_payload(metadata, html_content, thumb_media_id)

    thumb_media_id = None # None
    with pytest.raises(ValueError, match="thumb_media_id cannot be empty."):
        build_draft_payload(metadata, html_content, thumb_media_id)