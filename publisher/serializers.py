# /Users/junluo/Documents/wechat_publisher_web/publisher/serializers.py
import logging
from rest_framework import serializers
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Request Serializers ---

class UploadSerializer(serializers.Serializer):
    """Serializer for validating the initial upload request."""
    markdown_file = serializers.FileField(
        allow_empty_file=False,
        required=True,
        help_text="The Markdown (.md) file for the article."
        )
    cover_image = serializers.ImageField(
        required=True,
        help_text="The cover image for the article (used for thumbnail)."
        )
    content_images = serializers.ListField(
        child=serializers.ImageField(allow_empty_file=False), # Validate each file as an image
        required=False, # Content images are optional
        allow_empty=True,
        max_length=50, # Optional: Limit number of content images
        help_text="Optional: Content images referenced by filename within the markdown."
    )

    def validate_markdown_file(self, file):
        """Optional: Add specific validation for markdown file if needed."""
        allowed_extensions = ['.md', '.markdown']
        ext = Path(file.name).suffix.lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(f"Invalid file extension '{ext}'. Only {', '.join(allowed_extensions)} allowed.")
        # Add size validation if needed:
        # if file.size > MAX_MD_SIZE: raise ValidationError(...)
        return file

    def validate(self, data):
        """Optional cross-field validation."""
        md_name = data.get('markdown_file', None)
        cover_name = data.get('cover_image', None)
        img_count = len(data.get('content_images', []))
        logger.debug(f"UploadSerializer validating: md='{md_name.name if md_name else 'N/A'}', cover='{cover_name.name if cover_name else 'N/A'}', content_images_count={img_count}")
        # Add more complex validation across fields if needed
        return data

class ConfirmSerializer(serializers.Serializer):
    """Serializer for validating the confirmation request."""
    task_id = serializers.UUIDField(
        required=True,
        help_text="The unique Task ID received from the initial processing step."
        )

    def validate_task_id(self, value: uuid.UUID) -> uuid.UUID:
        """Basic validation for UUID format."""
        logger.debug(f"ConfirmSerializer validating task_id: {value}")
        # View typically handles DoesNotExist check against DB
        return value

# --- Response Serializers ---

class PreviewResponseSerializer(serializers.Serializer):
    """Formats the data returned after successful processing and preview generation."""
    task_id = serializers.UUIDField(read_only=True)
    preview_url = serializers.URLField(read_only=True, help_text="URL to view the generated HTML preview.")
    # title = serializers.CharField(read_only=True, required=False, source='metadata.title') # Example if title is in metadata

class ConfirmResponseSerializer(serializers.Serializer):
    """Formats the data returned after successful publication to WeChat drafts."""
    task_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True, help_text="Final status of the publishing job (e.g., 'Published').")
    message = serializers.CharField(read_only=True, help_text="Success or informational message.")
    wechat_media_id = serializers.CharField(read_only=True, allow_null=True, required=False, help_text="The WeChat media_id of the created draft.")