# tests/test_api.py (or publishing_engine/wechat/tests/test_api.py)

import pytest
import requests
import json
from pathlib import Path
from unittest.mock import MagicMock # Can use MagicMock directly too

# Assuming your api module is importable like this:
from publishing_engine.wechat import api

# --- Fixtures ---

@pytest.fixture
def mock_requests_session(mocker):
    """Mocks requests.Session and its methods."""
    mock_session_class = mocker.patch('requests.Session', autospec=True)
    mock_session_instance = mock_session_class.return_value

    # Mock prepare_request to return a mock prepared request
    mock_prepared_request = MagicMock()
    mock_prepared_request.headers = {} # Simulate headers dict
    mock_prepared_request.body = b''   # Simulate body bytes
    mock_session_instance.prepare_request.return_value = mock_prepared_request

    # Mock the send method
    mock_response = MagicMock(spec=requests.Response)
    mock_response.request = MagicMock() # Mock request attribute for _check_response logging
    mock_response.request.url = "http://mockurl/fake"
    mock_session_instance.send.return_value = mock_response

    # Make the mock prepared request available for assertions if needed
    mock_session_instance._mock_prepared_request = mock_prepared_request

    # Make the mock response available for configuration in tests
    mock_session_instance._mock_response = mock_response

    return mock_session_instance # Return the instance for configuration/assertions

@pytest.fixture
def mock_requests_post(mocker):
    """Mocks requests.post."""
    mock_post = mocker.patch('requests.post', autospec=True)
    mock_response = MagicMock(spec=requests.Response)
    mock_response.request = MagicMock()
    mock_response.request.url = "http://mockurl/fake_post"
    mock_post.return_value = mock_response
    # Make response available for configuration
    mock_post._mock_response = mock_response
    return mock_post


# --- Tests for _check_response ---

def test_check_response_success():
    """Test _check_response with a successful response."""
    mock_response = MagicMock(spec=requests.Response)
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"errcode": 0, "errmsg": "ok", "data": "success"}
    mock_response.request = MagicMock()
    mock_response.request.url = "http://success.com"

    result = api._check_response(mock_response)
    assert result == {"errcode": 0, "errmsg": "ok", "data": "success"}
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_called_once()

def test_check_response_http_error():
    """Test _check_response with an HTTP error status."""
    mock_response = MagicMock(spec=requests.Response)
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
    mock_response.request = MagicMock()
    mock_response.request.url = "http://notfound.com"

    with pytest.raises(RuntimeError, match="Network error during API call"):
        api._check_response(mock_response)
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_not_called() # Should fail before json decode

def test_check_response_timeout_error():
    """Test _check_response with a Timeout error."""
    mock_response = MagicMock(spec=requests.Response)
    # Simulate timeout occurring during the request, caught by _check_response's caller
    # For testing _check_response itself, simulate raise_for_status raising it
    mock_response.raise_for_status.side_effect = requests.exceptions.Timeout("Timeout")
    mock_response.request = MagicMock()
    mock_response.request.url = "http://timeout.com"

    # The function catches Timeout specifically after raise_for_status
    with pytest.raises(RuntimeError, match="Request timed out"):
         api._check_response(mock_response)

def test_check_response_invalid_json():
    """Test _check_response with invalid JSON in the response."""
    mock_response = MagicMock(spec=requests.Response)
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "<html>error</html>", 0)
    mock_response.text = "<html>error</html>" # Provide text for error message
    mock_response.request = MagicMock()
    mock_response.request.url = "http://badjson.com"

    with pytest.raises(RuntimeError, match="Invalid response"):
        api._check_response(mock_response)
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_called_once()

def test_check_response_wechat_api_error():
    """Test _check_response with a WeChat API error code."""
    mock_response = MagicMock(spec=requests.Response)
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"errcode": 40001, "errmsg": "invalid credential"}
    mock_response.request = MagicMock()
    mock_response.request.url = "http://wechat-error.com"

    with pytest.raises(RuntimeError, match=r"WeChat API error .* 40001 - invalid credential"):
        api._check_response(mock_response)
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_called_once()


# --- Tests for upload_content_image ---

