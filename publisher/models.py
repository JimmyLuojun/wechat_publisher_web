# /Users/junluo/Documents/wechat_publisher_web/publisher/models.py
import uuid
import logging
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone # Import timezone

logger = logging.getLogger(__name__)

class PublishingJob(models.Model):
    """
    Represents a single job to process and publish an article to WeChat.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Processing')
        PROCESSING = 'PROCESSING', _('Processing Content')
        PREVIEW_READY = 'PREVIEW_READY', _('Preview Ready')
        PUBLISHING = 'PUBLISHING', _('Publishing to WeChat')
        PUBLISHED = 'PUBLISHED', _('Published Successfully')
        FAILED = 'FAILED', _('Processing/Publishing Failed')

    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                               help_text="Unique identifier for the publishing task.")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Current status of the publishing job."
    )

    # Store relative paths within MEDIA_ROOT for locally saved files
    original_markdown_path = models.CharField(max_length=500, blank=True, null=True,
                                      help_text="Relative path to the locally saved original Markdown file.")
    # **** Store LOCAL PATH of cover image for WeChat re-upload ****
    original_cover_image_path = models.CharField(max_length=500, blank=True, null=True,
                                         help_text="Relative path to the locally saved original cover image (for WeChat re-upload if needed).")

    # Information extracted/generated during processing
    metadata = models.JSONField(blank=True, null=True,
                                help_text="Metadata extracted (title, author, etc.) and Cloudinary cover URL.")
    # Permanent WeChat media_id for the uploaded cover image thumbnail
    thumb_media_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, # Added index
                                      help_text="WeChat permanent media ID for the cover image (thumb_media_id).")
    # Relative path to the generated HTML preview file
    preview_html_path = models.CharField(max_length=500, blank=True, null=True,
                                       help_text="Relative path to the generated HTML preview file.")

    # Outcome of publishing
    wechat_media_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, # Added index
                                     help_text="WeChat media ID of the published draft/article.")
    error_message = models.TextField(blank=True, null=True,
                                     help_text="Stores error details if the job failed.")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True, editable=False,
                                       help_text="Timestamp when the article was successfully published to WeChat.")

    def __str__(self):
        return f"Job {self.task_id} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Publishing Job"
        verbose_name_plural = "Publishing Jobs"
        ordering = ['-created_at']

# Remember to run:
# python manage.py makemigrations publisher
# python manage.py migrate