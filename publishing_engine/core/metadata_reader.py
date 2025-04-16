# publishing_engine/core/metadata_reader.py
"""
Extracts metadata and body content from markdown files with YAML frontmatter.
Ensures UTF-8 encoding is used for reading.
Validates presence and basic types of required metadata fields.
"""

import yaml
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, List

logger = logging.getLogger(__name__)

# --- Constants ---
YAML_DELIMITER: str = '---'
# Define required fields and their expected types (example)
# Adjust types as needed (e.g., datetime.date for dates)
REQUIRED_FIELDS_WITH_TYPES: Dict[str, type] = {
    "title": str,
    "cover_image_path": str,
    # Add other required fields and their types here
    # "author": str,
    # "date": str, # Or datetime.date after parsing
    # "tags": list,
}

def extract_metadata_and_content(filepath: str | Path) -> Tuple[Dict[str, Any], str]:
    """
    Reads Markdown (UTF-8), extracts/validates YAML frontmatter, returns metadata & body.

    Args:
        filepath: Path to the markdown file.

    Returns:
        Tuple[Dict[str, Any], str]: (Validated metadata dict (potentially empty), Markdown body string).

    Raises:
        FileNotFoundError: If the markdown file does not exist.
        ValueError: For format errors, missing/invalid required metadata fields.
        yaml.YAMLError: For invalid YAML syntax.
        RuntimeError: For file reading issues.
    """
    path = Path(filepath)
    logger.info(f"Extracting metadata and content from: {path}")

    # --- Read the file directly using UTF-8 ---
    try:
        full_content = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.error(f"Markdown file not found: {path}")
        raise # Re-raise FileNotFoundError
    except Exception as e:
        logger.exception(f"Error reading file {path}")
        raise RuntimeError(f"Failed to read file {path}") from e

    metadata: Dict[str, Any] = {}
    body_content: str = full_content # Default: assume all content is body

    # --- YAML Frontmatter Parsing ---
    # Normalize line endings for consistent splitting
    normalized_content = full_content.replace('\r\n', '\n')
    start_delimiter = YAML_DELIMITER + '\n'
    end_delimiter = '\n' + YAML_DELIMITER + '\n'

    if normalized_content.startswith(start_delimiter):
        # Find the end delimiter position after the start delimiter
        end_delimiter_search_start = len(start_delimiter)
        end_delimiter_pos = normalized_content.find(end_delimiter, end_delimiter_search_start)

        if end_delimiter_pos != -1:
            # Extract YAML block
            yaml_part = normalized_content[end_delimiter_search_start : end_delimiter_pos].strip()
            # Extract body content (starts after the ending delimiter)
            body_content_start = end_delimiter_pos + len(end_delimiter)
            body_content = full_content[body_content_start:] # Use original content to preserve original newlines in body
            logger.debug(f"Found YAML delimiters. YAML part length: {len(yaml_part)}, Body content start index: {body_content_start}")

            if not yaml_part:
                logger.debug("Empty content between YAML frontmatter delimiters.")
                metadata = {}
            else:
                try:
                    loaded_yaml = yaml.safe_load(yaml_part)
                    if isinstance(loaded_yaml, dict):
                        metadata = loaded_yaml
                        logger.debug("Successfully parsed YAML frontmatter.")
                    elif loaded_yaml is None:
                        metadata = {}
                        logger.debug("YAML frontmatter parsed as None (empty).")
                    else:
                        logger.error(f"YAML frontmatter content in {path} is not a dictionary (key-value pairs). Type: {type(loaded_yaml)}")
                        raise ValueError("YAML frontmatter content must parse to a dictionary.")
                except yaml.YAMLError as e:
                    error_msg = f"Invalid YAML syntax in frontmatter of {path}: {e}"
                    logger.error(error_msg)
                    raise e # Re-raise YAML error

        else:
            # Found start delimiter but no proper end delimiter
            logger.warning(f"Found starting '---' but no valid closing '---' delimiter in {path}. Treating all as body content.")
            body_content = full_content # Revert to full content as body
            metadata = {}
    else:
        # No YAML frontmatter delimiter found at the start
        logger.debug(f"No YAML frontmatter found (doesn't start with '---'). Treating all content as body.")
        body_content = full_content
        metadata = {}

    # --- Metadata Validation ---
    # Check required fields only if metadata was potentially found
    if metadata or normalized_content.startswith(start_delimiter):
        errors: List[str] = []
        for field, expected_type in REQUIRED_FIELDS_WITH_TYPES.items():
            if field not in metadata or not metadata[field]:
                errors.append(f"Missing or empty required field: '{field}'")
            elif not isinstance(metadata[field], expected_type):
                errors.append(f"Field '{field}' has incorrect type: expected {expected_type.__name__}, got {type(metadata[field]).__name__}")
            # Add more specific type checks if needed (e.g., list elements, date format)

        if errors:
            error_msg = f"Metadata validation failed for {filepath}: {'; '.join(errors)}"
            logger.error(error_msg)
            raise ValueError(error_msg) # Raise error for missing/invalid required fields

        logger.info(f"Metadata extracted and validated successfully from {filepath}")
    else:
        # No frontmatter found, assume it's optional
        logger.info(f"No valid metadata found or parsed from {filepath}. Proceeding with body content.")
        metadata = {} # Ensure metadata is empty dict if no frontmatter

    # Return the potentially empty metadata dict and the stripped body content
    return metadata, body_content.strip()