def test_upload_content_image_success(tmp_path, mock_requests_post, mocker):
    """Test successful content image upload."""
    # Setup: Create a dummy image file
    img_path = tmp_path / "test_content.jpg"
    img_path.write_bytes(b"dummy image data" * 10) # Small file < 1MB
    access_token = "CONTENT_TOKEN"
    base_url = "http://content.test.com"
    expected_url = f"{base_url}/cgi-bin/media/uploadimg"
    expected_wechat_url = "http://mmbiz.qpic.cn/sz_mmbiz_jpg/fake_url/0"

    # Configure mock response
    mock_requests_post._mock_response.raise_for_status.return_value = None
    mock_requests_post._mock_response.json.return_value = {"url": expected_wechat_url, "errcode": 0}

    # Mock Path methods used before request
    mocker.patch.object(Path, 'is_file', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=len(b"dummy image data")*10))
    # Note: Path methods on img_path itself will work because tmp_path creates real files

    # Call function
    result_url = api.upload_content_image(access_token, img_path, base_url=base_url)

    # Assertions
    assert result_url == expected_wechat_url
    mock_requests_post.assert_called_once()
    call_args, call_kwargs = mock_requests_post.call_args
    assert call_args[0] == expected_url
    assert call_kwargs['params'] == {"access_token": access_token}
    assert 'files' in call_kwargs
    # Add more assertions about file content if needed, though mocking open might be complex

def test_upload_content_image_file_not_found(tmp_path):
    """Test content image upload when file doesn't exist."""
    non_existent_path = tmp_path / "not_real.jpg"
    with pytest.raises(FileNotFoundError):
        api.upload_content_image("TOKEN", non_existent_path)

def test_upload_content_image_invalid_type(tmp_path):
    """Test content image upload with invalid file type."""
    img_path = tmp_path / "test_content.txt"
    img_path.write_bytes(b"dummy text data")
    with pytest.raises(ValueError, match="Invalid content image type"):
        api.upload_content_image("TOKEN", img_path)

def test_upload_content_image_too_large(tmp_path, mocker):
    """Test content image upload when file is too large."""
    img_path = tmp_path / "large_content.jpg"
    # Mock stat to return size > 1MB
    mocker.patch.object(Path, 'is_file', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=2 * 1024 * 1024))
    # mocker.patch.object(Path, 'suffix', '.jpg') # Not needed if using tmp_path actual file

    with pytest.raises(ValueError, match="exceeds 1MB limit"):
        api.upload_content_image("TOKEN", img_path)


# --- Tests for upload_thumb_media ---

def test_upload_thumb_media_success(tmp_path, mock_requests_post, mocker):
    """Test successful thumb media upload."""
    thumb_path = tmp_path / "test_thumb.jpg"
    thumb_path.write_bytes(b"dummy thumb data" * 5) # Small file < 64KB
    access_token = "THUMB_TOKEN"
    base_url = "http://thumb.test.com"
    expected_url = f"{base_url}/cgi-bin/material/add_material"
    expected_media_id = "THUMB_MEDIA_ID_XYZ"

    # Configure mock response
    mock_requests_post._mock_response.raise_for_status.return_value = None
    mock_requests_post._mock_response.json.return_value = {"media_id": expected_media_id, "errcode": 0}

    # Mock Path methods if needed (like content image test)
    mocker.patch.object(Path, 'is_file', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=len(b"dummy thumb data")*5))

    result_id = api.upload_thumb_media(access_token, thumb_path, base_url=base_url)

    assert result_id == expected_media_id
    mock_requests_post.assert_called_once()
    call_args, call_kwargs = mock_requests_post.call_args
    assert call_args[0] == expected_url
    assert call_kwargs['params'] == {"access_token": access_token, "type": "thumb"}
    assert 'files' in call_kwargs

def test_upload_thumb_media_invalid_type(tmp_path):
    """Test thumb media upload with invalid file type (e.g., png)."""
    thumb_path = tmp_path / "test_thumb.png"
    thumb_path.write_bytes(b"dummy png data")
    with pytest.raises(ValueError, match="Invalid thumbnail image type"):
        api.upload_thumb_media("TOKEN", thumb_path)

def test_upload_thumb_media_too_large(tmp_path, mocker):
    """Test thumb media upload when file is too large."""
    thumb_path = tmp_path / "large_thumb.jpg"
    mocker.patch.object(Path, 'is_file', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=70 * 1024)) # > 64KB
    # mocker.patch.object(Path, 'suffix', '.jpg') # Not needed if using tmp_path actual file

    with pytest.raises(ValueError, match="exceeds 64KB limit"):
        api.upload_thumb_media("TOKEN", thumb_path)


# --- Tests for add_draft ---

