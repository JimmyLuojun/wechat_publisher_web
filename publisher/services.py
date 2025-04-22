# /Users/junluo/Documents/wechat_publisher_web/publisher/services.py
import os
import uuid
import json
import logging
from pathlib import Path
from typing import Dict, Callable, Any, List, Optional, Tuple # Added Tuple

from django.conf import settings
from django.utils import timezone
import yaml
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist

# --- Add Cache Import ---
from django.core.cache import cache

from .models import PublishingJob

# --- Import publishing engine components ---
try:
    from publishing_engine.core import metadata_reader, html_processor, payload_builder
    from publishing_engine.wechat import auth
    from publishing_engine.wechat import api as wechat_api
    from publishing_engine.utils.hashing_checking import calculate_file_hash
    # --- Import Image Processing Utility ---
    from publishing_engine.utils.image_processing import (
        ensure_image_size,
        COVER_IMAGE_SIZE_LIMIT_KB,
        CONTENT_IMAGE_SIZE_LIMIT_KB
    )
    # from publishing_engine.wechat.exceptions import WeChatAPIError # Example if used

    logger = logging.getLogger(__name__) # Correctly gets 'publisher' logger
    logger.info("Successfully imported modules from publishing_engine and utils.")
except ImportError as e:
    # Specific check for Pillow if image processing is the source
    if 'PIL' in str(e) or 'Pillow' in str(e):
         logger.exception("Failed to import Pillow. Image processing features require 'Pillow'. Please install it.", exc_info=True)
         raise ImportError("Image processing library 'Pillow' not found. Please install it (`pip install Pillow`).") from e
    logger.exception("Failed to import critical 'publishing_engine' or 'utils' modules.", exc_info=True)
    raise ImportError("Failed to import critical 'publishing_engine' or 'utils' modules.") from e
except ModuleNotFoundError as e:
     # Catch cases where the utils module itself is missing etc.
     logger.exception(f"Failed to import a required module, check dependencies (e.g., Pillow?): {e}", exc_info=True)
     raise ModuleNotFoundError(f"Failed to import a required module: {e}") from e


# --- Helper Functions ---

# _save_uploaded_file_locally (Unchanged)
def _save_uploaded_file_locally(file_obj: UploadedFile, subfolder: str = "") -> Path:
    """
    Saves an uploaded file locally with a unique name and returns its absolute Path object.
    """
    try:
        file_obj.seek(0)
        file_content = file_obj.read()
        file_obj.seek(0)
        file_ext = Path(file_obj.name).suffix.lower()
        original_filename_stem = Path(file_obj.name).stem
        safe_stem = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in original_filename_stem)[:50]
        unique_filename = f"{safe_stem}_{uuid.uuid4().hex[:8]}{file_ext}"
        local_save_dir = Path(settings.MEDIA_ROOT) / subfolder
        local_save_dir.mkdir(parents=True, exist_ok=True)
        local_save_path_abs = local_save_dir / unique_filename
        with open(local_save_path_abs, 'wb') as destination:
            destination.write(file_content)
        logger.info(f"File '{file_obj.name}' saved locally to absolute path: {local_save_path_abs}")
        return local_save_path_abs
    except IOError as e:
        logger.exception(f"IOError saving uploaded file '{file_obj.name}' locally.")
        raise RuntimeError(f"Failed to save '{file_obj.name}' locally due to file system error.") from e
    except Exception as e:
        logger.exception(f"Unexpected error saving uploaded file '{file_obj.name}' locally.")
        raise RuntimeError(f"Unexpected failure saving '{file_obj.name}' locally.") from e


# _generate_preview_file (Unchanged)
def _generate_preview_file(full_html_content: str, task_id: uuid.UUID) -> str:
    """
    Saves the FULL HTML content to a preview file locally and returns its relative path as a string.
    """
    try:
        preview_filename = f"{task_id}.html"
        preview_subdir = Path('previews')
        preview_path_rel = preview_subdir / preview_filename
        preview_file_abs = Path(settings.MEDIA_ROOT) / preview_path_rel
        preview_file_abs.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Attempting to save FULL HTML preview file locally to: {preview_file_abs}")
        with open(preview_file_abs, 'w', encoding='utf-8') as f:
            f.write(full_html_content)
        relative_path_str = preview_path_rel.as_posix()
        logger.info(f"Preview file saved successfully to relative path: {relative_path_str}")
        return relative_path_str
    except IOError as e:
        logger.exception(f"IOError writing preview file for task {task_id}")
        raise RuntimeError(f"Failed to write preview file {task_id}.html due to file system error.") from e
    except Exception as e:
        logger.exception(f"Unexpected error writing preview file for task {task_id}")
        raise RuntimeError(f"Unexpected failure writing preview file {task_id}.html: {e}") from e


# --- Main Service Functions ---

# Constants for update_fields (Unchanged)
JOB_STATUS_UPDATE_FIELDS = ['status', 'updated_at']
JOB_ERROR_UPDATE_FIELDS = ['status', 'error_message', 'updated_at']
JOB_PATHS_UPDATE_FIELDS = ['original_markdown_path', 'original_cover_image_path', 'updated_at']
JOB_THUMB_UPDATE_FIELDS = ['thumb_media_id', 'updated_at']
JOB_METADATA_UPDATE_FIELDS = ['metadata', 'updated_at']
JOB_PREVIEW_UPDATE_FIELDS = ['preview_html_path', 'status', 'updated_at']
JOB_PUBLISH_SUCCESS_FIELDS = ['status', 'wechat_media_id', 'error_message', 'published_at', 'updated_at']
JOB_ERROR_MSG_UPDATE_FIELDS = ['error_message', 'updated_at'] # Added for warning updates


