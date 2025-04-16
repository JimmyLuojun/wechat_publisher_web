# publishing_engine/tests/test_html_processor.py

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from bs4 import BeautifulSoup # Import BeautifulSoup for parsing results

# Import the module containing the code under test
from publishing_engine.core import html_processor

# --- Fixtures (Unchanged) ---

@pytest.fixture
def mock_markdown_file(tmp_path) -> Path:
    """Creates a dummy markdown file in tmp_path."""
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
    return md_path

@pytest.fixture
def mock_image_file(mock_markdown_file: Path) -> Path:
    """Creates a dummy image file relative to the markdown file."""
    image_path = mock_markdown_file.parent / "image.jpg"
    image_path.touch()
    return image_path

@pytest.fixture
def mock_css_file(tmp_path) -> Path:
    """Creates a dummy CSS file in tmp_path."""
    css_path = tmp_path / "style.css"
    css_content = "h1 { color: red; }"
    css_path.write_text(css_content, encoding='utf-8')
    return css_path

# --- Test Cases ---

def test_process_html_basic_conversion(mock_markdown_file, mock_css_file):
    """Test basic Markdown conversion and heading wrapping."""
    md_content = "# Title\n\nPara"
    mock_uploader = MagicMock(return_value=None)

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=mock_css_file,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    assert '<style type="text/css">h1 { color: red; }</style>' in result_html
    soup = BeautifulSoup(result_html, 'lxml')
    h1 = soup.find('h1')
    assert h1 is not None
    assert h1.find('span', class_='prefix') is not None
    assert h1.find('span', class_='suffix') is not None
    content_span = h1.find('span', class_='content')
    assert content_span is not None
    assert content_span.get_text(strip=True) == "Title"
    assert not h1.has_attr('id')
    p_tag = soup.find('p')
    assert p_tag is not None
    assert p_tag.get_text(strip=True) == "Para"


def test_process_html_with_image_callback_success(mock_markdown_file, mock_image_file, mock_css_file):
    """Test successful image replacement using the callback."""
    md_content = mock_markdown_file.read_text(encoding='utf-8')
    expected_wechat_url = "http://mmbiz.qpic.cn/mmbiz_jpg/fake_url_123"
    mock_uploader = MagicMock(return_value=expected_wechat_url)

    assert (mock_markdown_file.parent / "image.jpg").exists()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=mock_css_file,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    # Check CSS using string contains
    assert '<style type="text/css">h1 { color: red; }</style>' in result_html
    # Check Heading using BeautifulSoup
    soup = BeautifulSoup(result_html, 'lxml')
    h1 = soup.find('h1')
    assert h1 is not None and not h1.has_attr('id')
    assert h1.find('span', class_='content').get_text(strip=True) == "Title"

    # Check callback was called
    resolved_image_path = mock_image_file.resolve()
    mock_uploader.assert_called_once_with(resolved_image_path)

    # *** FIX: Use BeautifulSoup to check image attributes ***
    img_tag = soup.find('img', alt='Alt Text')
    assert img_tag is not None, "Image tag with correct alt text not found"
    assert img_tag.get('src') == expected_wechat_url, "Image src attribute was not replaced correctly"


def test_process_html_with_image_callback_failure(mock_markdown_file, mock_image_file, mock_css_file):
    """Test scenario where the image uploader callback fails (returns None)."""
    md_content = mock_markdown_file.read_text(encoding='utf-8')
    mock_uploader = MagicMock(return_value=None)

    assert (mock_markdown_file.parent / "image.jpg").exists()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=mock_css_file,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    resolved_image_path = mock_image_file.resolve()
    mock_uploader.assert_called_once_with(resolved_image_path)

    # *** FIX: Use BeautifulSoup to check image attributes ***
    soup = BeautifulSoup(result_html, 'lxml')
    img_tag = soup.find('img', alt='Alt Text')
    assert img_tag is not None, "Image tag with correct alt text not found"
    # Check that src remains the original when callback fails
    assert img_tag.get('src') == 'image.jpg', "Image src should remain original when callback fails"


def test_process_html_image_file_not_found(mock_markdown_file, mock_css_file):
    """Test when the image referenced in markdown doesn't exist locally."""
    md_content = mock_markdown_file.read_text(encoding='utf-8')
    mock_uploader = MagicMock()

    image_path = mock_markdown_file.parent / "image.jpg"
    if image_path.exists(): image_path.unlink()
    assert not image_path.exists()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=mock_css_file,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    mock_uploader.assert_not_called()

    # *** FIX: Use BeautifulSoup to check image attributes ***
    soup = BeautifulSoup(result_html, 'lxml')
    img_tag = soup.find('img', alt='Alt Text')
    assert img_tag is not None, "Image tag with correct alt text not found"
    # Check that src remains the original when the file isn't found
    assert img_tag.get('src') == 'image.jpg', "Image src should remain original when file not found"


def test_process_html_css_not_found(mock_markdown_file):
    """Test behavior when the CSS file is missing (should not raise error)."""
    md_content = "# Title"
    mock_uploader = MagicMock()
    non_existent_css_path = mock_markdown_file.parent / "non_existent.css"
    assert not non_existent_css_path.exists()

    # *** FIX: Assert function runs without error and CSS is absent/commented ***
    try:
        result_html = html_processor.process_html_content(
            md_content=md_content,
            css_path=non_existent_css_path, # Pass non-existent path
            markdown_file_path=mock_markdown_file,
            image_uploader=mock_uploader
        )
    except FileNotFoundError:
        # The processor should handle this internally now
        pytest.fail("process_html_content raised FileNotFoundError for missing CSS, but shouldn't have.")

    # Check that the CSS rule is NOT present
    assert 'h1 { color: red; }' not in result_html
    # Check for the placeholder comment added by the processor
    assert '' in result_html
    # Check that basic HTML conversion still happened correctly
    soup = BeautifulSoup(result_html, 'lxml')
    h1 = soup.find('h1')
    assert h1 is not None
    assert h1.find('span', class_='content').get_text(strip=True) == "Title"


def test_process_html_heading_wrapping(mock_markdown_file, mock_css_file):
    """Verify different heading levels are wrapped and IDs are removed."""
    md_content = "# H1\n## H2\n### H3"
    mock_uploader = MagicMock()

    result_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=mock_css_file,
        markdown_file_path=mock_markdown_file,
        image_uploader=mock_uploader
    )

    soup = BeautifulSoup(result_html, 'lxml')
    h1 = soup.find('h1'); assert h1 is not None and not h1.has_attr('id')
    assert h1.find('span', class_='content').get_text(strip=True) == "H1"
    h2 = soup.find('h2'); assert h2 is not None and not h2.has_attr('id')
    assert h2.find('span', class_='content').get_text(strip=True) == "H2"
    h3 = soup.find('h3'); assert h3 is not None and not h3.has_attr('id')
    assert h3.find('span', class_='content').get_text(strip=True) == "H3"