# /Users/junluo/Documents/wechat_publisher_web/publisher/views.py

from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status # Import status constants
# Import your app's serializers
from .serializers import UploadSerializer, ConfirmSerializer, PreviewResponseSerializer, ConfirmResponseSerializer
from .services import start_processing_job, confirm_and_publish_job
from .models import PublishingJob # Import model for DoesNotExist exception
from django.conf import settings
from pathlib import Path
from django.core.files.storage import default_storage # For saving images
import logging
import uuid # If needed for unique filenames (recommended!)
import yaml # For catching YAMLError
import os # For path joining safely

logger = logging.getLogger(__name__) # Use __name__ for logger hierarchy

# --- View for rendering the upload form ---
class UploadFormView(View):
    """Serves the initial HTML form for uploading files."""
    def get(self, request, *args, **kwargs):
        logger.debug("Rendering upload page view")
        # Assuming a simple template render without a Django Form object
        return render(request, 'publisher/upload_form.html')


# --- API View for processing the uploaded files ---
class ProcessPreviewAPIView(APIView):
    """Handles the POST request with uploaded files to start processing."""
    serializer_class = UploadSerializer # Link serializer for potential DRF tooling/docs

    def post(self, request, *args, **kwargs):
        logger.info("Received request for ProcessPreviewAPIView endpoint.")
        # Use the defined serializer for input validation
        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            logger.debug("UploadSerializer data is valid.")
            validated_data = serializer.validated_data
            markdown_file = validated_data['markdown_file']
            cover_image = validated_data['cover_image']
            # Use validated_data for content_images if defined in serializer,
            # otherwise fallback to request.FILES.getlist
            uploaded_content_images = validated_data.get('content_images', []) # Get from validated data
            logger.info(f"Received {len(uploaded_content_images)} content image file(s) via serializer.")

            # --- Define and create directory for content images (within MEDIA_ROOT) ---
            # Get subdirectory name from settings
            content_images_subdir = getattr(settings, 'CONTENT_IMAGES_SUBDIR', 'uploads/content_images')
            # Construct absolute path using MEDIA_ROOT
            content_images_abs_dir = Path(settings.MEDIA_ROOT) / content_images_subdir
            try:
                # Ensure directory exists using Pathlib
                content_images_abs_dir.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Ensured content images directory exists: {content_images_abs_dir}")
            except OSError as e:
                 logger.exception(f"Could not create content images directory: {content_images_abs_dir}")
                 return Response(
                     {"error": f"Server error: Could not create image directory. {e}"},
                     status=status.HTTP_500_INTERNAL_SERVER_ERROR
                 )

            # --- Save uploaded content images ---
            saved_image_paths = {} # Optional: Store mapping if needed later
            for img_file in uploaded_content_images:
                try:
                    # *** SECURITY WARNING: Using original filename is risky! ***
                    # Sanitize or generate unique names in production.
                    # Example (safer):
                    # file_ext = Path(img_file.name).suffix
                    # safe_filename = f"{uuid.uuid4()}{file_ext}"
                    image_filename = Path(img_file.name).name # Basic extraction, USE WITH CAUTION
                    if not image_filename: continue # Skip if filename is empty

                    # Define relative path for storage
                    save_path_rel = Path(content_images_subdir) / image_filename
                    # Use default_storage which handles MEDIA_ROOT implicitly
                    actual_path = default_storage.save(str(save_path_rel), img_file) # actual_path is relative to MEDIA_ROOT
                    logger.info(f"Saved content image '{image_filename}' to '{actual_path}' (relative to MEDIA_ROOT)")
                    saved_image_paths[image_filename] = actual_path
                except Exception as e:
                    logger.exception(f"Failed to save uploaded content image: {img_file.name}")
                    # Return error immediately if any image fails to save
                    return Response(
                        {"error": f"Failed to save content image '{img_file.name}'. Error: {e}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            # --- End saving content images ---

            # --- Call the service layer ---
            try:
                # Pass the absolute path to the directory where content images were saved
                result_data = start_processing_job(
                    markdown_file=markdown_file,
                    cover_image=cover_image,
                    content_images_dir_abs=content_images_abs_dir # Pass the absolute directory path
                )
                logger.info(f"Processing job started successfully. Task ID: {result_data.get('task_id')}")
                # Use response serializer for output formatting
                response_serializer = PreviewResponseSerializer(result_data)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            # Catch specific, expected errors from the service layer
            except FileNotFoundError as e:
                 logger.warning(f"File not found during processing: {e}") # Warning level might be sufficient
                 return Response({"error": f"Processing failed: Required file not found. {e}"}, status=status.HTTP_400_BAD_REQUEST)
            except (ValueError, yaml.YAMLError) as e: # Catch config/format/metadata errors
                 logger.error(f"Invalid input or format error during processing: {e}", exc_info=True)
                 # Provide a slightly more user-friendly message
                 return Response({"error": f"Processing failed due to invalid input or format. Please check the markdown file/metadata. Details: {e}"}, status=status.HTTP_400_BAD_REQUEST)
            except ImportError as e: # Catch missing engine dependencies
                 logger.critical(f"ImportError during processing - check publishing_engine installation: {e}", exc_info=True)
                 return Response({"error": f"Server configuration error: Required processing module not found."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except RuntimeError as e: # Catch other runtime errors from engine/API calls
                 logger.error(f"Runtime error during processing: {e}", exc_info=True)
                 return Response({"error": f"Processing failed due to a runtime error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e: # Catch unexpected errors
                logger.exception("Unhandled exception during processing job start") # Log full traceback
                return Response(
                    {"error": "An unexpected server error occurred during processing. Please contact support."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Serializer validation failed
            logger.warning("UploadSerializer validation failed.", extra={'errors': serializer.errors})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# --- API View for Confirmation/Publishing ---
class ConfirmPublishAPIView(APIView):
    """Handles the POST request to confirm and publish the draft."""
    serializer_class = ConfirmSerializer # Link serializer

    def post(self, request, *args, **kwargs):
        logger.info("Received request for ConfirmPublishAPIView endpoint.")
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            task_id = serializer.validated_data['task_id']
            logger.info(f"Confirmation received for task ID: {task_id}")
            try:
                result_data = confirm_and_publish_job(task_id)
                logger.info(f"Publishing job completed for task ID: {task_id}. Result keys: {result_data.keys()}")
                # Use response serializer
                response_serializer = ConfirmResponseSerializer(result_data)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            except PublishingJob.DoesNotExist:
                 logger.warning(f"Confirm/publish failed: Job not found for task_id: {task_id}")
                 return Response({"error": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
            # Catch specific errors that might come from confirm_and_publish_job
            except ValueError as e: # E.g., job not in correct state, missing config/file path error from service
                 logger.error(f"Validation/Configuration error during publishing job {task_id}: {e}", exc_info=False) # Less verbose log for expected errors
                 return Response({"error": f"Publishing failed: {e}"}, status=status.HTTP_400_BAD_REQUEST) # 400 for client-side correctable errors
            except RuntimeError as e: # E.g., API errors returned from WeChat, re-upload failure
                 logger.error(f"Runtime error during publishing job {task_id}: {e}", exc_info=True)
                 return Response({"error": f"Publishing failed due to API or runtime issue: {e}"}, status=status.HTTP_502_BAD_GATEWAY) # 502 might be appropriate for upstream API errors
            except ImportError as e: # Catch missing engine dependencies during publish step
                 logger.critical(f"ImportError during publishing - check publishing_engine installation: {e}", exc_info=True)
                 return Response({"error": f"Server configuration error: Required publishing module not found."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e: # Catch unexpected errors
                logger.exception(f"Unhandled exception during publishing job {task_id}") # Log full traceback
                return Response(
                    {"error": "An unexpected server error occurred during publishing. Please contact support."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Confirmation request validation failed
            logger.warning("ConfirmSerializer validation failed.", extra={'errors': serializer.errors})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)