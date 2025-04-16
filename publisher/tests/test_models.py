# tests/publisher/test_models.py

import pytest
import uuid
from django.utils import timezone
# This import should now work after 'poetry install'
from freezegun import freeze_time
import datetime # Import datetime for creating expected timestamp

from publisher.models import PublishingJob

# Mark tests needing DB access
pytestmark = pytest.mark.django_db

def test_publishing_job_creation_defaults():
    """Test default values upon creating a PublishingJob."""
    job = PublishingJob.objects.create() # Create with minimal args

    assert isinstance(job.task_id, uuid.UUID)
    assert job.status == PublishingJob.Status.PENDING
    assert job.original_markdown_path is None
    assert job.original_cover_image_path is None
    assert job.metadata is None
    assert job.thumb_media_id is None
    assert job.preview_html_path is None
    assert job.wechat_media_id is None
    assert job.error_message is None
    assert job.created_at is not None
    assert job.updated_at is not None
    assert job.published_at is None
    # Timestamps should be close to now
    assert job.created_at <= timezone.now()
    assert job.updated_at <= timezone.now()


@freeze_time("2025-04-14 12:00:00 UTC") # Specify UTC in freeze_time for clarity
def test_publishing_job_timestamp_auto_update():
    """Test that updated_at timestamp changes on save."""
    job = PublishingJob.objects.create()

    # --- CORRECTED: Create expected time directly in UTC ---
    initial_creation_time_utc = datetime.datetime(2025, 4, 14, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Ensure created_at matches the initial frozen UTC time
    assert job.created_at == initial_creation_time_utc
    initial_updated_at = job.updated_at
    assert initial_updated_at == initial_creation_time_utc # Should also be same initially

    # Simulate passage of time and update
    frozen_update_time_str = "2025-04-14 12:05:00 UTC" # Specify UTC
    with freeze_time(frozen_update_time_str):
        # --- CORRECTED: Create expected update time directly in UTC ---
        expected_update_time_utc = datetime.datetime(2025, 4, 14, 12, 5, 0, tzinfo=datetime.timezone.utc)

        job.status = PublishingJob.Status.PROCESSING
        job.save() # This should trigger auto_now=True for updated_at
        job.refresh_from_db() # Reload from DB to be sure

        # Assert update time *inside* the block where save happened
        assert job.updated_at == expected_update_time_utc

    # Assertions *after* the inner freeze block exits
    assert job.updated_at > initial_updated_at
    # Check against the specific UTC time it should have been set to
    assert job.updated_at == expected_update_time_utc
    # created_at should not change on save
    assert job.created_at == initial_creation_time_utc


def test_publishing_job_str_representation():
    """Test the __str__ method of the model."""
    job = PublishingJob.objects.create(status=PublishingJob.Status.PREVIEW_READY)
    # Use the .label property for the display name from choices
    expected_str = f"Job {job.task_id} ({PublishingJob.Status.PREVIEW_READY.label})"
    assert str(job) == expected_str


# Use UTC for consistency in this test too
@freeze_time("2025-01-01 00:00:00 UTC")
def test_publishing_job_ordering():
    """Test that jobs are ordered by creation date descending by default."""
    # Create jobs with distinct timestamps
    job1 = PublishingJob.objects.create() # Time frozen at 2025-01-01 00:00:00 UTC

    with freeze_time("2025-01-01 01:00:00 UTC"):
        job2 = PublishingJob.objects.create() # Created later

    with freeze_time("2024-12-31 23:00:00 UTC"):
        job3 = PublishingJob.objects.create() # Created earlier

    # Queryset respects default ordering defined in Meta ('-created_at')
    jobs = list(PublishingJob.objects.all())

    # Verify the order based on creation time
    assert jobs[0].task_id == job2.task_id # Newest first (01:00 UTC)
    assert jobs[1].task_id == job1.task_id # Middle (00:00 UTC)
    assert jobs[2].task_id == job3.task_id # Oldest first (23:00 UTC previous day)

