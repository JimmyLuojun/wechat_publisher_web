# publisher/tests/test_frontend_upload.py

import pytest
import asyncio
from pathlib import Path
from playwright.async_api import Page, expect # Use async_api consistently

# Mark all tests in this module to use the django_db and run with asyncio
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.asyncio
]

# --- Helper Fixture to create dummy files ---
@pytest.fixture
def dummy_files(tmp_path: Path) -> dict:
    """Creates dummy markdown, cover image, and content image files."""
    md_path = tmp_path / "test_article.md"
    md_path.write_text("---\ntitle: Test Title\nauthor: Test Author\n---\n# Content\n![img](content_image.jpg)")

    cover_path = tmp_path / "cover.jpg"
    # Using bytes is slightly better for image-like files
    cover_path.write_bytes(b"dummy cover image data")

    content_img_path = tmp_path / "content_image.jpg"
    content_img_path.write_bytes(b"dummy content image data")

    return {
        "markdown": md_path,
        "cover": cover_path,
        "content": content_img_path
    }

# --- Test Cases (All tests using 'page' should be async) ---

async def test_initial_page_load(page: Page, live_server):
    """Test the initial state of the upload form."""
    print("\n>>> test_initial_page_load: START")
    upload_url = f"{live_server.url}/publisher/upload/"
    print(f"!!! Attempting to navigate to: {upload_url}")
    print(f">>> test_initial_page_load: Navigating to {upload_url}")
    try:
        # Try simplifying the goto first, remove wait_until
        await page.goto(upload_url, timeout=15000)
        print(">>> test_initial_page_load: Page loaded")
    except Exception as e:
        print(f">>> test_initial_page_load: page.goto FAILED: {e}")
        # Re-raise the exception to ensure the test fails clearly if goto fails
        raise e # Or use pytest.fail(f"page.goto failed: {e}")

    # Check initial elements are present and in correct state
    await expect(page.locator("h1")).to_contain_text("Upload Markdown for WeChat")
    await expect(page.locator("#upload-form")).to_be_visible()
    await expect(page.locator("#markdown_file")).to_be_visible()
    await expect(page.locator("#cover_image")).to_be_visible()
    await expect(page.locator("#content_images")).to_be_visible()
    await expect(page.locator("#submit-button")).to_be_enabled()
    await expect(page.locator("#status p")).to_contain_text("Please select your files")
    await expect(page.locator("#preview-section")).to_be_hidden()
    # Confirm button is initially disabled (as per JS logic)
    await expect(page.locator("#confirm-button")).to_be_disabled()


async def test_successful_process_and_preview(page: Page, live_server, dummy_files):
    """Test the successful upload, processing, and preview flow."""
    upload_url = f"{live_server.url}/publisher/upload/"
    await page.goto(upload_url)

    # Locate elements
    markdown_input = page.locator("#markdown_file")
    cover_input = page.locator("#cover_image")
    content_input = page.locator("#content_images")
    submit_button = page.locator("#submit-button")
    status_div = page.locator("#status")
    preview_section = page.locator("#preview-section")
    preview_link = page.locator("#preview-link")
    confirm_button = page.locator("#confirm-button")

    # Set input files
    await markdown_input.set_input_files(dummy_files["markdown"])
    await cover_input.set_input_files(dummy_files["cover"])
    await content_input.set_input_files(dummy_files["content"])

    # Click the process button
    await submit_button.click()

    # Assert intermediate state (processing)
    # Increased timeout slightly as processing might take a moment
    await expect(status_div).to_contain_text("Processing your upload", timeout=3000)
    await expect(submit_button).to_have_text("Processing...")
    await expect(submit_button).to_be_disabled()
    await expect(confirm_button).to_be_disabled() # Should remain disabled

    # Assert final state after successful processing (wait for JS to update DOM)
    # Playwright's expect has auto-waiting built-in
    # Longer timeout for processing which involves file saving, API calls etc.
    await expect(status_div).to_contain_text("Processing complete! Preview is ready.", timeout=15000)
    await expect(status_div).to_have_class("success")
    await expect(submit_button).to_have_text("Process & Preview")
    await expect(submit_button).to_be_enabled()

    # *** THE KEY ASSERTION FOR YOUR FIX ***
    await expect(confirm_button).to_be_enabled(timeout=5000) # Confirm button should now be enabled

    await expect(preview_section).to_be_visible()
    # Use a function with lambda or re.compile for flexible attribute matching
    await expect(preview_link).to_have_attribute("href", lambda href: href.startswith("/media/previews/"))
    await expect(preview_link).to_have_attribute("target", "_blank")
    await expect(confirm_button).to_have_attribute("data-task-id", lambda task_id: len(task_id) > 10) # Check task ID looks like a UUID

