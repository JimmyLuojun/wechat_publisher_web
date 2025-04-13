# /Users/junluo/Documents/wechat_publisher_web/publisher/views.py
"""
Defines API views for the publisher app using Django REST Framework.

Views handle incoming HTTP requests, use serializers for validation,
call service functions for business logic, and return serialized responses.

Views:
- ProcessPreviewAPIView: Handles Request 1 (upload, process, preview).
- ConfirmPublishAPIView: Handles Request 2 (confirm, publish).
"""
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser # For file uploads

from .serializers import (
    UploadSerializer,
    PreviewResponseSerializer,
    ConfirmRequestSerializer,
    ConfirmResponseSerializer
)
from .services import start_processing_job, confirm_and_publish_job
from .models import PublishingJob # For DoesNotExist exception

# Get an instance of a logger
logger = logging.getLogger(__name__)

class ProcessPreviewAPIView(APIView):
    """
    API endpoint to handle the initial upload, processing, and preview generation.
    Accepts POST requests with multipart/form-data.
    """
    # Use parsers that handle file uploads
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        """
        Handles POST request for processing and preview.

        Expects 'markdown_file' and 'cover_image' in the request data.
        """
        logger.info("Received request for ProcessPreviewAPIView")
        serializer = UploadSerializer(data=request.data)

        if serializer.is_valid():
            logger.debug("UploadSerializer is valid.")
            markdown_file = serializer.validated_data['markdown_file']
            cover_image = serializer.validated_data['cover_image']

            try:
                # Call the service function to handle the core logic
                result_data = start_processing_job(markdown_file, cover_image)
                logger.info("Processing job started successfully for task: %s", result_data.get('task_id'))

                # Serialize the successful response
                response_serializer = PreviewResponseSerializer(result_data)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            except ValueError as ve:
                # Handle configuration errors or validation errors from services
                logger.error("ValueError during processing: %s", ve, exc_info=True)
                return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
            except ImportError as ie:
                 # Handle issues with publishing_engine not being found
                 logger.error("ImportError during processing: %s", ie, exc_info=True)
                 return Response({"error": "Internal configuration error: Publishing engine not available."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                # Catch unexpected errors from the service layer
                logger.exception("Unhandled exception during processing: %s", e)
                # Return a generic server error
                return Response({"error": "An unexpected error occurred during processing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Input validation failed
            logger.warning("UploadSerializer validation failed: %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfirmPublishAPIView(APIView):
    """
    API endpoint to handle the confirmation and final publishing to WeChat drafts.
    Accepts POST requests with JSON data containing the 'task_id'.
    """
    # Assuming JSON input for this endpoint
    # parser_classes = (JSONParser,) # Explicitly set if needed

    def post(self, request, *args, **kwargs):
        """
        Handles POST request for confirming and publishing.

        Expects 'task_id' in the request data.
        """
        logger.info("Received request for ConfirmPublishAPIView")
        serializer = ConfirmRequestSerializer(data=request.data)

        if serializer.is_valid():
            task_id = serializer.validated_data['task_id']
            logger.debug("ConfirmRequestSerializer is valid for task_id: %s", task_id)

            try:
                # Call the service function to handle the confirmation logic
                result_data = confirm_and_publish_job(task_id)
                logger.info("Confirmation and publish successful for task: %s", task_id)

                # Serialize the successful response
                response_serializer = ConfirmResponseSerializer(result_data)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            except PublishingJob.DoesNotExist:
                logger.warning("Job not found for task_id: %s during confirmation.", task_id)
                return Response({"error": f"Publishing job with ID {task_id} not found."}, status=status.HTTP_404_NOT_FOUND)
            except ValueError as ve:
                # Handle errors like wrong job state or missing config
                logger.error("ValueError during confirmation for task %s: %s", task_id, ve, exc_info=True)
                return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
            except ImportError as ie:
                 # Handle issues with publishing_engine not being found
                 logger.error("ImportError during confirmation: %s", ie, exc_info=True)
                 return Response({"error": "Internal configuration error: Publishing engine not available."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                # Catch unexpected errors from the service layer
                logger.exception("Unhandled exception during confirmation for task %s: %s", task_id, e)
                # Return a generic server error
                return Response({"error": "An unexpected error occurred during publishing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Input validation failed
            logger.warning("ConfirmRequestSerializer validation failed: %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)