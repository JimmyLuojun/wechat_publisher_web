# /Users/junluo/Documents/wechat_publisher_web/publisher/services.py
"""
Contains the business logic for processing and publishing WeChat articles.

This module orchestrates the workflow, calls the framework-agnostic
'publishing_engine', interacts with the database models, and handles file storage.

Functions:
- _save_uploaded_file: Helper to save an uploaded file.
- _generate_preview_file: Helper to save generated HTML to a preview file.
- start_processing_job: Handles the initial processing request (Request 1).
- confirm_and_publish_job: Handles the confirmation and publishing request (Request 2).
"""
import os
import uuid
import json
import logging
from django.conf import settings
from django.core.files.storage import default_storage
from django.urls import reverse # To build URLs if needed, though direct path is used here
from django.utils import timezone

# Import from our app
from .models import PublishingJob
# Import from the independent engine
# Assuming publishing_engine is correctly installed or on Python path
try:
    from publishing_engine.core import metadata_reader, markdown_processor, html_processor
    from publishing_engine.wechat import auth, media_manager, payload_builder, api as wechat_api
    from publishing_engine.utils import file_handler # If used by the engine
except ImportError as e:
    # Handle cases where the engine might not be installed correctly during setup
    # This allows manage.py commands to run before full setup in some cases.
    logging.getLogger(__name__).error("Failed to import publishing_engine: %s", e, exc_info=True)
    # You might raise a more specific custom exception or just log
    raise ImportError("Could not import publishing_engine. Ensure it's installed and accessible.") from e


# Get an instance of a logger
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _save_uploaded_file(file_obj, subfolder="") -> str:
    """
    Saves an uploaded file to a unique path within MEDIA_ROOT.

    Args:
        file_obj: The InMemoryUploadedFile object from the request.
        subfolder: Optional subfolder within MEDIA_ROOT (e.g., 'uploads/markdown').

    Returns:
        The relative path to the saved file within MEDIA_ROOT.

    Raises:
        Exception: If saving fails.
    """
    try:
        # Create a unique filename to avoid collisions
        file_ext = os.path.splitext(file_obj.name)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        save_path = os.path.join(subfolder, unique_filename)
        logger.info("Attempting to save uploaded file to: %s", save_path)

        # default_storage handles saving to MEDIA_ROOT based on settings.py
        actual_path = default_storage.save(save_path, file_obj)
        logger.info("File saved successfully to relative path: %s", actual_path)
        return actual_path # Returns the path relative to MEDIA_ROOT
    except Exception as e:
        logger.exception("Failed to save uploaded file '%s' to subfolder '%s'", file_obj.name, subfolder)
        raise  # Re-raise the exception to be handled by the caller


