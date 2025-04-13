"""
api.py

Handles requests to WeChat APIs (uploading media, articles).

Dependencies:
    - requests
    - exceptions.WechatAPIError
    - auth (to get access tokens)

Input: Payload data, media files
Output: API responses (media IDs, URLs)
"""
# publishing_engine/wechat/api.py
import requests
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# If using schemas: from .schemas import UploadImageResponse, AddMaterialResponse, AddDraftResponse, BaseResponse
# Otherwise, handle dictionaries directly.

logger = logging.getLogger(__name__)

def _check_response(response: requests.Response) -> Dict[str, Any]:
    """Helper to check response status and decode JSON, handling errors."""
    try:
        response.raise_for_status() # Check for HTTP errors
        data = response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Request timed out: {response.request.url}")
        raise RuntimeError(f"Request timed out: {response.request.url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during API call to {response.request.url}: {e}")
        raise RuntimeError(f"Network error during API call to {response.request.url}") from e
    except ValueError as e: # Includes JSON decoding errors
        logger.error(f"Failed to decode JSON response from {response.request.url}: {response.text}")
        raise RuntimeError(f"Invalid response from {response.request.url}: {response.text}") from e

    # Check for WeChat specific error codes
    if isinstance(data, dict) and data.get("errcode", 0) != 0:
         error_msg = f"WeChat API error ({response.request.url}): {data.get('errcode')} - {data.get('errmsg', 'Unknown error')}"
         logger.error(error_msg)
         raise RuntimeError(error_msg) # Raise an error for WeChat API errors

    return data


def upload_content_image(access_token: str, image_path: str | Path, base_url: str = "https://api.weixin.qq.com") -> str:
    """
    Uploads an image for use within article content (media/uploadimg).

    Args:
        access_token: Valid WeChat access token.
        image_path: Path to the image file (JPG/PNG, < 1MB).
        base_url: Base URL for WeChat API.

    Returns:
        The URL of the uploaded image on WeChat servers.

    Raises:
        FileNotFoundError: If image_path does not exist.
        ValueError: If image type or size is invalid.
        RuntimeError: If the API request fails or returns an error.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Content image not found: {image_path}")

    # Basic validation (can be enhanced with Pillow or python-magic)
    file_size = path.stat().st_size
    suffix = path.suffix.lower()
    if suffix not in ['.jpg', '.jpeg', '.png']:
        raise ValueError(f"Invalid content image type ({suffix}). Must be JPG or PNG: {image_path}")
    if file_size > 1 * 1024 * 1024: # 1 MB limit
         raise ValueError(f"Content image size ({file_size / 1024:.1f} KB) exceeds 1MB limit: {image_path}")

    upload_url = f"{base_url}/cgi-bin/media/uploadimg"
    params = {"access_token": access_token}

    try:
        with open(path, 'rb') as f:
            files = {'media': (path.name, f)}
            logger.info(f"Uploading content image '{path.name}' to WeChat...")
            response = requests.post(upload_url, params=params, files=files, timeout=30) # Longer timeout for uploads
        data = _check_response(response) # Handles HTTP/network/WeChat errors

        if "url" not in data:
             raise RuntimeError(f"WeChat API did not return 'url' after image upload: {data}")
        img_url = data["url"]

        logger.info(f"Successfully uploaded content image {path.name}. URL: {img_url}")
        return img_url

    except (FileNotFoundError, ValueError) as e: # Re-raise validation errors
        logger.error(f"Validation failed for content image {image_path}: {e}")
        raise e
    except Exception as e: # Catch other potential errors like file read errors
        logger.error(f"Failed to upload content image {image_path}: {e}")
        if isinstance(e, RuntimeError): # Don't wrap RuntimeErrors from _check_response
            raise e
        raise RuntimeError(f"Failed to upload content image {image_path}") from e


def upload_thumb_media(access_token: str, thumb_path: str | Path, base_url: str = "https://api.weixin.qq.com") -> str:
    """
    Uploads a thumbnail image as permanent material (material/add_material, type=thumb).

    Args:
        access_token: Valid WeChat access token.
        thumb_path: Path to the thumbnail image file (JPG, < 64KB).
        base_url: Base URL for WeChat API.

    Returns:
        The permanent media_id ('thumb_media_id') for the thumbnail.

    Raises:
        FileNotFoundError: If thumb_path does not exist.
        ValueError: If image type or size is invalid.
        RuntimeError: If the API request fails or returns an error.
    """
    path = Path(thumb_path)
    if not path.is_file():
        raise FileNotFoundError(f"Thumbnail image not found: {thumb_path}")

    # Basic validation
    file_size = path.stat().st_size
    suffix = path.suffix.lower()
    # WeChat doc says JPG, let's be strict but allow .jpeg too
    if suffix not in ['.jpg', '.jpeg']:
         raise ValueError(f"Invalid thumbnail image type ({suffix}). Must be JPG: {thumb_path}")
    if file_size > 64 * 1024: # 64 KB limit
         raise ValueError(f"Thumbnail image size ({file_size / 1024:.1f} KB) exceeds 64KB limit: {thumb_path}")

    upload_url = f"{base_url}/cgi-bin/material/add_material"
    params = {"access_token": access_token, "type": "thumb"}

    try:
        with open(path, 'rb') as f:
            files = {'media': (path.name, f)}
            logger.info(f"Uploading thumbnail image '{path.name}' to WeChat...")
            response = requests.post(upload_url, params=params, files=files, timeout=30)
        data = _check_response(response)

        if "media_id" not in data:
            raise RuntimeError(f"WeChat API did not return 'media_id' after thumb upload: {data}")
        media_id = data["media_id"]

        logger.info(f"Successfully uploaded thumbnail {path.name}. Media ID: {media_id}")
        return media_id

    except (FileNotFoundError, ValueError) as e: # Re-raise validation errors
        logger.error(f"Validation failed for thumbnail image {thumb_path}: {e}")
        raise e
    except Exception as e: # Catch other potential errors
        logger.error(f"Failed to upload thumbnail image {thumb_path}: {e}")
        if isinstance(e, RuntimeError):
            raise e
        raise RuntimeError(f"Failed to upload thumbnail image {thumb_path}") from e


def add_draft(access_token: str, draft_payload: Dict[str, Any], base_url: str = "https://api.weixin.qq.com") -> str:
    """
    Adds a new draft article to the WeChat Official Account.

    Args:
        access_token: Valid WeChat access token.
        draft_payload: Dictionary representing the draft article structure ('articles' key).
        base_url: Base URL for WeChat API.

    Returns:
        The media_id of the created draft.

    Raises:
        ValueError: If draft_payload is missing the 'articles' key.
        RuntimeError: If the API request fails or returns an error.
    """
    if "articles" not in draft_payload or not isinstance(draft_payload["articles"], list):
        raise ValueError("Draft payload must contain an 'articles' list.")

    draft_url = f"{base_url}/cgi-bin/draft/add"
    params = {"access_token": access_token}

    try:
        logger.info("Submitting article as draft to WeChat...")
        response = requests.post(draft_url, params=params, json=draft_payload, timeout=30)
        data = _check_response(response)

        if "media_id" not in data:
             raise RuntimeError(f"WeChat API did not return 'media_id' after adding draft: {data}")
        media_id = data["media_id"]

        logger.info(f"Successfully created draft. Media ID: {media_id}")
        return media_id

    except Exception as e:
        logger.error(f"Failed to add draft: {e}")
        if isinstance(e, (RuntimeError, ValueError)): # Don't wrap known errors
            raise e
        raise RuntimeError("Failed to add draft to WeChat") from e