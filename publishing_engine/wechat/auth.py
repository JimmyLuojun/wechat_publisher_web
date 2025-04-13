"""
auth.py

Handles authentication and access token retrieval for WeChat API.

Dependencies:
    - requests
    - config_loader

Input: API credentials from config.ini
Output: WeChat API access token
"""
# publishing_engine/wechat/auth.py
import requests
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Simple in-memory cache for the token
_token_cache: Dict[str, Any] = {
    "access_token": None,
    "expires_at": 0
}

def get_access_token(app_id: str, app_secret: str, base_url: str = "https://api.weixin.qq.com") -> str:
    """
    Fetches a WeChat access token, using a simple cache.

    Args:
        app_id: WeChat App ID.
        app_secret: WeChat App Secret.
        base_url: Base URL for WeChat API.

    Returns:
        A valid access token string.

    Raises:
        ValueError: If app_id or app_secret are missing.
        RuntimeError: If the API request fails or returns an error.
    """
    if not app_id or not app_secret:
        raise ValueError("WeChat App ID and App Secret must be provided.")

    current_time = time.time()
    # Check cache, leave a buffer (e.g., 5 minutes) before expiry
    if _token_cache["access_token"] and _token_cache["expires_at"] > current_time + 300:
        logger.info("Using cached access token.")
        return _token_cache["access_token"]

    logger.info("Fetching new access token from WeChat API...")
    token_url = f"{base_url}/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": app_id,
        "secret": app_secret,
    }

    try:
        response = requests.get(token_url, params=params, timeout=10) # 10 second timeout
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
    except requests.exceptions.Timeout:
        logger.error("Request timed out while fetching access token.")
        raise RuntimeError("Request timed out while fetching access token.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching access token: {e}")
        raise RuntimeError(f"Network error fetching access token: {e}") from e
    except ValueError as e: # Includes JSON decoding errors
        logger.error(f"Failed to decode JSON response from token API: {e}")
        raise RuntimeError(f"Invalid response from token API: {response.text}") from e


    if "errcode" in data and data["errcode"] != 0:
        error_msg = f"WeChat API error fetching token: {data.get('errcode')} - {data.get('errmsg', 'Unknown error')}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    if "access_token" not in data or "expires_in" not in data:
        logger.error(f"Unexpected response format from token API: {data}")
        raise RuntimeError(f"Unexpected response format from token API: {data}")

    access_token = data["access_token"]
    # expires_in is in seconds (typically 7200)
    expires_in = data["expires_in"]

    # Update cache
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = current_time + expires_in
    logger.info(f"Successfully fetched new access token, expires in {expires_in} seconds.")

    return access_token