# /Users/junluo/Documents/wechat_publisher_web/publisher/services.py
import os
import uuid
import json
import logging
from pathlib import Path
from typing import Dict, Callable, Any, List, Optional

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
    # --- Add Hash Util Import ---
    from publishing_engine.utils.hashing_checking import calculate_file_hash
    # Import the specific error if needed for type checking in except blocks
    # from publishing_engine.wechat.exceptions import WeChatAPIError # Example if used

    # Use logger from the 'publisher' app namespace defined in settings.py
    logger = logging.getLogger(__name__) # Correctly gets 'publisher' logger
    logger.info("Successfully imported modules from publishing_engine and utils.")
except ImportError as e:
    logger.exception("Failed to import critical 'publishing_engine' or 'utils' modules.", exc_info=True)
    # Propagate the ImportError to make startup failures clear
    raise ImportError("Failed to import critical 'publishing_engine' or 'utils' modules.") from e


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
        relative_path_str = (Path(subfolder) / unique_filename).as_posix()
        logger.info(f"File '{file_obj.name}' saved locally to absolute path: {local_save_path_abs} (relative: {relative_path_str})")
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


# start_processing_job (Unchanged - includes previous preview HTML refinement)
def start_processing_job(
    markdown_file: UploadedFile,
    cover_image: UploadedFile,
    content_images: List[UploadedFile]
) -> Dict[str, Any]:
    """
    Handles Request 1: Saves files, uploads/caches cover thumb, processes Markdown, generates preview.
    """
    job: Optional[PublishingJob] = None
    task_id = uuid.uuid4()
    local_cover_path_abs: Optional[Path] = None
    local_md_path_abs: Optional[Path] = None
    access_token: Optional[str] = None

    try:
        logger.info(f"[Job {task_id}] Starting new processing job (Callback workflow)")
        job = PublishingJob.objects.create(task_id=task_id, status=PublishingJob.Status.PENDING)
        job.status = PublishingJob.Status.PROCESSING
        job.save(update_fields=JOB_STATUS_UPDATE_FIELDS)
        logger.debug(f"[Job {task_id}] Status set to PROCESSING.")

        # Step 1-3: Save Files Locally
        local_md_path_abs = _save_uploaded_file_locally(markdown_file, subfolder='uploads/markdown')
        job.original_markdown_path = local_md_path_abs.relative_to(settings.MEDIA_ROOT).as_posix()
        local_cover_path_abs = _save_uploaded_file_locally(cover_image, subfolder='uploads/cover_images')
        job.original_cover_image_path = local_cover_path_abs.relative_to(settings.MEDIA_ROOT).as_posix()
        logger.info(f"[Job {task_id}] Saved Markdown to '{local_md_path_abs.name}'. Saved Cover locally to '{local_cover_path_abs.name}'.")
        saved_content_image_paths: List[Path] = []
        for image_file in content_images:
            path = _save_uploaded_file_locally(image_file, subfolder='uploads/content_images')
            saved_content_image_paths.append(path)
        logger.info(f"[Job {task_id}] Saved {len(saved_content_image_paths)} content images locally.")
        job.save(update_fields=JOB_PATHS_UPDATE_FIELDS)
        logger.debug(f"[Job {task_id}] Saved original file paths to job record.")

        # Step 4: WeChat Setup & Thumbnail Upload (with Caching)
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret:
            raise ValueError("WECHAT_APP_ID and/or WECHAT_SECRET are not configured in settings.")
        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        if not access_token:
             raise RuntimeError("Failed to retrieve WeChat access token.")
        logger.debug(f"[Job {task_id}] Retrieved WeChat access token.")
        logger.info(f"[Job {task_id}] Preparing PERMANENT WeChat thumbnail from local path: '{local_cover_path_abs}'")
        if not local_cover_path_abs or not local_cover_path_abs.is_file():
            raise FileNotFoundError(f"Local cover image for WeChat permanent upload not found at expected path: {local_cover_path_abs}")

        # Caching Logic Start
        permanent_thumb_media_id: Optional[str] = None
        cover_image_hash = calculate_file_hash(local_cover_path_abs, algorithm='sha256')
        if cover_image_hash:
            cache_key = f"wechat_thumb_sha256_{cover_image_hash}"
            logger.debug(f"[Job {task_id}] Checking cache for thumbnail with key: {cache_key}")
            cached_media_id = cache.get(cache_key)
            if cached_media_id:
                permanent_thumb_media_id = cached_media_id
                logger.info(f"[Job {task_id}] Cache HIT for thumbnail. Using cached Media ID: {permanent_thumb_media_id}")
            else:
                logger.info(f"[Job {task_id}] Cache MISS for thumbnail. Uploading image '{local_cover_path_abs.name}' to WeChat...")
                try:
                    permanent_thumb_media_id = wechat_api.upload_thumb_media(
                        access_token=access_token, thumb_path=local_cover_path_abs, base_url=base_url
                    )
                    if not permanent_thumb_media_id:
                        raise RuntimeError("WeChat API returned no media ID for thumbnail upload.")
                    logger.info(f"[Job {task_id}] Successfully uploaded thumbnail. New Media ID: {permanent_thumb_media_id}")
                    cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                    cache.set(cache_key, permanent_thumb_media_id, timeout=cache_timeout)
                    logger.info(f"[Job {task_id}] Stored new thumbnail Media ID in cache (Timeout: {cache_timeout}).")
                except Exception as upload_error:
                    logger.exception(f"[Job {task_id}] Failed to upload thumbnail '{local_cover_path_abs.name}': {upload_error}")
                    raise RuntimeError(f"Failed to upload thumbnail to WeChat: {upload_error}") from upload_error
        else:
            logger.error(f"[Job {task_id}] Failed to calculate hash for cover image {local_cover_path_abs}, cannot use cache.")
            logger.warning(f"[Job {task_id}] Proceeding with direct thumbnail upload due to hash failure.")
            try:
                permanent_thumb_media_id = wechat_api.upload_thumb_media(
                    access_token=access_token, thumb_path=local_cover_path_abs, base_url=base_url
                )
                if not permanent_thumb_media_id:
                     raise RuntimeError("WeChat API returned no media ID for thumbnail upload (after hash failure).")
                logger.info(f"[Job {task_id}] Successfully uploaded thumbnail (after hash failure). Media ID: {permanent_thumb_media_id}")
            except Exception as upload_error:
                logger.exception(f"[Job {task_id}] Failed to upload thumbnail '{local_cover_path_abs.name}' (after hash failure): {upload_error}")
                raise RuntimeError(f"Failed to upload thumbnail to WeChat (after hash failure): {upload_error}") from upload_error
        # Caching Logic End

        if not permanent_thumb_media_id:
             raise RuntimeError("Failed to obtain permanent thumbnail media ID for WeChat.")
        job.thumb_media_id = permanent_thumb_media_id
        job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
        logger.info(f"[Job {task_id}] PERMANENT WeChat thumbnail processed. Media ID: {permanent_thumb_media_id}")

        # Step 5: Metadata Extraction
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

        # Step 5.5: Callback Definition (with Caching for Content Images)
        callback_upload_cache: Dict[str, Optional[str]] = {}
        def _wechat_image_uploader_callback(image_local_path: Path) -> Optional[str]:
            nonlocal access_token, base_url, callback_upload_cache
            if not access_token or not base_url:
                 logger.error(f"[Job {task_id}] Callback invoked without valid access_token or base_url.")
                 return None
            try:
                resolved_path = image_local_path.resolve(strict=True)
                if not resolved_path.is_file():
                     logger.error(f"[Job {task_id}] Callback resolved path is not a file: {resolved_path}")
                     return None
            except FileNotFoundError:
                logger.error(f"[Job {task_id}] Callback cannot find image referenced in Markdown: {image_local_path}")
                return None
            except Exception as resolve_err:
                logger.error(f"[Job {task_id}] Error resolving image path '{image_local_path}': {resolve_err}")
                return None

            content_image_hash = calculate_file_hash(resolved_path, algorithm='sha256')
            wechat_url: Optional[str] = None
            if not content_image_hash:
                logger.warning(f"[Job {task_id}] Could not calculate hash for content image {resolved_path.name}, skipping cache.")
            else:
                content_cache_key = f"wechat_content_url_sha256_{content_image_hash}"
                cached_url = cache.get(content_cache_key) or callback_upload_cache.get(content_cache_key)
                if cached_url:
                    logger.debug(f"[Job {task_id}] Cache HIT for content image {resolved_path.name}. Using URL: {cached_url}")
                    return cached_url
                logger.debug(f"[Job {task_id}] Cache MISS for content image {resolved_path.name} (Key: {content_cache_key})")

            try:
                logger.debug(f"[Job {task_id}] Uploading content image via callback: {resolved_path.name}")
                wechat_url = wechat_api.upload_content_image(
                    access_token=access_token, image_path=resolved_path, base_url=base_url
                )
                if wechat_url:
                    logger.info(f"[Job {task_id}] Uploaded via callback: {resolved_path.name} -> {wechat_url}")
                    if content_image_hash:
                         cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                         cache.set(content_cache_key, wechat_url, timeout=cache_timeout)
                         callback_upload_cache[content_cache_key] = wechat_url
                         logger.debug(f"[Job {task_id}] Stored new content image URL in cache (Key: {content_cache_key}).")
                    return wechat_url
                else:
                    logger.error(f"[Job {task_id}] Callback received no URL from upload_content_image for: {resolved_path.name}")
                    return None
            except Exception as e:
                logger.exception(f"[Job {task_id}] Unexpected error during callback upload for {resolved_path.name}: {e}")
                return None

        # Step 6: Process HTML Fragment
        logger.info(f"[Job {task_id}] Processing HTML fragment from Markdown body using uploader callback...")
        if not local_md_path_abs:
             raise FileNotFoundError("Markdown file path missing before HTML processing.")
        markdown_body_content = markdown_body_content or ""
        css_path_setting = getattr(settings, 'PREVIEW_CSS_FILE_PATH', None)
        css_path_str: Optional[str] = None
        if css_path_setting:
            css_path = Path(css_path_setting)
            if not css_path.is_absolute() and hasattr(settings, 'BASE_DIR'):
                base_dir_path = Path(settings.BASE_DIR)
                css_path = base_dir_path / css_path
            if css_path.is_file():
                css_path_str = str(css_path)
                logger.debug(f"[Job {task_id}] Using preview CSS file: {css_path_str}")
            else:
                logger.warning(f"[Job {task_id}] Preview CSS file configured but not found at resolved path: {css_path}. Proceeding without it.")
        else:
            logger.info("[Job {task_id}] No PREVIEW_CSS_FILE_PATH configured in settings.")
        processed_html_fragment = html_processor.process_html_content(
            md_content=markdown_body_content,
            css_path=css_path_str,
            markdown_file_path=local_md_path_abs,
            image_uploader=_wechat_image_uploader_callback
        )
        logger.info(f"[Job {task_id}] HTML fragment processed successfully.")

        # Step 7 & 8: Wrap Full HTML, Generate Preview, Finalize (Includes Preview Title Refinement)
        preview_title = metadata_dict.get("title", f"Preview - {task_id}")
        full_html_for_preview = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{preview_title}</title>
    <style>
        body {{ font-family: sans-serif; line-height: 1.6; padding: 20px; max-width: 800px; margin: auto; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 10px 0; }}
        h1, h2, h3 {{ margin-top: 1.5em; }}
    </style>