def _generate_preview_file(html_content: str, task_id: uuid.UUID) -> str:
    """
    Saves the generated HTML content to a preview file.

    Args:
        html_content: The HTML string to save.
        task_id: The UUID of the job, used for filename uniqueness.

    Returns:
        The relative path to the saved preview file within MEDIA_ROOT.

    Raises:
        Exception: If saving fails.
    """
    try:
        preview_filename = f"{task_id}.html"
        # Save previews in a dedicated subdirectory within media
        preview_path_rel = os.path.join('previews', preview_filename)
        preview_path_abs = os.path.join(settings.MEDIA_ROOT, 'previews', preview_filename)

        # Ensure the previews directory exists
        os.makedirs(os.path.dirname(preview_path_abs), exist_ok=True)

        logger.info("Attempting to save preview file to: %s", preview_path_abs)
        with open(preview_path_abs, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info("Preview file saved successfully to relative path: %s", preview_path_rel)
        return preview_path_rel
    except IOError as e:
        logger.exception("Failed to write preview file for task %s", task_id)
        raise  # Re-raise the exception

# --- Main Service Functions ---

def start_processing_job(markdown_file, cover_image):
    """
    Handles Request 1: Processes uploaded markdown and cover image,
    generates a preview, and creates a PublishingJob record.

    Args:
        markdown_file: Uploaded markdown file object.
        cover_image: Uploaded cover image file object.

    Returns:
        A dictionary containing 'task_id' and 'preview_url' on success.

    Raises:
        ValueError: If configuration (API keys) is missing.
        Exception: For errors during processing, file handling, or API calls.
    """
    job = None # Initialize job to None
    markdown_path_rel = None
    cover_image_path_rel = None
    task_id = uuid.uuid4() # Generate task ID early for potential use in logging/filenames

    try:
        logger.info("Starting new processing job for task ID: %s", task_id)

        # 1. Create initial Job record (Status: PENDING)
        job = PublishingJob.objects.create(task_id=task_id, status=PublishingJob.Status.PENDING)
        logger.debug("Created initial PublishingJob record with task_id: %s", task_id)

        # 2. Save uploaded files
        job.status = PublishingJob.Status.PROCESSING
        job.save(update_fields=['status', 'updated_at'])
        logger.info("Saving uploaded files for task: %s", task_id)
        markdown_path_rel = _save_uploaded_file(markdown_file, subfolder='uploads/markdown')
        cover_image_path_rel = _save_uploaded_file(cover_image, subfolder='uploads/cover_images')
        job.original_markdown_path = markdown_path_rel
        job.original_cover_image_path = cover_image_path_rel
        job.save(update_fields=['original_markdown_path', 'original_cover_image_path', 'updated_at'])
        logger.info("Uploaded files saved for task: %s", task_id)

        # Construct absolute paths for the engine (engine should ideally handle paths better,
        # but this works if it expects absolute paths for now)
        markdown_path_abs = os.path.join(settings.MEDIA_ROOT, markdown_path_rel)
        cover_image_path_abs = os.path.join(settings.MEDIA_ROOT, cover_image_path_rel)

        # 3. Get WeChat Credentials from Settings
        logger.debug("Retrieving WeChat credentials from settings for task: %s", task_id)
        app_id = getattr(settings, 'WECHAT_APP_ID', None)
        secret = getattr(settings, 'WECHAT_SECRET', None)
        if not app_id or not secret:
            raise ValueError("WECHAT_APP_ID and WECHAT_SECRET must be configured in settings.")

        # 4. Get Access Token (using publishing_engine)
        logger.info("Fetching WeChat access token for task: %s", task_id)
        access_token = auth.get_access_token(app_id=app_id, secret=secret)
        logger.debug("Fetched access token successfully for task: %s", task_id)

        # 5. Upload Cover Image (using publishing_engine) - Get thumb_media_id
        # Assuming media_manager has an upload_thumb function
        logger.info("Uploading cover image to WeChat for task: %s", task_id)
        # The media_manager might need the token and file path, or file content
        thumb_media_id = media_manager.upload_thumb(
            access_token=access_token,
            file_path=cover_image_path_abs # Or pass file content if preferred by engine
        )
        job.thumb_media_id = thumb_media_id
        job.save(update_fields=['thumb_media_id', 'updated_at'])
        logger.info("Cover image uploaded, thumb_media_id: %s for task: %s", thumb_media_id, task_id)

        # 6. Read Metadata (using publishing_engine)
        logger.info("Reading metadata from markdown for task: %s", task_id)
        metadata_dict = metadata_reader.read_metadata(markdown_path_abs)
        job.metadata = metadata_dict # Assumes metadata_dict is JSON serializable
        job.save(update_fields=['metadata', 'updated_at'])
        logger.info("Metadata read successfully for task: %s", task_id)

        # 7. Convert Markdown to HTML (using publishing_engine)
        logger.info("Converting Markdown to HTML for task: %s", task_id)
        raw_html = markdown_processor.convert_md_to_html(markdown_path_abs)
        logger.debug("Markdown converted to raw HTML for task: %s", task_id)

        # 8. Process HTML (Upload content images, sanitize etc. using publishing_engine)
        logger.info("Processing HTML (uploading content images, etc.) for task: %s", task_id)
        # Assuming html_processor needs token for image uploads via media_manager internally or passed
        # The media_uploader instance might be created here or inside html_processor
        media_uploader = media_manager.WeChatMediaUploader(access_token, settings.MEDIA_ROOT) # Example instantiation
        processed_html = html_processor.prepare_html_for_wechat(
            raw_html=raw_html,
            media_uploader=media_uploader # Pass uploader if needed
        )
        logger.info("HTML processing complete for task: %s", task_id)

        # 9. Generate and save Preview HTML file
        logger.info("Generating preview file for task: %s", task_id)
        preview_path_rel = _generate_preview_file(processed_html, task_id)
        job.preview_html_path = preview_path_rel
        logger.info("Preview file generated at: %s for task: %s", preview_path_rel, task_id)

        # 10. Update Job Status to PREVIEW_READY
        job.status = PublishingJob.Status.PREVIEW_READY
        job.save(update_fields=['preview_html_path', 'status', 'updated_at'])
        logger.info("Job status updated to PREVIEW_READY for task: %s", task_id)

        # 11. Prepare response data
        preview_url = settings.MEDIA_URL + preview_path_rel.replace(os.path.sep, '/') # Ensure forward slashes for URL
        logger.info("Preview URL: %s for task: %s", preview_url, task_id)

        return {
            "task_id": job.task_id,
            "preview_url": preview_url,
            # "title": metadata_dict.get("title", "Untitled") # Optionally return title
        }

    except Exception as e:
        logger.exception("Error during processing job %s: %s", task_id, e)
        if job:
            # Mark job as failed if an error occurred after creation
            job.status = PublishingJob.Status.FAILED
            job.error_message = f"{type(e).__name__}: {str(e)}"
            job.save(update_fields=['status', 'error_message', 'updated_at'])
        # Re-raise the exception to be caught by the API view
        raise


def confirm_and_publish_job(task_id: uuid.UUID):
    """
    Handles Request 2: Retrieves a job by task_id, builds the final payload,
    and publishes the article as a draft to WeChat.

    Args:
        task_id: The UUID of the job to confirm and publish.

    Returns:
        A dictionary containing job status, message, and wechat_media_id on success.

    Raises:
        PublishingJob.DoesNotExist: If no job found for the task_id.
        ValueError: If job is not in the PREVIEW_READY state or config is missing.
        Exception: For errors during payload building or API calls.
    """
    logger.info("Attempting to confirm and publish job with task_id: %s", task_id)

    try:
        # 1. Retrieve the job
        job = PublishingJob.objects.get(pk=task_id)
        logger.debug("Found job record for task_id: %s", task_id)

        # 2. Check job status
        if job.status != PublishingJob.Status.PREVIEW_READY:
            logger.warning("Job %s is not in PREVIEW_READY state (current state: %s). Cannot publish.", task_id, job.status)
            raise ValueError(f"Job is not ready for publishing. Current status: {job.get_status_display()}")

        # 3. Update status to PUBLISHING
        job.status = PublishingJob.Status.PUBLISHING
        job.save(update_fields=['status', 'updated_at'])
        logger.info("Job status updated to PUBLISHING for task: %s", task_id)

        # 4. Get WeChat Credentials
        logger.debug("Retrieving WeChat credentials from settings for task: %s", task_id)
        app_id = getattr(settings, 'WECHAT_APP_ID', None)
        secret = getattr(settings, 'WECHAT_SECRET', None)
        if not app_id or not secret:
            # This check might be redundant if start_processing_job succeeded, but good practice
            raise ValueError("WECHAT_APP_ID and WECHAT_SECRET must be configured in settings.")

        # 5. Get Access Token
        logger.info("Fetching WeChat access token for publishing task: %s", task_id)
        access_token = auth.get_access_token(app_id=app_id, secret=secret)
        logger.debug("Fetched access token successfully for publishing task: %s", task_id)

        # 6. Prepare the minimal payload for add_draft (using publishing_engine)
        logger.info("Building draft payload for task: %s", task_id)
        # Ensure metadata and thumb_media_id were stored correctly
        if not job.metadata or not job.thumb_media_id:
             raise ValueError("Missing required metadata or thumb_media_id for publishing.")

        # Define placeholder content (can be moved to settings)
        placeholder_content = getattr(settings, 'WECHAT_DRAFT_PLACEHOLDER_CONTENT',
                                      '<p>Content is being prepared. Please edit in WeChat backend.</p>')

        # Build payload using engine function
        article_payload = payload_builder.build_article_payload(
            title=job.metadata.get('title', 'Untitled Article'),
            author=job.metadata.get('author', 'Unknown Author'),
            content=placeholder_content, # Use placeholder
            thumb_media_id=job.thumb_media_id,
            content_source_url=job.metadata.get('content_source_url', None), # Optional
            # Pass other metadata fields as needed by the payload builder
        )
        logger.debug("Draft payload built for task: %s", task_id)

        # 7. Call WeChat API to add draft (using publishing_engine)
        logger.info("Calling WeChat add_draft API for task: %s", task_id)
        # Assuming wechat_api.add_draft takes token and the article payload list
        # Note: add_draft expects a *list* of articles, even if just one.
        wechat_response = wechat_api.add_draft(
            access_token=access_token,
            articles=[article_payload] # Pass as a list
        )

        # Check response and extract media_id (assuming add_draft returns it)
        # The exact structure of wechat_response depends on your api.py implementation
        if 'media_id' in wechat_response:
             final_media_id = wechat_response['media_id']
             logger.info("Successfully published draft to WeChat. Media ID: %s for task: %s", final_media_id, task_id)
             # 8. Update Job Status to PUBLISHED
             job.status = PublishingJob.Status.PUBLISHED
             job.wechat_media_id = final_media_id
             job.save(update_fields=['status', 'wechat_media_id', 'updated_at'])

             return {
                 "task_id": job.task_id,
                 "status": job.get_status_display(),
                 "message": "Article published to WeChat drafts successfully.",
                 "wechat_media_id": final_media_id
             }
        else:
             # Handle cases where the API call succeeded (HTTP 200) but WeChat returned an error
             error_msg = f"WeChat API call succeeded but failed to return media_id. Response: {wechat_response}"
             logger.error(error_msg)
             raise Exception(error_msg) # Or a custom WeChat API error

    except PublishingJob.DoesNotExist:
        logger.warning("Publishing job not found for task_id: %s", task_id)
        raise # Re-raise to be handled by the view (as 404 Not Found)
    except Exception as e:
        logger.exception("Error during confirmation/publishing job %s: %s", task_id, e)
        if 'job' in locals() and job:
            # Mark job as failed
            job.status = PublishingJob.Status.FAILED
            job.error_message = f"{type(e).__name__}: {str(e)}"
            job.save(update_fields=['status', 'error_message', 'updated_at'])
        # Re-raise the exception to be caught by the API view
        raise