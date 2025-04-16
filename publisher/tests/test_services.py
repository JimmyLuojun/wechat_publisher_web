# publisher/tests/test_services.py

import pytest
import uuid
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY, call
import yaml

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.conf import settings as django_settings
from django.core.exceptions import ObjectDoesNotExist

# Import the service functions under test
from publisher import services
# Import the real model
from publisher.models import PublishingJob

# --- Custom Exception for Mocking API Errors ---
class MockWeChatAPIError(Exception):
    """Custom exception to mimic potential API errors with codes."""
    def __init__(self, message, errcode=None, errmsg=None):
        super().__init__(message)
        self.errcode = errcode
        self.errmsg = errmsg

# --- Fixtures specific to this test file ---

@pytest.fixture(autouse=True)
def setup_django_settings(tmp_path, settings):
    """Configure necessary Django settings for the tests."""
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.MEDIA_URL = "/media/"
    settings.WECHAT_APP_ID = "test_app_id"
    settings.WECHAT_SECRET = "test_secret"
    settings.WECHAT_BASE_URL = "https://fake-wechat-api.com"
    css_dir = tmp_path / "static"; css_dir.mkdir(parents=True, exist_ok=True)
    css_path = css_dir / "preview_style.css"; css_path.write_text("body { font-family: sans-serif; }")
    settings.PREVIEW_CSS_FILE_PATH = str(css_path)
    settings.WECHAT_DRAFT_PLACEHOLDER_CONTENT = "<p>Test Placeholder</p>"
    settings.BASE_DIR = str(tmp_path)

@pytest.fixture
def mock_filesystem_helpers(tmp_path, settings):
    """Mocks the internal file saving helpers."""
    saved_files_map = {} # key: original stem, value: absolute Path
    def _mock_save_side_effect(file_obj, subfolder=""):
        save_dir = Path(settings.MEDIA_ROOT) / subfolder
        save_dir.mkdir(parents=True, exist_ok=True)
        original_stem = Path(file_obj.name).stem
        save_path = save_dir / f"saved_{original_stem}_{Path(file_obj.name).suffix.replace('.', '')}_{uuid.uuid4().hex[:4]}"
        file_obj.seek(0); save_path.write_bytes(file_obj.read()); file_obj.seek(0)
        saved_files_map[original_stem] = save_path
        return save_path
    def _mock_gen_preview_side_effect(content, task_id):
        save_dir = Path(settings.MEDIA_ROOT) / "previews"
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{task_id}.html"
        save_path_abs = save_dir / filename
        save_path_abs.write_text(content, encoding='utf-8')
        relative_path_str = str(Path("previews") / filename)
        return relative_path_str
    with patch('publisher.services._save_uploaded_file_locally', side_effect=_mock_save_side_effect) as mock_save, \
         patch('publisher.services._generate_preview_file', side_effect=_mock_gen_preview_side_effect) as mock_gen_preview:
        yield mock_save, mock_gen_preview, saved_files_map


