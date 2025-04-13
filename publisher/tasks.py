# /Users/junluo/Documents/wechat_publisher_web/publisher/tasks.py
"""
Defines background tasks for the publisher app using Celery.

This is where long-running operations (e.g., extensive image processing,
multiple API calls) should be placed to avoid blocking web requests.

NOTE: This file provides a structure. Actual implementation requires
      setting up Celery (see wechat_publisher_web/celery.py and settings.py)
      and refactoring parts of services.py to enqueue tasks defined here.
"""
import logging
from celery import shared_task
# from django.conf import settings # If task needs settings directly
# from .services import _some_long_running_helper # Example: If refactoring services

# Get an instance of a logger
logger = logging.getLogger(__name__)

# Example structure for a background task (Not fully implemented here)
# @shared_task(bind=True, max_retries=3, default_retry_delay=60) # bind=True allows access to self
# def process_html_and_upload_images_async(self, job_id, raw_html):
#     """
#     Example background task to process HTML and upload images asynchronously.
#
#     Args:
#         job_id: The primary key (task_id as string) of the PublishingJob.
#         raw_html: The HTML content needing processing.
#
#     Returns:
#         Path to the processed HTML file or raises an exception on failure.
#     """
#     logger.info("Starting async HTML processing for job: %s", job_id)
#     try:
#         # 1. Get job instance (optional, if needed to update status during task)
#         # from .models import PublishingJob
#         # job = PublishingJob.objects.get(pk=job_id)
#         # job.status = PublishingJob.Status.PROCESSING_IMAGES # Example intermediate status
#         # job.save()
#
#         # 2. Get Access Token (needs credentials - pass them or get from settings)
#         # access_token = ...
#
#         # 3. Perform the long-running operation (call engine parts)
#         # media_uploader = ...
#         # processed_html = html_processor.prepare_html_for_wechat(raw_html, media_uploader)
#
#         # 4. Save result (e.g., save processed_html to a file)
#         # preview_path = _generate_preview_file(processed_html, uuid.UUID(job_id))
#
#         # 5. Update job status on completion
#         # job.preview_html_path = preview_path
#         # job.status = PublishingJob.Status.PREVIEW_READY # Or next step
#         # job.save()
#
#         logger.info("Async HTML processing complete for job: %s", job_id)
#         # return preview_path # Return result if needed by subsequent tasks/logic
#
#     except Exception as exc:
#         logger.exception("Async HTML processing failed for job %s: %s", job_id, exc)
#         # Optionally update job status to FAILED here
#         # try:
#         #     job.status = PublishingJob.Status.FAILED
#         #     job.error_message = f"Task failed: {exc}"
#         #     job.save()
#         # except PublishingJob.DoesNotExist:
#         #      pass # Job might have been deleted
#
#         # Retry the task if possible (uses max_retries, default_retry_delay)
#         # self.retry(exc=exc)
#         raise # Re-raise exception if retries exhausted or not configured

# To use this (after Celery setup):
# In services.py, instead of calling the processing directly:
# process_html_and_upload_images_async.delay(str(job.task_id), raw_html)