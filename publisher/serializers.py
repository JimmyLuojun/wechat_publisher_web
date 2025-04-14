# /Users/junluo/Documents/wechat_publisher_web/publisher/serializers.py
"""
Defines serializers for API request validation and response formatting
for the publisher app using Django REST Framework.

Serializers:
- UploadSerializer: Validates input for the initial processing request.
- PreviewResponseSerializer: Formats the successful response for the processing request.
- ConfirmSerializer: Validates input for the confirmation/publishing request. (Renamed from ConfirmRequestSerializer for consistency)
- ConfirmResponseSerializer: Formats the successful response for the publishing request.
"""
import logging
from rest_framework import serializers
import uuid # Import uuid for UUIDField
from pathlib import Path

# Get an instance of a logger
logger = logging.getLogger(__name__)

# --- Request Serializers ---

class UploadSerializer(serializers.Serializer):
    """Serializer for validating the initial upload request."""
    markdown_file = serializers.FileField(allow_empty_file=False, required=True)
    cover_image = serializers.ImageField(required=True) # DRF ImageField handles basic image validation
    content_images = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False, allow_null=False),
        required=False, # Content images are optional
        allow_empty=True,
        help_text="Upload content images used within the markdown (referenced by filename)."
    )

    def validate(self, data):
        """Optional cross-field validation."""
        md_file = data.get('markdown_file')
        cover_img = data.get('cover_image')
        content_imgs = data.get('content_images', [])

        md_name = md_file.name if md_file else 'N/A'
        cover_name = cover_img.name if cover_img else 'N/A'
        img_count = len(content_imgs)

        logger.debug(f"UploadSerializer validating: md='{md_name}', cover='{cover_name}', content_images_count={img_count}")

        # Example Validation: Check file extensions if needed (though FileField/ImageField do some)
        # allowed_md_ext = ['.md', '.markdown']
        # if md_file and Path(md_name).suffix.lower() not in allowed_md_ext:
        #     raise serializers.ValidationError("Invalid markdown file extension.")

        # Add more complex validation if needed (e.g., total size)
        return data

class ConfirmSerializer(serializers.Serializer):
    """Serializer for validating the confirmation request."""
    task_id = serializers.UUIDField(required=True, help_text="The unique Task ID received from the initial processing step.")

    def validate_task_id(self, value: uuid.UUID) -> uuid.UUID:
        """Basic validation for UUID."""
        logger.debug(f"ConfirmSerializer validating task_id: {value}")
        # Could add check here if task_id format looks okay beyond UUID type if necessary
        # For example, check if it exists in DB (though view usually handles DoesNotExist)
        return value

# --- Response Serializers ---

class PreviewResponseSerializer(serializers.Serializer):
    """
    Formats the data returned after successful processing and preview generation.
    """
    task_id = serializers.UUIDField(read_only=True)
    preview_url = serializers.URLField(read_only=True, help_text="URL to view the generated HTML preview.")
    # Optionally return other info like extracted title if available in result_data
    # title = serializers.CharField(read_only=True, required=False)

class ConfirmResponseSerializer(serializers.Serializer):
    """
    Formats the data returned after successful publication to WeChat drafts.
    """
    task_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True, help_text="Final status of the publishing job (e.g., 'Published').")
    message = serializers.CharField(read_only=True, help_text="Success message.")
    wechat_media_id = serializers.CharField(read_only=True, allow_null=True, help_text="The WeChat media_id of the created draft.")