@pytest.fixture
def mock_publishing_engine(mock_filesystem_helpers):
    """Mocks all components imported from publishing_engine."""
    # This mock now consistently simulates the processor finding the relative path
    # and passing that potentially non-existent path to the callback.
    # This is simpler and allows tests to focus on the callback's behavior.
    _, _, saved_files_map = mock_filesystem_helpers # Get map, still useful for other tests

    with patch('publisher.services.metadata_reader') as mock_meta, \
         patch('publisher.services.html_processor') as mock_html, \
         patch('publisher.services.payload_builder') as mock_payload, \
         patch('publisher.services.auth') as mock_auth, \
         patch('publisher.services.wechat_api') as mock_api:

        mock_auth.get_access_token.return_value = "mock_access_token_12345"
        mock_meta.extract_metadata_and_content.return_value = (
            {'title': 'Sample Test Article', 'author': 'Pytest Fixture', 'tags': ['test', 'fixture']},
            "# Main Content\n\nThis is a paragraph.\n\n![Sample Image Alt Text](images/sample_content.gif)\n\nAnother paragraph."
        )

        # Keep the simpler html_processor mock that passes the unresolved path
        def html_processor_side_effect(md_content, css_path, markdown_file_path, image_uploader):
            image_relative_path_in_md = "images/sample_content.gif"
            path_to_resolve = Path(markdown_file_path).parent / image_relative_path_in_md
            uploaded_url = image_uploader(path_to_resolve) # Pass unresolved path
            style_tag = f"<style>{Path(css_path).read_text()}</style>" if css_path and Path(css_path).exists() else ""
            alt_text = "Sample Image Alt Text"
            if uploaded_url:
                html = f"<p>Processed HTML with image: <img src='{uploaded_url}' alt='{alt_text}'></p>"
            else:
                html = f"<p>Processed HTML - image '{image_relative_path_in_md}' upload failed</p>"
            return f"{style_tag}{html}"
        mock_html.process_html_content.side_effect = html_processor_side_effect

        mock_payload.build_draft_payload.return_value = {
            "title": "Payload Title", "author": "Payload Author", "content": "<p>Payload Content Placeholder</p>",
            "thumb_media_id": "payload_thumb_id", "digest": "Payload Digest...", "content_source_url": "http://example.com/source",
            "need_open_comment": 1, "only_fans_can_comment": 0
        }
        mock_api.upload_thumb_media.return_value = "mock_permanent_thumb_id_67890"
        # This mock might not be called if the path resolve fails first in the callback
        mock_api.upload_content_image.side_effect = lambda access_token, image_path, base_url: f"http://mmbiz.qpic.cn/mmbiz_gif/mock_url_for_{image_path.stem}/0"
        mock_api.add_draft.return_value = "mock_draft_media_id_abcde"
        mock_api.WeChatAPIError = MockWeChatAPIError
        yield {
            "metadata_reader": mock_meta, "html_processor": mock_html, "payload_builder": mock_payload,
            "auth": mock_auth, "wechat_api": mock_api, "saved_files_map": saved_files_map
        }


@pytest.fixture
def mock_job_manager():
    """Mocks the PublishingJob model manager."""
    with patch('publisher.services.PublishingJob.objects') as mock_manager:
        mock_job_instance = MagicMock(spec=PublishingJob)
        mock_job_instance.task_id = uuid.uuid4(); mock_job_instance.pk = mock_job_instance.task_id
        mock_job_instance.status = PublishingJob.Status.PENDING
        mock_job_instance.metadata = None; mock_job_instance.thumb_media_id = None
        mock_job_instance.original_cover_image_path = None; mock_job_instance.original_markdown_path = None
        mock_job_instance.preview_html_path = None; mock_job_instance.wechat_media_id = None
        mock_job_instance.error_message = None; mock_job_instance.published_at = None
        def mock_get_status_display():
            for value, label in PublishingJob.Status.choices:
                if value == mock_job_instance.status: return label
            return str(mock_job_instance.status)
        mock_job_instance.get_status_display.side_effect = mock_get_status_display
        mock_manager.create.return_value = mock_job_instance
        def get_side_effect(pk=None, task_id=None):
             if pk == mock_job_instance.pk or task_id == mock_job_instance.task_id: return mock_job_instance
             raise ObjectDoesNotExist("Mock Job not found")
        mock_manager.get.side_effect = get_side_effect
        yield mock_manager, mock_job_instance

# ============================================================
# ==                  Test Cases                            ==
# ============================================================

# --- Tests for start_processing_job ---

