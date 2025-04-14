# /Users/junluo/Documents/wechat_publisher_web/publisher/services.py
"""
Contains the business logic for processing and publishing WeChat articles.
Orchestrates workflow, calls publishing_engine, interacts with models, handles files.
"""
import os
import uuid
import json
import logging
from pathlib import Path
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
import yaml

from .models import PublishingJob
try:
    from publishing_engine.core import metadata_reader, html_processor, payload_builder
    from publishing_engine.wechat import auth, api as wechat_api
    # MediaManager might still be needed for content images
    from publishing_engine.wechat.media_manager import MediaManager
    # Import the actual function name from api.py
    from publishing_engine.wechat.api import upload_thumb_media, upload_content_image, add_draft # Example if needed
    logger = logging.getLogger(__name__)
    logger.info("Successfully imported modules from publishing_engine.")
except ImportError as e:
    logger.error("Failed to import publishing_engine: %s", e, exc_info=True)
    raise ImportError("Could not import publishing_engine. Ensure it's installed and accessible.") from e
except ModuleNotFoundError as e:
    logger.error("Missing module in publishing_engine?: %s", e, exc_info=True)
    raise ImportError(f"Could not import required module from publishing_engine: {e}") from e

# --- Helper Functions --- ( _save_uploaded_file, _generate_preview_file remain the same)
def _save_uploaded_file(file_obj, subfolder="") -> str:
    try:
        file_ext = os.path.splitext(file_obj.name)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        save_path = os.path.join(subfolder, unique_filename)
        actual_path = default_storage.save(save_path, file_obj)
        logger.info("File saved successfully to relative path: %s", actual_path)
        return actual_path
    except Exception as e:
        logger.exception("Failed to save uploaded file '%s'", file_obj.name)
        raise

