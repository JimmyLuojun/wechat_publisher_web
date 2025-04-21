# tests/publishing_engine/core/test_html_processor.py

import pytest
from pathlib import Path
from unittest.mock import MagicMock, call, patch # Use unittest.mock via pytest-mock's mocker
from typing import Dict, Any, Tuple, Callable, Optional # For fixture type hints

from bs4 import BeautifulSoup
from django.conf import settings # For mocking MEDIA_ROOT

# Module to test
from publishing_engine.core import html_processor

# --- Fixtures ---

@pytest.fixture
def mock_uploader(mocker) -> MagicMock:
    """Fixture for a mock image uploader callback (returns Optional[str])."""
    return mocker.MagicMock(return_value="http://wechat.example.com/uploaded_image.jpg")

@pytest.fixture
def tmp_markdown_file(tmp_path: Path) -> Tuple[Path, Path]:
    """Creates a dummy markdown file and returns its path and dir."""
    md_dir = tmp_path / "markdown_files"
    md_dir.mkdir()
    md_file = md_dir / "test_article.md"
    md_file.write_text("Dummy content", encoding='utf-8')
    return md_file, md_dir

@pytest.fixture
def setup_image_files(tmp_path: Path, tmp_markdown_file: Tuple[Path, Path]) -> Dict[str, Any]:
    """Creates dummy image files for testing resolution."""
    md_file, md_dir = tmp_markdown_file
    # Image relative to markdown
    relative_img_dir = md_dir / "images"
    relative_img_dir.mkdir(exist_ok=True)
    relative_img = relative_img_dir / "relative.png"
    relative_img.touch() # Create empty file

    # Image in central media location (simulating structure)
    central_dir = tmp_path / "media" / "uploads" / "content_images"
    central_dir.mkdir(parents=True, exist_ok=True)
    # Simulate a file saved with a unique ID part
    central_img = central_dir / "central_image_abc123.jpg"
    central_img.touch() # Create empty file

    return {
        "md_dir": md_dir,
        "relative_img_path": relative_img,
        "relative_img_src": "images/relative.png", # How it appears in HTML src
        "central_img_path": central_img,
        "central_img_src": "central_image.jpg", # How it might appear in HTML src
        "central_media_root": tmp_path / "media", # Root for settings mock
    }

# --- Tests for Helper Functions ---
# (These passed previously, no changes needed)
def test_read_file_success(tmp_path: Path):
    p = tmp_path / "test.txt"
    expected_content = "Hello World! with Ümlauts"
    p.write_text(expected_content, encoding='utf-8')
    assert html_processor._read_file(p) == expected_content

def test_read_file_not_found(tmp_path: Path):
    p = tmp_path / "nonexistent.txt"
    with pytest.raises(FileNotFoundError):
        html_processor._read_file(p)

def test_read_file_other_error(tmp_path: Path, mocker):
    p = tmp_path / "test.txt"; p.touch()
    mocker.patch('pathlib.Path.read_text', side_effect=OSError("Permission denied"))
    with pytest.raises(OSError):
        html_processor._read_file(p)

def test_wrap_heading_content():
    html = "<h1>Title</h1><h2>Subtitle <em>Emphasis</em></h2><h3></h3><h4><code>Code</code> Title</h4>"
    soup = BeautifulSoup(html, 'html.parser')
    html_processor._wrap_heading_content(soup)
    h1 = soup.find('h1'); h2 = soup.find('h2'); h3 = soup.find('h3'); h4 = soup.find('h4')
    assert str(h1.find('span', class_='content')) == '<span class="content">Title</span>'
    assert str(h2.find('span', class_='content')) == '<span class="content">Subtitle <em>Emphasis</em></span>'
    assert str(h3.find('span', class_='content')) == '<span class="content"></span>' # Corrected assertion
    assert str(h4.find('span', class_='content')) == '<span class="content"><code>Code</code> Title</span>'
    assert h1.find('span', class_='prefix') is not None; assert h1.find('span', class_='suffix') is not None
    assert h4.find('span', class_='prefix') is not None; assert h4.find('span', class_='suffix') is not None

def test_wrap_heading_content_idempotent():
    html = '<h2><span class="prefix"></span><span class="content">Already Wrapped</span><span class="suffix"></span></h2>'
    soup = BeautifulSoup(html, 'html.parser')
    html_processor._wrap_heading_content(soup)
    html_processor._wrap_heading_content(soup)
    assert len(soup.find('h2').find_all('span', class_='content', recursive=False)) == 1
    assert len(soup.find('h2').find_all('span', class_='prefix', recursive=False)) == 1
    assert len(soup.find('h2').find_all('span', class_='suffix', recursive=False)) == 1

