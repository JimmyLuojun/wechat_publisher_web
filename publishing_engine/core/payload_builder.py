"""
payload_builder.py

Constructs JSON payload for WeChat Draft API.

Dependencies:
    - BeautifulSoup (bs4)
    - logging

Inputs:
    - Metadata dictionary
    - HTML content string
    - Thumb media ID string

Output:
    - JSON payload dictionary for WeChat Draft API
"""
# publishing_engine/core/payload_builder.py
from typing import Dict, Any
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

MAX_DIGEST_LENGTH = 54

def generate_digest(metadata: Dict[str, Any], html_content: str) -> str:
    """Generates a digest for the WeChat draft article."""
    digest = metadata.get("digest", "").strip()

    if not digest:
        if html_content:
            soup = BeautifulSoup(html_content, 'lxml')
            text_content = soup.get_text(separator=' ', strip=True)
            digest = text_content[:MAX_DIGEST_LENGTH].strip()
            logger.debug(f"Digest generated from content: '{digest}'")
        else:
            digest = "No summary provided."
            logger.debug("No content available; using default digest.")

    if len(digest) > MAX_DIGEST_LENGTH:
        logger.warning(f"Digest length ({len(digest)}) exceeds {MAX_DIGEST_LENGTH} characters. Truncating.")
        digest = digest[:MAX_DIGEST_LENGTH].strip()

    return digest

def build_draft_payload(metadata: Dict[str, Any], html_content: str, thumb_media_id: str) -> Dict[str, Any]:
    """
    Builds the payload dictionary for submitting a draft article to WeChat.

    Args:
        metadata: Metadata dictionary containing article info.
                  Required key: 'title'. Optional keys: 'author', 'digest',
                  'content_source_url', 'need_open_comment', 'only_fans_can_comment'.
        html_content: Processed HTML content.
        thumb_media_id: Permanent media ID of the cover image.

    Returns:
        Dictionary structured for WeChat draft API.

    Raises:
        KeyError: If 'title' metadata is missing.
        ValueError: If thumb_media_id is empty.
    """
    logger.info("Building WeChat draft API payload...")

    title = metadata.get("title")
    if not title:
        raise KeyError("Required metadata 'title' is missing.")

    if not thumb_media_id:
        raise ValueError("thumb_media_id cannot be empty.")

    digest = generate_digest(metadata, html_content)

    article_data = {
        "title": title,
        "author": metadata.get("author", ""),
        "digest": digest,
        "content": html_content,
        "content_source_url": metadata.get("content_source_url", ""),
        "thumb_media_id": thumb_media_id,
        "need_open_comment": metadata.get("need_open_comment", 0),
        "only_fans_can_comment": metadata.get("only_fans_can_comment", 0),
    }

    logger.info("WeChat draft payload successfully built.")

    return article_data