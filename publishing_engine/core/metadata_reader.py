# publishing_engine/core/metadata_reader.py
"""
metadata_reader.py

Extracts and validates metadata from markdown files using YAML frontmatter.

Responsibilities:
- Read markdown file.
- Extract YAML frontmatter.
- Validate required metadata fields.

Dependencies:
- PyYAML
- exceptions.MarkdownProcessingError
- utils.file_handler (for file operations)

Inputs:
- Path to markdown file.

Outputs:
- Dictionary of metadata fields.

Raises:
- MarkdownProcessingError if metadata is invalid or missing.
"""

import yaml
import logging
from typing import Dict, Any
from pathlib import Path
from ..utils.file_handler import read_file # Use relative import within package

logger = logging.getLogger(__name__)

# Define required fields for validation
REQUIRED_FIELDS = ["title", "cover_image_path"] # Title and cover are essential

def extract_metadata(filepath: str | Path) -> Dict[str, Any]:
    """
    Extract metadata from markdown YAML frontmatter and validate required fields.

    Args:
        filepath: Path to the markdown file.

    Returns:
        Dictionary of metadata fields.

    Raises:
        FileNotFoundError: If the markdown file does not exist.
        ValueError: If metadata is missing, invalid, or lacks required fields.
        RuntimeError: If there's an issue reading the file.
    """
    path = Path(filepath)
    logger.info(f"Attempting to extract metadata from: {path}")

    # read_file already handles FileNotFoundError and basic read errors (raising RuntimeError)
    content = read_file(path)

    metadata: Dict[str, Any] = {}
    try:
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                yaml_part = parts[1]
                # Handle empty YAML block gracefully
                loaded_yaml = yaml.safe_load(yaml_part.strip())
                if isinstance(loaded_yaml, dict):
                    metadata = loaded_yaml
                elif loaded_yaml is None:
                    metadata = {} # Treat empty YAML as empty metadata dict
                else:
                    # YAML loaded but it's not a dictionary (e.g., just a string)
                    raise ValueError("YAML frontmatter must be a dictionary (key-value pairs).")
            else:
                 # Found '---' but couldn't split into 3 parts (malformed)
                 raise ValueError("Invalid YAML frontmatter format (check delimiters '---').")
        else:
            # No YAML frontmatter found
            raise ValueError("Missing YAML frontmatter (must start with '---').")

    except yaml.YAMLError as e:
        error_msg = f"Invalid YAML format in metadata: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e
    except ValueError as e: # Catch specific ValueErrors from above checks
        logger.error(f"Metadata format error in {filepath}: {e}")
        raise e # Re-raise the specific ValueError

    # Validate required fields
    missing_fields = [field for field in REQUIRED_FIELDS if field not in metadata or not metadata[field]]
    if missing_fields:
        error_msg = f"Missing or empty required metadata fields: {missing_fields} in {filepath}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate cover image path exists relative to project root (basic check)
    # Assuming the path in YAML is relative to the project root where the script runs
    cover_path_str = metadata.get("cover_image_path")
    if cover_path_str:
         cover_path = Path(cover_path_str)
         if not cover_path.is_file():
              logger.error(f"Cover image specified in metadata not found at: {cover_path.resolve()}")
              raise FileNotFoundError(f"Cover image specified in metadata not found: {cover_path_str}")
         logger.info(f"Verified cover image path exists: {cover_path_str}")
    # Note: Further validation (size, type) happens during upload in wechat.api

    logger.info(f"Metadata extracted and validated successfully from {filepath}")
    return metadata