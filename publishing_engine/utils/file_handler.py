# publishing_engine/utils/file_handler.py
"""
file_handler.py

Utility functions for file operations: reading and writing.

Dependencies: built-in modules only
Input: file paths
Output: file content or writes content to disk
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def read_file(filepath: str | Path, encoding: str = 'utf-8') -> str:
    """Reads and returns the contents of a file."""
    path = Path(filepath)
    if not path.is_file():
        logger.error(f"Attempted to read a non-existent file: {filepath}")
        raise FileNotFoundError(f"File not found: {filepath}")
    try:
        content = path.read_text(encoding=encoding)
        logger.info(f"File read successfully: {filepath}")
        return content
    except Exception as e:
        logger.error(f"Failed to read file {filepath}: {e}")
        raise RuntimeError(f"Failed to read file {filepath}") from e


def write_file(filepath: str | Path, content: str, encoding: str = 'utf-8') -> None:
    """Writes content to a file, creating parent directories if needed."""
    path = Path(filepath)
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)
        logger.info(f"Content written to file: {filepath}")
    except Exception as e:
        logger.error(f"Failed to write to file {filepath}: {e}")
        raise RuntimeError(f"Failed to write to file {filepath}") from e
