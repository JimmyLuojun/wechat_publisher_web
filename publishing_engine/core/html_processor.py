# publishing_engine/core/html_processor.py
import re
from pathlib import Path
from typing import Callable, Optional
from markdown import Markdown
from bs4 import BeautifulSoup, NavigableString
import logging

# Import settings to know where content images are saved by services.py
from django.conf import settings

logger = logging.getLogger(__name__)

# Matches src attributes that don't start with http://, https://, or data:
LOCAL_IMAGE_SRC_PATTERN = re.compile(r"^(?!https?://|data:).+", re.IGNORECASE)

# --- Helper: _read_file ---
def _read_file(file_path: Path | str) -> str:
    """Reads file content, ensuring UTF-8 encoding."""
    try:
        # Ensure file_path is Path object for consistency
        path_obj = Path(file_path)
        return path_obj.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except Exception as e:
        logger.exception(f"Error reading file {file_path}: {e}")
        raise

# --- Helper: _find_and_replace_local_images ---
# (No changes needed in this helper based on test results)
def _find_and_replace_local_images(
    soup: BeautifulSoup,
    markdown_dir: Path,
    image_uploader: Callable[[Path], Optional[str]] # Expects func(path) -> Optional[url]
) -> None:
    """
    Find local image sources, attempt to resolve paths (relative to MD first,
    then central content_images dir), call uploader, and replace src.
    """
    logger.info("Searching for local images in HTML to replace with WeChat URLs...")
    images_processed = 0
    images_failed = 0
    # Define where side-uploaded content images are stored by services.py
    content_images_subfolder = 'uploads/content_images'
    central_image_dir = Path(settings.MEDIA_ROOT) / content_images_subfolder

    for img in soup.find_all('img'):
        src = img.get('src')
        # Ensure alt attribute exists, even if empty, for accessibility/validation
        img['alt'] = img.get('alt', '')

        if not src or not LOCAL_IMAGE_SRC_PATTERN.match(src):
            # Skip if src is missing, empty, or already an absolute URL/data URI
            continue

        logger.debug(f"Found potential local image source: '{src}'")
        resolved_image_path: Optional[Path] = None
        image_filename = Path(src).name # Extract filename for central search

        # --- Path Resolution Strategy ---
        # 1. Try relative to markdown dir (most common case for Markdown files)
        try:
            # Use resolve() to normalize paths (e.g., handle ../) and check existence
            path_relative_to_md = (markdown_dir / src).resolve(strict=True)
            if path_relative_to_md.is_file():
                resolved_image_path = path_relative_to_md
                logger.debug(f"Resolved image '{src}' relative to markdown dir: {resolved_image_path}")
        except FileNotFoundError:
            # This is expected if the path is not relative or doesn't exist there
            logger.debug(f"Image '{src}' not found relative to markdown dir {markdown_dir}.")
        except Exception as e:
            # Log other potential errors during resolution (e.g., permission issues)
            logger.warning(f"Error resolving image '{src}' relative to markdown dir: {e}")

        # 2. If not found relative, try finding by filename in the central content_images dir
        if not resolved_image_path:
            logger.debug(f"Attempting to find image filename '{image_filename}' in central dir: {central_image_dir}")
            found_in_central = False
            if central_image_dir.is_dir():
                src_path = Path(src)
                src_stem = src_path.stem
                src_suffix = src_path.suffix.lower() # Use lower case for comparison
                try:
                    # Use glob to find files matching the pattern stem*suffix
                    possible_matches = list(central_image_dir.glob(f"{src_stem}*{src_suffix}"))
                    if possible_matches:
                        # Use the first match found. Might need smarter logic if multiple exist.
                        match_path = possible_matches[0].resolve(strict=True)
                        if match_path.is_file():
                             resolved_image_path = match_path
                             logger.debug(f"Resolved image '{src}' (matched stem/suffix) in central content dir: {resolved_image_path}")
                             found_in_central = True
                        else:
                             logger.warning(f"Glob matched '{possible_matches[0]}' but file check failed after resolve.")
                except FileNotFoundError:
                     logger.debug(f"Glob match for '{image_filename}' resolved, but strict file check failed.")
                except Exception as e:
                     logger.warning(f"Error searching for '{image_filename}' in central content dir: {e}")

            if not found_in_central:
                 logger.debug(f"Image filename '{image_filename}' not found in central content dir {central_image_dir}.")
        # --- End Path Resolution ---


        # --- Upload and Replace Src ---
        if resolved_image_path:
            try:
                logger.debug(f"Calling image uploader for resolved path: {resolved_image_path}")
                # The image_uploader is the adapted callback from services.py
                wechat_url = image_uploader(resolved_image_path)
                if wechat_url:
                    img['src'] = wechat_url
                    images_processed += 1
                    logger.debug(f"Replaced original src='{src}' with WeChat URL: '{wechat_url}'")
                else:
                    # Callback failed (e.g., size issue, upload error, API error)
                    logger.warning(f"Image upload/processing failed for: {resolved_image_path} (original src: '{src}'). Keeping original src.")
                    images_failed += 1
            except Exception as e:
                # Catch unexpected errors during the callback execution itself
                logger.exception(f"Unexpected error during image_uploader callback for {resolved_image_path} (original src='{src}'): {e}")
                images_failed += 1
        else:
            # Image specified in Markdown could not be found locally
            logger.error(f"Local image file could not be located for src='{src}'. Checked relative to MD and in central dir. Keeping original src.")
            images_failed += 1
        # --- End Upload and Replace ---

    logger.info(f"Image processing complete. Replaced: {images_processed}, Failed/Skipped: {images_failed}.")


