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

from .models import PublishingJob

# --- Import publishing engine components ---
try:
    from publishing_engine.core import metadata_reader, html_processor, payload_builder
    from publishing_engine.wechat import auth
    from publishing_engine.wechat import api as wechat_api
    # Attempt to import specific API errors if they exist
    # !!! IMPORTANT: If your actual wechat_api module provides a specific error class
    # (e.g., WeChatAPIError) import it here and use it in the 'except' block below.
    # from publishing_engine.wechat.exceptions import WeChatAPIError # Example
    logger = logging.getLogger(__name__)
    logger.info("Successfully imported modules from publishing_engine.")
except ImportError as e:
    logger.exception("Failed to import critical 'publishing_engine' modules.", exc_info=True)
    raise

# --- Helper Functions (unchanged from previous correct version) ---

def _save_uploaded_file_locally(file_obj: UploadedFile, subfolder: str = "") -> Path:
    """
    Saves an uploaded file locally with a unique name and returns its absolute Path object.
    Args: file_obj, subfolder
    Returns: Absolute Path object of the saved file.
    Raises: RuntimeError on failure.
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
        relative_path = Path(subfolder) / unique_filename
        logger.info(f"File '{file_obj.name}' saved locally to absolute path: {local_save_path_abs} (relative: {relative_path})")
        return local_save_path_abs
    except IOError as e:
        logger.exception(f"IOError saving uploaded file '{file_obj.name}' locally.")
        raise RuntimeError(f"Failed to save '{file_obj.name}' locally due to file system error.") from e
    except Exception as e:
        logger.exception(f"Unexpected error saving uploaded file '{file_obj.name}' locally.")
        raise RuntimeError(f"Unexpected failure saving '{file_obj.name}' locally.") from e

def _generate_preview_file(full_html_content: str, task_id: uuid.UUID) -> str:
    """
    Saves the FULL HTML content to a preview file locally and returns its relative path as a string.
    Args: full_html_content, task_id
    Returns: Relative path (string) of the saved preview file.
    Raises: RuntimeError on failure.
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
        logger.info(f"Preview file saved successfully to relative path: {preview_path_rel}")
        return str(preview_path_rel)
    except IOError as e:
        logger.exception(f"IOError writing preview file for task {task_id}")
        raise RuntimeError(f"Failed to write preview file {task_id}.html due to file system error.") from e
    except Exception as e:
        logger.exception(f"Unexpected error writing preview file for task {task_id}")
        raise RuntimeError(f"Unexpected failure writing preview file {task_id}.html.") from e

# --- Main Service Functions ---

# Constants for update_fields (unchanged)
JOB_STATUS_UPDATE_FIELDS = ['status', 'updated_at']
JOB_ERROR_UPDATE_FIELDS = ['status', 'error_message', 'updated_at']
JOB_PATHS_UPDATE_FIELDS = ['original_markdown_path', 'original_cover_image_path', 'updated_at']
JOB_THUMB_UPDATE_FIELDS = ['thumb_media_id', 'updated_at']
JOB_METADATA_UPDATE_FIELDS = ['metadata', 'updated_at']
JOB_PREVIEW_UPDATE_FIELDS = ['preview_html_path', 'status', 'updated_at']
JOB_PUBLISH_SUCCESS_FIELDS = ['status', 'wechat_media_id', 'error_message', 'published_at', 'updated_at']