def _generate_preview_file(html_content: str, task_id: uuid.UUID) -> str:
    try:
        preview_filename = f"{task_id}.html"
        preview_path_rel = os.path.join('previews', preview_filename)
        preview_dir_abs = Path(settings.MEDIA_ROOT) / 'previews'
        preview_file_abs = preview_dir_abs / preview_filename
        preview_dir_abs.mkdir(parents=True, exist_ok=True)
        logger.info("Attempting to save preview file to: %s", preview_file_abs)
        with open(preview_file_abs, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info("Preview file saved successfully to relative path: %s", preview_path_rel)
        return preview_path_rel
    except IOError as e:
        logger.exception("Failed to write preview file for task %s", task_id)
        raise

# --- Main Service Functions ---

def start_processing_job(markdown_file, cover_image, content_images_dir_abs: Path):
    """
    Handles Request 1: Upload files (incl. PERMANENT thumb), process Markdown, generate preview.
    """
    job = None
    task_id = uuid.uuid4()
    try:
        logger.info(f"Starting new processing job for task ID: {task_id}")
        job = PublishingJob.objects.create(task_id=task_id, status=PublishingJob.Status.PENDING)
        job.status = PublishingJob.Status.PROCESSING
        job.save(update_fields=['status', 'updated_at'])

        markdown_path_rel = _save_uploaded_file(markdown_file, subfolder='uploads/markdown')
        cover_image_path_rel = _save_uploaded_file(cover_image, subfolder='uploads/cover_images')

        job.original_markdown_path = markdown_path_rel
        job.original_cover_image_path = cover_image_path_rel
        job.save(update_fields=['original_markdown_path', 'original_cover_image_path', 'updated_at'])

        markdown_path_abs = Path(settings.MEDIA_ROOT) / markdown_path_rel
        cover_image_path_abs = Path(settings.MEDIA_ROOT) / cover_image_path_rel

        # WeChat Setup & PERMANENT Thumbnail Upload
        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret: raise ValueError("WECHAT_APP_ID/SECRET not configured.")

        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)

        # *** Use the actual function name from api.py for permanent thumbnail upload ***
        logger.info(f"Uploading PERMANENT thumbnail from: {cover_image_path_abs}")
        permanent_thumb_media_id = wechat_api.upload_thumb_media( # <-- CORRECTED function name
            access_token=access_token,
            thumb_path=cover_image_path_abs,
            base_url=base_url
        )
        if not permanent_thumb_media_id:
             raise RuntimeError("Failed to upload permanent thumbnail, received no media ID.")

        job.thumb_media_id = permanent_thumb_media_id # Store the permanent ID
        job.save(update_fields=['thumb_media_id', 'updated_at'])
        logger.info(f"PERMANENT thumbnail uploaded. Media ID: {permanent_thumb_media_id} for task: {task_id}")

        # --- Content Image Upload (Still uses MediaManager/Temporary URL upload) ---
        cache_path = getattr(settings, 'WECHAT_MEDIA_CACHE_PATH', None)
        if cache_path: Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Using MediaManager with cache path: {cache_path} for content images")
        manager = MediaManager(cache_file_path=cache_path) # Keep manager for content images

        def image_uploader_callback(local_image_path: Path) -> str:
            try:
                logger.debug(f"Image uploader callback processing: {local_image_path}")
                if not local_image_path.is_absolute():
                     local_image_path = content_images_dir_abs / local_image_path
                # This uses /cgi-bin/media/uploadimg which is correct for content images
                return manager.get_or_upload_content_image_url(
                    access_token=access_token,
                    image_path=local_image_path,
                    base_url=base_url
                )
            except Exception as img_upload_e:
                logger.error("Failed uploading image via callback %s: %s", local_image_path, img_upload_e, exc_info=True)
                return ""

        # --- Metadata Extraction ---
        logger.info(f"Extracting metadata and body content from {markdown_path_abs}")
        try:
            metadata_dict, markdown_body_content = metadata_reader.extract_metadata_and_content(markdown_path_abs)
        except (ValueError, yaml.YAMLError) as meta_error:
             logger.error(f"Failed to extract valid metadata/content from {markdown_path_abs}: {meta_error}")
             job.status = PublishingJob.Status.FAILED # Set status before raising
             job.error_message = f"Metadata/Format Error in Markdown: {meta_error}"
             job.save(update_fields=['status', 'error_message', 'updated_at'])
             raise ValueError(f"Metadata/Format Error in Markdown: {meta_error}") from meta_error

        job.metadata = metadata_dict
        job.save(update_fields=['metadata', 'updated_at'])
        logger.info("Metadata extracted: %s", metadata_dict if metadata_dict else "None")

        # --- Process HTML ---
        logger.info("Processing HTML from MARKDOWN BODY content...")
        processed_html = html_processor.process_html_content(
            md_content=markdown_body_content,
            css_path=str(settings.PREVIEW_CSS_FILE_PATH), # Ensure this file exists
            content_images_dir=content_images_dir_abs,
            image_uploader=image_uploader_callback
        )

        # --- Generate Preview File ---
        preview_path_rel = _generate_preview_file(processed_html, task_id)
        job.preview_html_path = preview_path_rel
        job.status = PublishingJob.Status.PREVIEW_READY
        job.save(update_fields=['preview_html_path', 'status', 'updated_at'])

        preview_url = settings.MEDIA_URL + preview_path_rel.replace(os.path.sep, '/').lstrip('/')
        logger.info("Preview URL: %s for task: %s", preview_url, task_id)
        return {"task_id": job.task_id, "preview_url": preview_url}

    # --- Exception Handling ---
    except FileNotFoundError as e:
         logger.error(f"File not found during processing job {task_id}: {e}", exc_info=True)
         if job: job.status = PublishingJob.Status.FAILED; job.error_message = f"File Not Found Error: {e}"; job.save(update_fields=['status', 'error_message', 'updated_at'])
         if "style.css" in str(e): raise ValueError(f"Configuration Error: Preview CSS not found at specified path.") from e
         # Re-raise specific FileNotFoundError if it's the thumbnail during upload
         if "Thumbnail image not found" in str(e): raise
         # Otherwise, re-raise generic FileNotFoundError
         raise FileNotFoundError(f"Required file not found during processing: {e}") from e
    except (ValueError, yaml.YAMLError) as e:
         # Error status should already be set within the try block for metadata errors
         logger.error(f"Data/Format error during processing job {task_id}: {e}", exc_info=True)
         if job and job.status != PublishingJob.Status.FAILED: # Avoid double update
             job.status = PublishingJob.Status.FAILED
             job.error_message = f"Invalid Input/Format Error: {e}"
             job.save(update_fields=['status', 'error_message', 'updated_at'])
         raise
    except Exception as e:
        logger.exception("Unexpected error during processing job %s: %s", task_id, e)
        if job:
            # Avoid overwriting a more specific error/status if already set
            if job.status not in (PublishingJob.Status.FAILED, PublishingJob.Status.PUBLISHED):
                 job.status = PublishingJob.Status.FAILED
                 job.error_message = f"Unexpected Error: {type(e).__name__}: {e}"
                 job.save(update_fields=['status', 'error_message', 'updated_at'])
        raise


