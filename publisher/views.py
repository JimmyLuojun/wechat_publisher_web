# /Users/junluo/Documents/wechat_publisher_web/publisher/views.py

from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import (
    UploadSerializer, ConfirmSerializer, PreviewResponseSerializer,
    ConfirmResponseSerializer
)
from .services import start_processing_job, confirm_and_publish_job
from .models import PublishingJob
from django.conf import settings
from pathlib import Path
import logging
import yaml # For catching YAMLError specific exceptions

logger = logging.getLogger(__name__) # Use logger from publisher scope

# --- View for rendering the upload form ---
class UploadFormView(View):
    """Serves the initial HTML form for uploading files."""
    def get(self, request, *args, **kwargs):
        # Log the attempt to render the view
        logger.debug("Rendering upload page view (upload_form.html)")
        # Ensure 'publisher/upload_form.html' exists in your templates directory
        # associated with the 'publisher' app or in a project-level templates dir.
        return render(request, 'publisher/upload_form.html')


# --- API View for processing the uploaded files ---
class ProcessPreviewAPIView(APIView):
    """
    Handles the POST request with uploaded files (Markdown, Cover, Content Images)
    to start the processing and preview generation workflow using the service layer.
    Expects multipart/form-data.
    """
    serializer_class = UploadSerializer # Link serializer for DRF docs/UI

    def post(self, request, *args, **kwargs):
        # Log the beginning of the request handling
        logger.info("Received request: ProcessPreviewAPIView.")
        # Initialize the serializer with request data
        serializer = self.serializer_class(data=request.data)

        # Validate the incoming data using the serializer
        if serializer.is_valid():
            logger.debug("UploadSerializer data is valid.")
            validated_data = serializer.validated_data
            # Extract validated file objects
            markdown_file = validated_data['markdown_file']
            cover_image = validated_data['cover_image']
            # Content images are optional, default to empty list if not provided
            uploaded_content_images = validated_data.get('content_images', [])
            # Log received file information
            logger.info(
                f"Files received: MD='{markdown_file.name}', "
                f"Cover='{cover_image.name}', "
                f"ContentImages={len(uploaded_content_images)}"
            )

            try:
                # Delegate the core logic to the service layer function
                result_data = start_processing_job(
                    markdown_file=markdown_file,
                    cover_image=cover_image,
                    content_images=uploaded_content_images
                )
                # Log successful initiation and the returned task ID
                logger.info(f"Processing job initiated successfully. Task ID: {result_data.get('task_id')}")
                # Serialize the successful response data
                response_serializer = PreviewResponseSerializer(result_data)
                # Return a 200 OK response with the task ID and preview URL
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            # --- Specific Exception Handling from Service Layer ---
            # Handle cases where required files (like CSS) might be missing
            except FileNotFoundError as e:
                 logger.warning(f"Processing failed due to missing file: {e}", exc_info=True)
                 err_msg = f"Processing failed: Required file not found. {e}"
                 # Provide a more specific message if it's a known configuration issue
                 if "CSS" in str(e) or "Configuration Error" in str(e):
                     err_msg = f"Processing failed: {e}"
                 return Response({"error": err_msg}, status=status.HTTP_400_BAD_REQUEST)

            # Handle errors related to input format, configuration, or Markdown metadata
            except (ValueError, yaml.YAMLError) as e:
                 logger.error(f"Invalid input or format error during processing: {e}", exc_info=True)
                 return Response({"error": f"Processing failed due to invalid input or format. Details: {e}"}, status=status.HTTP_400_BAD_REQUEST)

            # Handle missing dependencies (e.g., publishing_engine not installed)
            except ImportError as e:
                 logger.critical(f"ImportError during processing - check publishing_engine installation: {e}", exc_info=True)
                 return Response({"error": "Server configuration error: Required processing module not found."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Handle runtime errors from services (e.g., API call failures, upload issues)
            except RuntimeError as e:
                 logger.error(f"Runtime error during processing: {e}", exc_info=True)
                 # Default to 500 Internal Server Error
                 status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                 # If error message suggests an upstream issue (GCS, WeChat), return 502 Bad Gateway
                 if "GCS" in str(e) or "WeChat" in str(e): # Basic check
                     status_code = status.HTTP_502_BAD_GATEWAY
                 return Response({"error": f"Processing failed due to a runtime error: {e}"}, status=status_code)

            # Catch any other unexpected exceptions
            except Exception as e:
                logger.exception("Unhandled exception during processing job start")
                return Response(
                    {"error": "An unexpected server error occurred during processing. Please check logs."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Handle serializer validation errors
            logger.warning("UploadSerializer validation failed.", extra={'errors': serializer.errors})
            # Return the validation errors from the serializer
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# --- API View for Confirmation/Publishing ---
class ConfirmPublishAPIView(APIView):
    """
    Handles the POST request to confirm and publish the draft associated
    with a given task_id to WeChat. Expects JSON data: {"task_id": "..."}.
    """
    serializer_class = ConfirmSerializer # Link serializer for DRF docs/UI

    def post(self, request, *args, **kwargs):
        logger.info("Received request: ConfirmPublishAPIView.")
        # Initialize the serializer with request data
        serializer = self.serializer_class(data=request.data)

        # Validate the incoming data
        if serializer.is_valid():
            # Extract validated task_id
            task_id = serializer.validated_data['task_id']
            logger.info(f"Confirmation received for task ID: {task_id}")
            try:
                # Delegate the confirmation and publishing logic to the service layer
                result_data = confirm_and_publish_job(task_id)
                # Log successful completion
                logger.info(f"Publishing job completed for task ID: {task_id}. Status: {result_data.get('status')}")
                # Serialize the successful response data
                response_serializer = ConfirmResponseSerializer(result_data)
                # Return 200 OK response with status and WeChat media ID (if applicable)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            # --- Specific Exception Handling from Service Layer ---
            # Handle case where the job task_id doesn't exist
            except PublishingJob.DoesNotExist:
                 logger.warning(f"Confirm/publish failed: Job not found for task_id: {task_id}")
                 return Response({"error": "Publishing job not found."}, status=status.HTTP_404_NOT_FOUND)

            # Handle validation/state errors (e.g., job not ready, missing files/config)
            except ValueError as e:
                 logger.error(f"Validation/Configuration error during publishing job {task_id}: {e}", exc_info=False) # Log less verbosely for expected validation errors
                 return Response({"error": f"Publishing failed: {e}"}, status=status.HTTP_400_BAD_REQUEST)

            # Handle runtime errors (e.g., WeChat API failures, GCS issues during retry)
            except RuntimeError as e:
                 logger.error(f"Runtime error during publishing job {task_id}: {e}", exc_info=True)
                 # Default to 500 Internal Server Error
                 status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                 # If error suggests upstream issue, return 502 Bad Gateway
                 if "API error" in str(e) or "WeChat" in str(e) or "GCS" in str(e):
                     status_code = status.HTTP_502_BAD_GATEWAY
                 return Response({"error": f"Publishing failed due to API or runtime issue: {e}"}, status=status_code)

            # Handle missing dependencies during the publish step
            except ImportError as e:
                 logger.critical(f"ImportError during publishing - check publishing_engine: {e}", exc_info=True)
                 return Response({"error": "Server configuration error: Required publishing module not found."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Catch any other unexpected exceptions
            except Exception as e:
                logger.exception(f"Unhandled exception during publishing job {task_id}")
                return Response(
                    {"error": "An unexpected server error occurred during publishing. Please check logs."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Handle confirmation request validation errors
            logger.warning("ConfirmSerializer validation failed.", extra={'errors': serializer.errors})
            # Return the validation errors
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