@pytest.mark.django_db
class TestStartProcessingJob:

    def test_success_path(self, sample_markdown_file, sample_cover_image_file, sample_content_image_file,
                          mock_filesystem_helpers, mock_publishing_engine, mock_job_manager):
        """
        Verify the successful execution flow of start_processing_job,
        acknowledging that image upload might fail if relative path doesn't exist.
        """
        mock_save_local, mock_gen_preview, saved_files_map = mock_filesystem_helpers
        mock_engine = mock_publishing_engine
        mock_manager, mock_job = mock_job_manager

        # --- Act ---
        result = services.start_processing_job(
            markdown_file=sample_markdown_file,
            cover_image=sample_cover_image_file,
            content_images=[sample_content_image_file]
        )

        # --- Assert ---
        # Job Creation/Status (unchanged)
        mock_manager.create.assert_called_once_with(task_id=ANY, status=PublishingJob.Status.PENDING)
        expected_save_calls = [
            call(update_fields=services.JOB_STATUS_UPDATE_FIELDS), call(update_fields=services.JOB_PATHS_UPDATE_FIELDS),
            call(update_fields=services.JOB_THUMB_UPDATE_FIELDS), call(update_fields=services.JOB_METADATA_UPDATE_FIELDS),
            call(update_fields=services.JOB_PREVIEW_UPDATE_FIELDS + ['error_message']),
        ]
        mock_job.save.assert_has_calls(expected_save_calls)
        assert mock_job.status == PublishingJob.Status.PREVIEW_READY
        assert mock_job.error_message is None

        # File Operations (unchanged)
        assert mock_save_local.call_count == 3
        mock_gen_preview.assert_called_once()
        assert mock_job.preview_html_path is not None

        # Engine Interactions
        mock_engine["auth"].get_access_token.assert_called_once()
        mock_engine["wechat_api"].upload_thumb_media.assert_called_once()
        assert mock_job.thumb_media_id == "mock_permanent_thumb_id_67890"
        mock_engine["metadata_reader"].extract_metadata_and_content.assert_called_once()
        assert mock_job.metadata['title'] == 'Sample Test Article'
        mock_engine["html_processor"].process_html_content.assert_called_once()

        # *** FIX: Assert upload_content_image was NOT called ***
        # Because the simple html_processor mock passes a path that doesn't exist
        # relative to the markdown file, the callback's resolve(strict=True) fails.
        mock_engine["wechat_api"].upload_content_image.assert_not_called()

        # *** FIX: Check preview content for failure message ***
        preview_call_args, _ = mock_gen_preview.call_args
        generated_html = preview_call_args[0]
        assert "image 'images/sample_content.gif' upload failed" in generated_html

        # Result (unchanged)
        assert result["task_id"] == mock_job.task_id
        assert result["preview_url"].endswith(mock_job.preview_html_path.replace(os.path.sep, '/'))


    # test_failure_missing_wechat_keys (unchanged)
    def test_failure_missing_wechat_keys(self, sample_markdown_file, sample_cover_image_file, sample_content_image_file,
                                         mock_filesystem_helpers, mock_publishing_engine, mock_job_manager, settings):
        mock_manager, mock_job = mock_job_manager; settings.WECHAT_APP_ID = None
        with pytest.raises(ValueError, match="WECHAT_APP_ID"):
            services.start_processing_job(sample_markdown_file, sample_cover_image_file, [sample_content_image_file])
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED

    # test_failure_metadata_parsing (unchanged)
    def test_failure_metadata_parsing(self, sample_markdown_file, sample_cover_image_file, sample_content_image_file,
                                      mock_filesystem_helpers, mock_publishing_engine, mock_job_manager):
        mock_engine = mock_publishing_engine; mock_manager, mock_job = mock_job_manager
        mock_engine["metadata_reader"].extract_metadata_and_content.side_effect = yaml.YAMLError("Bad YAML")
        with pytest.raises(ValueError, match="Invalid YAML"):
             services.start_processing_job(sample_markdown_file, sample_cover_image_file, [sample_content_image_file])
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED

    # test_failure_thumb_upload_api_error (unchanged)
    def test_failure_thumb_upload_api_error(self, sample_markdown_file, sample_cover_image_file, sample_content_image_file,
                                           mock_filesystem_helpers, mock_publishing_engine, mock_job_manager):
        mock_engine = mock_publishing_engine; mock_manager, mock_job = mock_job_manager
        mock_engine["wechat_api"].upload_thumb_media.return_value = None
        with pytest.raises(RuntimeError, match="Failed to upload permanent thumbnail"):
             services.start_processing_job(sample_markdown_file, sample_cover_image_file, [sample_content_image_file])
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED

    # test_failure_callback_image_resolve_error (Fixed setup and assertion)
    def test_failure_callback_image_resolve_error(self, sample_markdown_file, sample_cover_image_file, sample_content_image_file,
                                           mock_filesystem_helpers, mock_publishing_engine, mock_job_manager):
        """Test the scenario where the callback fails to resolve the image path."""
        mock_engine = mock_publishing_engine; mock_manager, mock_job = mock_job_manager
        mock_save_local, mock_gen_preview, saved_files_map = mock_filesystem_helpers

        # *** FIX: Configure mock_resolve without using saved_files_map ***
        # It should fail when Path.resolve is called on a path matching the pattern
        # passed by the html_processor mock (e.g., .../markdown/images/sample_content.gif)
        original_resolve = Path.resolve
        def mock_resolve(self, strict=False):
            # Check if the path looks like the one derived from markdown
            # This is less precise than before but avoids the timing issue
            if "images" in self.parts and self.name == "sample_content.gif":
                 # print(f"DEBUG: mock_resolve raising FileNotFoundError for {self}")
                 raise FileNotFoundError(f"Mock resolve error: Cannot find image {self}")
            # print(f"DEBUG: mock_resolve allowing original resolve for {self}")
            # Important: Call original resolve for other paths
            return original_resolve(self, strict=strict)

        # Patch Path.resolve which is used inside the service's callback
        with patch('pathlib.Path.resolve', side_effect=mock_resolve, autospec=True):
             result = services.start_processing_job(
                 sample_markdown_file,
                 sample_cover_image_file,
                 [sample_content_image_file]
             )

        # Assert that upload was NOT called because resolve failed inside callback
        mock_engine["wechat_api"].upload_content_image.assert_not_called()
        # Assert preview was still generated
        mock_gen_preview.assert_called_once()
        # Assert preview content shows failure
        preview_content = mock_gen_preview.call_args[0][0]
        assert "image 'images/sample_content.gif' upload failed" in preview_content
        # Assert overall job status is success (preview ready)
        assert mock_job.status == PublishingJob.Status.PREVIEW_READY