# start_processing_job (unchanged from previous correct version)
def start_processing_job(
    markdown_file: UploadedFile,
    cover_image: UploadedFile,
    content_images: List[UploadedFile]
) -> Dict[str, Any]:
    """
    Handles Request 1: Saves files, uploads cover thumb, processes Markdown via callback, generates preview.
    (Docstring and implementation unchanged from previous correct version)
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

        # --- Step 1-3: Save Files Locally ---
        local_md_path_abs = _save_uploaded_file_locally(markdown_file, subfolder='uploads/markdown')
        job.original_markdown_path = str(local_md_path_abs.relative_to(settings.MEDIA_ROOT))
        local_cover_path_abs = _save_uploaded_file_locally(cover_image, subfolder='uploads/cover_images')
        job.original_cover_image_path = str(local_cover_path_abs.relative_to(settings.MEDIA_ROOT))
        logger.info(f"[Job {task_id}] Saved Markdown to '{local_md_path_abs.name}'. Saved Cover locally to '{local_cover_path_abs.name}'.")
        logger.info(f"[Job {task_id}] Saving {len(content_images)} content images locally...")
        saved_content_image_paths: List[Path] = []
        for image_file in content_images:
            path = _save_uploaded_file_locally(image_file, subfolder='uploads/content_images')
            saved_content_image_paths.append(path)
        logger.info(f"[Job {task_id}] Saved {len(saved_content_image_paths)} content images locally.")
        job.save(update_fields=JOB_PATHS_UPDATE_FIELDS)
        logger.debug(f"[Job {task_id}] Saved original file paths to job record.")

        # --- Step 4: WeChat Setup & Thumbnail Upload ---
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret:
            raise ValueError("WECHAT_APP_ID and/or WECHAT_SECRET are not configured in settings.")
        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        if not access_token:
             raise RuntimeError("Failed to retrieve WeChat access token.")
        logger.debug(f"[Job {task_id}] Retrieved WeChat access token.")
        logger.info(f"[Job {task_id}] Uploading PERMANENT WeChat thumbnail from local path: '{local_cover_path_abs}'")
        if not local_cover_path_abs or not local_cover_path_abs.is_file():
            raise FileNotFoundError(f"Local cover image for WeChat permanent upload not found at expected path: {local_cover_path_abs}")
        permanent_thumb_media_id = wechat_api.upload_thumb_media(
            access_token=access_token, thumb_path=local_cover_path_abs, base_url=base_url
        )
        if not permanent_thumb_media_id:
            raise RuntimeError("Failed to upload permanent thumbnail to WeChat (received no media ID). Check API logs for details.")
        job.thumb_media_id = permanent_thumb_media_id
        job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
        logger.info(f"[Job {task_id}] PERMANENT WeChat thumbnail uploaded. Media ID: {permanent_thumb_media_id}")

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
        except FileNotFoundError as file_err:
             logger.error(f"[Job {task_id}] Metadata reader could not find file {local_md_path_abs}: {file_err}", exc_info=True)
             raise
        job.metadata = metadata_dict
        job.save(update_fields=JOB_METADATA_UPDATE_FIELDS)
        logger.info(f"[Job {task_id}] Metadata extracted successfully.")
        logger.debug(f"[Job {task_id}] Extracted metadata keys: {list(metadata_dict.keys())}")

        # --- Step 5.5: Callback Definition ---
        wechat_url_cache: Dict[Path, Optional[str]] = {}
        def _wechat_image_uploader_callback(image_local_path: Path) -> Optional[str]:
            """Inner callback function to upload images found during HTML processing."""
            nonlocal access_token, base_url, wechat_url_cache
            if not access_token or not base_url:
                 logger.error(f"[Job {task_id}] Callback invoked without valid access_token or base_url.")
                 return None
            try:
                resolved_path = image_local_path.resolve(strict=True)
            except FileNotFoundError:
                logger.error(f"[Job {task_id}] Callback cannot resolve/find image referenced in Markdown: {image_local_path}")
                wechat_url_cache[image_local_path] = None
                return None
            except Exception as resolve_err:
                logger.error(f"[Job {task_id}] Error resolving image path '{image_local_path}': {resolve_err}")
                wechat_url_cache[image_local_path] = None
                return None

            if resolved_path in wechat_url_cache:
                cached_url = wechat_url_cache[resolved_path]
                if cached_url is not None:
                    logger.debug(f"[Job {task_id}] Cache hit for {resolved_path.name}")
                    return cached_url
                else:
                    logger.warning(f"[Job {task_id}] Cache hit (failed): Skipping upload for {resolved_path.name}")
                    return None

            logger.debug(f"[Job {task_id}] Cache miss: Attempting upload for image: {resolved_path.name}")
            if not resolved_path.is_file():
                 logger.error(f"[Job {task_id}] Image file check failed post-resolve (should not happen): {resolved_path}")
                 wechat_url_cache[resolved_path] = None
                 return None
            try:
                wechat_url = wechat_api.upload_content_image(
                    access_token=access_token, image_path=resolved_path, base_url=base_url
                )
                if wechat_url:
                    logger.info(f"[Job {task_id}] Uploaded via callback: {resolved_path.name} -> {wechat_url}")
                    wechat_url_cache[resolved_path] = wechat_url
                    return wechat_url
                else:
                    logger.error(f"[Job {task_id}] Callback received no URL from upload_content_image for: {resolved_path.name}")
                    wechat_url_cache[resolved_path] = None
                    return None
            except Exception as e:
                logger.exception(f"[Job {task_id}] Unexpected error during callback upload for {resolved_path.name}: {e}")
                wechat_url_cache[resolved_path] = None
                return None

        # --- Step 6: Process HTML Fragment ---
        logger.info(f"[Job {task_id}] Processing HTML fragment from Markdown body using uploader callback...")
        if not local_md_path_abs:
             raise FileNotFoundError("Markdown file path missing before HTML processing.")
        if markdown_body_content is None:
             logger.warning(f"[Job {task_id}] Markdown body content is None. Preview might be blank.")
             markdown_body_content = ""

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

        # --- Step 7: Wrap Full HTML Document ---
        logger.info(f"[Job {task_id}] Wrapping HTML fragment in full document structure for preview.")
        preview_title = metadata_dict.get("title", f"Preview - {task_id}")
        full_html_for_preview = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{preview_title}</title>
</head>
<body>
    {processed_html_fragment}
</body>
</html>"""

        # --- Step 8: Generate Preview File & Finalize ---
        preview_path_rel_str = _generate_preview_file(full_html_for_preview, task_id)
        job.preview_html_path = preview_path_rel_str
        job.status = PublishingJob.Status.PREVIEW_READY
        job.error_message = None
        job.save(update_fields=JOB_PREVIEW_UPDATE_FIELDS + ['error_message'])

        media_url = settings.MEDIA_URL.rstrip('/') + '/'
        preview_url_path = preview_path_rel_str.replace(os.path.sep, '/').lstrip('/')
        preview_url = media_url + preview_url_path

        logger.info(f"[Job {task_id}] Preview ready. Accessible at: {preview_url}")
        return {"task_id": job.task_id, "preview_url": preview_url}

    # --- Exception Handling (unchanged from previous correct version) ---
    except FileNotFoundError as e:
        logger.error(f"[Job {task_id}] File Not Found Error during processing: {e}", exc_info=True)
        err_msg = f"Required file not found: {e}"
        if job:
            job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
            job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise FileNotFoundError(err_msg) from e
    except (ValueError, yaml.YAMLError) as e:
        logger.error(f"[Job {task_id}] Value Error or YAML Parsing Error: {e}", exc_info=True)
        err_msg = f"Invalid data or configuration: {e}"
        if job:
            job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
            job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise ValueError(err_msg) from e
    except RuntimeError as e:
        logger.error(f"[Job {task_id}] Runtime Error during processing: {e}", exc_info=True)
        err_msg = f"Operation failed: {e}"
        if job:
            job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
            job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during processing job: {e}")
        err_msg = f"An unexpected internal error occurred. Please check application logs."
        if job:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status to FAILED after initial error: {db_err}", exc_info=True)
        raise