@pytest.fixture
def draft_payload_chinese():
    """Provides a sample draft payload with Chinese characters."""
    return {
        "articles": [
            {
                "title": "逻辑与世界", # Chinese Title
                "author": "测试作者",
                "digest": "重视逻辑，重获自由", # Chinese Digest
                "content": "<p>一些内容 Content.</p>",
                "content_source_url": "http://example.com/source",
                "thumb_media_id": "DUMMY_THUMB_ID_123",
                "need_open_comment": 0,
                "only_fans_can_comment": 0
            }
        ]
    }

def test_add_draft_success_manual_encoding(mock_requests_session, mocker, draft_payload_chinese):
    """Test successful draft creation using manual encoding."""
    access_token = "DRAFT_TOKEN_123"
    base_url = "http://draft.test.com"
    expected_media_id = "DRAFT_MEDIA_ID_456"
    expected_url = f"{base_url}/cgi-bin/draft/add"

    # Configure the mock response via the session mock
    mock_response = mock_requests_session._mock_response
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"media_id": expected_media_id, "errcode": 0}

    # Mock requests.Request to capture arguments
    mock_request_class = mocker.patch('requests.Request', autospec=True)

    # Call the function
    result_media_id = api.add_draft(access_token, draft_payload_chinese, base_url=base_url)

    # Assertions
    assert result_media_id == expected_media_id

    # Check that requests.Request was called correctly
    mock_request_class.assert_called_once()
    call_args, call_kwargs = mock_request_class.call_args

    assert call_args[0] == "POST"
    assert call_args[1] == expected_url
    assert call_kwargs.get('params') == {"access_token": access_token}
    assert call_kwargs.get('headers') == {'Content-Type': 'application/json; charset=utf-8'}
    assert 'json' not in call_kwargs # Ensure json= parameter was NOT used

    # Verify the data argument (most critical part)
    sent_data_bytes = call_kwargs.get('data')
    assert isinstance(sent_data_bytes, bytes)

    # Decode and check content
    decoded_body = sent_data_bytes.decode('utf-8')
    assert "逻辑与世界" in decoded_body # Check for actual Chinese chars
    assert "重视逻辑，重获自由" in decoded_body
    assert "\\u" not in decoded_body   # Ensure no escapes remain

    # Check structure after decoding
    sent_payload = json.loads(decoded_body)
    assert sent_payload == draft_payload_chinese

    # Check that session.send was called
    mock_requests_session.send.assert_called_once()
    # Check session closed
    mock_requests_session.close.assert_called_once()


def test_add_draft_missing_articles():
    """Test add_draft with payload missing 'articles' key."""
    payload = {"no_articles": "here"}
    # --- CORRECTED MATCH PATTERN ---
    with pytest.raises(ValueError, match="must contain a non-empty 'articles' list"):
        api.add_draft("TOKEN", payload)

def test_add_draft_articles_not_list():
    """Test add_draft with 'articles' not being a list."""
    payload = {"articles": "not a list"}
    # --- CORRECTED MATCH PATTERN ---
    with pytest.raises(ValueError, match="must contain a non-empty 'articles' list"):
        api.add_draft("TOKEN", payload)

def test_add_draft_articles_empty_list():
    """Test add_draft with 'articles' being an empty list."""
    payload = {"articles": []}
    # This test uses the correct message already
    with pytest.raises(ValueError, match="must contain a non-empty 'articles' list"):
        api.add_draft("TOKEN", payload)

def test_add_draft_json_dumps_error(mocker, draft_payload_chinese):
    """Test add_draft when json.dumps fails."""
    mocker.patch('json.dumps', side_effect=TypeError("Cannot serialize"))
    with pytest.raises(ValueError, match="Failed to prepare JSON payload"):
        api.add_draft("TOKEN", draft_payload_chinese)

def test_add_draft_api_error(mock_requests_session, draft_payload_chinese):
    """Test add_draft when the API call returns a WeChat error."""
    mock_response = mock_requests_session._mock_response
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"errcode": 45009, "errmsg": "api freq out of limit"}

    with pytest.raises(RuntimeError, match=r"WeChat API error .* 45009"):
        api.add_draft("TOKEN", draft_payload_chinese)

def test_add_draft_missing_media_id(mock_requests_session, draft_payload_chinese):
    """Test add_draft when the API response is successful but missing media_id."""
    mock_response = mock_requests_session._mock_response
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"} # Missing media_id

    with pytest.raises(RuntimeError, match="WeChat API did not return 'media_id'"):
        api.add_draft("TOKEN", draft_payload_chinese)