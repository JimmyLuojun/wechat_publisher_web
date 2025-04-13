# publishing_engine/core/html_processor.py
import re
from pathlib import Path
from typing import Callable
from markdown import markdown
from bs4 import BeautifulSoup
from loguru import logger

from ..utils.file_handler import read_file

LOCAL_IMAGE_SRC_PATTERN = re.compile(r"^(?!https?://|data:).+", re.IGNORECASE)

def _find_and_replace_local_images(
    soup: BeautifulSoup,
    markdown_dir: Path,
    image_uploader: Callable[[Path], str]
) -> None:
    """Replace local image sources with uploaded URLs in HTML content."""
    logger.info("Searching for local images in HTML...")
    images_processed = 0

    for img in soup.find_all('img'):
        src = img.get('src')
        if src and LOCAL_IMAGE_SRC_PATTERN.match(src):
            logger.debug(f"Processing local image source: {src}")
            local_image_path = Path(src) if Path(src).is_absolute() else (markdown_dir / src).resolve()

            if not local_image_path.is_file():
                logger.error(f"Local image not found: {local_image_path}")
                raise FileNotFoundError(f"Image not found: {local_image_path}")

            wechat_url = image_uploader(local_image_path)
            img['src'] = wechat_url
            images_processed += 1

            logger.debug(f"Replaced '{src}' with '{wechat_url}'")

    logger.info(f"Processed {images_processed} local images.")

def _wrap_heading_content(soup: BeautifulSoup) -> None:
    """Wrap headings in span elements for consistent styling."""
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        content_html = ''.join(str(e) for e in header.contents)
        header.clear()

        header.append(soup.new_tag('span', **{'class': 'prefix'}))
        content_span = soup.new_tag('span', **{'class': 'content'})
        content_span.append(BeautifulSoup(content_html, 'html.parser'))
        header.append(content_span)
        header.append(soup.new_tag('span', **{'class': 'suffix'}))

def process_html_content(
    md_content: str,
    css_path: Path | str,
    markdown_file_path: Path | str,
    image_uploader: Callable[[Path], str]
) -> str:
    """Convert markdown to styled HTML suitable for WeChat."""
    logger.info("Starting HTML processing...")

    markdown_dir = Path(markdown_file_path).parent

    html_body = markdown(md_content, output_format='html5', extensions=[
        'extra', 'codehilite', 'toc', 'fenced_code', 'tables'
    ])

    soup = BeautifulSoup(html_body, 'lxml')

    _wrap_heading_content(soup)
    _find_and_replace_local_images(soup, markdown_dir, image_uploader)

    css_content = read_file(css_path).strip()
    final_html = f"""
    <style>{css_content}</style>
    <div id="nice">{soup.decode()}</div>
    """

    logger.info("HTML processing completed.")
    return final_html
