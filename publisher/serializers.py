# /Users/junluo/Documents/wechat_publisher_web/publisher/serializers.py
"""
Defines serializers for API request validation and response formatting
for the publisher app using Django REST Framework.

Serializers:
- UploadSerializer: Validates input for the initial processing request.
- PreviewResponseSerializer: Formats the successful response for the processing request.
- ConfirmRequestSerializer: Validates input for the confirmation/publishing request.
- ConfirmResponseSerializer: Formats the successful response for the publishing request.
"""
import logging
from rest_framework import serializers

# Get an instance of a logger
logger = logging.getLogger(__name__)

# --- Request Serializers ---

class UploadSerializer(serializers.Serializer):
    """
    Validates the data submitted to start the processing and preview generation.
    """
    # Ensure these field names match the 'name' attributes in your HTML form
    markdown_file = serializers.FileField(required=True, allow_empty_file=False)
    # Cover image is often required by WeChat for drafts
    cover_image = serializers.ImageField(required=True) # Use ImageField for basic validation

    # Add any other fields expected from the upload form (e.g., specific tags)
    # custom_tags = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        """
        Perform cross-field validation if needed.
        Example: Check file extensions or sizes more strictly.
        """
        # Example: Check markdown file extension (adapt as needed)
        # md_filename = data['markdown_file'].name
        # if not md_filename.lower().endswith(('.md', '.markdown')):
        #     raise serializers.ValidationError("Invalid Markdown file extension.")

        # Example: Check image size (ensure Pillow is installed: poetry add Pillow)
        # max_size = 2 * 1024 * 1024 # 2MB
        # if data['cover_image'].size > max_size:
        #     raise serializers.ValidationError(f"Cover image size cannot exceed {max_size // 1024 // 1024}MB.")

        logger.debug("UploadSerializer validation successful for: %s", data.get('markdown_file').name)
        return data


class ConfirmRequestSerializer(serializers.Serializer):
    """
    Validates the data submitted to confirm and publish a previously processed job.
    """
    # Expecting the task_id generated in the first step
    task_id = serializers.UUIDField(required=True)

    def validate_task_id(self, value):
        """
        Optional: Add validation logic here if needed,
        e.g., check if a job with this ID actually exists in a preliminary state,
        though the main check happens in the view/service.
        """
        logger.debug("ConfirmRequestSerializer validation successful for task_id: %s", value)
        return value

# --- Response Serializers ---

class PreviewResponseSerializer(serializers.Serializer):
    """
    Formats the data returned after successful processing and preview generation.
    """
    task_id = serializers.UUIDField(read_only=True)
    # Returns the full URL to the preview file
    preview_url = serializers.URLField(read_only=True)
    # Optionally return other info like extracted title
    # title = serializers.CharField(read_only=True)

class ConfirmResponseSerializer(serializers.Serializer):
    """
    Formats the data returned after successful publication to WeChat.
    """
    task_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    # The WeChat media_id of the created draft/article
    wechat_media_id = serializers.CharField(read_only=True, allow_null=True)