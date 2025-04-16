# /Users/junluo/Documents/wechat_publisher_web/publishing_engine/utils/hashing_checking.py

import hashlib
import logging
from pathlib import Path

# Use the logger configured in settings.py for the 'publishing_engine'
logger = logging.getLogger(__name__) # Will inherit from 'publishing_engine.utils'

def calculate_file_hash(file_path: Path | str, algorithm: str = 'sha256', buffer_size: int = 65536) -> str | None:
    """
    Calculates the hash of a file's content.

    Args:
        file_path: Path object or string path to the file.
        algorithm: Hash algorithm (e.g., 'sha256', 'md5').
        buffer_size: Size of chunks to read from the file.

    Returns:
        The hex digest of the file hash, or None if the file doesn't exist or an error occurs.
    """
    try:
        path = Path(file_path)
        if not path.is_file():
            logger.error(f"Cannot calculate hash. File not found: {path}")
            return None

        hasher = hashlib.new(algorithm)
        with open(path, 'rb') as f:
            while True:
                data = f.read(buffer_size)
                if not data:
                    break
                hasher.update(data)
        hex_digest = hasher.hexdigest()
        logger.debug(f"Calculated {algorithm} hash for {path}: {hex_digest}")
        return hex_digest
    except FileNotFoundError: # Explicitly catch FileNotFoundError again just in case path object behaves unexpectedly
         logger.error(f"Cannot calculate hash. File not found during hashing: {file_path}")
         return None
    except Exception as e:
        logger.exception(f"Error calculating {algorithm} hash for {file_path}: {e}")
        return None