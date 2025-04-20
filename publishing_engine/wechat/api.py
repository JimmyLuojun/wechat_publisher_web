# publishing_engine/wechat/api.py
"""
api.py

Handles requests to WeChat APIs (uploading media, articles).

Dependencies:
    - requests
    - exceptions.WechatAPIError # Assuming you might have this defined elsewhere
    - auth (to get access tokens) # Assuming you have an auth mechanism

Input: Payload data, media files
Output: API responses (media IDs, URLs)
"""
import requests
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import json # Make sure json is imported

# If using schemas: from .schemas import UploadImageResponse, AddMaterialResponse, AddDraftResponse, BaseResponse
# Otherwise, handle dictionaries directly.

logger = logging.getLogger(__name__)
# Can remove the logger name check if you added it earlier
# logger.error(f"***** Logger name configured in api.py: {__name__} *****")

def _check_response(response: requests.Response) -> Dict[str, Any]:
    """Helper to check response status and decode JSON, handling errors."""
    try:
        response.raise_for_status() # Check for HTTP errors
        data = response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Request timed out: {response.request.url}")
        raise RuntimeError(f"Request timed out: {response.request.url}")
    except requests.exceptions.RequestException as e:
        # Log the request URL from the original request if available
        request_url = response.request.url if response.request else "Unknown URL"
        logger.error(f"Network error during API call to {request_url}: {e}")
        raise RuntimeError(f"Network error during API call to {request_url}") from e
    except ValueError as e: # Includes JSON decoding errors
        request_url = response.request.url if response.request else "Unknown URL"
        logger.error(f"Failed to decode JSON response from {request_url}: {response.text}")
        raise RuntimeError(f"Invalid response from {request_url}: {response.text}") from e

    # Check for WeChat specific error codes
    if isinstance(data, dict) and data.get("errcode", 0) != 0:
         request_url = response.request.url if response.request else "Unknown URL"
         error_msg = f"WeChat API error ({request_url}): {data.get('errcode')} - {data.get('errmsg', 'Unknown error')}"
         logger.error(error_msg)
         # Consider raising a custom WechatAPIError if defined
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
            # Ensure filename in files tuple matches the actual filename
            files = {'media': (path.name, f, 'image/jpeg' if suffix in ['.jpg', '.jpeg'] else 'image/png')}
            logger.info(f"Uploading content image '{path.name}' to WeChat...")
            response = requests.post(upload_url, params=params, files=files, timeout=60) # Increased timeout for uploads
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
        logger.error(f"Failed to upload content image {image_path}: {e}", exc_info=True) # Add traceback
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
            # Ensure filename in files tuple matches the actual filename and specify content type
            files = {'media': (path.name, f, 'image/jpeg')}
            logger.info(f"Uploading thumbnail image '{path.name}' to WeChat...")
            response = requests.post(upload_url, params=params, files=files, timeout=45) # Adjusted timeout
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
        logger.error(f"Failed to upload thumbnail image {thumb_path}: {e}", exc_info=True) # Add traceback
        if isinstance(e, RuntimeError):
            raise e
        raise RuntimeError(f"Failed to upload thumbnail image {thumb_path}") from e