def confirm_and_publish_job(task_id: uuid.UUID):
    """
    Handles Request 2: Confirm, Build Payload (using PERMANENT thumb_media_id), Publish Draft.
    Includes retry logic for '40007 invalid media id' error by re-uploading the thumbnail.
    """
    logger.info("Attempting to confirm and publish job with task_id: %s", task_id)
    job = None
    try:
        job = PublishingJob.objects.get(pk=task_id)
        logger.debug("Found job record for task_id: %s", task_id)

        if job.status != PublishingJob.Status.PREVIEW_READY:
            logger.warning("Job %s not PREVIEW_READY (state: %s). Publishing aborted.", task_id, job.status)
            raise ValueError(f"Job not ready. Current status: {job.get_status_display()}")

        job.status = PublishingJob.Status.PUBLISHING
        job.save(update_fields=['status', 'updated_at'])
        logger.info("Job status updated to PUBLISHING for task: %s", task_id)

        app_id = settings.WECHAT_APP_ID
        secret = settings.WECHAT_SECRET
        base_url = settings.WECHAT_BASE_URL
        if not app_id or not secret: raise ValueError("WECHAT_APP_ID/SECRET not configured.")

        access_token = auth.get_access_token(app_id=app_id, app_secret=secret, base_url=base_url)
        logger.debug("Fetched access token for publishing task: %s", task_id)

        if not job.metadata or not job.thumb_media_id:
             raise ValueError("Missing metadata or thumb_media_id for publishing.")
        if not job.original_cover_image_path:
             raise ValueError("Missing original_cover_image_path for potential re-upload.")

        placeholder_content = settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT or "<p>Content will be updated via Free Publish.</p>"

        # --- Build Initial Payload ---
        logger.info(f"Building initial draft payload with thumb_media_id: {job.thumb_media_id}")
        single_article_payload = payload_builder.build_draft_payload(
            metadata=job.metadata,
            html_content=placeholder_content,
            thumb_media_id=job.thumb_media_id # Use current (potentially expired) ID
        )
        final_draft_payload = {"articles": [single_article_payload]}
        logger.debug(f"Initial payload structure being sent: {json.dumps(final_draft_payload, indent=2)}")

        # --- Call API (with potential retry) ---
        try:
            logger.info(f"Attempting WeChat add_draft API call (1st try) for task: {task_id}")
            final_media_id = wechat_api.add_draft(
                access_token=access_token,
                draft_payload=final_draft_payload,
                base_url=base_url
            )
            # SUCCESS on first try!
            logger.info("Successfully published draft (1st try). Draft Media ID: %s for task: %s", final_media_id, task_id)

        except (RuntimeError, Exception) as e: # Catch API errors
            error_msg = str(e)
            logger.warning(f"WeChat add_draft API call failed (1st try) for task {task_id}: {error_msg}", exc_info=True)

            # --- Retry Logic for Invalid Media ID ---
            if "40007" in error_msg and "invalid media_id" in error_msg: # Check for specific error
                logger.info(f"Detected invalid media_id (40007) for task {task_id}. Attempting thumbnail re-upload and retry.")

                try:
                    original_cover_path_abs = Path(settings.MEDIA_ROOT) / job.original_cover_image_path
                    if not original_cover_path_abs.is_file():
                        raise FileNotFoundError(f"Original cover image not found at {original_cover_path_abs} for re-upload.")

                    logger.info(f"Re-uploading thumbnail from: {original_cover_path_abs}")
                    new_thumb_media_id = wechat_api.upload_thumb_media(
                        access_token=access_token,
                        thumb_path=original_cover_path_abs,
                        base_url=base_url
                    )
                    if not new_thumb_media_id:
                         raise RuntimeError("Failed to re-upload thumbnail, received no media ID.")

                    logger.info(f"Thumbnail re-uploaded successfully. New Media ID: {new_thumb_media_id} for task {task_id}")
                    job.thumb_media_id = new_thumb_media_id # Update job with new ID
                    job.save(update_fields=['thumb_media_id', 'updated_at'])

                    # Rebuild payload with the NEW thumb_media_id
                    logger.info("Rebuilding draft payload with new thumb_media_id.")
                    single_article_payload_retry = payload_builder.build_draft_payload(
                        metadata=job.metadata,
                        html_content=placeholder_content,
                        thumb_media_id=new_thumb_media_id # Use the NEW ID
                    )
                    final_draft_payload_retry = {"articles": [single_article_payload_retry]}
                    logger.debug(f"Retry payload structure: {json.dumps(final_draft_payload_retry, indent=2)}")

                    # --- Attempt API Call Again ---
                    logger.info(f"Attempting WeChat add_draft API call (2nd try) for task: {task_id}")
                    final_media_id = wechat_api.add_draft(
                        access_token=access_token,
                        draft_payload=final_draft_payload_retry, # Send retry payload
                        base_url=base_url
                    )
                    # SUCCESS on second try!
                    logger.info("Successfully published draft (2nd try). Draft Media ID: %s for task: %s", final_media_id, task_id)

                except (FileNotFoundError, RuntimeError, Exception) as retry_e:
                    # Handle failures during the retry process (re-upload or 2nd add_draft)
                    retry_error_msg = str(retry_e)
                    logger.error(f"Retry attempt failed for task {task_id}: {retry_error_msg}", exc_info=True)
                    job.error_message = f"Publishing Retry Failed: {type(retry_e).__name__}: {retry_error_msg}"
                    job.status = PublishingJob.Status.FAILED
                    job.save(update_fields=['status', 'error_message', 'updated_at'])
                    # Raise a specific error indicating retry failure
                    if isinstance(retry_e, FileNotFoundError):
                        raise RuntimeError(f"Failed to re-upload thumbnail: Original file not found.") from retry_e
                    elif "Failed to re-upload thumbnail" in retry_error_msg:
                        raise RuntimeError(f"Failed to re-upload thumbnail: {retry_error_msg}") from retry_e
                    else:
                         raise RuntimeError(f"Publishing failed on retry attempt: {retry_error_msg}") from retry_e
            else:
                # --- Non-retriable API Error ---
                logger.error(f"Non-retriable API error for task {task_id}: {error_msg}")
                job.error_message = f"API Error: {type(e).__name__}: {error_msg}"
                job.status = PublishingJob.Status.FAILED
                job.save(update_fields=['status', 'error_message', 'updated_at'])
                raise RuntimeError(f"Publishing failed due to API error: {error_msg}") from e

        # --- Common Success Path (reached after 1st or 2nd try) ---
        job.status = PublishingJob.Status.PUBLISHED
        job.wechat_media_id = final_media_id
        job.error_message = None
        job.save(update_fields=['status', 'wechat_media_id', 'error_message', 'updated_at'])

        return {
            "task_id": job.task_id,
            "status": job.get_status_display(),
            "message": "Article published to WeChat drafts successfully.",
            "wechat_media_id": final_media_id
        }

    # --- Exception Handling (Overall process) ---
    except PublishingJob.DoesNotExist:
        logger.warning("Publishing job not found for task_id: %s", task_id)
        raise # Re-raise directly
    except ValueError as e: # Covers config errors, state errors, missing fields
        logger.error(f"Validation or Configuration error during publishing job {task_id}: {e}", exc_info=True)
        if job and job.status == PublishingJob.Status.PUBLISHING: # Only set FAILED if it was PUBLISHING
            job.status = PublishingJob.Status.FAILED
            job.error_message = f"ValueError: {e}"
            job.save(update_fields=['status', 'error_message', 'updated_at'])
        raise # Re-raise directly
    except Exception as e: # Catch unexpected errors or errors raised *during* retry handling
        # Check if it's one of the specific RuntimeErrors we raised from retry logic
        err_str = str(e)
        if not ( "Publishing failed due to API error" in err_str or \
                 "Failed to re-upload thumbnail" in err_str or \
                 "Publishing failed on retry attempt" in err_str ):
             # Log unexpected errors if they weren't the ones we explicitly raised
             logger.exception("Unexpected error during confirmation/publishing job %s: %s", task_id, e)

        # Ensure status is FAILED if it reached here during publishing
        if job and job.status == PublishingJob.Status.PUBLISHING:
             job.status = PublishingJob.Status.FAILED
             # Use the existing error message if it's one of our specific RuntimeErrors
             if not job.error_message:
                 job.error_message = f"Unexpected Error: {type(e).__name__}: {e}"
             job.save(update_fields=['status', 'error_message', 'updated_at'])
        raise # Re-raise the exception