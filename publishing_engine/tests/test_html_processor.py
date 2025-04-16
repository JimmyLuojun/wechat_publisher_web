# publishing_engine/tests/test_html_processor.py

import pytest
from pathlib import Path
from unittest.mock import MagicMock, call
import logging # Import logging module

# Module to test
from publishing_engine.core import html_processor

# Configure logging for tests if needed (optional, caplog works independently)
# logging.basicConfig(level=logging.DEBUG) # Keep if useful for general debug
logger = logging.getLogger(__name__) # Keep if used elsewhere

# --- Fixtures ---

@pytest.fixture
def mock_markdown_file(tmp_path):
    """Creates a dummy markdown file with content."""
    md_path = tmp_path / "test_article.md"
    md_content = """---
title: Title
author: Test Author
---
# Title

Some text.

![Alt Text](image.jpg)

## Subheading
"""
    md_path.write_text(md_content, encoding='utf-8')
    # logger.debug(f"Created mock markdown file at: {md_path}") # Optional debug log
    return md_path

@pytest.fixture
def mock_image_file(tmp_path):
    """Creates a dummy image file."""
    img_path = tmp_path / "image.jpg"
    img_path.write_bytes(b"dummy image data")
    # logger.debug(f"Created mock image file at: {img_path}") # Optional debug log
    return img_path

@pytest.fixture
def mock_css_file(tmp_path):
    """Creates a dummy CSS file."""
    css_path = tmp_path / "style.css"
    css_content = "h1 { color: red; }\n" # Content used in tests
    css_path.write_text(css_content, encoding='utf-8')
    # logger.debug(f"Created mock CSS file at: {css_path}") # Optional debug log
    return css_path

# --- Test Cases ---

def test_process_html_basic_conversion(mock_markdown_file, mock_css_file):
    """Test basic Markdown conversion and heading wrapping."""
    md_content = "# Title\n\nPara"
    mock_uploader = MagicMock(return_value=None)

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=str(mock_css_file),
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    assert '<h1><span class="prefix"></span><span class="content">Title</span><span class="suffix"></span></h1>' in result_html
    assert '<p>Para</p>' in result_html
    assert 'h1 { color: red; }' in result_html, "CSS rule h1 { color: red; } not found"
    assert '<div id="nice">' in result_html
    assert '</div>' in result_html
    mock_uploader.assert_not_called()


def test_process_html_with_image_callback_success(mock_markdown_file, mock_image_file, mock_css_file):
    """Test successful image replacement using the callback."""
    md_content = mock_markdown_file.read_text(encoding='utf-8')
    expected_wechat_url = "http://mmbiz.qpic.cn/mmbiz_jpg/fake_url_123"
    mock_uploader = MagicMock(return_value=expected_wechat_url)

    assert mock_image_file.exists()
    assert mock_image_file.name == "image.jpg"

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=str(mock_css_file),
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    assert f'src="{expected_wechat_url}"' in result_html, "Image src attribute not updated with callback URL"
    assert 'src="image.jpg"' not in result_html, "Original image src attribute still present"
    expected_image_path = mock_markdown_file.parent / "image.jpg"
    mock_uploader.assert_called_once_with(expected_image_path)
    assert 'h1 { color: red; }' in result_html, "CSS rule h1 { color: red; } not found"


def test_process_html_with_image_callback_failure(mock_markdown_file, mock_image_file, mock_css_file):
    """Test image replacement when the callback returns None (simulating upload failure)."""
    md_content = mock_markdown_file.read_text(encoding='utf-8')
    mock_uploader = MagicMock(return_value=None)
    assert mock_image_file.exists()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=str(mock_css_file),
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    assert 'src="image.jpg"' in result_html, "Original image src should remain if callback returns None"
    expected_image_path = mock_markdown_file.parent / "image.jpg"
    mock_uploader.assert_called_once_with(expected_image_path)


def test_process_html_image_file_not_found(mock_markdown_file, mock_css_file):
    """Test processing when an image referenced in Markdown does not exist locally."""
    md_content = mock_markdown_file.read_text(encoding='utf-8')
    mock_uploader = MagicMock()
    non_existent_image_path = mock_markdown_file.parent / "image.jpg"
    assert not non_existent_image_path.exists()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=str(mock_css_file),
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    assert 'src="image.jpg"' in result_html, "Original image src should remain if local file not found"
    mock_uploader.assert_not_called()


# !!!!!!!!!! START OF CORRECTION !!!!!!!!!!
def test_process_html_css_not_found(mock_markdown_file, caplog): # Add caplog fixture
    """Test processing when the specified CSS file does not exist."""
    md_content = "# Title\n\nPara"
    non_existent_css_path = "/path/to/non/existent/style.css"
    mock_uploader = MagicMock()

    assert not Path(non_existent_css_path).exists()

    # Set the logging level for the test (optional, but good practice)
    caplog.set_level(logging.WARNING)

    # Call the function that should log the warning
    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=non_existent_css_path,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    # Check that the expected warning message was logged
    # Check caplog.records for detailed info or caplog.text for the full text
    assert "CSS file not found" in caplog.text, "Warning for missing CSS file not logged"
    # Alternatively, check records more specifically:
    # assert any("CSS file not found" in record.getMessage() and record.levelno == logging.WARNING for record in caplog.records)

    # Check that no <style> tag was added
    assert '<style' not in result_html # Check for opening tag is sufficient
    # Basic HTML conversion should still happen
    assert '<h1><span class="prefix"></span><span class="content">Title</span><span class="suffix"></span></h1>' in result_html
    assert '<p>Para</p>' in result_html
# !!!!!!!!!! END OF CORRECTION !!!!!!!!!!


def test_process_html_heading_wrapping(mock_markdown_file):
    """Test that different levels of headings are correctly wrapped."""
    md_content = """
# H1 Title
## H2 Subtitle
### H3 Section
#### H4 Detail
##### H5 More Detail
###### H6 Even More Detail
"""
    mock_uploader = MagicMock()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=None,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    assert '<h1><span class="prefix"></span><span class="content">H1 Title</span><span class="suffix"></span></h1>' in result_html
    assert '<h2><span class="prefix"></span><span class="content">H2 Subtitle</span><span class="suffix"></span></h2>' in result_html
    assert '<h3><span class="prefix"></span><span class="content">H3 Section</span><span class="suffix"></span></h3>' in result_html
    assert '<h4><span class="prefix"></span><span class="content">H4 Detail</span><span class="suffix"></span></h4>' in result_html
    assert '<h5><span class="prefix"></span><span class="content">H5 More Detail</span><span class="suffix"></span></h5>' in result_html
    assert '<h6><span class="prefix"></span><span class="content">H6 Even More Detail</span><span class="suffix"></span></h6>' in result_html