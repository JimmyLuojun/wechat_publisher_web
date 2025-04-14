# /Users/junluo/Documents/wechat_publisher_web/publisher/tests/test_models.py
"""
Tests for the models defined in the publisher app.
"""
import uuid
import pytest
from django.utils import timezone
from mixer.backend.django import mixer # Import mixer

# Import the model to be tested
from ..models import PublishingJob

# Mark all tests in this module to use the database
pytestmark = pytest.mark.django_db

def test_publishing_job_creation_defaults():
    """Test that a PublishingJob instance gets correct default values."""
    # Mixer creates an instance with default/random values for non-specified fields
    job = mixer.blend(PublishingJob)

    assert isinstance(job.task_id, uuid.UUID)
    assert job.status == PublishingJob.Status.PENDING # Check default status
    assert job.metadata is None # Check default
    assert job.thumb_media_id is None
    assert job.wechat_media_id is None
    assert job.error_message is None
    assert job.created_at is not None
    assert job.updated_at is not None
    assert job.created_at <= timezone.now()
    assert job.updated_at <= timezone.now()

def test_publishing_job_str_representation():
    """Test the __str__ method of the PublishingJob model."""
    task_id = uuid.uuid4()
    # Create instance with specific values needed for __str__
    job = mixer.blend(PublishingJob, task_id=task_id, status=PublishingJob.Status.PREVIEW_READY)
    expected_str = f"Publishing Job {task_id} ({PublishingJob.Status.PREVIEW_READY.label})"
    assert str(job) == expected_str

def test_publishing_job_status_choices():
    """Test that status choices are accessible."""
    assert PublishingJob.Status.PUBLISHED == 'PUBLISHED'
    assert PublishingJob.Status.PUBLISHED.label == 'Published Successfully' # Check label translation might need setup

def test_publishing_job_ordering():
    """Test the default ordering defined in Meta."""
    job1 = mixer.blend(PublishingJob)
    # Ensure subsequent jobs have slightly later timestamps
    job2 = mixer.blend(PublishingJob, created_at=timezone.now() + timezone.timedelta(seconds=1))
    job3 = mixer.blend(PublishingJob, created_at=timezone.now() + timezone.timedelta(seconds=2))

    # QuerySet should be ordered by -created_at (newest first)
    jobs = PublishingJob.objects.all()
    assert jobs[0] == job3
    assert jobs[1] == job2
    assert jobs[2] == job1

def test_publishing_job_metadata_field():
    """Test storing and retrieving JSON data (requires DB support or JSON string fallback)."""
    metadata = {"title": "Test Title", "author": "Test Author", "tags": ["test", "django"]}
    job = mixer.blend(PublishingJob, metadata=metadata)
    job.refresh_from_db() # Ensure data is saved and retrieved
    assert job.metadata == metadata
    assert job.metadata["title"] == "Test Title"