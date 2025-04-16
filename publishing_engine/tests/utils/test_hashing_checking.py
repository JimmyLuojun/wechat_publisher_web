# publishing_engine/tests/utils/test_hashing_checking.py

import pytest
from pathlib import Path
import hashlib

# Function to test
from publishing_engine.utils.hashing_checking import calculate_file_hash

def test_calculate_file_hash_success(tmp_path):
    """Test calculating SHA-256 hash for an existing file."""
    file_content = b"This is test content."
    file_path = tmp_path / "test_file.txt"
    file_path.write_bytes(file_content)

    expected_hash = hashlib.sha256(file_content).hexdigest()
    actual_hash = calculate_file_hash(file_path)

    assert actual_hash == expected_hash

def test_calculate_file_hash_different_content(tmp_path):
    """Test that different content yields different hashes."""
    file_path1 = tmp_path / "file1.txt"
    file_path1.write_bytes(b"Content 1")
    hash1 = calculate_file_hash(file_path1)

    file_path2 = tmp_path / "file2.txt"
    file_path2.write_bytes(b"Content 2")
    hash2 = calculate_file_hash(file_path2)

    assert hash1 is not None
    assert hash2 is not None
    assert hash1 != hash2

def test_calculate_file_hash_non_existent_file(tmp_path):
    """Test calculating hash for a file that does not exist."""
    file_path = tmp_path / "non_existent_file.dat"
    actual_hash = calculate_file_hash(file_path)
    assert actual_hash is None

def test_calculate_file_hash_directory(tmp_path):
    """Test calculating hash for a directory (should fail)."""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()
    actual_hash = calculate_file_hash(dir_path)
    assert actual_hash is None

def test_calculate_file_hash_md5(tmp_path):
    """Test calculating hash using MD5 algorithm."""
    file_content = b"Test MD5 hash."
    file_path = tmp_path / "md5_test.txt"
    file_path.write_bytes(file_content)

    expected_hash = hashlib.md5(file_content).hexdigest()
    actual_hash = calculate_file_hash(file_path, algorithm='md5')

    assert actual_hash == expected_hash