# --- UPDATED add_draft function ---
def add_draft(access_token: str, draft_payload: Dict[str, Any], base_url: str = "https://api.weixin.qq.com") -> str:
    """
    Adds a new draft article to the WeChat Official Account using manual encoding.

    Args:
        access_token: Valid WeChat access token.
        draft_payload: Dictionary representing the draft article structure ('articles' key).
        base_url: Base URL for WeChat API.

    Returns:
        The media_id of the created draft.

    Raises:
        ValueError: If draft_payload is missing the 'articles' key or JSON prep fails.
        RuntimeError: If the API request fails or returns an error.
    """
    if "articles" not in draft_payload or not isinstance(draft_payload["articles"], list) or not draft_payload["articles"]:
        raise ValueError("Draft payload must contain a non-empty 'articles' list.")

    draft_url = f"{base_url}/cgi-bin/draft/add"
    params = {"access_token": access_token}

    # --- Manual JSON Encoding ---
    try:
        # 1. Serialize to JSON string with ensure_ascii=False
        json_body_string = json.dumps(draft_payload, ensure_ascii=False)
        # 2. Encode the string to UTF-8 bytes
        request_body_bytes = json_body_string.encode('utf-8')
        logger.debug(f"Manually prepared JSON body (UTF-8 Bytes sample): {request_body_bytes[:500]}...") # Log sample bytes
        # For readable log, decode back (should show Chinese chars)
        logger.debug(f"Manually prepared JSON body (Decoded for log): {request_body_bytes.decode('utf-8')}")

    except Exception as json_err:
        logger.error(f"Error during manual JSON preparation: {json_err}", exc_info=True)
        raise ValueError("Failed to prepare JSON payload for WeChat draft.") from json_err

    # 3. Set explicit headers
    headers = {
        'Content-Type': 'application/json; charset=utf-8'
    }
    # --- End Manual JSON Encoding ---

    # Using session for potential connection reuse and prepare_request capability
    session = requests.Session()
    # 4. Use `data=` parameter with bytes, pass explicit headers
    #    Remove the `json=` parameter
    request = requests.Request(
        "POST",
        draft_url,
        params=params,
        data=request_body_bytes, # Use data= with bytes
        headers=headers          # Pass explicit headers
    )

    try:
        # Prepare the request to inspect headers and body before sending (optional now, but good for verification)
        prepared_request = session.prepare_request(request)

        # --- DETAILED LOGGING (Verify Manual Preparation) ---
        logger.debug("--- Preparing to send MANUALLY ENCODED request via Python requests ---")
        logger.debug(f"Method: {prepared_request.method}")
        logger.debug(f"URL: {prepared_request.url}")
        logger.debug("Headers Sent:")
        for key, value in prepared_request.headers.items():
            logger.debug(f"  {key}: {value}") # Verify Content-Type includes charset=utf-8

        request_body_log = prepared_request.body
        if isinstance(request_body_log, bytes):
            try:
                decoded_body = request_body_log.decode('utf-8')
                # CRITICAL CHECK: Should now show Chinese characters, not \uXXXX
                logger.debug(f"Body Sent (decoded as UTF-8): {decoded_body}")
            except UnicodeDecodeError:
                logger.warning("Could not decode request body as UTF-8 for logging.")
                logger.debug(f"Body Sent (bytes): {prepared_request.body}") # Log sample bytes if decode fails
        elif request_body_log is not None:
             logger.debug(f"Body Sent (type {type(request_body_log)}): {request_body_log}")
        else:
             logger.debug("Body Sent: None")

        logger.debug("--- End of prepared request details ---")
        # --- END DETAILED LOGGING ---

        logger.info("Submitting article as draft to WeChat (using manual encoding)...")

        # Now send the prepared request
        response = session.send(prepared_request, timeout=30) # Adjust timeout as needed

        # Check response and extract media_id
        data = _check_response(response) # Handles HTTP/network/WeChat errors

        if "media_id" not in data:
             raise RuntimeError(f"WeChat API did not return 'media_id' after adding draft: {data}")
        media_id = data["media_id"]

        logger.info(f"Successfully created draft. Media ID: {media_id}")
        return media_id

    except Exception as e:
        # Use exc_info=True to log the full traceback for better debugging
        logger.error(f"Failed to add draft: {e}", exc_info=True)
        if isinstance(e, (RuntimeError, ValueError)): # Re-raise specific handled errors
            raise e
        # Wrap other exceptions in a RuntimeError
        raise RuntimeError("Failed to add draft to WeChat") from e
    finally:
        # Ensure session is closed
        session.close()


# Example usage remains commented out
# if __name__ == '__main__':
#    ...