async def test_process_missing_markdown(page: Page, live_server, dummy_files):
    """Test the error handling when the markdown file is missing."""
    upload_url = f"{live_server.url}/publisher/upload/"
    await page.goto(upload_url)

    # Locate elements
    cover_input = page.locator("#cover_image")
    submit_button = page.locator("#submit-button")
    status_div = page.locator("#status")
    confirm_button = page.locator("#confirm-button")

    # Set only cover image file
    await cover_input.set_input_files(dummy_files["cover"])

    # Click the process button
    await submit_button.click()

    # Assert error state
    await expect(status_div).to_contain_text("Error: Markdown file is required.")
    await expect(status_div).to_have_class("error")
    await expect(submit_button).to_be_enabled() # Should be re-enabled on error
    await expect(confirm_button).to_be_disabled() # Should remain disabled

async def test_process_missing_cover_image(page: Page, live_server, dummy_files):
    """Test the error handling when the cover image file is missing."""
    upload_url = f"{live_server.url}/publisher/upload/"
    await page.goto(upload_url)

    # Locate elements
    markdown_input = page.locator("#markdown_file")
    submit_button = page.locator("#submit-button")
    status_div = page.locator("#status")
    confirm_button = page.locator("#confirm-button")

    # Set only markdown file
    await markdown_input.set_input_files(dummy_files["markdown"])

    # Click the process button
    await submit_button.click()

    # Assert error state
    await expect(status_div).to_contain_text("Error: Cover image file is required.")
    await expect(status_div).to_have_class("error")
    await expect(submit_button).to_be_enabled()
    await expect(confirm_button).to_be_disabled()


# --- Tests for Confirmation (Simulate successful process first) ---

async def test_successful_confirmation(page: Page, live_server, dummy_files):
    """Test clicking the confirm button after successful processing."""
    upload_url = f"{live_server.url}/publisher/upload/"
    await page.goto(upload_url)

    # --- Perform successful upload first ---
    await page.locator("#markdown_file").set_input_files(dummy_files["markdown"])
    await page.locator("#cover_image").set_input_files(dummy_files["cover"])
    await page.locator("#content_images").set_input_files(dummy_files["content"])
    await page.locator("#submit-button").click()

    # Wait for preview and confirm button to be ready
    confirm_button = page.locator("#confirm-button")
    await expect(confirm_button).to_be_enabled(timeout=15000) # Increased timeout
    # ---------------------------------------

    # --- Mock the API response for /confirm/ ---
    task_id = await confirm_button.get_attribute("data-task-id") # Get the actual task id if needed
    await page.route(f"{live_server.url}/publisher/api/confirm/", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=f'{{"task_id": "{task_id}", "status": "Published", "message": "Success", "wechat_media_id": "WECHAT_MEDIA_ID_123"}}'
    ))
    # -----------------------------------------

    # Click the confirm button
    await confirm_button.click()

    publish_status_p = page.locator("#publish-status")

    # Assert intermediate state (publishing)
    await expect(publish_status_p).to_contain_text("Publishing to WeChat drafts...")
    await expect(confirm_button).to_be_disabled() # Should disable during publish attempt

    # Assert final state after successful confirmation
    await expect(publish_status_p).to_contain_text("Successfully published! WeChat Media ID: WECHAT_MEDIA_ID_123")
    await expect(publish_status_p).to_have_class("success")
    await expect(confirm_button).to_be_disabled() # Stays disabled after success

async def test_failed_confirmation(page: Page, live_server, dummy_files):
    """Test clicking the confirm button when the backend fails."""
    upload_url = f"{live_server.url}/publisher/upload/"
    await page.goto(upload_url)

    # --- Perform successful upload first ---
    await page.locator("#markdown_file").set_input_files(dummy_files["markdown"])
    await page.locator("#cover_image").set_input_files(dummy_files["cover"])
    await page.locator("#content_images").set_input_files(dummy_files["content"])
    await page.locator("#submit-button").click()

    confirm_button = page.locator("#confirm-button")
    await expect(confirm_button).to_be_enabled(timeout=15000) # Increased timeout
    # ---------------------------------------

    # --- Mock a FAILED API response for /confirm/ ---
    await page.route(f"{live_server.url}/publisher/api/confirm/", lambda route: route.fulfill(
        status=500, # Or 400, 404 etc.
        content_type="application/json",
        body='{"error": "Backend publishing error"}'
    ))
    # ---------------------------------------------

    # Click the confirm button
    await confirm_button.click()

    publish_status_p = page.locator("#publish-status")

    # Assert intermediate state (publishing)
    await expect(publish_status_p).to_contain_text("Publishing to WeChat drafts...")
    await expect(confirm_button).to_be_disabled()

    # Assert final state after failed confirmation
    await expect(publish_status_p).to_contain_text("Publishing failed: Backend publishing error")
    await expect(publish_status_p).to_have_class("error")

    # *** Assert that the confirm button is RE-ENABLED for retry (as per JS logic) ***
    await expect(confirm_button).to_be_enabled()
    await expect(page.locator("#submit-button")).to_be_enabled() # Check submit button is also re-enabled