# /Users/junluo/Documents/wechat_publisher_web/publisher/models.py
"""
Defines the database models for the publisher app.

Models:
- PublishingJob: Tracks the state and details of a WeChat publishing request
                 from initial processing to final publication.
"""
import uuid
import logging
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

# Get an instance of a logger
logger = logging.getLogger(__name__)

class PublishingJob(models.Model):
    """
    Represents a single job to process and potentially publish an article to WeChat.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Processing')
        PROCESSING = 'PROCESSING', _('Processing Content')
        PREVIEW_READY = 'PREVIEW_READY', _('Preview Ready')
        PUBLISHING = 'PUBLISHING', _('Publishing to WeChat')
        PUBLISHED = 'PUBLISHED', _('Published Successfully')
        FAILED = 'FAILED', _('Processing/Publishing Failed')

    # Unique identifier for the job, used in API calls
    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                               help_text="Unique identifier for the publishing task.")

    # Tracking the job's state
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Current status of the publishing job."
    )

    # Input information (optional, useful for debugging/retries)
    # Store relative path within MEDIA_ROOT
    # Consider using FileField if you want Django's file handling features,
    # but CharField might be simpler if just storing the path handled by services.py
    original_markdown_path = models.CharField(max_length=500, blank=True, null=True,
                                      help_text="Path to the originally uploaded Markdown file.")
    original_cover_image_path = models.CharField(max_length=500, blank=True, null=True,
                                         help_text="Path to the originally uploaded cover image.")

    # Information extracted/generated during processing
    # Use JSONField if your DB supports it (PostgreSQL recommended)
    # Otherwise, store as TextField and handle JSON manually in services.py
    metadata = models.JSONField(blank=True, null=True,
                                help_text="Metadata extracted from the markdown file (title, author, etc.).")
    # Store the permanent WeChat media_id for the uploaded cover image
    thumb_media_id = models.CharField(max_length=255, blank=True, null=True,
                                      help_text="WeChat permanent media ID for the cover image (thumb_media_id).")
    # Store the relative path to the generated HTML preview file
    preview_html_path = models.CharField(max_length=500, blank=True, null=True,
                                       help_text="Path to the generated HTML preview file within MEDIA_ROOT.")

    # Outcome of publishing
    # Stores the media_id of the successfully created draft/article in WeChat
    wechat_media_id = models.CharField(max_length=255, blank=True, null=True,
                                     help_text="WeChat media ID of the published draft/article.")
    error_message = models.TextField(blank=True, null=True,
                                     help_text="Stores error details if the job failed.")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True,
                                      help_text="Timestamp when the job was created.")
    updated_at = models.DateTimeField(auto_now=True,
                                      help_text="Timestamp when the job was last updated.")

    def __str__(self):
        """String representation of the PublishingJob."""
        return f"Publishing Job {self.task_id} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Publishing Job"
        verbose_name_plural = "Publishing Jobs"
        ordering = ['-created_at'] # Show newest jobs first by default

# Remember to run:
# python manage.py makemigrations publisher
# python manage.py migrate