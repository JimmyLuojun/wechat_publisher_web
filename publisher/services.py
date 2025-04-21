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
        # relative_path_str = (Path(subfolder) / unique_filename).as_posix() # Not used directly
        logger.info(f"File '{file_obj.name}' saved locally to absolute path: {local_save_path_abs}")
        return local_save_path_abs
    except IOError as e:
        logger.exception(f"IOError saving uploaded file '{file_obj.name}' locally.")
        raise RuntimeError(f"Failed to save '{file_obj.name}' locally due to file system error.") from e
    except Exception as e:
        logger.exception(f"Unexpected error saving uploaded file '{file_obj.name}' locally.")
        raise RuntimeError(f"Unexpected failure saving '{file_obj.name}' locally.") from e


# _generate_preview_file (Unchanged from previous correction)
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


# start_processing_job (Modified to process cover image and content images via callback)
def start_processing_job(
    markdown_file: UploadedFile,
    cover_image: UploadedFile,
    content_images: List[UploadedFile] # Note: These are side-uploaded, not directly used unless referenced in MD
) -> Dict[str, Any]:
    """
    Handles Request 1: Saves files, processes cover image, uploads/caches cover thumb,
    processes Markdown (incl. processing referenced content images), generates preview.
    """
    job: Optional[PublishingJob] = None
    task_id = uuid.uuid4()
    local_cover_path_abs: Optional[Path] = None
    processed_cover_path_abs: Optional[Path] = None # Store path after potential processing
    local_md_path_abs: Optional[Path] = None
    access_token: Optional[str] = None
    image_processing_warnings: List[str] = [] # To collect warnings for the response

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
        job.save(update_fields=JOB_PATHS_UPDATE_FIELDS) # Save original paths first

        # --- Step 3.5: Process Cover Image ---
        try:
            logger.info(f"[Job {task_id}] Ensuring cover image '{local_cover_path_abs.name}' meets size limit ({COVER_IMAGE_SIZE_LIMIT_KB} KB)...")
            processed_cover_path_abs = ensure_image_size(local_cover_path_abs, COVER_IMAGE_SIZE_LIMIT_KB)
            if processed_cover_path_abs != local_cover_path_abs:
                logger.info(f"[Job {task_id}] Cover image optimized. Using '{processed_cover_path_abs.name}' for WeChat.")
                # Optional: Store the processed path if needed later (e.g., for retry without re-processing)
                # job.processed_cover_image_path = processed_cover_path_abs.relative_to(settings.MEDIA_ROOT).as_posix()
                # job.save(update_fields=JOB_PROCESSED_PATHS_UPDATE_FIELDS) # Example if storing path
            else:
                 logger.debug(f"[Job {task_id}] Cover image size OK. Using original '{local_cover_path_abs.name}'.")
                 processed_cover_path_abs = local_cover_path_abs # Ensure it's assigned for subsequent steps
        except (FileNotFoundError, ValueError, ImportError) as img_err:
            logger.error(f"[Job {task_id}] CRITICAL: Failed to process cover image '{local_cover_path_abs.name}': {img_err}", exc_info=True)
            # Fail the job if cover image processing fails, as it's essential for the thumbnail
            raise RuntimeError(f"Failed to process cover image '{cover_image.name}': {img_err}") from img_err
        except Exception as e: # Catch any other unexpected error during image processing
            logger.error(f"[Job {task_id}] CRITICAL: Unexpected error processing cover image '{local_cover_path_abs.name}': {e}", exc_info=True)
            raise RuntimeError(f"Unexpected failure processing cover image '{cover_image.name}': {e}") from e

        # Save side-uploaded content images (processing happens later if referenced in Markdown)
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

        # Use the *processed* cover image path for hashing and upload
        logger.info(f"[Job {task_id}] Preparing PERMANENT WeChat thumbnail from processed path: '{processed_cover_path_abs}'")
        if not processed_cover_path_abs or not processed_cover_path_abs.is_file():
             # This check should ideally be redundant due to checks in ensure_image_size
             raise FileNotFoundError(f"Processed cover image not found at expected path: {processed_cover_path_abs}")

        # --- Caching Logic Start (Using hash of the *processed* file) ---
        permanent_thumb_media_id: Optional[str] = None
        cover_image_hash = calculate_file_hash(processed_cover_path_abs, algorithm='sha256') # Hash the processed file
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
                    # Upload the processed file
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
            # Handle hash failure (upload processed file directly)
            logger.error(f"[Job {task_id}] Failed to calculate hash for processed cover image {processed_cover_path_abs}, cannot use cache.")
            logger.warning(f"[Job {task_id}] Proceeding with direct thumbnail upload of processed file due to hash failure.")
            try:
                 # Upload the processed file
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
            metadata_dict = metadata_dict or {}
        except (ValueError, yaml.YAMLError) as meta_error:
             logger.error(f"[Job {task_id}] Failed to parse metadata YAML from {local_md_path_abs}: {meta_error}", exc_info=True)
             raise ValueError(f"Invalid YAML metadata found in Markdown file '{markdown_file.name}': {meta_error}") from meta_error
        job.metadata = metadata_dict
        job.save(update_fields=JOB_METADATA_UPDATE_FIELDS)
        logger.info(f"[Job {task_id}] Metadata extracted successfully: {metadata_dict}")

        # --- Step 5.5: Callback Definition (Processes Content Images) ---
        # Cache stores tuple: (Optional[str], Optional[str]) -> (wechat_url, error_message)
        callback_upload_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

        def _wechat_image_uploader_callback(image_local_path: Path) -> Tuple[Optional[str], Optional[str]]:
            """
            Resolves, processes (ensures size limits), uploads (or uses cache) content images.
            Returns (wechat_url, error_message). error_message is None on success.
            Adds warnings to the outer scope list `image_processing_warnings`.
            """
            nonlocal access_token, base_url, callback_upload_cache, image_processing_warnings
            processed_content_path: Optional[Path] = None # Define scope

            if not access_token or not base_url:
                err = "Callback invoked without valid access_token or base_url."
                logger.error(f"[Job {task_id}] {err}")
                return None, err

            # --- Resolve and Process Content Image ---
            try:
                # Use image_local_path directly first, as html_processor should resolve it
                resolved_path = image_local_path
                if not resolved_path.is_file(): # Double check after resolution by html_processor
                     # Attempt to resolve strictly if needed (e.g., if html_processor didn't)
                     try:
                        resolved_path = image_local_path.resolve(strict=True)
                     except FileNotFoundError:
                          err = f"Callback cannot find image referenced in Markdown: {image_local_path}"
                          logger.error(f"[Job {task_id}] {err}")
                          image_processing_warnings.append(f"Image not found: {image_local_path.name}")
                          return None, err

                logger.debug(f"[Job {task_id}] Ensuring content image '{resolved_path.name}' meets size limit ({CONTENT_IMAGE_SIZE_LIMIT_KB} KB)...")
                processed_content_path = ensure_image_size(resolved_path, CONTENT_IMAGE_SIZE_LIMIT_KB)
                if processed_content_path != resolved_path:
                    logger.info(f"[Job {task_id}] Content image '{resolved_path.name}' optimized. Using '{processed_content_path.name}'.")
                else:
                    logger.debug(f"[Job {task_id}] Content image size OK. Using original '{resolved_path.name}'.")
                    processed_content_path = resolved_path # Ensure assigned

            except FileNotFoundError: # Should be caught above ideally, but as safeguard
                 err = f"Callback cannot find image file: {image_local_path}"
                 logger.error(f"[Job {task_id}] {err}")
                 image_processing_warnings.append(f"Image not found: {image_local_path.name}")
                 return None, err
            except (ValueError, ImportError) as img_err: # Catch image processing errors
                 err = f"Failed to process content image '{image_local_path.name}': {img_err}"
                 logger.error(f"[Job {task_id}] {err}", exc_info=True) # Log stack trace for processing errors
                 image_processing_warnings.append(f"Image processing failed: {image_local_path.name} ({type(img_err).__name__})")
                 return None, err
            except Exception as process_err: # Catch other resolution/processing errors
                err = f"Error resolving/processing image path '{image_local_path}': {process_err}"
                logger.error(f"[Job {task_id}] {err}", exc_info=True)
                image_processing_warnings.append(f"Image error: {image_local_path.name}")
                return None, err
            # --- End Resolve and Process ---

            # --- Caching Logic (Based on Processed Image Hash) ---
            content_image_hash = calculate_file_hash(processed_content_path, algorithm='sha256')
            wechat_url: Optional[str] = None
            cached_result: Optional[Tuple[Optional[str], Optional[str]]] = None

            if not content_image_hash:
                logger.warning(f"[Job {task_id}] Could not calculate hash for processed content image {processed_content_path.name}, skipping cache.")
            else:
                content_cache_key = f"wechat_content_url_sha256_{content_image_hash}"
                # Check both Django cache and in-memory cache for this request
                cached_result = cache.get(content_cache_key) or callback_upload_cache.get(content_cache_key)
                if cached_result:
                    cached_url, cached_err = cached_result
                    if cached_url:
                        logger.debug(f"[Job {task_id}] Cache HIT for content image {processed_content_path.name}. Using URL: {cached_url}")
                        return cached_url, None # Return cached success
                    else:
                         # Previous attempt failed, don't retry automatically via cache hit
                         logger.warning(f"[Job {task_id}] Cache HIT for {processed_content_path.name}, but previous attempt failed (Error: {cached_err}). Skipping.")
                         image_processing_warnings.append(f"Image skipped (previous failure): {processed_content_path.name}")
                         return None, cached_err # Return cached failure

                logger.debug(f"[Job {task_id}] Cache MISS for content image {processed_content_path.name} (Key: {content_cache_key})")
            # --- End Caching Logic ---

            # --- Upload Processed Image ---
            try:
                logger.debug(f"[Job {task_id}] Uploading processed content image via callback: {processed_content_path.name}")
                # Use the *processed* path for upload
                wechat_url = wechat_api.upload_content_image(
                    access_token=access_token, image_path=processed_content_path, base_url=base_url
                )
                if wechat_url:
                    logger.info(f"[Job {task_id}] Uploaded via callback: {processed_content_path.name} -> {wechat_url}")
                    result_to_cache = (wechat_url, None) # Success result
                    if content_image_hash:
                         cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                         cache.set(content_cache_key, result_to_cache, timeout=cache_timeout)
                         callback_upload_cache[content_cache_key] = result_to_cache
                         logger.debug(f"[Job {task_id}] Stored success result in cache (Key: {content_cache_key}).")
                    return wechat_url, None # Return success
                else:
                    # API returned no URL, treat as failure
                    err = f"WeChat API returned no URL for uploaded image: {processed_content_path.name}"
                    logger.error(f"[Job {task_id}] {err}")
                    result_to_cache = (None, err) # Failure result
                    if content_image_hash: # Cache the failure too
                        cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT # Use same timeout?
                        cache.set(content_cache_key, result_to_cache, timeout=cache_timeout)
                        callback_upload_cache[content_cache_key] = result_to_cache
                        logger.debug(f"[Job {task_id}] Stored failure result in cache (Key: {content_cache_key}).")
                    image_processing_warnings.append(f"Image upload failed (no URL): {processed_content_path.name}")
                    return None, err # Return failure

            except Exception as e:
                # Catch API call errors or other unexpected issues during upload
                err = f"Upload error for {processed_content_path.name}: {e}"
                logger.exception(f"[Job {task_id}] {err}") # Log stack trace for upload errors
                result_to_cache = (None, err)
                if content_image_hash:
                    cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                    cache.set(content_cache_key, result_to_cache, timeout=cache_timeout)
                    callback_upload_cache[content_cache_key] = result_to_cache
                    logger.debug(f"[Job {task_id}] Stored unexpected error result in cache (Key: {content_cache_key}).")
                image_processing_warnings.append(f"Image upload error: {processed_content_path.name} ({type(e).__name__})")
                return None, err # Return failure
            # --- End Upload Processed Image ---

        # --- Step 6: Process HTML Fragment ---
        logger.info(f"[Job {task_id}] Processing HTML fragment from Markdown body using uploader callback...")
        if not local_md_path_abs:
             raise FileNotFoundError("Markdown file path missing before HTML processing.")
        markdown_body_content = markdown_body_content or ""

        # Adapter function to bridge the callback return type difference
        def adapted_uploader(local_path: Path) -> Optional[str]:
            """Adapts the callback result for the html_processor interface."""
            url, error = _wechat_image_uploader_callback(local_path)
            # The error/warning logging is handled inside _wechat_image_uploader_callback
            if error:
                return None # Signal failure to html_processor
            return url

        # Get CSS path (logic remains the same)
        css_path_setting = getattr(settings, 'PREVIEW_CSS_FILE_PATH', None)
        css_path_str: Optional[str] = None
        if css_path_setting:
            css_path = Path(css_path_setting)
            if not css_path.is_absolute() and hasattr(settings, 'BASE_DIR'):
                css_path = Path(settings.BASE_DIR) / css_path
            if css_path.is_file():
                css_path_str = str(css_path)
                logger.debug(f"[Job {task_id}] Using preview CSS file: {css_path_str}")
            else:
                logger.warning(f"[Job {task_id}] Preview CSS file configured but not found at {css_path}. No CSS applied.")
        else:
            logger.info("[Job {task_id}] No PREVIEW_CSS_FILE_PATH configured.")

        # Call html_processor with the adapted uploader
        processed_html_fragment = html_processor.process_html_content(
            md_content=markdown_body_content,
            css_path=css_path_str,
            markdown_file_path=local_md_path_abs,
            image_uploader=adapted_uploader # Use the adapted uploader
        )
        logger.info(f"[Job {task_id}] HTML fragment processed.")
        if image_processing_warnings:
            logger.warning(f"[Job {task_id}] Issues encountered during image processing: {len(image_processing_warnings)} warning(s). See details above.")
            # Store summary in job record
            warning_summary = "; ".join(image_processing_warnings)
            job.error_message = warning_summary[:1000] # Truncate if needed for DB field size
            job.save(update_fields=JOB_ERROR_MSG_UPDATE_FIELDS)


        # --- Step 7 & 8: Wrap Full HTML, Generate Preview, Finalize ---
        preview_title = metadata_dict.get("title", f"Preview - {task_id}")
        # Basic HTML structure for preview (can be customized)
        full_html_for_preview = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{preview_title}</title>
    <style>
        body {{ font-family: sans-serif; line-height: 1.6; padding: 20px; max-width: 800px; margin: auto; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 10px 0; border: 1px solid #eee; }} /* Added border */
        h1, h2, h3 {{ margin-top: 1.5em; }}
        /* Add styles from html_processor if needed, or link to external CSS */
    </style>
</head>
<body>
    <h1>{preview_title}</h1>
    <hr>
    {processed_html_fragment}
</body>
</html>"""
        preview_path_rel_str = _generate_preview_file(full_html_for_preview, task_id)
        job.preview_html_path = preview_path_rel_str
        job.status = PublishingJob.Status.PREVIEW_READY
        # Clear previous errors only if successful now, otherwise keep warnings
        if not image_processing_warnings:
             job.error_message = None
        job.save(update_fields=JOB_PREVIEW_UPDATE_FIELDS + ['error_message'])

        # Construct preview URL
        media_url = settings.MEDIA_URL.rstrip('/') + '/' if settings.MEDIA_URL else '/media/'
        preview_url_path = preview_path_rel_str.lstrip('/')
        preview_url = media_url + preview_url_path
        logger.info(f"[Job {task_id}] Preview ready. Accessible at: {preview_url}")

        # Modify return value to include warnings
        final_result = {"task_id": str(job.task_id), "preview_url": preview_url}
        if image_processing_warnings:
            final_result["warnings"] = image_processing_warnings

        return final_result

    # --- Exception Handling ---
    except FileNotFoundError as e:
        logger.error(f"[Job {task_id}] File Not Found Error: {e}", exc_info=True)
        err_msg = f"Required file not found: {e}"
        if job: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise FileNotFoundError(err_msg) from e
    except (ValueError, yaml.YAMLError) as e: # ValueError can come from image processing too
        logger.error(f"[Job {task_id}] Value/YAML/Image Error: {e}", exc_info=True)
        err_msg = f"Invalid data, config, or image processing failed: {e}"
        if job: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise ValueError(err_msg) from e
    except RuntimeError as e:
        logger.error(f"[Job {task_id}] Runtime Error: {e}", exc_info=True)
        err_msg = str(e)
        if job: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during processing job: {e}")
        err_msg = "An unexpected internal error occurred. Please check application logs."
        if job:
            try: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err: logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after error: {db_err}", exc_info=True)
        raise # Re-raise the original exception


# confirm_and_publish_job (Modified for re-processing cover image on retry)
def confirm_and_publish_job(task_id: uuid.UUID) -> Dict[str, Any]:
    """
    Handles Request 2: Confirms job, builds payload, publishes draft, handles 40007 retry.
    Includes re-processing cover image on thumbnail re-upload during retry.
    """
    job: Optional[PublishingJob] = None
    access_token: Optional[str] = None

    try:
        logger.info(f"[Job {task_id}] Attempting to confirm and publish job.")
        job = PublishingJob.objects.get(pk=task_id)

        # --- Diagnostic Logging ---
        try:
            metadata_from_db = job.metadata or {}
            title_from_db = metadata_from_db.get('title', 'N/A')
            digest_from_db = metadata_from_db.get('digest', 'N/A')
            logger.debug(f"[Job {task_id}] Checking metadata retrieved FROM DB:")
            logger.debug(f"[Job {task_id}]   Title='{title_from_db}' (Type: {type(title_from_db)})")
            logger.debug(f"[Job {task_id}]   Digest='{digest_from_db}' (Type: {type(digest_from_db)})")
            logger.debug(f"[Job {task_id}]   Raw job.metadata from DB: {job.metadata}")
        except Exception as log_ex:
            logger.error(f"[Job {task_id}] Error logging metadata from DB: {log_ex}")

        # --- Pre-flight Checks ---
        if job.status != PublishingJob.Status.PREVIEW_READY:
            logger.warning(f"[Job {task_id}] Cannot publish job with status '{job.get_status_display()}'. Required: PREVIEW_READY.")
            raise ValueError(f"Job not ready for publishing (Current Status: {job.get_status_display()}).")
        if not job.metadata: raise ValueError("Cannot publish job: Metadata is missing.")
        if not job.thumb_media_id: raise ValueError("Cannot publish job: WeChat thumbnail ID is missing.")
        if "title" not in job.metadata or not job.metadata["title"]:
             raise ValueError("Cannot publish job: 'title' is missing in metadata.")

        logger.info(f"[Job {task_id}] Job status is PREVIEW_READY. Proceeding.")
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
        placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT or "<p>Content pending update.</p>" # Default placeholder
        logger.info(f"[Job {task_id}] Building initial draft payload with thumb_media_id: {job.thumb_media_id}")
        current_thumb_media_id = job.thumb_media_id
        try:
            article_payload = payload_builder.build_draft_payload(
                metadata=job.metadata,
                html_content=placeholder_content,
                thumb_media_id=current_thumb_media_id
            )
            final_draft_payload = {"articles": [article_payload]}
            logger.debug(f"[Job {task_id}] Payload built successfully for initial attempt.")
        except (KeyError, ValueError) as build_err:
             logger.error(f"[Job {task_id}] Failed to build initial draft payload: {build_err}", exc_info=True)
             raise ValueError(f"Payload building failed: {build_err}") from build_err

        # --- Call WeChat API (Add Draft) with Retry and Cache Update ---
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
                logger.error(f"[Job {task_id}] Caught exception during add_draft: {type(e).__name__} - {e}", exc_info=False) # Log basic info first
                errcode = None
                try:
                    logger.debug(f"[Job {task_id}] Exception details: args={e.args}")
                    # Try to get errcode robustly
                    if hasattr(e, 'errcode'): errcode = getattr(e, 'errcode')
                    elif hasattr(e, 'code'): errcode = getattr(e, 'code')
                    elif len(e.args) > 0 and isinstance(e.args[0], dict) and 'errcode' in e.args[0]: errcode = e.args[0]['errcode'] # Check dict in args
                    elif isinstance(e, RuntimeError) and '40007' in str(e): errcode = 40007 # Manual check for specific known string
                    logger.error(f"[Job {task_id}]   Detected errcode: {errcode}")
                    if hasattr(e, 'response'): logger.error(f"[Job {task_id}]   Response attribute available.") # Indicate if response exists
                except Exception as log_err:
                    logger.error(f"[Job {task_id}] Error during diagnostic logging of exception details: {log_err}")

                # --- Error Identification for Retry ---
                # Check for media_id invalid or expired (40007)
                is_thumb_error = (errcode == 40007)

                if is_thumb_error and attempt <= max_retries:
                    logger.warning(f"[Job {task_id}] Identified thumb error (Code 40007) on attempt {attempt}. Re-processing and re-uploading thumbnail...")

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
                    try:
                        logger.info(f"[Job {task_id}] Re-processing original cover image '{local_cover_path_abs.name}' for retry...")
                        processed_cover_path_retry = ensure_image_size(local_cover_path_abs, COVER_IMAGE_SIZE_LIMIT_KB)
                        if processed_cover_path_retry != local_cover_path_abs:
                            logger.info(f"[Job {task_id}] Original cover image optimized during retry to '{processed_cover_path_retry.name}'.")
                        else:
                             logger.debug(f"[Job {task_id}] Original cover image size OK during retry.")
                             processed_cover_path_retry = local_cover_path_abs # Ensure assigned
                    except (FileNotFoundError, ValueError, ImportError) as img_err:
                        logger.error(f"[Job {task_id}] CRITICAL: Failed to re-process cover image during retry: {img_err}", exc_info=True)
                        raise RuntimeError(f"Failed to re-process cover image during retry: {img_err}") from img_err
                    except Exception as img_err_other: # Catch any other unexpected error
                         logger.error(f"[Job {task_id}] CRITICAL: Unexpected error re-processing cover image during retry: {img_err_other}", exc_info=True)
                         raise RuntimeError(f"Unexpected failure re-processing cover image during retry: {img_err_other}") from img_err_other

                    # --- Get fresh token ---
                    logger.debug(f"[Job {task_id}] Getting fresh access token for retry...")
                    access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url) # No force_refresh needed usually
                    if not access_token:
                        logger.error(f"[Job {task_id}] Failed to get fresh WeChat token for retry.")
                        raise RuntimeError("Failed to get fresh WeChat token for retry.")
                    logger.debug(f"[Job {task_id}] Retrieved fresh access token for retry.")

                    # --- Re-upload using the API ---
                    logger.info(f"[Job {task_id}] Re-uploading *processed* thumbnail from: {processed_cover_path_retry}")
                    new_thumb_media_id = None
                    try:
                        # Upload the potentially newly processed file
                        new_thumb_media_id = wechat_api.upload_thumb_media(
                            access_token=access_token, thumb_path=processed_cover_path_retry, base_url=base_url
                        )
                    except Exception as upload_retry_err:
                        logger.error(f"[Job {task_id}] Exception during thumbnail re-upload: {upload_retry_err}", exc_info=True)
                        raise RuntimeError(f"Failed during thumbnail re-upload attempt: {upload_retry_err}") from upload_retry_err

                    if not new_thumb_media_id:
                        err_retry = "Failed to re-upload permanent thumbnail during retry (API returned no ID)."
                        logger.error(f"[Job {task_id}] {err_retry}")
                        raise RuntimeError(err_retry)
                    logger.info(f"[Job {task_id}] New thumb media ID obtained: {new_thumb_media_id}.")

                    # --- Update DB and Cache ---
                    job.thumb_media_id = new_thumb_media_id
                    current_thumb_media_id = new_thumb_media_id # Use this new ID for the next attempt
                    job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
                    logger.info(f"[Job {task_id}] Updated job record with new thumb_media_id: {new_thumb_media_id}")

                    # Use hash of the *processed* file for the cache key
                    cover_image_hash_retry = calculate_file_hash(processed_cover_path_retry, algorithm='sha256')
                    if cover_image_hash_retry:
                        cache_key_retry = f"wechat_thumb_sha256_{cover_image_hash_retry}"
                        cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                        cache.set(cache_key_retry, new_thumb_media_id, timeout=cache_timeout)
                        logger.info(f"[Job {task_id}] Updated cache with new valid thumbnail Media ID (Key: {cache_key_retry}).")
                    else:
                         logger.warning(f"[Job {task_id}] Could not calculate hash for processed cover image during retry, cache not updated.")

                    # --- Re-build payload with the new thumb_media_id ---
                    logger.info(f"[Job {task_id}] Re-building payload with new thumb media ID ({current_thumb_media_id}) for retry.")
                    try:
                        article_payload = payload_builder.build_draft_payload(
                            metadata=job.metadata,
                            html_content=placeholder_content,
                            thumb_media_id=current_thumb_media_id # Use the NEWLY obtained ID
                        )
                        final_draft_payload = {"articles": [article_payload]} # Update the payload for the next loop iteration
                        logger.debug(f"[Job {task_id}] Payload rebuilt successfully for retry.")
                    except (KeyError, ValueError) as build_err:
                        logger.error(f"[Job {task_id}] Failed to re-build draft payload during retry: {build_err}", exc_info=True)
                        # Re-raise specific error, will be caught by outer loop and prevent further retries if needed
                        raise ValueError(f"Payload re-building failed during retry: {build_err}") from build_err

                    logger.info(f"[Job {task_id}] --- Finished Thumb Re-process & Re-upload ---")
                    continue # Retry the add_draft call with the new payload/thumb_id

                else:
                    # Error is not the specific 40007, OR retries exhausted, OR error occurred during retry steps themselves
                    logger.error(f"[Job {task_id}] Non-retryable error or retries exhausted. Error: {type(e).__name__}, Code: {errcode}, Attempt: {attempt}", exc_info=False)
                    err_msg_publish = f"Failed to publish draft to WeChat after {attempt} attempt(s). Last error: {type(e).__name__} (Code: {errcode or 'N/A'})"
                    # Raise a runtime error to be caught by the main exception handler
                    raise RuntimeError(err_msg_publish) from e
            # --- End Exception Block for add_draft attempt ---
        # --- End While Loop for Retries ---

        # --- Common Success Path ---
        if not final_media_id:
             # This case should ideally not be reached if errors are raised correctly
             logger.error(f"[Job {task_id}] Logic error: Publishing loop finished but final WeChat media ID was not obtained.")
             raise RuntimeError("Publishing finished but final WeChat media ID was not obtained.")

        job.status = PublishingJob.Status.PUBLISHED
        job.wechat_media_id = final_media_id
        job.error_message = None # Clear any previous warnings on successful publish
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

    # --- Exception Handling ---
    except ObjectDoesNotExist:
        logger.warning(f"Publishing job with task_id {task_id} not found in database.")
        raise # Re-raise for the view to handle as 404
    except (ValueError, FileNotFoundError) as e: # Includes issues from pre-checks, payload building, image processing during retry
        logger.error(f"[Job {task_id}] Pre-condition or data error during publish: {e}", exc_info=True)
        err_msg = f"Publishing pre-check or setup failed: {e}"
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
             job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
             job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        # Re-raise as specific type for potentially different handling in the view
        if isinstance(e, FileNotFoundError): raise FileNotFoundError(err_msg) from e
        else: raise ValueError(err_msg) from e
    except RuntimeError as e: # Includes API call failures (non-retryable), token issues, retry process failures
        logger.error(f"[Job {task_id}] Runtime error during publish operation: {e}", exc_info=True)
        err_msg = str(e)
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
             job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
             job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise RuntimeError(err_msg) from e # Re-raise for the view (likely 50x error)
    except Exception as e: # Catch-all for unexpected errors
        logger.exception(f"[Job {task_id}] Unexpected error during confirmation/publishing: {e}")
        err_msg = "An unexpected internal error occurred during publishing."
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                 logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after publishing error: {db_err}", exc_info=True)
        raise # Re-raise the original exception for a 500 error