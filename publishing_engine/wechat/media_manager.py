# publishing_engine/core/metadata_reader.py

import yaml
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Assuming your file_handler is available, otherwise use standard open
try:
    from ...utils.file_handler import read_file # Adjust import path if needed
    # If using the imported read_file, ENSURE IT uses encoding='utf-8'
    logger.info("Using imported read_file from utils.file_handler.")
except (ImportError, ModuleNotFoundError):
    logger.warning("Could not import custom read_file, using standard open with UTF-8.")
    # Fallback definition explicitly uses UTF-8
    def read_file(path: Path | str) -> str:
        """Fallback function to read a file using UTF-8."""
        try:
            file_path = Path(path)
            return file_path.read_text(encoding='utf-8') # Explicit UTF-8
        except FileNotFoundError:
            logger.error(f"Fallback read_file: File not found at {path}")
            raise # Re-raise FileNotFoundError
        except Exception as e:
            logger.error(f"Fallback read_file: Error reading {path}: {e}")
            # Re-raise as a runtime error for consistent handling upstream
            raise RuntimeError(f"Fallback read_file failed for {path}") from e

def extract_metadata_and_content(filepath: str | Path) -> Tuple[Dict[str, Any], str]:
    """
    Reads Markdown (UTF-8), extracts/validates YAML frontmatter, returns metadata & body.
    Ensures metadata is always a dictionary (empty if none found/invalid non-critical).

    Args:
        filepath: Path to the markdown file.

    Returns:
        Tuple[Dict[str, Any], str]: (Validated metadata dict (potentially empty), Markdown body string).

    Raises:
        FileNotFoundError: If the markdown file does not exist.
        ValueError: For format errors or missing required metadata fields.
        yaml.YAMLError: For invalid YAML syntax.
        RuntimeError: For file reading issues.
    """
    path = Path(filepath)
    logger.info(f"Extracting metadata and content from: {path}")

    # Ensure file is read with UTF-8 using the (potentially fallback) read_file
    full_content = read_file(path)

    metadata: Dict[str, Any] = {}
    body_content: str = full_content # Default: assume all content is body
    YAML_DELIMITER = '---'

    # Check for standard '---' delimiters
    if full_content.startswith(YAML_DELIMITER + '\n') or full_content.startswith(YAML_DELIMITER + '\r\n'):
        # Find the end delimiter '---' followed by a newline
        # +1 for the newline after the first delimiter
        end_delimiter_search_start = len(YAML_DELIMITER) + 1
        end_delimiter_pos = full_content.find('\n' + YAML_DELIMITER + '\n', end_delimiter_search_start)
        if end_delimiter_pos == -1: # Try with Windows newline
             end_delimiter_pos = full_content.find('\r\n' + YAML_DELIMITER + '\r\n', end_delimiter_search_start)

        if end_delimiter_pos != -1:
            # Extract YAML block
            yaml_part = full_content[len(YAML_DELIMITER)+1 : end_delimiter_pos].strip()
            # Extract body content (start after the ending delimiter line)
            # Calculate start based on delimiter length and preceding/following newlines
            body_content_start = end_delimiter_pos + len(YAML_DELIMITER) + 2 # Assuming \n---\n
            if full_content[end_delimiter_pos:body_content_start] == '\r\n' + YAML_DELIMITER + '\r\n':
                body_content_start += 2 # Adjust for \r\n on both sides if needed

            body_content = full_content[body_content_start:]
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
                        # Treat non-dict YAML as an error or warning
                        logger.error(f"YAML frontmatter content in {path} is not a dictionary (key-value pairs). Type: {type(loaded_yaml)}")
                        # Option 1: Raise Error
                        raise ValueError("YAML frontmatter content must parse to a dictionary.")
                        # Option 2: Treat as empty metadata (less strict)
                        # metadata = {}
                except yaml.YAMLError as e:
                    error_msg = f"Invalid YAML syntax in frontmatter of {path}: {e}"
                    logger.error(error_msg)
                    raise e # Re-raise YAML error

        else:
            logger.warning(f"Found starting '---' but no valid closing '---' delimiter in {path}. Treating all as body content.")
            body_content = full_content
            metadata = {}
    else:
        logger.debug(f"No YAML frontmatter found (doesn't start with '---'). Treating all content as body.")
        body_content = full_content
        metadata = {}

    # --- Metadata Validation ---
    # Define required fields within the function or import from constants
    REQUIRED_FIELDS = ["title", "cover_image_path"] # Example required fields

    missing_fields = [field for field in REQUIRED_FIELDS if field not in metadata or not metadata[field]]
    if missing_fields:
        # If metadata was expected (i.e., delimiters were present) but fields are missing
        if full_content.startswith(YAML_DELIMITER):
             error_msg = f"Missing or empty required metadata fields: {missing_fields} in {filepath}"
             logger.error(error_msg)
             raise ValueError(error_msg)
        else:
             # No frontmatter found, and it seems optional, so proceed with empty metadata
             logger.info(f"No frontmatter found in {filepath}, required fields check skipped.")
             metadata = {} # Ensure it's an empty dict

    if metadata: # Log only if metadata was successfully parsed and validated
        logger.info(f"Metadata extracted and validated successfully from {filepath}")

    return metadata, body_content.strip()