</head>
<body>

    {processed_html_fragment}
</body>
</html>"""
        preview_path_rel_str = _generate_preview_file(full_html_for_preview, task_id)
        job.preview_html_path = preview_path_rel_str
        job.status = PublishingJob.Status.PREVIEW_READY
        job.error_message = None
        job.save(update_fields=JOB_PREVIEW_UPDATE_FIELDS + ['error_message'])
        media_url = settings.MEDIA_URL if settings.MEDIA_URL.endswith('/') else f"{settings.MEDIA_URL}/"
        preview_url_path = preview_path_rel_str.lstrip('/')
        preview_url = media_url + preview_url_path
        logger.info(f"[Job {task_id}] Preview ready. Accessible at: {preview_url}")
        return {"task_id": str(job.task_id), "preview_url": preview_url}

    # Exception Handling (Unchanged)
    except FileNotFoundError as e:
        logger.error(f"[Job {task_id}] File Not Found Error during processing: {e}", exc_info=True)
        err_msg = f"Required file not found: {e}"
        if job: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise FileNotFoundError(err_msg) from e
    except (ValueError, yaml.YAMLError) as e:
        logger.error(f"[Job {task_id}] Value Error or YAML Parsing Error: {e}", exc_info=True)
        err_msg = f"Invalid data or configuration: {e}"
        if job: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise ValueError(err_msg) from e
    except RuntimeError as e:
        logger.error(f"[Job {task_id}] Runtime Error during processing: {e}", exc_info=True)
        err_msg = str(e)
        if job: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during processing job: {e}")
        err_msg = "An unexpected internal error occurred. Please check application logs."
        if job:
            try: job.status = PublishingJob.Status.FAILED; job.error_message = err_msg; job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err: logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after error: {db_err}", exc_info=True)
        raise


# confirm_and_publish_job (Includes diagnostic logging update)
def confirm_and_publish_job(task_id: uuid.UUID) -> Dict[str, Any]:
    """
    Handles Request 2: Confirms job, builds payload, publishes draft, handles 40007 retry.
    Includes updating cache on successful thumbnail re-upload during retry.
    """
    job: Optional[PublishingJob] = None
    access_token: Optional[str] = None

    try:
        logger.info(f"[Job {task_id}] Attempting to confirm and publish job.")
        job = PublishingJob.objects.get(pk=task_id)

        # !!!!!!!!!! START DIAGNOSTIC LOGGING (DATABASE) !!!!!!!!!!
        try:
            # Access metadata safely using .get()
            metadata_from_db = job.metadata or {} # Ensure it's a dict
            title_from_db = metadata_from_db.get('title', 'N/A')
            digest_from_db = metadata_from_db.get('digest', 'N/A') # Assuming digest might also have issues
            logger.debug(f"[Job {task_id}] Checking metadata retrieved FROM DB:")
            logger.debug(f"[Job {task_id}]   Title='{title_from_db}' (Type: {type(title_from_db)})")
            logger.debug(f"[Job {task_id}]   Digest='{digest_from_db}' (Type: {type(digest_from_db)})")
            # Log the raw metadata dict as well for comparison
            logger.debug(f"[Job {task_id}]   Raw job.metadata from DB: {job.metadata}")
        except Exception as log_ex:
            logger.error(f"[Job {task_id}] Error logging metadata from DB: {log_ex}")
        # !!!!!!!!!! END DIAGNOSTIC LOGGING (DATABASE) !!!!!!!!!!

        # Pre-flight Checks
        if job.status != PublishingJob.Status.PREVIEW_READY:
            logger.warning(f"[Job {task_id}] Cannot publish job with status '{job.get_status_display()}'. Required status: PREVIEW_READY.")
            raise ValueError(f"Job not ready for publishing (Current Status: {job.get_status_display()}).")
        if not job.metadata: raise ValueError("Cannot publish job: Metadata is missing.")
        if not job.thumb_media_id: raise ValueError("Cannot publish job: WeChat thumbnail ID is missing.")
        if "title" not in job.metadata or not job.metadata["title"]:
             raise ValueError("Cannot publish job: 'title' is missing in metadata.")

        logger.info(f"[Job {task_id}] Job status is PREVIEW_READY. Proceeding.")
        job.status = PublishingJob.Status.PUBLISHING
        job.save(update_fields=JOB_STATUS_UPDATE_FIELDS)

        # WeChat Setup
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret: raise ValueError("WeChat credentials not configured.")
        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        if not access_token: raise RuntimeError("Failed to get WeChat access token for publishing.")
        logger.debug(f"[Job {task_id}] Retrieved WeChat access token for publishing.")

        # Build Payload
        placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT or "<p>Content pending.</p>"
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

        # Call WeChat API (Add Draft) with Retry and Cache Update
        final_media_id: Optional[str] = None
        max_retries: int = 1
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

            # !!!!!!!!!! START OF UPDATED EXCEPTION BLOCK !!!!!!!!!!
            except Exception as e:
                # --- Start Diagnostic Logging ---
                logger.error(f"[Job {task_id}] Caught exception during add_draft: {type(e).__name__} - {e}", exc_info=False)
                try:
                    # Try to log attributes common for API errors
                    logger.error(f"[Job {task_id}] Exception details: args={e.args}")
                    if hasattr(e, 'errcode'):
                        logger.error(f"[Job {task_id}]   errcode attribute: {getattr(e, 'errcode')}")
                    if hasattr(e, 'code'):
                        logger.error(f"[Job {task_id}]   code attribute: {getattr(e, 'code')}")
                    if hasattr(e, 'response'):
                        # Log response carefully, it might be large or sensitive
                        response_attr = getattr(e, 'response')
                        logger.error(f"[Job {task_id}]   response attribute type: {type(response_attr)}")
                        # Example: log only keys if it's a dict, or first 100 chars if string
                        if isinstance(response_attr, dict):
                             logger.error(f"[Job {task_id}]   response keys: {list(response_attr.keys())}")
                        elif isinstance(response_attr, str):
                             logger.error(f"[Job {task_id}]   response (first 100 chars): {response_attr[:100]}")
                        else:
                             logger.error(f"[Job {task_id}]   response attribute: {response_attr}")

                    logger.error(f"[Job {task_id}] Full dir(e): {dir(e)}")
                except Exception as log_err:
                    logger.error(f"[Job {task_id}] Error during diagnostic logging: {log_err}")
                # --- End Diagnostic Logging ---

                # --- Error Identification (Keep original check for now, adjust based on logs) ---
                # TODO: Adjust this check based on the actual attributes logged for the 40007 error
                # Check if it's a RuntimeError and the message contains the 40007 code
                is_thumb_error = isinstance(e, RuntimeError) and '40007' in str(e)

                if is_thumb_error and attempt <= max_retries:
                    logger.warning(f"[Job {task_id}] Identified as thumb error (Code 40007) on attempt {attempt}. Attempting re-upload...", exc_info=False) # Added log

                    # --- Retry Logic (Re-upload Thumbnail - Includes previous fix) ---
                    logger.info(f"[Job {task_id}] --- Starting Thumb Re-upload Process ---")
                    if not job.original_cover_image_path:
                        logger.error(f"[Job {task_id}] Cannot retry thumb upload: original cover image path not found.") # More specific log
                        raise ValueError("Cannot retry thumb upload: original cover image path not found in job record.")
                    local_cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
                    if not local_cover_path_abs.is_file():
                        logger.error(f"[Job {task_id}] Cannot retry thumb upload: local cover file not found at {local_cover_path_abs}") # More specific log
                        raise FileNotFoundError(f"Cannot retry thumb upload: local cover file not found at {local_cover_path_abs}")

                    # Get fresh token WITHOUT force_refresh
                    logger.debug(f"[Job {task_id}] Getting fresh access token for retry...")
                    access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
                    if not access_token:
                        logger.error(f"[Job {task_id}] Failed to get fresh WeChat token for retry.") # More specific log
                        raise RuntimeError("Failed to get fresh WeChat token for retry.")
                    logger.debug(f"[Job {task_id}] Retrieved fresh access token for retry.")
                    logger.info(f"[Job {task_id}] Re-uploading thumbnail from: {local_cover_path_abs}")

                    # Re-upload using the API
                    new_thumb_media_id = None # Initialize before try
                    try:
                        new_thumb_media_id = wechat_api.upload_thumb_media(
                            access_token=access_token, thumb_path=local_cover_path_abs, base_url=base_url
                        )
                    except Exception as upload_retry_err:
                        logger.error(f"[Job {task_id}] Exception during thumbnail re-upload: {upload_retry_err}", exc_info=True)
                        # Raise a new error indicating failure during retry upload
                        raise RuntimeError(f"Failed during thumbnail re-upload attempt: {upload_retry_err}") from upload_retry_err

                    if not new_thumb_media_id:
                        logger.error(f"[Job {task_id}] Failed to re-upload permanent thumbnail during retry (API returned no ID).") # More specific log
                        raise RuntimeError("Failed to re-upload permanent thumbnail during retry (API returned no ID).")
                    logger.info(f"[Job {task_id}] New thumb media ID obtained: {new_thumb_media_id}.")

                    # Update DB and Cache
                    job.thumb_media_id = new_thumb_media_id
                    current_thumb_media_id = new_thumb_media_id # Update variable for next loop/payload
                    job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
                    logger.info(f"[Job {task_id}] Updated job record with new thumb_media_id: {new_thumb_media_id}") # Log DB update

                    cover_image_hash = calculate_file_hash(local_cover_path_abs, algorithm='sha256')
                    if cover_image_hash:
                        cache_key = f"wechat_thumb_sha256_{cover_image_hash}"
                        cache_timeout = settings.WECHAT_PERMANENT_MEDIA_CACHE_TIMEOUT
                        cache.set(cache_key, new_thumb_media_id, timeout=cache_timeout)
                        logger.info(f"[Job {task_id}] Updated cache with new valid thumbnail Media ID (Key: {cache_key}).")
                    else:
                         logger.warning(f"[Job {task_id}] Could not calculate hash for cover image during retry, cache not updated for new thumb ID.")

                    # Re-build payload with the new thumb_media_id
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
                        raise ValueError(f"Payload re-building failed during retry: {build_err}") from build_err # Re-raise specific error

                    logger.info(f"[Job {task_id}] --- Finished Thumb Re-upload Process ---")
                    continue # Retry the add_draft call

                else:
                    # Error is not the specific 40007, OR retries exhausted, OR error occurred during retry steps
                    logger.error(f"[Job {task_id}] Condition for retry not met or retry failed. is_thumb_error={is_thumb_error}, attempt={attempt}, max_retries={max_retries}", exc_info=False)
                    err_msg_publish = f"Failed to publish draft to WeChat after {attempt} attempt(s). Last error: {e}"
                    raise RuntimeError(err_msg_publish) from e
            # !!!!!!!!!! END OF UPDATED EXCEPTION BLOCK !!!!!!!!!!

        # Common Success Path
        if not final_media_id:
             logger.error(f"[Job {task_id}] Logic error: Publishing loop finished but final WeChat media ID was not obtained.")
             raise RuntimeError("Publishing finished but final WeChat media ID was not obtained.")
        job.status = PublishingJob.Status.PUBLISHED
        job.wechat_media_id = final_media_id
        job.error_message = None
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

    # Exception Handling (Unchanged)
    except ObjectDoesNotExist:
        logger.warning(f"Publishing job with task_id {task_id} not found in database.")
        raise
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"[Job {task_id}] Pre-condition or data error during publish: {e}", exc_info=True)
        err_msg = f"Publishing pre-check failed: {e}"
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
             job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
             job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise ValueError(err_msg) from e
    except RuntimeError as e:
        logger.error(f"[Job {task_id}] Runtime error during publish operation: {e}", exc_info=True)
        err_msg = str(e)
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
             job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
             job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during confirmation/publishing: {e}")
        err_msg = "An unexpected internal error occurred during publishing."
        if job and job.status not in [PublishingJob.Status.PUBLISHED, PublishingJob.Status.FAILED]:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                 logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status after publishing error: {db_err}", exc_info=True)
        raise