# start_processing_job (Modified preview HTML generation & default title)
def start_processing_job(
    markdown_file: UploadedFile,
    cover_image: UploadedFile,
    content_images: List[UploadedFile]
) -> Dict[str, Any]:
    """
    Handles Request 1: Saves files, processes cover image, uploads/caches cover thumb,
    processes Markdown (incl. processing referenced content images), generates preview.
    Includes default title generation if missing from metadata.
    """
    job: Optional[PublishingJob] = None
    task_id = uuid.uuid4()
    local_cover_path_abs: Optional[Path] = None
    processed_cover_path_abs: Optional[Path] = None
    local_md_path_abs: Optional[Path] = None
    access_token: Optional[str] = None
    image_processing_warnings: List[str] = []

    try:
        logger.info(f"[Job {task_id}] Starting new processing job (Callback workflow)")
        job = PublishingJob.objects.create(task_id=task_id, status=PublishingJob.Status.PENDING)
        job.status = PublishingJob.Status.PROCESSING
        job.save(update_fields=JOB_STATUS_UPDATE_FIELDS)
        logger.debug(f"[Job {task_id}] Status set to PROCESSING.")

        # --- Step 1-3: Save Files Locally ---
        local_md_path_abs = _save_uploaded_file_locally(markdown_file, subfolder='uploads/markdown')
        job.original_markdown_path = local_md_path_abs.relative_to(settings.MEDIA_ROOT).as_posix()

        local_cover_path_abs = _save_uploaded_file_locally(cover_image, subfolder='uploads/cover_images')
        job.original_cover_image_path = local_cover_path_abs.relative_to(settings.MEDIA_ROOT).as_posix()
        logger.info(f"[Job {task_id}] Saved Markdown: '{local_md_path_abs.name}'. Saved Cover: '{local_cover_path_abs.name}'.")
        job.save(update_fields=JOB_PATHS_UPDATE_FIELDS)

        # --- Step 3.5: Process Cover Image ---
        try:
            logger.info(f"[Job {task_id}] Ensuring cover image '{local_cover_path_abs.name}' meets size limit ({COVER_IMAGE_SIZE_LIMIT_KB} KB)...")
            processed_cover_path_abs = ensure_image_size(local_cover_path_abs, COVER_IMAGE_SIZE_LIMIT_KB)
            if processed_cover_path_abs != local_cover_path_abs:
                logger.info(f"[Job {task_id}] Cover image optimized. Using '{processed_cover_path_abs.name}' for WeChat.")
            else:
                 logger.debug(f"[Job {task_id}] Cover image size OK. Using original '{local_cover_path_abs.name}'.")
                 processed_cover_path_abs = local_cover_path_abs
        except (FileNotFoundError, ValueError, ImportError) as img_err:
            logger.error(f"[Job {task_id}] CRITICAL: Failed to process cover image '{local_cover_path_abs.name}': {img_err}", exc_info=True)
            raise RuntimeError(f"Failed to process cover image '{cover_image.name}': {img_err}") from img_err
        except Exception as e:
            logger.error(f"[Job {task_id}] CRITICAL: Unexpected error processing cover image '{local_cover_path_abs.name}': {e}", exc_info=True)
            raise RuntimeError(f"Unexpected failure processing cover image '{cover_image.name}': {e}") from e

        # Save side-uploaded content images
        saved_content_image_paths: List[Path] = []
        for image_file in content_images:
            path = _save_uploaded_file_locally(image_file, subfolder='uploads/content_images')
            saved_content_image_paths.append(path)
        logger.info(f"[Job {task_id}] Saved {len(saved_content_image_paths)} side-uploaded content images locally.")

        # --- Step 4: WeChat Setup & Thumbnail Upload ---
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret: raise ValueError("WeChat credentials missing.")
        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        if not access_token: raise RuntimeError("Failed to get WeChat access token.")
        logger.debug(f"[Job {task_id}] Retrieved WeChat access token.")

        logger.info(f"[Job {task_id}] Preparing PERMANENT WeChat thumbnail from processed path: '{processed_cover_path_abs}'")
        if not processed_cover_path_abs or not processed_cover_path_abs.is_file():
             raise FileNotFoundError(f"Processed cover image not found at expected path: {processed_cover_path_abs}")

        # --- Caching Logic Start (Using hash of the *processed* file) ---
        permanent_thumb_media_id: Optional[str] = None
        cover_image_hash = calculate_file_hash(processed_cover_path_abs, algorithm='sha256')
        if cover_image_hash:
            cache_key = f"wechat_thumb_sha256_{cover_image_hash}"
            logger.debug(f"[Job {task_id}] Checking cache for thumbnail key: {cache_key} (from processed file)")
            cached_media_id = cache.get(cache_key)
            if cached_media_id:
                permanent_thumb_media_id = cached_media_id
                logger.info(f"[Job {task_id}] Cache HIT for thumbnail. Using cached Media ID: {permanent_thumb_media_id}")
            else:
                logger.info(f"[Job {task_id}] Cache MISS for thumbnail. Uploading processed image '{processed_cover_path_abs.name}' to WeChat...")
                try:
                    permanent_thumb_media_id = wechat_api.upload_thumb_media(
                        access_token=access_token, thumb_path=processed_cover_path_abs, base_url=base_url
                    )
                    if not permanent_thumb_media_id: raise RuntimeError("WeChat API returned no media ID for thumbnail.")
                    logger.info(f"[Job {task_id}] Uploaded thumbnail. New Media ID: {permanent_thumb_media_id}")
                    cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                    cache.set(cache_key, permanent_thumb_media_id, timeout=cache_timeout)
                    logger.info(f"[Job {task_id}] Stored new thumbnail Media ID in cache (Timeout: {cache_timeout}).")
                except Exception as upload_error:
                    logger.exception(f"[Job {task_id}] Failed to upload thumbnail '{processed_cover_path_abs.name}': {upload_error}")
                    raise RuntimeError(f"Failed to upload thumbnail to WeChat: {upload_error}") from upload_error
        else:
            logger.error(f"[Job {task_id}] Failed to calculate hash for processed cover image {processed_cover_path_abs}, cannot use cache.")
            logger.warning(f"[Job {task_id}] Proceeding with direct thumbnail upload of processed file due to hash failure.")
            try:
                permanent_thumb_media_id = wechat_api.upload_thumb_media(
                    access_token=access_token, thumb_path=processed_cover_path_abs, base_url=base_url
                )
                if not permanent_thumb_media_id: raise RuntimeError("WeChat API returned no media ID for thumbnail upload (after hash failure).")
                logger.info(f"[Job {task_id}] Uploaded thumbnail (after hash failure). Media ID: {permanent_thumb_media_id}")
            except Exception as upload_error:
                logger.exception(f"[Job {task_id}] Failed to upload thumbnail '{processed_cover_path_abs.name}' (after hash failure): {upload_error}")
                raise RuntimeError(f"Failed to upload thumbnail to WeChat (after hash failure): {upload_error}") from upload_error
        # --- Caching Logic End ---

        if not permanent_thumb_media_id: raise RuntimeError("Failed to obtain permanent thumbnail media ID.")
        job.thumb_media_id = permanent_thumb_media_id
        job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
        logger.info(f"[Job {task_id}] PERMANENT WeChat thumbnail processed. Media ID: {permanent_thumb_media_id}")

        # --- Step 5: Metadata Extraction ---
        logger.info(f"[Job {task_id}] Extracting metadata and body content from {local_md_path_abs}")
        if not local_md_path_abs:
             raise FileNotFoundError("Markdown file path unexpectedly missing before metadata extraction.")
        try:
            metadata_dict, markdown_body_content = metadata_reader.extract_metadata_and_content(local_md_path_abs)
            metadata_dict = metadata_dict or {} # Ensure it's a dict even if null/empty
        except (ValueError, yaml.YAMLError) as meta_error:
             logger.error(f"[Job {task_id}] Failed to parse metadata YAML from {local_md_path_abs}: {meta_error}", exc_info=True)
             raise ValueError(f"Invalid YAML metadata found in Markdown file '{markdown_file.name}': {meta_error}") from meta_error
        job.metadata = metadata_dict # Save potentially empty metadata first
        job.save(update_fields=JOB_METADATA_UPDATE_FIELDS)
        logger.info(f"[Job {task_id}] Metadata extracted successfully: {metadata_dict}")

        # --- *** NEW: Ensure a default title exists if not provided *** ---
        if "title" not in metadata_dict or not metadata_dict.get("title"):
            # Use the original Markdown filename stem as a default title
            default_title = Path(markdown_file.name).stem.replace('_', ' ').replace('-', ' ').title()
            logger.warning(f"[Job {task_id}] Metadata 'title' missing or empty. Defaulting title to filename stem: '{default_title}'")
            metadata_dict["title"] = default_title
            # Update the job metadata in the DB immediately if we defaulted the title
            job.metadata = metadata_dict # Update the job instance attribute as well
            job.save(update_fields=JOB_METADATA_UPDATE_FIELDS)
            logger.info(f"[Job {task_id}] Updated job metadata with default title.")
        # --- *** END NEW *** ---

        # --- Step 5.5: Callback Definition (Processes Content Images) ---
        callback_upload_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        def _wechat_image_uploader_callback(image_local_path: Path) -> Tuple[Optional[str], Optional[str]]:
            nonlocal access_token, base_url, callback_upload_cache, image_processing_warnings, task_id # Added task_id for logging consistency
            processed_content_path: Optional[Path] = None
            if not access_token or not base_url:
                err = "Callback invoked without valid access_token or base_url."
                logger.error(f"[Job {task_id}] {err}")
                return None, err
            try:
                resolved_path = image_local_path
                # Attempt to resolve relative paths relative to the original markdown file's directory
                # Note: This assumes image paths in Markdown are relative to the MD file.
                # If they are absolute or relative to project root, this might need adjustment.
                if not resolved_path.is_absolute() and local_md_path_abs:
                    resolved_path = local_md_path_abs.parent / image_local_path
                    logger.debug(f"[Job {task_id}] Resolved relative image path '{image_local_path}' to '{resolved_path}'")

                if not resolved_path.is_file():
                     # Try resolving strictly one more time in case of symlinks etc.
                     try: resolved_path = resolved_path.resolve(strict=True)
                     except FileNotFoundError:
                          err = f"Callback cannot find image referenced in Markdown: '{image_local_path}' (Resolved: '{resolved_path}')"
                          logger.error(f"[Job {task_id}] {err}")
                          image_processing_warnings.append(f"Image not found: {image_local_path.name}")
                          return None, err

                logger.debug(f"[Job {task_id}] Ensuring content image '{resolved_path.name}' meets size limit ({CONTENT_IMAGE_SIZE_LIMIT_KB} KB)...")
                processed_content_path = ensure_image_size(resolved_path, CONTENT_IMAGE_SIZE_LIMIT_KB)
                if processed_content_path != resolved_path: logger.info(f"[Job {task_id}] Content image '{resolved_path.name}' optimized. Using '{processed_content_path.name}'.")
                else: logger.debug(f"[Job {task_id}] Content image size OK. Using original '{resolved_path.name}'."); processed_content_path = resolved_path

            except FileNotFoundError:
                 err = f"Callback cannot find image file: {image_local_path}"; logger.error(f"[Job {task_id}] {err}"); image_processing_warnings.append(f"Image not found: {image_local_path.name}"); return None, err
            except (ValueError, ImportError) as img_err:
                 err = f"Failed to process content image '{image_local_path.name}': {img_err}"; logger.error(f"[Job {task_id}] {err}", exc_info=True); image_processing_warnings.append(f"Image processing failed: {image_local_path.name} ({type(img_err).__name__})"); return None, err
            except Exception as process_err:
                err = f"Error resolving/processing image path '{image_local_path}': {process_err}"; logger.error(f"[Job {task_id}] {err}", exc_info=True); image_processing_warnings.append(f"Image error: {image_local_path.name}"); return None, err

            # Ensure processed_content_path is valid before hashing/uploading
            if not processed_content_path or not processed_content_path.is_file():
                err = f"Processed content image path is invalid or file not found: {processed_content_path}"
                logger.error(f"[Job {task_id}] {err}")
                image_processing_warnings.append(f"Image processing error: {image_local_path.name}")
                return None, err

            content_image_hash = calculate_file_hash(processed_content_path, algorithm='sha256')
            wechat_url: Optional[str] = None; cached_result: Optional[Tuple[Optional[str], Optional[str]]] = None
            content_cache_key: Optional[str] = None # Define here for broader scope

            if not content_image_hash: logger.warning(f"[Job {task_id}] Could not calculate hash for processed content image {processed_content_path.name}, skipping cache.")
            else:
                content_cache_key = f"wechat_content_url_sha256_{content_image_hash}"; cached_result = cache.get(content_cache_key) or callback_upload_cache.get(content_cache_key)
                if cached_result:
                    cached_url, cached_err = cached_result
                    if cached_url: logger.debug(f"[Job {task_id}] Cache HIT for content image {processed_content_path.name}. Using URL: {cached_url}"); return cached_url, None
                    else: logger.warning(f"[Job {task_id}] Cache HIT for {processed_content_path.name}, but previous attempt failed (Error: {cached_err}). Skipping."); image_processing_warnings.append(f"Image skipped (previous failure): {processed_content_path.name}"); return None, cached_err
                logger.debug(f"[Job {task_id}] Cache MISS for content image {processed_content_path.name} (Key: {content_cache_key})")
            try:
                logger.debug(f"[Job {task_id}] Uploading processed content image via callback: {processed_content_path.name}"); wechat_url = wechat_api.upload_content_image(access_token=access_token, image_path=processed_content_path, base_url=base_url)
                if wechat_url:
                    logger.info(f"[Job {task_id}] Uploaded via callback: {processed_content_path.name} -> {wechat_url}"); result_to_cache = (wechat_url, None)
                    if content_image_hash and content_cache_key: cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT; cache.set(content_cache_key, result_to_cache, timeout=cache_timeout); callback_upload_cache[content_cache_key] = result_to_cache; logger.debug(f"[Job {task_id}] Stored success result in cache (Key: {content_cache_key}).")
                    return wechat_url, None
                else:
                    err = f"WeChat API returned no URL for uploaded image: {processed_content_path.name}"; logger.error(f"[Job {task_id}] {err}"); result_to_cache = (None, err)
                    if content_image_hash and content_cache_key: cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT; cache.set(content_cache_key, result_to_cache, timeout=cache_timeout); callback_upload_cache[content_cache_key] = result_to_cache; logger.debug(f"[Job {task_id}] Stored failure result in cache (Key: {content_cache_key}).")
                    image_processing_warnings.append(f"Image upload failed (no URL): {processed_content_path.name}"); return None, err
            except Exception as e:
                err = f"Upload error for {processed_content_path.name}: {e}"; logger.exception(f"[Job {task_id}] {err}"); result_to_cache = (None, err)
                if content_image_hash and content_cache_key: cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT; cache.set(content_cache_key, result_to_cache, timeout=cache_timeout); callback_upload_cache[content_cache_key] = result_to_cache; logger.debug(f"[Job {task_id}] Stored unexpected error result in cache (Key: {content_cache_key}).")
                image_processing_warnings.append(f"Image upload error: {processed_content_path.name} ({type(e).__name__})"); return None, err


        # --- Step 6: Process HTML Fragment ---
        logger.info(f"[Job {task_id}] Processing HTML fragment from Markdown body using uploader callback...")
        if not local_md_path_abs: raise FileNotFoundError("Markdown file path missing before HTML processing.")
        markdown_body_content = markdown_body_content or ""

        def adapted_uploader(local_path: Path) -> Optional[str]:
            # This adapter calls the main callback and only returns the URL if successful
            url, error = _wechat_image_uploader_callback(local_path)
            # Error logging and warning appending happens inside _wechat_image_uploader_callback
            return url # Return URL or None

        css_path_setting = getattr(settings, 'PREVIEW_CSS_FILE_PATH', None)
        css_path_str: Optional[str] = None
        css_content: str = '/* No external CSS file provided or found */' # Default CSS content
        if css_path_setting:
            css_path = Path(css_path_setting)
            if not css_path.is_absolute() and hasattr(settings, 'BASE_DIR'):
                css_path = Path(settings.BASE_DIR) / css_path
            if css_path.is_file():
                try:
                    css_path_str = str(css_path)
                    css_content = css_path.read_text(encoding="utf-8") # Read content here
                    logger.debug(f"[Job {task_id}] Using preview CSS file: {css_path_str}")
                except Exception as css_read_err:
                     logger.warning(f"[Job {task_id}] Failed to read CSS file '{css_path}': {css_read_err}. CSS will not be embedded.")
                     css_path_str = None # Invalidate path if read fails
            else:
                logger.warning(f"[Job {task_id}] Preview CSS file configured but not found at {css_path}. Cannot embed CSS.")
                css_path_str = None
        else:
            logger.info(f"[Job {task_id}] No PREVIEW_CSS_FILE_PATH configured.")

        processed_html_fragment = html_processor.process_html_content(
            md_content=markdown_body_content,
            # css_path is not directly used by process_html_content for embedding,
            # but passed for potential internal use (though current structure doesn't seem to use it).
            # Embedding happens later in the full preview HTML construction.
            css_path=css_path_str,
            markdown_file_path=local_md_path_abs, # Crucial for resolving relative image paths
            image_uploader=adapted_uploader
        )
        logger.info(f"[Job {task_id}] HTML fragment processed.")
        if image_processing_warnings:
            warning_summary = "; ".join(image_processing_warnings)
            logger.warning(f"[Job {task_id}] Issues encountered during image processing: {len(image_processing_warnings)} warning(s). Summary: {warning_summary[:200]}...")
            # Store warnings, but don't overwrite fatal errors if they occur later
            current_error = job.error_message or ""
            job.error_message = (current_error + " | Warnings: " + warning_summary)[:1000]
            job.save(update_fields=JOB_ERROR_MSG_UPDATE_FIELDS)


        # --- Step 7 & 8: Wrap Full HTML, Generate Preview, Finalize ---
        # Use the potentially updated metadata_dict (with default title)
        preview_page_title = metadata_dict.get("title", "Article Preview") # Fallback just in case
        article_html_content = processed_html_fragment

        # --- REFINED HTML STRUCTURE for Preview (Embed CSS, Center Body) ---
        full_html_for_preview = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{preview_page_title}</title>
    <style type="text/css">
        /* Style to center the preview body */
        body {{
            max-width: 800px; /* Reading width */
            margin: 20px auto; /* Centering with top/bottom margin */
            padding: 0 15px; /* Side padding */
            box-sizing: border-box;
            background-color: #fdfdfd; /* Light off-white background */
            color: #333; /* Default text color for body */
            font-family: sans-serif; /* Basic fallback font for body */
            line-height: 1.6; /* Basic line height for body */
        }}
        /* Add a little space above the main #nice content */
        #nice {{
             margin-top: 1em; /* Adjust as needed */
        }}

        /* --- Embedded CSS from file below --- */
{css_content}
    </style>
