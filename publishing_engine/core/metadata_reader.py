# publishing_engine/core/metadata_reader.py
"""
metadata_reader.py

Extracts metadata and body content from markdown files with YAML frontmatter.

Responsibilities:
- Read markdown file content.
- Extract YAML frontmatter and parse it.
- Separate the markdown body content.
- Validate required metadata fields.

Dependencies:
- PyYAML
- utils.file_handler (for file operations)

Inputs:
- Path to markdown file.

Outputs:
- Tuple containing:
    - Dictionary of validated metadata fields (or {} if none/invalid).
    - String of the markdown body content.

Raises:
- FileNotFoundError if the markdown file does not exist.
- ValueError if metadata is invalid (e.g., not a dict) or lacks required fields,
  or if frontmatter delimiters are malformed.
- yaml.YAMLError if the YAML syntax is invalid.
- RuntimeError from underlying file read issues.
"""

import yaml
import logging
from typing import Dict, Any, Tuple
from pathlib import Path

# Use relative import within the package structure
try:
    from ..utils.file_handler import read_file
except ImportError:
    # Fallback or error handling if running outside expected package structure
    logger = logging.getLogger(__name__)
    logger.error("Failed relative import for ..utils.file_handler. Check structure.")
    # Define a dummy or raise error to prevent continuation
    def read_file(path): raise ImportError("Cannot import file_handler")

logger = logging.getLogger(__name__)

YAML_DELIMITER = '---'
REQUIRED_FIELDS = ["title", "cover_image_path"] # Essential fields

def extract_metadata_and_content(filepath: str | Path) -> Tuple[Dict[str, Any], str]:
    """
    Reads Markdown, extracts/validates YAML frontmatter, returns metadata & body.

    Args:
        filepath: Path to the markdown file.

    Returns:
        Tuple[Dict[str, Any], str]: (Validated metadata dict, Markdown body string).
        Returns ({}, full_content) if no valid frontmatter is found.

    Raises:
        FileNotFoundError: If the markdown file does not exist.
        ValueError: For format errors or missing required metadata fields.
        yaml.YAMLError: For invalid YAML syntax.
        RuntimeError: For file reading issues.
    """
    path = Path(filepath)
    logger.info(f"Extracting metadata and content from: {path}")

    # Read the entire file content once using the utility function
    full_content = read_file(path)

    metadata: Dict[str, Any] = {}
    body_content: str = full_content # Default: assume all content is body

    if full_content.startswith(YAML_DELIMITER + '\n') or full_content.startswith(YAML_DELIMITER + '\r\n'):
        # Find the end delimiter '---' followed by a newline
        end_delimiter_search_start = len(YAML_DELIMITER) + 1 # Start searching after the first '---' and its newline
        end_delimiter_pos = full_content.find('\n' + YAML_DELIMITER + '\n', end_delimiter_search_start)
        if end_delimiter_pos == -1:
             end_delimiter_pos = full_content.find('\n' + YAML_DELIMITER + '\r\n', end_delimiter_search_start)

        if end_delimiter_pos != -1:
            # Extract YAML block (between first and second delimiters)
            # +1 to skip the newline after the first delimiter
            yaml_part = full_content[len(YAML_DELIMITER)+1 : end_delimiter_pos].strip()
            # Extract body content (after second delimiter and its newline)
            # +2 accounts for the newline before and after the second delimiter
            body_content_start = end_delimiter_pos + len(YAML_DELIMITER) + 2
            body_content = full_content[body_content_start:]
            logger.debug(f"Found YAML delimiters. YAML part length: {len(yaml_part)}, Body content start index: {body_content_start}")

            if not yaml_part:
                logger.debug("Empty content between YAML frontmatter delimiters.")
                metadata = {} # Treat empty block as empty metadata
            else:
                try:
                    loaded_yaml = yaml.safe_load(yaml_part)
                    if isinstance(loaded_yaml, dict):
                        metadata = loaded_yaml
                        logger.debug("Successfully parsed YAML frontmatter.")
                    elif loaded_yaml is None:
                        metadata = {} # Treat explicitly empty YAML as empty dict
                        logger.debug("YAML frontmatter parsed as None (empty).")
                    else:
                        # YAML loaded but it's not a dictionary
                        raise ValueError("YAML frontmatter content must parse to a dictionary (key-value pairs).")
                except yaml.YAMLError as e:
                    error_msg = f"Invalid YAML syntax in frontmatter of {path}: {e}"
                    logger.error(error_msg)
                    # Let YAML errors propagate up
                    raise e

        else:
            # Found start delimiter but no proper end delimiter
            # Treat as error for strictness, or potentially treat all as body
            logger.warning(f"Found starting '---' but no valid closing '---' delimiter in {path}. Treating all as body content.")
            body_content = full_content # Revert to full content as body
            metadata = {}

    else:
        # No YAML frontmatter delimiter found at the start
        logger.debug(f"No YAML frontmatter found (doesn't start with '---'). Treating all content as body.")
        body_content = full_content
        metadata = {}

    # --- Metadata Validation ---
    # Perform validation only if metadata was potentially found and parsed
    if metadata:
        missing_fields = [field for field in REQUIRED_FIELDS if field not in metadata or not metadata[field]]
        if missing_fields:
            error_msg = f"Missing or empty required metadata fields: {missing_fields} in {filepath}"
            logger.error(error_msg)
            raise ValueError(error_msg) # Raise error for missing required fields

        # Optionally add other validation rules here (e.g., checking data types)

        logger.info(f"Metadata extracted and validated successfully from {filepath}")
    else:
        # If no metadata was parsed, check if any was REQUIRED.
        # This logic implies frontmatter itself isn't strictly required,
        # but IF present, it must contain REQUIRED_FIELDS. Adjust if needed.
        logger.info(f"No valid metadata found or parsed from {filepath}. Proceeding with body content.")
        # If frontmatter itself IS required, raise ValueError here if metadata is empty.

    return metadata, body_content