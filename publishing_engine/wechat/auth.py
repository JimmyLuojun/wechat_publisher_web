# publishing_engine/wechat/auth.py
"""
Handles fetching and caching WeChat Official Account Access Tokens.
"""
import time
import logging
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# --- In-memory cache ---
# Simple approach for single-process scenarios (like development server or single worker)
# For multi-process/multi-server setups, use Redis, Memcached, or Database cache.
_token_cache = {
    "access_token": None,
    "expires_at": 0 # Unix timestamp when the token expires
}
# Safety buffer in seconds (request new token slightly before expiry)
TOKEN_EXPIRY_BUFFER = 300 # 5 minutes

def get_access_token(
    app_id: str,
    app_secret: str,
    base_url: str = 'https://api.weixin.qq.com'
    ) -> str:
    """
    Retrieves a valid WeChat access token, using a cache if possible.

    Args:
        app_id: WeChat AppID.
        app_secret: WeChat AppSecret.
        base_url: Base URL for WeChat API (defaults to production).

    Returns:
        A valid access token string.

    Raises:
        ValueError: If AppID or AppSecret are missing.
        RuntimeError: If the API call fails to retrieve a token.
    """
    if not app_id or not app_secret:
        logger.error("Missing AppID or AppSecret for fetching access token.")
        raise ValueError("AppID and AppSecret must be provided.")

    current_time = time.time()

    # Check cache first
    if _token_cache["access_token"] and current_time < (_token_cache["expires_at"] - TOKEN_EXPIRY_BUFFER):
        logger.info("Using cached access token.")
        return _token_cache["access_token"]

    # --- Token is missing or expired, fetch a new one ---
    logger.info("Fetching new access token from WeChat API...")
    token_url = f"{base_url.rstrip('/')}/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": app_id,
        "secret": app_secret,
    }

    try:
        response = requests.get(token_url, params=params, timeout=10) # Added timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        if "access_token" in data and "expires_in" in data:
            new_token = data["access_token"]
            expires_in = data["expires_in"] # Usually 7200 seconds
            expiry_time = current_time + expires_in

            # Update cache
            _token_cache["access_token"] = new_token
            _token_cache["expires_at"] = expiry_time

            logger.info(f"Successfully fetched new access token, expires in {expires_in} seconds.")
            return new_token
        else:
            # Handle WeChat API error structure (e.g., errcode, errmsg)
            errcode = data.get('errcode', -1)
            errmsg = data.get('errmsg', 'Unknown error')
            logger.error(f"WeChat API error while fetching token: {errcode} - {errmsg}")
            raise RuntimeError(f"Failed to retrieve access token from WeChat: {errmsg}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while fetching access token: {e}", exc_info=True)
        raise RuntimeError(f"Network error connecting to WeChat API: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error fetching access token: {e}", exc_info=True)
        # Re-raise original or wrap in RuntimeError
        raise RuntimeError(f"Unexpected error fetching access token: {e}") from e