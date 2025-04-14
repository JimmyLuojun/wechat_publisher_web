# publishing_engine/core/html_processor.py
import re
from pathlib import Path
from typing import Callable, List
from markdown import markdown
from bs4 import BeautifulSoup, Tag
import logging

logger = logging.getLogger(__name__)

# Assuming file_handler is correctly placed relative to this file
try:
    from ..utils.file_handler import read_file
except ImportError:
    logger.error("Failed relative import for ..utils.file_handler. Check structure.")
    def read_file(path): raise NotImplementedError("read_file could not be imported")

# Regex to identify image src attributes that are likely filenames to be looked up
# It matches strings that DO NOT start with http://, https://, or data:
# We assume these are filenames to be found in the content_images_dir.
LOCAL_IMAGE_SRC_PATTERN = re.compile(r"^(?!https?://|data:).+", re.IGNORECASE)

def _find_and_replace_local_images(
    soup: BeautifulSoup,
    content_images_dir: Path, # Directory where uploaded content images are stored
    image_uploader: Callable[[Path], str]
) -> None:
    """
    Finds <img> tags with potential local filenames in 'src', looks for them
    in the `content_images_dir`, uploads found images using the provided
    callback, and replaces the src attribute.

    Args:
        soup: BeautifulSoup object representing the parsed HTML content.
        content_images_dir: The absolute path to the directory where uploaded
                           content images are stored.
        image_uploader: A callback function that takes a local image Path obj
                        and returns the uploaded image URL string.

    Raises:
        FileNotFoundError: If an image specified in the Markdown src cannot be
                           found in the `content_images_dir`, or if the directory itself doesn't exist.
    """
    logger.info(f"Searching for local image filenames in HTML content, checking against directory: {content_images_dir}")
    images_found: List[Tag] = soup.find_all('img')
    images_processed_count = 0

    # Ensure the designated content images directory exists
    if not content_images_dir.is_dir():
        error_msg = f"Provided content_images_dir does not exist or is not a directory: {content_images_dir}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    for img_tag in images_found:
        src = img_tag.get('src')

        # Check if src looks like a filename we should process
        if src and LOCAL_IMAGE_SRC_PATTERN.match(src):
            # Assume src is a filename. Construct the expected path within the content images dir.
            # Extract filename part using Path().name for safety against accidental relative paths in src
            image_filename = Path(src).name
            local_image_path = (content_images_dir / image_filename).resolve()
            logger.debug(f"Potential local image filename: '{image_filename}'. Looking for it at: {local_image_path}")

            # Check if the image file exists in the designated directory
            if not local_image_path.is_file():
                error_msg = f"Content image file not found in designated directory: {local_image_path} (original src: '{src}')"
                logger.error(error_msg)
                # Raise error to stop processing if an image is missing
                raise FileNotFoundError(error_msg)

            try:
                # Call the provided uploader function to get the WeChat URL
                wechat_url = image_uploader(local_image_path)

                if wechat_url: # Ensure the uploader returned a valid URL
                    logger.debug(f"Replacing src '{src}' with uploaded URL '{wechat_url}'")
                    img_tag['src'] = wechat_url # Update the src attribute in the soup
                    images_processed_count += 1
                else:
                    logger.warning(f"Image uploader returned empty URL for {local_image_path}. Keeping original src: '{src}'")

            except Exception as e:
                # Catch potential errors during the image_uploader call
                logger.exception(f"Error calling image_uploader for {local_image_path}: {e}. Keeping original src: '{src}'")
                # Depending on requirements, could skip replacement or re-raise

    logger.info(f"Finished processing content images. Replaced sources for {images_processed_count} images found in {content_images_dir}.")


def _wrap_heading_content(soup: BeautifulSoup) -> None:
    """Wraps heading content with spans for CSS styling."""
    logger.debug("Wrapping heading content with prefix/content/suffix spans...")
    headings: List[Tag] = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    for header in headings:
        original_content_html = ''.join(str(content_part) for content_part in header.contents)
        header.clear()
        header.append(soup.new_tag('span', attrs={'class': 'prefix'}))
        content_span = soup.new_tag('span', attrs={'class': 'content'})
        # Use html.parser for parsing the fragment back into the span
        content_span.append(BeautifulSoup(original_content_html, 'html.parser'))
        header.append(content_span)
        header.append(soup.new_tag('span', attrs={'class': 'suffix'}))
    logger.debug(f"Finished wrapping content for {len(headings)} headings.")


def process_html_content(
    md_content: str,
    css_path: Path | str,
    content_images_dir: Path, # Changed from markdown_file_path
    image_uploader: Callable[[Path], str]
) -> str:
    """
    Converts Markdown string to a complete, styled HTML5 document string.
    Includes CSS, processes local image filenames found in content_images_dir,
    and wraps headings.

    Args:
        md_content: The raw Markdown body content string.
        css_path: Path object or string path to the CSS file.
        content_images_dir: Absolute path to the directory containing uploaded content images.
        image_uploader: Callback function to upload local images and get their URLs.

    Returns:
        A string containing a full HTML5 document.

    Raises:
        FileNotFoundError: If the CSS file or expected content images are not found.
        Exception: Can re-raise exceptions from markdown processing or image uploading.
    """
    logger.info("Starting full HTML processing pipeline...")
    css_path = Path(css_path)
    # markdown_dir = Path(markdown_file_path).parent # No longer needed for image lookup

    logger.debug("Converting Markdown to HTML fragment...")
    try:
        html_body_fragment = markdown(md_content, output_format='html5', extensions=[
            'extra', 'codehilite', 'toc', 'fenced_code', 'tables'
        ])
    except Exception as e:
        logger.exception("Error during Markdown conversion.")
        raise

    logger.debug("Parsing HTML fragment with BeautifulSoup (lxml)...")
    soup = BeautifulSoup(html_body_fragment, 'lxml')

    # Process content: Wrap headings, Find/replace images using content_images_dir
    _wrap_heading_content(soup)
    # Pass the directory where content images are stored
    _find_and_replace_local_images(soup, content_images_dir, image_uploader)

    logger.debug(f"Reading CSS content from: {css_path}")
    try:
        css_content = read_file(css_path).strip()
        if not css_content: logger.warning(f"CSS file is empty: {css_path}")
    except FileNotFoundError:
        logger.error(f"CSS file not found: {css_path}")
        raise
    except Exception as e:
        logger.exception(f"Failed to read CSS file: {css_path}")
        raise

    logger.debug("Constructing final HTML5 document string...")
    processed_body_content = soup.decode()
    final_html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Processed Content Preview</title>
    <style>
{css_content}
    </style>
</head>
<body>
    <div id="nice">
{processed_body_content}
    </div>
</body>
</html>"""

    logger.info("HTML processing completed successfully. Returning full HTML document string.")
    return final_html_document