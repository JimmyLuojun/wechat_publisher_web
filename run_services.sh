#!/bin/bash

# Set up environment
echo "Setting up environment..."

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export DJANGO_SETTINGS_MODULE=wechat_publisher_web.settings
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Run services
echo "Running services..."
python -c "
import django
django.setup()
from publisher.services import start_processing_job, confirm_and_publish_job
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Example usage
try:
    # Create a new task ID
    task_id = uuid.uuid4()
    logger.info(f'Created new task ID: {task_id}')
    
    # Example of how to use the services
    logger.info('Example usage:')
    logger.info('1. Start processing job:')
    logger.info('   start_processing_job(task_id, markdown_file, cover_image, content_images)')
    logger.info('2. Confirm and publish job:')
    logger.info('   confirm_and_publish_job(task_id)')
    
except Exception as e:
    logger.error(f'Error running services: {e}', exc_info=True)
" 