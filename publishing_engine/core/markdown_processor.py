# publishing_engine/core/markdown_processor.py
"""
markdown_processor.py

Parses markdown files and extracts YAML frontmatter metadata.

Dependencies:
    - yaml
    - exceptions.MarkdownProcessingError

Input: Path to markdown file
Output: Markdown content and metadata as dictionary
"""

import logging
from pathlib import Path
from typing import Optional
from ..utils.file_handler import read_file # Use relative import

logger = logging.getLogger(__name__)

def extract_markdown_content(filepath: str | Path) -> str:
    """
    Parses a markdown file and returns only the content after the YAML frontmatter.

    Args:
        filepath: Path to the markdown file.

    Returns:
        The markdown content string (empty if no content after frontmatter).

    Raises:
        FileNotFoundError: If the markdown file does not exist.
        RuntimeError: If there's an issue reading the file.
    """
    path = Path(filepath)
    logger.info(f"Extracting markdown content from: {path}")

    # read_file handles FileNotFoundError and basic read errors
    raw_content = read_file(path)
    markdown_content = raw_content # Default if no frontmatter

    if raw_content.startswith('---'):
        parts = raw_content.split('---', 2)
        # Ensure we have at least frontmatter and content parts
        if len(parts) >= 3:
            markdown_content = parts[2].strip()
            logger.info("YAML frontmatter detected and stripped.")
        else:
            # Found '---' but format is wrong, treat whole thing as content? Or error?
            # For simplicity, let's treat it as content if format is bad.
            logger.warning(f"File starts with '---' but format seems invalid in {path}. Treating entire file as content.")
            markdown_content = raw_content.strip() # Keep original content

    logger.info(f"Markdown content extracted successfully from {filepath}")
    return markdown_content # Return stripped content