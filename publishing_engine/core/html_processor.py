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

LOCAL_IMAGE_SRC_PATTERN = re.compile(r"^(?!https?://|data:).+", re.IGNORECASE)

# --- _read_file (Keep as is) ---
def _read_file(file_path: Path | str) -> str:
    """Reads file content, ensuring UTF-8 encoding."""
    try:
        return Path(file_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except Exception as e:
        logger.exception(f"Error reading file {file_path}: {e}")
        raise

# --- _find_and_replace_local_images (Keep as is - it's working based on logs) ---
def _find_and_replace_local_images(
    soup: BeautifulSoup,
    markdown_dir: Path,
    image_uploader: Callable[[Path], Optional[str]]
) -> None:
    """
    Find local image sources, attempt to resolve paths (relative to MD first,
    then central content_images dir), call uploader, and replace src.
    """
    logger.info("Searching for local images in HTML to replace with WeChat URLs...")
    images_processed = 0
    images_failed = 0
    content_images_subfolder = 'uploads/content_images'
    central_image_dir = Path(settings.MEDIA_ROOT) / content_images_subfolder

    for img in soup.find_all('img'):
        src = img.get('src')
        img['alt'] = img.get('alt', '') # Ensure alt attribute

        if not src or not LOCAL_IMAGE_SRC_PATTERN.match(src):
            continue

        logger.debug(f"Found potential local image source: '{src}'")
        resolved_image_path: Optional[Path] = None
        image_filename = Path(src).name

        # 1. Try relative to markdown dir
        try:
            path_relative_to_md = (markdown_dir / src).resolve(strict=True)
            if path_relative_to_md.is_file():
                resolved_image_path = path_relative_to_md
                logger.debug(f"Resolved image '{src}' relative to markdown dir: {resolved_image_path}")
        except FileNotFoundError:
            logger.debug(f"Image '{src}' not found relative to markdown dir {markdown_dir}.")
        except Exception as e:
            logger.warning(f"Error resolving image '{src}' relative to markdown dir: {e}")

        # 2. Try central content_images dir by filename stem/suffix
        if not resolved_image_path:
            logger.debug(f"Attempting to find image filename '{image_filename}' in central dir: {central_image_dir}")
            found_in_central = False
            if central_image_dir.is_dir():
                src_path = Path(src)
                src_stem = src_path.stem
                src_suffix = src_path.suffix
                try:
                    # Use glob to find files potentially saved with UUIDs
                    possible_matches = list(central_image_dir.glob(f"{src_stem}*{src_suffix}"))
                    if possible_matches:
                        # Assuming the first match is correct (might need refinement if duplicates occur)
                        match_path = possible_matches[0].resolve(strict=True)
                        if match_path.is_file():
                             resolved_image_path = match_path
                             logger.debug(f"Resolved image '{src}' (matched stem/suffix) in central content dir: {resolved_image_path}")
                             found_in_central = True
                except FileNotFoundError:
                     logger.debug(f"Glob match for '{image_filename}' resolved, but file check failed.")
                except Exception as e:
                     logger.warning(f"Error searching for '{image_filename}' in central content dir: {e}")

            if not found_in_central:
                 logger.debug(f"Image filename '{image_filename}' not found in central content dir {central_image_dir}.")

        # Upload and Replace
        if resolved_image_path:
            try:
                logger.debug(f"Calling image uploader for: {resolved_image_path}")
                wechat_url = image_uploader(resolved_image_path)
                if wechat_url:
                    img['src'] = wechat_url
                    images_processed += 1
                    logger.debug(f"Replaced '{src}' with WeChat URL: '{wechat_url}'")
                else:
                    logger.warning(f"Callback failed for image path: {resolved_image_path} (original src: '{src}'). Keeping original src.")
                    images_failed += 1
            except Exception as e:
                logger.exception(f"Error during callback/replacement for image path {resolved_image_path} (original src='{src}'): {e}")
                images_failed += 1
        else:
            logger.error(f"Local image file could not be located for src='{src}'. Checked relative to MD and in central dir. Keeping original src.")
            images_failed += 1

    logger.info(f"Image processing complete. Replaced: {images_processed}, Failed/Skipped: {images_failed}.")


# --- _wrap_heading_content (Keep as is) ---
def _wrap_heading_content(soup: BeautifulSoup) -> None:
    """Wrap headings in span elements for consistent styling."""
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # Check if already wrapped to prevent double wrapping
        if header.find('span', class_='content', recursive=False):
            continue
        original_attrs = header.attrs # Preserve original attributes like class
        content_html = ''.join(str(c) for c in header.contents)
        header.clear()
        header.attrs = original_attrs # Restore attributes
        header.append(soup.new_tag('span', **{'class': 'prefix'}))
        content_span = soup.new_tag('span', **{'class': 'content'})
        # Parse the content HTML to handle nested tags correctly
        parsed_content = BeautifulSoup(content_html or "", 'html.parser')
        # Append children of parsed content to the span to avoid extra body/html tags
        for child in list(parsed_content.contents):
            content_span.append(child.extract())
        header.append(content_span)
        header.append(soup.new_tag('span', **{'class': 'suffix'}))


# --- _remove_heading_ids (Keep as is) ---
def _remove_heading_ids(soup: BeautifulSoup) -> None:
    """Remove 'id' attributes from heading tags."""
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        if header.has_attr('id'):
            del header['id']


# --- _extract_body_content (Keep as is) ---
def _extract_body_content(soup: BeautifulSoup) -> str:
    """Extracts the inner HTML of the body tag, or the whole soup if no body."""
    body = soup.find('body')
    if body:
        return body.decode_contents() # Get inner HTML of body
    else:
        # If markdown didn't create a full document, decode the whole soup's content
        return "".join(str(content) for content in soup.contents)


# --- MODIFIED process_html_content ---
def process_html_content(
    md_content: str,
    css_path: Optional[Path | str],
    markdown_file_path: Path | str,
    image_uploader: Callable[[Path], Optional[str]]
) -> str:
    """
    Convert markdown to styled HTML suitable for WeChat, mimicking the original script's output structure.
    """
    logger.info("Starting HTML processing with image uploader callback...")
    markdown_dir = Path(markdown_file_path).parent
    logger.info(f"Markdown directory set to: {markdown_dir}")

    # Initialize Markdown processor
    md_processor = Markdown(output_format='html5', extensions=[
        'extra',          # Includes features like tables, abbr, def_list, footnotes
        'codehilite',     # Syntax highlighting (requires Pygments)
        'toc',            # Table of contents (though often not used directly in WeChat)
        'fenced_code',    # GitHub-style code blocks
        'tables',         # Explicitly ensure tables are processed
    ])

    # Convert Markdown to HTML fragment
    html_body = md_processor.convert(md_content)

    # Parse the HTML with BeautifulSoup
    soup = BeautifulSoup(html_body, 'lxml') # Use lxml for robustness

    # --- Apply HTML transformations ---
    _remove_heading_ids(soup) # Remove potential conflicting IDs
    _wrap_heading_content(soup) # Apply heading structure for styling
    _find_and_replace_local_images(soup, markdown_dir, image_uploader) # Process images

    # Extract the processed body content
    body_fragment = _extract_body_content(soup)

    # --- Prepare CSS ---
    style_tag = "" # Default to no style tag
    if css_path:
        try:
            css_content = _read_file(css_path).strip()
            # Use type="text/css" for clarity, although browsers usually infer it
            style_tag = f'<style type="text/css">\n{css_content}\n</style>'
        except FileNotFoundError:
            logger.error(f"CSS file not found at {css_path}. Proceeding without CSS.")
        except Exception as e:
            logger.exception(f"Error reading CSS file {css_path}. Proceeding without CSS.")

    # --- Construct Final HTML (Matching original structure) ---
    # Place the <style> tag *before* the main content wrapper <div id="nice">
    final_html = f"""{style_tag}
<div id="nice">{body_fragment.strip()}</div>"""
    # --- End Structure Modification ---

    logger.info("HTML processing completed successfully.")
    return final_html