</head>
<body>
    {article_html_content}
</body>
</html>"""
        # --- End of REFINED HTML Structure ---

        preview_path_rel_str = _generate_preview_file(full_html_for_preview, task_id)
        job.preview_html_path = preview_path_rel_str
        job.status = PublishingJob.Status.PREVIEW_READY
        # If there were only warnings, clear the error message field *unless* a default title was needed (keep the warning)
        if not image_processing_warnings and job.error_message and job.error_message.startswith("Warnings:"):
             job.error_message = None # Clear if only warnings existed before
        job.save(update_fields=JOB_PREVIEW_UPDATE_FIELDS + ['error_message']) # Update status and potentially clear error

        media_url = settings.MEDIA_URL.rstrip('/') + '/' if settings.MEDIA_URL else '/media/'
        preview_url_path = preview_path_rel_str.lstrip('/')
        preview_url = media_url + preview_url_path
        logger.info(f"[Job {task_id}] Preview ready. Accessible at: {preview_url}")

        final_result = {"task_id": str(job.task_id), "preview_url": preview_url}
        # Include warnings in the response if any occurred
        if image_processing_warnings:
            final_result["warnings"] = image_processing_warnings
        # Also include the default title warning if generated
        if "Defaulting title" in (job.error_message or ""):
             final_result["warnings"] = final_result.get("warnings", []) + [f"Title defaulted from filename: {metadata_dict.get('title')}"]


        return final_result

    # --- Exception Handling (Error saving and status update logic remains largely the same) ---
    except FileNotFoundError as e:
        logger.error(f"[Job {task_id}] File Not Found Error: {e}", exc_info=True)
        err_msg = f"Required file not found: {e}"
        if job:
            try: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg[:1000]; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err: logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after FileNotFoundError: {db_err}", exc_info=True)
        raise FileNotFoundError(err_msg) from e
    except (ValueError, yaml.YAMLError) as e:
        logger.error(f"[Job {task_id}] Value/YAML/Image Error: {e}", exc_info=True)
        err_msg = f"Invalid data, config, or image processing failed: {e}"
        if job:
            try: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg[:1000]; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err: logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after ValueError/YAMLError: {db_err}", exc_info=True)
        raise ValueError(err_msg) from e
    except RuntimeError as e:
        # Specific handling for WeChat auth errors (like IP whitelist)
        if "invalid ip" in str(e) and "not in whitelist" in str(e):
             err_msg = f"WeChat API Error: The server's IP address is not in the WeChat Official Account IP whitelist. Please add it in the Basic Configuration section. (Original error: {e})"
             logger.error(f"[Job {task_id}] WeChat IP Whitelist Error: {e}", exc_info=False) # Don't need full traceback for config error
        else:
            err_msg = str(e)
            logger.error(f"[Job {task_id}] Runtime Error: {e}", exc_info=True)

        if job:
            try: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg[:1000]; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err: logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after RuntimeError: {db_err}", exc_info=True)
        raise RuntimeError(err_msg) from e # Re-raise with potentially clearer message
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during processing job: {e}")
        err_msg = "An unexpected internal error occurred during processing. Please check application logs."
        if job:
            try: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err: logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after unexpected error: {db_err}", exc_info=True)
        raise # Re-raise the original exception


# confirm_and_publish_job (Refined checks)
def confirm_and_publish_job(task_id: uuid.UUID) -> Dict[str, Any]:
    """
    Handles Request 2: Confirms job, builds payload, publishes draft, handles 40007 retry.
    Includes re-processing cover image on thumbnail re-upload during retry.
    """
    job: Optional[PublishingJob] = None
    access_token: Optional[str] = None

    try:
        logger.info(f"[Job {task_id}] Attempting to confirm and publish job.")
        try:
            job = PublishingJob.objects.get(pk=task_id)
        except PublishingJob.DoesNotExist:
             logger.warning(f"Publishing job with task_id {task_id} not found in database.")
             raise ObjectDoesNotExist(f"Job with ID {task_id} not found.")


        # --- Pre-flight Checks ---
        if job.status != PublishingJob.Status.PREVIEW_READY:
            logger.warning(f"[Job {task_id}] Cannot publish job with status '{job.get_status_display()}'. Required: PREVIEW_READY.")
            # Provide a more specific error message if it failed previously
            error_info = f" (Reason: {job.error_message})" if job.status == PublishingJob.Status.FAILED and job.error_message else ""
            raise ValueError(f"Job not ready for publishing. Current Status: {job.get_status_display()}{error_info}.")

        # Retrieve metadata *after* confirming status is PREVIEW_READY
        metadata_from_db = job.metadata or {}
        title_from_db = metadata_from_db.get('title') # Get title, could be None or empty
        digest_from_db = metadata_from_db.get('digest')

        # --- Diagnostic Logging ---
        try:
            logger.debug(f"[Job {task_id}] Checking metadata retrieved FROM DB:")
            logger.debug(f"[Job {task_id}]   Title='{title_from_db}' (Type: {type(title_from_db)})")
            logger.debug(f"[Job {task_id}]   Digest='{digest_from_db}' (Type: {type(digest_from_db)})")
            logger.debug(f"[Job {task_id}]   Raw job.metadata from DB: {job.metadata}")
        except Exception as log_ex:
            logger.error(f"[Job {task_id}] Error logging metadata from DB: {log_ex}")

        # Refined checks: Ensure metadata dict exists and title is present and non-empty
        # The `start_processing_job` should have defaulted the title, but check again for safety.
        if not isinstance(job.metadata, dict):
             # This shouldn't happen if start_processing_job worked, but safety check
             raise ValueError("Cannot publish job: Metadata is invalid or missing.")
        if not title_from_db: # Checks for None, empty string ""
             logger.error(f"[Job {task_id}] Cannot publish job: 'title' is missing or empty in metadata even after processing. Metadata: {job.metadata}")
             raise ValueError("Cannot publish job: Article 'title' is missing or empty in metadata.")
        if not job.thumb_media_id:
            raise ValueError("Cannot publish job: WeChat thumbnail ID (thumb_media_id) is missing.")


        logger.info(f"[Job {task_id}] Job status is PREVIEW_READY with valid title. Proceeding.")
        job.status = PublishingJob.Status.PUBLISHING
        job.save(update_fields=JOB_STATUS_UPDATE_FIELDS)

        # --- WeChat Setup ---
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret: raise ValueError("WeChat credentials not configured.")
        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        if not access_token: raise RuntimeError("Failed to get WeChat access token for publishing.")
        logger.debug(f"[Job {task_id}] Retrieved WeChat access token for publishing.")

        # --- Build Payload ---
        # Use the metadata retrieved from the DB (which includes the potentially defaulted title)
        placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT or "<p>Content pending update.</p>" # Default placeholder
        logger.info(f"[Job {task_id}] Building initial draft payload with thumb_media_id: {job.thumb_media_id}")
        current_thumb_media_id = job.thumb_media_id
        try:
            article_payload = payload_builder.build_draft_payload(
                metadata=metadata_from_db, # Use metadata from DB
                html_content=placeholder_content,
                thumb_media_id=current_thumb_media_id
            )
            final_draft_payload = {"articles": [article_payload]}
            logger.debug(f"[Job {task_id}] Payload built successfully for initial attempt.")
        except (KeyError, ValueError) as build_err:
             logger.error(f"[Job {task_id}] Failed to build initial draft payload: {build_err}", exc_info=True)
             # Be more specific if title was somehow missing *here*
             if 'title' in str(build_err).lower():
                  raise ValueError(f"Payload building failed: 'title' key missing unexpectedly. Metadata: {metadata_from_db}") from build_err
             raise ValueError(f"Payload building failed: {build_err}") from build_err

        # --- Call WeChat API (Add Draft) with Retry and Cache Update ---
        # (Retry logic remains the same as the original provided code)
        final_media_id: Optional[str] = None
        max_retries: int = 1 # Only retry once for thumb error
        attempt: int = 0
        while attempt <= max_retries:
            attempt += 1
            try:
                logger.info(f"[Job {task_id}] Attempting WeChat 'add_draft' API call (Try {attempt}/{max_retries + 1}) using thumb_id: {current_thumb_media_id}")
                final_media_id = wechat_api.add_draft(
                    access_token=access_token,
                    draft_payload=final_draft_payload,
                    base_url=base_url
                )
                logger.info(f"[Job {task_id}] Successfully published draft placeholder (Try {attempt}). Draft Media ID: {final_media_id}")
                break # Success

            except Exception as e:
                # --- Diagnostic Logging for Exception ---
                logger.error(f"[Job {task_id}] Caught exception during add_draft: {type(e).__name__} - {e}", exc_info=False)
                errcode = None
                errmsg = str(e) # Default error message
                # Try to extract errcode and errmsg more reliably
                api_error_details = {}
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        api_error_details = e.response.json()
                        errcode = api_error_details.get('errcode')
                        errmsg = api_error_details.get('errmsg', errmsg)
                        logger.debug(f"[Job {task_id}] Extracted from response JSON: errcode={errcode}, errmsg='{errmsg}'")
                    except json.JSONDecodeError:
                        logger.warning(f"[Job {task_id}] Could not parse JSON from exception response.")
                    except Exception as parse_err:
                         logger.error(f"[Job {task_id}] Error parsing exception response details: {parse_err}")

                # Fallback checks if response parsing failed or wasn't available
                if errcode is None:
                    if hasattr(e, 'errcode'): errcode = getattr(e, 'errcode')
                    elif hasattr(e, 'code'): errcode = getattr(e, 'code')
                    elif len(e.args) > 0 and isinstance(e.args[0], dict) and 'errcode' in e.args[0]: errcode = e.args[0]['errcode']
                    elif isinstance(e, RuntimeError) and '40007' in str(e): errcode = 40007 # Specific check for thumb error string

                logger.error(f"[Job {task_id}]   Detected errcode: {errcode}, errmsg: '{errmsg}'")


                # --- Error Identification for Retry ---
                is_thumb_error = (errcode == 40007)

                if is_thumb_error and attempt <= max_retries:
                    logger.warning(f"[Job {task_id}] Identified thumb error (Code 40007: '{errmsg}') on attempt {attempt}. Re-processing and re-uploading thumbnail...")
                    # --- Retry Logic: Re-process and Re-upload Thumbnail ---
                    logger.info(f"[Job {task_id}] --- Starting Thumb Re-process & Re-upload ---")
                    if not job.original_cover_image_path:
                        err_retry = "Cannot retry thumb upload: original cover image path not found in job record."
                        logger.error(f"[Job {task_id}] {err_retry}")
                        raise ValueError(err_retry)

                    local_cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
                    if not local_cover_path_abs.is_file():
                         err_retry = f"Cannot retry thumb upload: original cover file not found at {local_cover_path_abs}"
                         logger.error(f"[Job {task_id}] {err_retry}")
                         raise FileNotFoundError(err_retry)

                    # --- Re-process the original image during retry ---
                    processed_cover_path_retry: Optional[Path] = None
                    try:
                        logger.info(f"[Job {task_id}] Re-processing original cover image '{local_cover_path_abs.name}' for retry...")
                        processed_cover_path_retry = ensure_image_size(local_cover_path_abs, COVER_IMAGE_SIZE_LIMIT_KB)
                        if processed_cover_path_retry != local_cover_path_abs: logger.info(f"[Job {task_id}] Original cover image optimized during retry to '{processed_cover_path_retry.name}'.")
                        else: logger.debug(f"[Job {task_id}] Original cover image size OK during retry."); processed_cover_path_retry = local_cover_path_abs
                    except (FileNotFoundError, ValueError, ImportError) as img_err:
                        logger.error(f"[Job {task_id}] CRITICAL: Failed to re-process cover image during retry: {img_err}", exc_info=True)
                        raise RuntimeError(f"Failed to re-process cover image during retry: {img_err}") from img_err
                    except Exception as img_err_other:
                         logger.error(f"[Job {task_id}] CRITICAL: Unexpected error re-processing cover image during retry: {img_err_other}", exc_info=True)
                         raise RuntimeError(f"Unexpected failure re-processing cover image during retry: {img_err_other}") from img_err_other

                    if not processed_cover_path_retry or not processed_cover_path_retry.is_file():
                         raise RuntimeError(f"Cover image path invalid after re-processing attempt: {processed_cover_path_retry}")


                    # --- Get fresh token ---
                    logger.debug(f"[Job {task_id}] Getting fresh access token for retry...")
                    access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
                    if not access_token: logger.error(f"[Job {task_id}] Failed to get fresh WeChat token for retry."); raise RuntimeError("Failed to get fresh WeChat token for retry.")
                    logger.debug(f"[Job {task_id}] Retrieved fresh access token for retry.")

                    # --- Re-upload using the API ---
                    logger.info(f"[Job {task_id}] Re-uploading *processed* thumbnail from: {processed_cover_path_retry}")
                    new_thumb_media_id = None
                    try:
                        new_thumb_media_id = wechat_api.upload_thumb_media(access_token=access_token, thumb_path=processed_cover_path_retry, base_url=base_url)
                    except Exception as upload_retry_err:
                        logger.error(f"[Job {task_id}] Exception during thumbnail re-upload: {upload_retry_err}", exc_info=True)
                        raise RuntimeError(f"Failed during thumbnail re-upload attempt: {upload_retry_err}") from upload_retry_err

                    if not new_thumb_media_id: err_retry = "Failed to re-upload permanent thumbnail during retry (API returned no ID)."; logger.error(f"[Job {task_id}] {err_retry}"); raise RuntimeError(err_retry)
                    logger.info(f"[Job {task_id}] New thumb media ID obtained: {new_thumb_media_id}.")

                    # --- Update DB and Cache ---
                    job.thumb_media_id = new_thumb_media_id
                    current_thumb_media_id = new_thumb_media_id
                    job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
                    logger.info(f"[Job {task_id}] Updated job record with new thumb_media_id: {new_thumb_media_id}")
                    cover_image_hash_retry = calculate_file_hash(processed_cover_path_retry, algorithm='sha256')
                    if cover_image_hash_retry:
                        cache_key_retry = f"wechat_thumb_sha256_{cover_image_hash_retry}"; cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                        cache.set(cache_key_retry, new_thumb_media_id, timeout=cache_timeout)
                        logger.info(f"[Job {task_id}] Updated cache with new valid thumbnail Media ID (Key: {cache_key_retry}).")
                    else: logger.warning(f"[Job {task_id}] Could not calculate hash for processed cover image during retry, cache not updated.")

                    # --- Re-build payload ---
                    logger.info(f"[Job {task_id}] Re-building payload with new thumb media ID ({current_thumb_media_id}) for retry.")
                    try:
                        # Re-fetch metadata from DB in case it was modified? Unlikely but safe.
                        metadata_for_retry = job.metadata or {}
                        article_payload = payload_builder.build_draft_payload(metadata=metadata_for_retry, html_content=placeholder_content, thumb_media_id=current_thumb_media_id)
                        final_draft_payload = {"articles": [article_payload]}
                        logger.debug(f"[Job {task_id}] Payload rebuilt successfully for retry.")
                    except (KeyError, ValueError) as build_err:
                        logger.error(f"[Job {task_id}] Failed to re-build draft payload during retry: {build_err}", exc_info=True)
                        raise ValueError(f"Payload re-building failed during retry: {build_err}") from build_err
                    logger.info(f"[Job {task_id}] --- Finished Thumb Re-process & Re-upload ---")
                    continue # Retry add_draft

                else:
                    # Non-retryable error or retries exhausted
                    logger.error(f"[Job {task_id}] Non-retryable error or retries exhausted. Error: {type(e).__name__}, Code: {errcode}, Attempt: {attempt}", exc_info=False)
                    err_msg_publish = f"Failed to publish draft to WeChat after {attempt} attempt(s). Last error: {errmsg} (Code: {errcode or 'N/A'})"
                    raise RuntimeError(err_msg_publish) from e
            # --- End Exception Block for add_draft attempt ---
        # --- End While Loop for Retries ---

        if not final_media_id:
             logger.error(f"[Job {task_id}] Logic error: Publishing loop finished but final WeChat media ID was not obtained.")
             raise RuntimeError("Publishing finished but final WeChat media ID was not obtained.")

        # --- Success Case ---
        job.status = PublishingJob.Status.PUBLISHED
        job.wechat_media_id = final_media_id
        job.error_message = None # Clear previous warnings/errors on success
        job.published_at = timezone.now()
        job.save(update_fields=JOB_PUBLISH_SUCCESS_FIELDS)
        status_display = job.get_status_display()
        logger.info(f"[Job {task_id}] Successfully published placeholder draft to WeChat. Final Status: {status_display}, WeChat Media ID: {final_media_id}")
        return {
            "task_id": str(job.task_id),
            "status": status_display,
            "message": "Article placeholder published to WeChat drafts successfully. Please copy the formatted content from the preview page and paste it into the WeChat editor to complete the process.",
            "wechat_media_id": final_media_id
        }

    # --- Exception Handling (Error saving and status update logic remains largely the same) ---
    except ObjectDoesNotExist:
        # Already logged above, just re-raise for the view to handle
        raise
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"[Job {task_id}] Pre-condition or data error during publish: {e}", exc_info=True)
        err_msg = f"Publishing pre-check or setup failed: {e}"
        # Ensure job exists before trying to update status
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg[:1000]
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                 logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after pre-condition error: {db_err}", exc_info=True)
        if isinstance(e, FileNotFoundError): raise FileNotFoundError(err_msg) from e
        else: raise ValueError(err_msg) from e
    except RuntimeError as e:
        # Specific handling for WeChat auth errors (like IP whitelist)
        if "invalid ip" in str(e) and "not in whitelist" in str(e):
             err_msg = f"WeChat API Error: The server's IP address is not in the WeChat Official Account IP whitelist. Please add it in the Basic Configuration section. (Original error: {e})"
             logger.error(f"[Job {task_id}] WeChat IP Whitelist Error during publish: {e}", exc_info=False)
        else:
            err_msg = str(e)
            logger.error(f"[Job {task_id}] Runtime error during publish operation: {e}", exc_info=True)

        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg[:1000]
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after runtime error: {db_err}", exc_info=True)
        raise RuntimeError(err_msg) from e # Re-raise with potentially clearer message
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during confirmation/publishing: {e}")
        err_msg = "An unexpected internal error occurred during publishing."
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                 logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after unexpected publishing error: {db_err}", exc_info=True)
        raise # Re-raise the original exception