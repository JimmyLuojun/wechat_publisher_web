# /Users/junluo/Documents/wechat_publisher_web/wechat_publisher_web/celery.py
"""
Celery configuration for the wechat_publisher_web project.

This sets up the Celery application instance used by workers and tasks.
It should be imported in the project's __init__.py to ensure tasks are discovered.

Requires celery and a broker (like redis or rabbitmq) to be installed.
(e.g., `poetry add celery redis`)
"""
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
# This must be set before creating the app instance.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wechat_publisher_web.settings')

# Create the Celery application instance.
# The first argument is the name of the current module ('wechat_publisher_web')
# which helps Celery auto-discover tasks.
app = Celery('wechat_publisher_web')

# Configure Celery using settings from Django settings.py.
# The 'CELERY_' prefix is used to namespace Celery settings.
# Example settings in settings.py:
# CELERY_BROKER_URL = 'redis://localhost:6379/0'
# CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
# CELERY_ACCEPT_CONTENT = ['json']
# CELERY_TASK_SERIALIZER = 'json'
# CELERY_RESULT_SERIALIZER = 'json'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
# This finds tasks defined in files like 'publisher/tasks.py'.
app.autodiscover_tasks()

# Example task for testing (can be removed later)
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')