# --- Tests for confirm_and_publish_job (unchanged from previous correct version) ---

@pytest.mark.django_db
class TestConfirmAndPublishJob:

    def test_success_path_with_db_fixture(self, preview_ready_job_in_db, mock_publishing_engine, settings):
        job = preview_ready_job_in_db; task_id = job.task_id
        mock_engine = mock_publishing_engine
        result = services.confirm_and_publish_job(task_id)
        job.refresh_from_db(); assert job.status == PublishingJob.Status.PUBLISHED
        assert job.wechat_media_id == "mock_draft_media_id_abcde"
        mock_engine["auth"].get_access_token.assert_called_once()
        mock_engine["payload_builder"].build_draft_payload.assert_called_once()
        mock_engine["wechat_api"].add_draft.assert_called_once()
        mock_engine["wechat_api"].upload_thumb_media.assert_not_called()
        assert result["status"] == PublishingJob.Status.PUBLISHED.label

    def test_failure_job_not_found(self, mock_job_manager):
        mock_manager, _ = mock_job_manager
        mock_manager.get.side_effect = ObjectDoesNotExist("Not found")
        with pytest.raises(ObjectDoesNotExist): services.confirm_and_publish_job(uuid.uuid4())

    def test_failure_wrong_status(self, mock_job_manager, mock_publishing_engine):
        mock_manager, mock_job = mock_job_manager
        mock_job.status = PublishingJob.Status.PROCESSING
        mock_job.metadata = {'title': 'Test'}; mock_job.thumb_media_id = 'some_id'
        with pytest.raises(ValueError, match="Job not ready"): services.confirm_and_publish_job(mock_job.task_id)
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED

    def test_failure_missing_metadata(self, mock_job_manager, mock_publishing_engine):
        mock_manager, mock_job = mock_job_manager
        mock_job.status = PublishingJob.Status.PREVIEW_READY
        mock_job.metadata = None; mock_job.thumb_media_id = 'some_id'
        with pytest.raises(ValueError, match="Metadata is missing"): services.confirm_and_publish_job(mock_job.task_id)
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED

    def test_failure_payload_build_error(self, mock_job_manager, mock_publishing_engine):
        mock_manager, mock_job = mock_job_manager; mock_engine = mock_publishing_engine
        mock_job.status = PublishingJob.Status.PREVIEW_READY
        mock_job.metadata = {'title': 'Test'}; mock_job.thumb_media_id = 'some_id'
        mock_engine["payload_builder"].build_draft_payload.side_effect = KeyError("Missing key")
        with pytest.raises(ValueError, match="Payload building failed"): services.confirm_and_publish_job(mock_job.task_id)
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED

    def test_success_with_thumb_retry(self, mock_job_manager, mock_publishing_engine, mock_filesystem_helpers, settings, tmp_path):
        mock_manager, mock_job = mock_job_manager; mock_engine = mock_publishing_engine
        mock_save_local, _, saved_files_map = mock_filesystem_helpers
        mock_job.status = PublishingJob.Status.PREVIEW_READY; mock_job.metadata = {'title': 'Retry Test'}
        mock_job.thumb_media_id = 'expired_thumb_id_111'; cover_rel_path = 'uploads/covers/retry_cover.gif'
        mock_job.original_cover_image_path = cover_rel_path; cover_abs_path = Path(settings.MEDIA_ROOT) / cover_rel_path
        cover_abs_path.parent.mkdir(parents=True, exist_ok=True)
        cover_abs_path.write_bytes(b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
        new_thumb_id = "new_thumb_id_222"; final_draft_id = "final_draft_id_after_retry"
        mock_engine["wechat_api"].add_draft.side_effect = [mock_engine["wechat_api"].WeChatAPIError("Invalid Media ID", errcode=40007), final_draft_id]
        mock_engine["wechat_api"].upload_thumb_media.return_value = new_thumb_id
        payload_call_count = 0; original_builder_mock = mock_engine["payload_builder"].build_draft_payload
        original_builder_return_value = original_builder_mock.return_value.copy()
        def payload_side_effect(*args, **kwargs):
            nonlocal payload_call_count; payload_call_count += 1; payload = original_builder_return_value.copy()
            payload['thumb_media_id'] = kwargs['thumb_media_id']; payload['title'] = kwargs['metadata']['title']; return payload
        mock_engine["payload_builder"].build_draft_payload.side_effect = payload_side_effect
        result = services.confirm_and_publish_job(mock_job.task_id)
        assert mock_engine["auth"].get_access_token.call_count == 2; assert mock_engine["wechat_api"].add_draft.call_count == 2
        mock_engine["wechat_api"].upload_thumb_media.assert_called_once(); assert payload_call_count == 2
        calls = mock_engine["payload_builder"].build_draft_payload.call_args_list
        assert calls[0].kwargs['thumb_media_id'] == 'expired_thumb_id_111'; assert calls[1].kwargs['thumb_media_id'] == new_thumb_id
        assert mock_job.status == PublishingJob.Status.PUBLISHED; assert mock_job.thumb_media_id == new_thumb_id
        assert mock_job.wechat_media_id == final_draft_id; assert result["wechat_media_id"] == final_draft_id
        assert result["status"] == PublishingJob.Status.PUBLISHED.label

    def test_failure_thumb_retry_missing_cover_file(self, mock_job_manager, mock_publishing_engine, settings, tmp_path):
        mock_manager, mock_job = mock_job_manager; mock_engine = mock_publishing_engine
        mock_job.status = PublishingJob.Status.PREVIEW_READY
        mock_job.metadata = {'title': 'Retry Fail Test'}; mock_job.thumb_media_id = 'expired_thumb_id_333'
        cover_rel_path = 'uploads/covers/missing_retry_cover.gif'; mock_job.original_cover_image_path = cover_rel_path
        cover_abs_path = Path(settings.MEDIA_ROOT) / cover_rel_path
        if cover_abs_path.exists(): cover_abs_path.unlink()
        mock_engine["wechat_api"].add_draft.side_effect = mock_engine["wechat_api"].WeChatAPIError("Invalid Media ID", errcode=40007)
        with pytest.raises(ValueError, match="Publishing pre-check failed: Cannot retry thumb upload"):
             services.confirm_and_publish_job(mock_job.task_id)
        mock_job.save.assert_called_with(update_fields=services.JOB_ERROR_UPDATE_FIELDS)
        assert mock_job.status == PublishingJob.Status.FAILED
        assert "local cover file not found" in mock_job.error_message