def confirm_and_publish_job(task_id: uuid.UUID) -> Dict[str, Any]:
    """
    Handles Request 2: Confirms job, builds payload (placeholder content), publishes draft to WeChat.
    Includes logic to retry thumbnail upload if initial publish fails due to expired media ID (40007).
    (Docstring unchanged)
    """
    job: Optional[PublishingJob] = None
    access_token: Optional[str] = None

    try:
        logger.info(f"[Job {task_id}] Attempting to confirm and publish job.")
        job = PublishingJob.objects.get(pk=task_id)

        # --- Pre-flight Checks (unchanged) ---
        if job.status != PublishingJob.Status.PREVIEW_READY:
            logger.warning(f"[Job {task_id}] Cannot publish job with status '{job.get_status_display()}'. Required status: PREVIEW_READY.")
            raise ValueError(f"Job not ready for publishing (Current Status: {job.get_status_display()}).")
        if not job.metadata:
            logger.error(f"[Job {task_id}] Cannot publish job: Metadata is missing from job record.")
            raise ValueError("Cannot publish job: Metadata is missing.")
        if not job.thumb_media_id:
            logger.error(f"[Job {task_id}] Cannot publish job: Permanent WeChat thumb_media_id is missing.")
            raise ValueError("Cannot publish job: WeChat thumbnail ID is missing.")

        logger.info(f"[Job {task_id}] Job status is PREVIEW_READY. Proceeding with publishing placeholder draft.")
        job.status = PublishingJob.Status.PUBLISHING
        job.save(update_fields=JOB_STATUS_UPDATE_FIELDS)

        # --- WeChat Setup (unchanged) ---
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret:
            raise ValueError("WECHAT_APP_ID and/or WECHAT_SECRET are not configured in settings.")
        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        if not access_token:
             raise RuntimeError("Failed to retrieve WeChat access token for publishing.")
        logger.debug(f"[Job {task_id}] Retrieved WeChat access token for publishing.")

        # --- Build Payload (unchanged) ---
        placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT or "<p>Please paste formatted content here.</p>"
        logger.info(f"[Job {task_id}] Building initial draft payload with thumb_media_id: {job.thumb_media_id} and placeholder content.")
        current_thumb_media_id = job.thumb_media_id
        try:
            article_payload = payload_builder.build_draft_payload(
                metadata=job.metadata,
                html_content=placeholder_content,
                thumb_media_id=current_thumb_media_id
            )
            final_draft_payload = {"articles": [article_payload]}
            logger.debug(f"[Job {task_id}] Payload built successfully.")
        except (KeyError, ValueError) as build_err:
             logger.error(f"[Job {task_id}] Failed to build draft payload: {build_err}", exc_info=True)
             raise ValueError(f"Payload building failed: {build_err}") from build_err

        # --- Call WeChat API (Add Draft) with Retry for Expired Media ID ---
        final_media_id: Optional[str] = None
        max_retries: int = 1
        attempt: int = 0
        while attempt <= max_retries:
            attempt += 1
            try:
                logger.info(f"[Job {task_id}] Attempting WeChat 'add_draft' API call (Try {attempt}/{max_retries + 1})")
                final_media_id = wechat_api.add_draft(
                    access_token=access_token,
                    draft_payload=final_draft_payload,
                    base_url=base_url
                )
                logger.info(f"[Job {task_id}] Successfully published draft placeholder (Try {attempt}). Draft Media ID: {final_media_id}")
                break # Success

            # *** FIX START: Modify exception handling for retry ***
            # Check for specific API error types first, if available from the library.
            # except WeChatAPIError as e: # Example if a specific error class exists
            #     logger.warning(f"[Job {task_id}] WeChat API Error on attempt {attempt}: Code={e.errcode}, Msg={e.errmsg}")
            #     is_thumb_error = hasattr(e, 'errcode') and e.errcode == 40007
            #     if is_thumb_error and attempt <= max_retries:
            #          # ... (retry logic below) ...
            #          continue
            #     else: # Not the specific error or retries exhausted
            #          logger.error(f"[Job {task_id}] Non-retriable WeChat API error or max retries exceeded.")
            #          raise RuntimeError(f"WeChat API Error after {attempt} attempt(s): {e.errcode} - {e.errmsg}") from e
            except Exception as e:
                # Check if the exception *is* the type we expect for 40007 *and* has the code.
                # This relies on the test raising MockWeChatAPIError with errcode set.
                # For production, adapt this to check the actual exception type/attributes from wechat_api.
                is_thumb_error = hasattr(e, 'errcode') and getattr(e, 'errcode') == 40007

                if is_thumb_error and attempt <= max_retries:
                    logger.warning(f"[Job {task_id}] Caught potential thumb media ID expiry error (Code 40007) on attempt {attempt}. Details: {e}. Attempting re-upload...", exc_info=False)

                    # --- Retry Logic (identical to previous version) ---
                    logger.info(f"[Job {task_id}] --- Starting Thumb Re-upload Process ---")
                    if not job.original_cover_image_path:
                        logger.error(f"[Job {task_id}] Cannot retry thumb upload: Original cover image path is missing.")
                        raise ValueError("Cannot retry thumb upload: original cover image path not found in job record.")
                    local_cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
                    if not local_cover_path_abs.is_file():
                        logger.error(f"[Job {task_id}] Cannot retry thumb upload: Local cover file not found: {local_cover_path_abs}")
                        raise FileNotFoundError(f"Cannot retry thumb upload: local cover file not found at {local_cover_path_abs}")
                    logger.info(f"[Job {task_id}] Re-fetching access token for retry.")
                    access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
                    if not access_token:
                         raise RuntimeError("Failed to retrieve fresh WeChat access token for retry.")
                    logger.debug(f"[Job {task_id}] Retrieved fresh access token for retry.")
                    logger.info(f"[Job {task_id}] Re-uploading thumbnail from: {local_cover_path_abs}")
                    new_thumb_media_id = wechat_api.upload_thumb_media(
                        access_token=access_token, thumb_path=local_cover_path_abs, base_url=base_url
                    )
                    if not new_thumb_media_id:
                        raise RuntimeError("Failed to re-upload permanent thumbnail during retry.")
                    logger.info(f"[Job {task_id}] New thumb media ID obtained: {new_thumb_media_id}. Updating job record.")
                    job.thumb_media_id = new_thumb_media_id
                    current_thumb_media_id = new_thumb_media_id
                    job.save(update_fields=JOB_THUMB_UPDATE_FIELDS)
                    logger.info(f"[Job {task_id}] Re-building payload with new thumb media ID for retry.")
                    try:
                        article_payload = payload_builder.build_draft_payload(
                            metadata=job.metadata,
                            html_content=placeholder_content,
                            thumb_media_id=current_thumb_media_id
                        )
                        final_draft_payload = {"articles": [article_payload]}
                        logger.debug(f"[Job {task_id}] Payload rebuilt successfully for retry.")
                    except (KeyError, ValueError) as build_err:
                        logger.error(f"[Job {task_id}] Failed to re-build draft payload during retry: {build_err}", exc_info=True)
                        raise ValueError(f"Payload re-building failed during retry: {build_err}") from build_err
                    logger.info(f"[Job {task_id}] --- Finished Thumb Re-upload Process ---")
                    # --- End Retry Logic ---
                    continue # Retry the add_draft call
                else:
                    # Error is not the specific 40007 error we handle, or retries exhausted
                    logger.error(f"[Job {task_id}] Non-retriable error or max retries ({max_retries}) exceeded during 'add_draft'. Last error type: {type(e).__name__}", exc_info=True)
                    raise RuntimeError(f"Failed to publish draft to WeChat after {attempt} attempt(s). Last error: {e}") from e
            # *** FIX END ***

        # --- Common Success Path (unchanged) ---
        if not final_media_id:
             logger.error(f"[Job {task_id}] Publishing process seemingly succeeded, but final WeChat media ID was not obtained.")
             raise RuntimeError("Publishing finished but final WeChat media ID was not obtained.")
        job.status = PublishingJob.Status.PUBLISHED
        job.wechat_media_id = final_media_id
        job.error_message = None
        job.published_at = timezone.now()
        job.save(update_fields=JOB_PUBLISH_SUCCESS_FIELDS)
        status_display = job.get_status_display() if hasattr(job, 'get_status_display') else job.status
        logger.info(f"[Job {task_id}] Successfully published placeholder draft to WeChat. Final Status: {status_display}, WeChat Media ID: {final_media_id}")
        return {
            "task_id": job.task_id,
            "status": status_display,
            "message": "Article placeholder published to WeChat drafts successfully. Please copy the formatted content from the preview page and paste it into the WeChat editor to complete the process.",
            "wechat_media_id": final_media_id
        }

    # --- Exception Handling (unchanged from previous correct version) ---
    except ObjectDoesNotExist:
        logger.warning(f"Publishing job with task_id {task_id} not found in database.")
        raise
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"[Job {task_id}] Pre-condition or data error during publish: {e}", exc_info=True)
        err_msg = f"Publishing pre-check failed: {e}"
        if job and job.status != PublishingJob.Status.PUBLISHED:
             job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
             job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise ValueError(err_msg) from e
    except RuntimeError as e:
        logger.error(f"[Job {task_id}] Runtime error during publish operation: {e}", exc_info=True)
        err_msg = f"Publishing operation failed: {e}"
        if job and job.status != PublishingJob.Status.PUBLISHED:
             job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
             job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        logger.exception(f"[Job {task_id}] Unexpected error during confirmation/publishing: {e}")
        err_msg = f"An unexpected internal error occurred during publishing. Please check application logs."
        if job and job.status != PublishingJob.Status.PUBLISHED:
            try:
                job.status = PublishingJob.Status.FAILED; job.error_message = err_msg
                job.save(update_fields=JOB_ERROR_UPDATE_FIELDS)
            except Exception as db_err:
                 logger.critical(f"[Job {task_id}] CRITICAL: Failed to update job status to FAILED after publishing error: {db_err}", exc_info=True)
        raise