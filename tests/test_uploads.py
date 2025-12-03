"""Tests for profile picture upload functionality.

This module provides unit tests for the ImageProcessor service and helper functions
for testing image processing functionality. The helper functions (create_test_image,
assert_image_valid) are exported for use in integration tests in test_user_flows.py.
"""

import tempfile
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from PIL import Image
from pyfakefs.fake_filesystem import FakeFilesystem

from app.uploads.service import ImageProcessingError, ImageProcessor

__all__ = ["assert_image_valid", "create_test_image"]


def create_test_image(size: tuple[int, int] = (500, 500), mode: str = "RGB") -> bytes:
    """Create a test image in memory.

    Args:
        size: Image dimensions as (width, height)
        mode: PIL image mode (RGB, RGBA, etc.)

    Returns:
        PNG image bytes
    """
    color = (255, 0, 0, 128) if mode == "RGBA" else "red"
    img = Image.new(mode, size, color=color)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def assert_image_valid(
    filepath: Path,
    expected_size: tuple[int, int] = (256, 256),
    expected_format: str = "WEBP",
) -> None:
    """Helper to validate processed image properties.

    Args:
        filepath: Path to the image file
        expected_size: Expected image dimensions
        expected_format: Expected image format
    """
    assert filepath.exists(), f"Image file not found: {filepath}"
    with Image.open(filepath) as img:
        assert img.format == expected_format
        assert img.size == expected_size


@pytest.fixture
def processor(fs: FakeFilesystem) -> ImageProcessor:
    """Create ImageProcessor with fake filesystem."""
    upload_dir = Path(tempfile.gettempdir()) / "test_uploads"
    fs.makedirs(str(upload_dir), exist_ok=True)
    return ImageProcessor(upload_dir)


@pytest.fixture
def mock_upload_dir(fs: FakeFilesystem) -> Generator[Path]:
    """Mock get_upload_dir to use fake filesystem for integration tests."""
    upload_dir = Path(tempfile.gettempdir()) / "test_uploads"
    fs.makedirs(str(upload_dir), exist_ok=True)
    with patch("app.uploads.service.get_upload_dir", return_value=upload_dir):
        yield upload_dir


class TestImageProcessor:
    """Unit tests for ImageProcessor class."""

    def test_process_valid_image(self, processor: ImageProcessor) -> None:
        """Test processing a valid image."""
        user_id = uuid4()
        filename = processor.process_and_save(create_test_image(), user_id)

        assert filename.endswith(".webp")
        assert str(user_id) in filename
        assert_image_valid(processor.upload_dir / filename)

    @pytest.mark.parametrize("mode", ["RGB", "RGBA"])
    def test_process_image_modes(self, processor: ImageProcessor, mode: str) -> None:
        """Test processing different image modes."""
        user_id = uuid4()
        filename = processor.process_and_save(create_test_image(mode=mode), user_id)
        assert_image_valid(processor.upload_dir / filename)

    @pytest.mark.parametrize("size", [(800, 400), (400, 800), (500, 500)])
    def test_process_various_aspect_ratios(self, processor: ImageProcessor, size: tuple[int, int]) -> None:
        """Test square cropping for various aspect ratios."""
        user_id = uuid4()
        filename = processor.process_and_save(create_test_image(size=size), user_id)
        assert_image_valid(processor.upload_dir / filename)

    def test_process_with_crop_data(self, processor: ImageProcessor) -> None:
        """Test processing with crop data."""
        user_id = uuid4()
        crop_data = {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5}
        filename = processor.process_and_save(create_test_image(), user_id, crop_data=crop_data)
        assert_image_valid(processor.upload_dir / filename)

    def test_reject_oversized_file(self, processor: ImageProcessor) -> None:
        """Test rejection of files exceeding size limit."""
        with pytest.raises(ImageProcessingError, match="File too large"):
            processor.process_and_save(b"x" * (6 * 1024 * 1024), uuid4())

    def test_reject_invalid_file(self, processor: ImageProcessor) -> None:
        """Test rejection of non-image files."""
        with pytest.raises(ImageProcessingError, match="Invalid image file"):
            processor.process_and_save(b"not an image", uuid4())

    def test_cleanup_old_pictures(self, processor: ImageProcessor) -> None:
        """Test that old profile pictures are cleaned up."""
        user_id = uuid4()
        img_bytes = create_test_image()

        filename1 = processor.process_and_save(img_bytes, user_id)
        assert (processor.upload_dir / filename1).exists()

        filename2 = processor.process_and_save(img_bytes, user_id)
        assert not (processor.upload_dir / filename1).exists()
        assert (processor.upload_dir / filename2).exists()

    def test_delete_picture(self, processor: ImageProcessor) -> None:
        """Test deleting a profile picture."""
        user_id = uuid4()
        filename = processor.process_and_save(create_test_image(), user_id)
        assert (processor.upload_dir / filename).exists()

        processor.delete_picture(filename)
        assert not (processor.upload_dir / filename).exists()