def test_remove_heading_ids():
    html = '<h1 id="title-1" class="main">Title</h1><h2 class="sub">Subtitle</h2><h3 id="old-id">Third</h3>'
    soup = BeautifulSoup(html, 'html.parser')
    html_processor._remove_heading_ids(soup)
    assert not soup.find('h1').has_attr('id'); assert soup.find('h1').has_attr('class')
    assert soup.find('h2').has_attr('class'); assert not soup.find('h3').has_attr('id')

def test_extract_body_content_with_body():
    html = "<html><head><title>T</title></head><body><p>Content 1</p><div>Content 2</div></body></html>"
    soup = BeautifulSoup(html, 'html.parser')
    assert html_processor._extract_body_content(soup) == "<p>Content 1</p><div>Content 2</div>"

def test_extract_body_content_without_body():
    html = "<p>Content 1</p><div>Content 2</div>"
    soup = BeautifulSoup(html, 'html.parser')
    assert html_processor._extract_body_content(soup) == "<p>Content 1</p><div>Content 2</div>"


# --- Tests for _find_and_replace_local_images ---
# (No changes needed in these tests based on results)
def test_find_replace_no_images(tmp_markdown_file: Tuple[Path, Path], mock_uploader: MagicMock):
    html = "<p>No images here.</p>"; soup = BeautifulSoup(html, 'html.parser')
    md_file, md_dir = tmp_markdown_file
    html_processor._find_and_replace_local_images(soup, md_dir, mock_uploader)
    assert soup.find('img') is None; mock_uploader.assert_not_called()

def test_find_replace_absolute_url_skipped(tmp_markdown_file: Tuple[Path, Path], mock_uploader: MagicMock):
    html = '<p><img src="http://example.com/image.jpg" alt="Absolute"></p>'; soup = BeautifulSoup(html, 'html.parser')
    md_file, md_dir = tmp_markdown_file
    html_processor._find_and_replace_local_images(soup, md_dir, mock_uploader)
    assert soup.find('img')['src'] == "http://example.com/image.jpg"; mock_uploader.assert_not_called()

def test_find_replace_data_uri_skipped(tmp_markdown_file: Tuple[Path, Path], mock_uploader: MagicMock):
    html = '<p><img src="data:image/png;base64,iVBORw0KG..." alt="Data URI"></p>'; soup = BeautifulSoup(html, 'html.parser')
    md_file, md_dir = tmp_markdown_file
    html_processor._find_and_replace_local_images(soup, md_dir, mock_uploader)
    assert soup.find('img')['src'].startswith("data:image/png;base64,"); mock_uploader.assert_not_called()

def test_find_replace_relative_image_success(mocker, setup_image_files: Dict, mock_uploader: MagicMock):
    img_info = setup_image_files; html = f'<p><img src="{img_info["relative_img_src"]}" alt="Relative"></p>'
    soup = BeautifulSoup(html, 'html.parser'); mocker.patch('django.conf.settings.MEDIA_ROOT', img_info["central_media_root"])
    html_processor._find_and_replace_local_images(soup, img_info["md_dir"], mock_uploader)
    assert soup.find('img')['src'] == mock_uploader.return_value; mock_uploader.assert_called_once_with(img_info["relative_img_path"])

def test_find_replace_central_image_success(mocker, setup_image_files: Dict, mock_uploader: MagicMock):
    img_info = setup_image_files; html = f'<p><img src="{img_info["central_img_src"]}" alt="Central"></p>'
    soup = BeautifulSoup(html, 'html.parser'); mocker.patch('django.conf.settings.MEDIA_ROOT', img_info["central_media_root"])
    html_processor._find_and_replace_local_images(soup, img_info["md_dir"], mock_uploader)
    assert soup.find('img')['src'] == mock_uploader.return_value; mock_uploader.assert_called_once_with(img_info["central_img_path"])

def test_find_replace_image_not_found(mocker, setup_image_files: Dict, mock_uploader: MagicMock):
    img_info = setup_image_files; original_src = "nonexistent/image.png"; html = f'<p><img src="{original_src}" alt="Not Found"></p>'
    soup = BeautifulSoup(html, 'html.parser'); mocker.patch('django.conf.settings.MEDIA_ROOT', img_info["central_media_root"])
    html_processor._find_and_replace_local_images(soup, img_info["md_dir"], mock_uploader)
    assert soup.find('img')['src'] == original_src; mock_uploader.assert_not_called()

