# publishing_engine/wechat/media_manager.py
import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional

# Import the actual API upload functions
from .api import upload_thumb_media, upload_content_image

logger = logging.getLogger(__name__)

CACHE_FILENAME = "data/output/media_cache.json" # Default cache file path

class MediaManager:
    """Manages uploading media to WeChat, using a cache to avoid duplicates."""

    def __init__(self, cache_file_path: str | Path = CACHE_FILENAME):
        self.cache_file_path = Path(cache_file_path)
        self.cache: Dict[str, str] = self._load_cache() # {file_hash: media_id_or_url}

    def _load_cache(self) -> Dict[str, str]:
        """Loads the media cache from the JSON file."""
        try:
            if self.cache_file_path.is_file():
                logger.info(f"Loading media cache from: {self.cache_file_path}")
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.info("Media cache file not found, starting with empty cache.")
                return {}
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load media cache ({self.cache_file_path}): {e}. Starting with empty cache.")
            return {}

    def _save_cache(self) -> None:
        """Saves the current media cache to the JSON file."""
        try:
            # Ensure parent directory exists
            self.cache_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            logger.debug(f"Media cache saved to: {self.cache_file_path}")
        except OSError as e:
            logger.error(f"Failed to save media cache ({self.cache_file_path}): {e}")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculates the SHA-256 hash of a file's content."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(4096) # Read in chunks
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError as e:
            logger.error(f"Failed to read file for hashing ({file_path}): {e}")
            raise RuntimeError(f"Could not read file for hashing: {file_path}") from e

    def get_or_upload_thumb_media(
        self,
        access_token: str,
        thumb_path: str | Path,
        base_url: str
        ) -> str:
        """Gets existing thumb_media_id from cache or uploads the thumbnail."""
        path = Path(thumb_path)
        if not path.is_file():
             raise FileNotFoundError(f"Thumbnail image file not found: {path}")

        try:
            file_hash = self._calculate_file_hash(path)
            if file_hash in self.cache:
                cached_id = self.cache[file_hash]
                logger.info(f"Found cached thumb_media_id for {path.name}: {cached_id}")
                return cached_id

            # Not in cache, upload required
            logger.info(f"No cache found for {path.name}. Uploading thumbnail...")
            media_id = upload_thumb_media(access_token, path, base_url) # Call actual API

            # Update cache and save
            self.cache[file_hash] = media_id
            self._save_cache()
            return media_id

        except Exception as e:
            # Catch potential errors during hashing or upload
            logger.error(f"Failed to get or upload thumbnail {path.name}: {e}")
            # Re-raise to let the main error handler deal with it
            # Ensure specific error types are maintained if possible
            raise e


    def get_or_upload_content_image_url(
        self,
        access_token: str,
        image_path: str | Path,
        base_url: str
        ) -> str:
        """Gets existing WeChat image URL from cache or uploads the content image."""
        path = Path(image_path)
        if not path.is_file():
             raise FileNotFoundError(f"Content image file not found: {path}")

        try:
            file_hash = self._calculate_file_hash(path)
            if file_hash in self.cache:
                cached_url = self.cache[file_hash]
                logger.info(f"Found cached URL for {path.name}: {cached_url}")
                return cached_url

            # Not in cache, upload required
            logger.info(f"No cache found for {path.name}. Uploading content image...")
            img_url = upload_content_image(access_token, path, base_url) # Call actual API

            # Update cache and save
            self.cache[file_hash] = img_url
            self._save_cache()
            return img_url

        except Exception as e:
            logger.error(f"Failed to get or upload content image {path.name}: {e}")
            raise e