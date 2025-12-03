"""Image processing service for secure profile picture uploads.

Security features:
- Re-encodes images to WebP to strip all metadata (EXIF, GPS, etc.)
- Validates file content, not just extension
- Uses UUID filenames to prevent path traversal
- Enforces size limits
"""

from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image
from PIL.Image import Image as PILImage

# Configuration
MAX_FILE_SIZE = 5 * 1024 * 1024
PROFILE_PIC_SIZE = (256, 256)
ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}


class ImageProcessingError(Exception):
    """Raised when image processing fails."""


class ImageProcessor:
    """Secure image processor for profile pictures."""

    def __init__(self, upload_dir: Path) -> None:
        """Initialize with upload directory.

        Args:
            upload_dir: Directory to store processed images
        """
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def process_and_save(
        self,
        file_content: bytes,
        user_id: UUID,
        *,
        crop_data: dict[str, float] | None = None,
    ) -> str:
        """Process uploaded image and save as WebP.

        Args:
            file_content: Raw file bytes
            user_id: User ID for filename generation
            crop_data: Optional crop coordinates {x, y, width, height} as percentages (0-1)

        Returns:
            Filename of saved image (not full path)

        Raises:
            ImageProcessingError: If processing fails
        """
        # Validate size
        if len(file_content) > MAX_FILE_SIZE:
            msg = f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB"
            raise ImageProcessingError(msg)

        # Load and validate image
        try:
            img: PILImage = Image.open(BytesIO(file_content))
        except Exception as e:
            msg = "Invalid image file"
            raise ImageProcessingError(msg) from e

        # Validate format (content-based, not extension)
        if img.format not in ALLOWED_FORMATS:
            msg = f"Unsupported image format. Allowed: {', '.join(ALLOWED_FORMATS)}"
            raise ImageProcessingError(msg)

        # Apply crop if provided
        if crop_data:
            img = self._apply_crop(img, crop_data)

        # Create square crop from center if not already square
        img = self._make_square(img)

        # Resize to target dimensions
        img = img.resize(PROFILE_PIC_SIZE, Image.Resampling.LANCZOS)

        # Detect if image has transparency
        has_transparency = img.mode in ("RGBA", "LA", "P")

        # Convert to appropriate format for WebP
        if has_transparency:
            # Preserve transparency by converting to RGBA
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            # Convert to RGB for opaque images
            img = img.convert("RGB")

        # Generate secure filename with UUID
        filename = f"{user_id}_{uuid4().hex[:8]}.webp"
        filepath = self.upload_dir / filename

        # Save as WebP with appropriate compression settings
        # Lossless for transparent images, lossy for opaque images
        if has_transparency:
            img.save(filepath, format="WEBP", lossless=True, method=6)
        else:
            img.save(filepath, format="WEBP", quality=82, method=6)

        # Clean up old profile pictures for this user
        self._cleanup_old_pictures(user_id, filename)

        return filename

    def _apply_crop(self, img: Image.Image, crop_data: dict[str, float]) -> Image.Image:
        """Apply crop based on percentage coordinates.

        Args:
            img: PIL Image
            crop_data: {x, y, width, height} as percentages (0-1 range)
                      These are normalized coordinates from the frontend cropper

        Returns:
            Cropped image
        """
        width, height = img.size

        # Convert percentage coordinates to pixel coordinates
        x = int(crop_data.get("x", 0) * width)
        y = int(crop_data.get("y", 0) * height)
        crop_width = int(crop_data.get("width", 1) * width)
        crop_height = int(crop_data.get("height", 1) * height)

        # Ensure bounds are valid and within image dimensions
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        crop_width = max(1, min(crop_width, width - x))
        crop_height = max(1, min(crop_height, height - y))

        # Crop the image: (left, top, right, bottom)
        return img.crop((x, y, x + crop_width, y + crop_height))

    def _make_square(self, img: Image.Image) -> Image.Image:
        """Crop image to square from center.

        Args:
            img: PIL Image

        Returns:
            Square cropped image
        """
        width, height = img.size
        if width == height:
            return img

        size = min(width, height)
        left = (width - size) // 2
        top = (height - size) // 2
        return img.crop((left, top, left + size, top + size))

    def _cleanup_old_pictures(self, user_id: UUID, current_filename: str) -> None:
        """Remove old profile pictures for a user.

        Args:
            user_id: User ID
            current_filename: Filename to keep
        """
        prefix = str(user_id)
        for filepath in self.upload_dir.glob(f"{prefix}_*.webp"):
            if filepath.name != current_filename:
                filepath.unlink(missing_ok=True)

    def delete_picture(self, filename: str) -> None:
        """Delete a profile picture.

        Args:
            filename: Filename to delete
        """
        filepath = self.upload_dir / filename
        if filepath.exists() and filepath.parent == self.upload_dir:
            filepath.unlink(missing_ok=True)


def get_upload_dir() -> Path:
    """Get the upload directory path."""
    return Path(__file__).resolve().parent.parent / "static" / "uploads" / "avatars"


def process_profile_picture(
    file_content: bytes,
    user_id: UUID,
    *,
    crop_data: dict[str, float] | None = None,
) -> str:
    """Convenience function to process a profile picture.

    Args:
        file_content: Raw file bytes
        user_id: User ID
        crop_data: Optional crop coordinates

    Returns:
        Filename of saved image
    """
    processor = ImageProcessor(get_upload_dir())
    return processor.process_and_save(file_content, user_id, crop_data=crop_data)