def test_find_replace_uploader_fails(mocker, setup_image_files: Dict, mock_uploader: MagicMock):
    img_info = setup_image_files; html = f'<p><img src="{img_info["relative_img_src"]}" alt="Upload Fail"></p>'
    soup = BeautifulSoup(html, 'html.parser'); mocker.patch('django.conf.settings.MEDIA_ROOT', img_info["central_media_root"])
    mock_uploader.return_value = None # Simulate upload failure
    html_processor._find_and_replace_local_images(soup, img_info["md_dir"], mock_uploader)
    assert soup.find('img')['src'] == img_info["relative_img_src"]; mock_uploader.assert_called_once_with(img_info["relative_img_path"])

# --- Tests for process_html_content (Integration) ---

def test_process_html_content_basic(tmp_markdown_file: Tuple[Path, Path], mock_uploader: MagicMock, mocker):
    """Test the overall processing flow: MD -> HTML -> Transformations -> Image Upload."""
    md_content = """
# Title

Some text with an image: ![Relative Alt Text](images/relative.png)

* List item
    """
    md_file, md_dir = tmp_markdown_file
    css_path = None

    img_path = md_dir / "images" / "relative.png"
    img_path.parent.mkdir(exist_ok=True)
    img_path.touch()

    mocker.patch('django.conf.settings.MEDIA_ROOT', tmp_markdown_file[0].parent.parent / "media")

    final_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=css_path,
        markdown_file_path=md_file,
        image_uploader=mock_uploader
    )

    # Parse the final HTML to check elements and attributes robustly
    final_soup = BeautifulSoup(final_html, 'html.parser')
    wrapper_div = final_soup.find('div', id='nice', class_='nice')
    assert wrapper_div is not None # Check main wrapper exists

    # Check heading
    h1 = wrapper_div.find('h1')
    assert h1 is not None
    assert h1.find('span', class_='content').text == 'Title'

    # Check list
    li = wrapper_div.find('li')
    assert li is not None
    assert li.text == 'List item'

    # *** Correction: Check image tag attributes ***
    img_tag = wrapper_div.find('img')
    assert img_tag is not None
    assert img_tag.get('alt') == "Relative Alt Text"
    assert img_tag.get('src') == mock_uploader.return_value

    # Check uploader call
    mock_uploader.assert_called_once_with(img_path)
    # Check no style tag
    assert final_soup.find('style') is None

def test_process_html_content_with_css(tmp_markdown_file: Tuple[Path, Path], mock_uploader: MagicMock, mocker, tmp_path: Path):
    """Test processing with CSS embedding."""
    md_content = "## Subtitle"
    md_file, md_dir = tmp_markdown_file

    css_file = tmp_path / "style.css"
    css_content = "h2 { color: blue; }"
    css_file.write_text(css_content, encoding='utf-8')

    mocker.patch('django.conf.settings.MEDIA_ROOT', tmp_path / "media")

    final_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=css_file,
        markdown_file_path=md_file,
        image_uploader=mock_uploader
    )

    # Parse final HTML
    final_soup = BeautifulSoup(final_html, 'html.parser')
    style_tag = final_soup.find('style')
    assert style_tag is not None
    assert css_content in style_tag.string # Check CSS content is inside

    wrapper_div = final_soup.find('div', id='nice', class_='nice')
    assert wrapper_div is not None
    h2 = wrapper_div.find('h2')
    assert h2 is not None
    assert h2.find('span', class_='content').text == 'Subtitle'
    mock_uploader.assert_not_called()

def test_process_html_content_css_not_found(tmp_markdown_file: Tuple[Path, Path], mock_uploader: MagicMock, mocker, tmp_path: Path):
    """Test processing when the specified CSS file does not exist."""
    md_content = "<p>Text</p>"
    md_file, md_dir = tmp_markdown_file
    non_existent_css = tmp_path / "ghost.css"

    mocker.patch('django.conf.settings.MEDIA_ROOT', tmp_path / "media")

    final_html = html_processor.process_html_content(
        md_content=md_content,
        css_path=non_existent_css,
        markdown_file_path=md_file,
        image_uploader=mock_uploader
    )

    # Parse final HTML
    final_soup = BeautifulSoup(final_html, 'html.parser')
    # Check NO style tag was added
    assert final_soup.find('style') is None

    # Check basic structure is still present
    wrapper_div = final_soup.find('div', id='nice', class_='nice')
    assert wrapper_div is not None
    p_tag = wrapper_div.find('p')
    assert p_tag is not None
    assert p_tag.text == 'Text'