# --- Helper: _wrap_heading_content ---
# (No changes needed in this helper based on test results)
def _wrap_heading_content(soup: BeautifulSoup) -> None:
    """Wrap headings' text content in span elements for consistent styling, preserving attributes."""
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # Check if already wrapped to prevent double wrapping if run multiple times
        if header.find('span', class_='content', recursive=False):
            continue

        original_attrs = header.attrs.copy() # Preserve original attributes like id, class
        content_html = ''.join(str(c) for c in header.contents) # Get inner HTML as string

        header.clear() # Remove original content
        header.attrs = original_attrs # Restore attributes to the header tag

        # Add structural spans (empty for now, content added next)
        header.append(soup.new_tag('span', **{'class': 'prefix'}))
        content_span = soup.new_tag('span', **{'class': 'content'})
        header.append(content_span)
        header.append(soup.new_tag('span', **{'class': 'suffix'}))

        # Parse the original inner HTML to handle nested tags correctly
        # Use 'html.parser' as it's built-in and sufficient here
        # If content_html is empty, BeautifulSoup creates empty body/html tags, but .contents will be empty or just whitespace
        parsed_content = BeautifulSoup(content_html or "", 'html.parser') # Use empty string if no content

        # Append children of parsed content to the central 'content' span
        # This avoids wrapping the entire parsed structure in extra <html><body> tags
        # Use list() to iterate over a copy as we modify the contents
        for child in list(parsed_content.contents):
             # Skip potential empty NavigableString if content_html was empty or whitespace only
            if isinstance(child, NavigableString) and not child.strip():
                continue
            content_span.append(child.extract()) # extract() removes from parsed_content and returns


# --- Helper: _remove_heading_ids ---
# (No changes needed in this helper based on test results)
def _remove_heading_ids(soup: BeautifulSoup) -> None:
    """Remove 'id' attributes from heading tags to avoid conflicts in WeChat."""
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        if header.has_attr('id'):
            del header['id']


# --- Helper: _extract_body_content ---
# (No changes needed in this helper based on test results)
def _extract_body_content(soup: BeautifulSoup) -> str:
    """Extracts the inner HTML of the body tag, or the whole soup if no body."""
    body = soup.find('body')
    if body:
        # Preserves the inner content of the body tag generated by Markdown
        return body.decode_contents()
    else:
        # If markdown didn't create a full document, decode the whole soup's content
        # This handles cases where md_content is just a paragraph or simple text
        return "".join(str(content) for content in soup.contents)


# --- Main Function: process_html_content ---
def process_html_content(
    md_content: str,
    css_path: Optional[Path | str],
    markdown_file_path: Path | str,
    image_uploader: Callable[[Path], Optional[str]] # Expects func(path) -> Optional[url]
) -> str:
    """
    Convert markdown to styled HTML suitable for WeChat.

    Args:
        md_content: The raw Markdown content (without frontmatter).
        css_path: Path to the CSS file to be embedded.
        markdown_file_path: Path to the original markdown file (used to resolve relative image paths).
        image_uploader: Callback function to handle image uploading.
                        Takes the local Path of an image, returns the WeChat URL (str) or None on failure.

    Returns:
        A string containing the final HTML fragment (including <style> tag and wrapper div).
    """
    logger.info("Starting HTML processing...")
    markdown_dir = Path(markdown_file_path).parent
    logger.info(f"Markdown directory set to: {markdown_dir}")

    # Initialize Markdown processor with desired extensions
    md_processor = Markdown(output_format='html5', extensions=[
        'extra', 'codehilite', 'toc', 'fenced_code', 'tables', 'sane_lists',
    ])

    # Convert Markdown to HTML fragment
    html_body = md_processor.convert(md_content)

    # Parse the generated HTML with BeautifulSoup for manipulation
    try:
        soup = BeautifulSoup(html_body, 'lxml')
    except ImportError:
        logger.warning("lxml not found, falling back to html.parser for HTML processing.")
        soup = BeautifulSoup(html_body, 'html.parser')

    # --- Apply HTML transformations ---
    _remove_heading_ids(soup)
    _wrap_heading_content(soup)
    _find_and_replace_local_images(soup, markdown_dir, image_uploader)

    # --- Extract the processed body content ---
    body_fragment = _extract_body_content(soup)

    # --- Prepare CSS ---
    style_tag = "" # Default to no style tag
    if css_path:
        css_file_path = Path(css_path)
        if css_file_path.is_file():
            try:
                css_content = _read_file(css_file_path).strip()
                style_tag = f'<style type="text/css">\n{css_content}\n</style>\n' # Add newline
            except Exception as e:
                logger.exception(f"Error reading CSS file {css_file_path}. Proceeding without CSS.")
        else:
            logger.error(f"CSS file specified but not found at {css_file_path}. Proceeding without CSS.")

    # --- Construct Final HTML structure ---
    # *** Correction: Added class="nice" to the wrapper div ***
    final_html = f"""{style_tag}<div id="nice" class="nice">{body_fragment.strip()}</div>"""

    logger.info("HTML processing completed successfully.")
    return final_html
