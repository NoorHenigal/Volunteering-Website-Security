"""Image processing service for secure uploads."""

import logging
from enum import Enum
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, ImageDraw
from PIL.Image import Image as PILImage

from app.core.config import settings

log = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}


class ImagePreset(str, Enum):
    """Standard image presets."""

    AVATAR = "avatars"  # 256x256 square
    BANNER = "banners"  # 1280x720 (16:9)
    LOGO = "logos"  # 512x512 square


# Preset dimensions (width, height)
PRESET_DIMENSIONS = {
    ImagePreset.AVATAR: (256, 256),
    ImagePreset.BANNER: (1280, 720),
    ImagePreset.LOGO: (512, 512),
}


class ImageProcessingError(Exception):
    """Raised when image processing fails."""


class ImageService:
    """Secure image processor service."""

    def __init__(self, static_dir: Path | None = None) -> None:
        """Initialize with base static directory.

        If not provided, attempts to use settings.UPLOAD_DIR or locate app/static.
        """
        if static_dir:
            self.base_dir = static_dir
        elif settings.upload_dir:
            self.base_dir = settings.upload_dir
        else:
            self.base_dir = Path(__file__).resolve().parent.parent.parent / "static" / "uploads"

    def process_and_save(
        self,
        file_content: bytes,
        entity_id: UUID,
        preset: ImagePreset,
        *,
        crop_square: bool = False,
        crop_circular: bool = False,
    ) -> str:
        """Process and save an uploaded image.

        Args:
            file_content: Raw image bytes
            entity_id: User/Org/Opp ID for linking/cleanup
            preset: ImagePreset (AVATAR, BANNER, LOGO)
            crop_square: Force center square crop (default False)
            crop_circular: Apply circular mask (default False)

        Returns:
            Filename of saved image
        """
        if len(file_content) > MAX_FILE_SIZE:
            msg = f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB"
            raise ImageProcessingError(msg)

        try:
            img: PILImage = Image.open(BytesIO(file_content))
        except Exception as e:
            msg = "Invalid image file"
            raise ImageProcessingError(msg) from e

        if img.format not in ALLOWED_FORMATS:
            msg = f"Unsupported image format. Allowed: {', '.join(ALLOWED_FORMATS)}"
            raise ImageProcessingError(msg)

        # Apply transformations
        if crop_square:
            img = self._make_square(img)

        # Resize to preset dimensions
        target_size = PRESET_DIMENSIONS[preset]
        img = img.resize(target_size, Image.Resampling.LANCZOS)

        # Apply circular mask if requested
        if crop_circular:
            img = self._apply_circular_mask(img)

        # Handle transparency
        has_transparency = img.mode in ("RGBA", "LA", "P") or crop_circular
        if has_transparency:
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Prepare save directory
        save_dir = self.base_dir / preset.value
        save_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = f"{entity_id}_{uuid4().hex[:8]}.webp"
        filepath = save_dir / filename

        # Save
        if has_transparency:
            img.save(filepath, format="WEBP", lossless=True, method=6)
        else:
            img.save(filepath, format="WEBP", quality=85, method=6)

        # Cleanup old images for this entity in this preset folder
        self._cleanup_old_images(save_dir, entity_id, filename)

        return filename

    def _make_square(self, img: Image.Image) -> Image.Image:
        """Crop image to square from center."""
        width, height = img.size
        if width == height:
            return img

        size = min(width, height)
        left = (width - size) // 2
        top = (height - size) // 2
        return img.crop((left, top, left + size, top + size))

    def _apply_circular_mask(self, img: Image.Image) -> Image.Image:
        """Apply a circular mask to the image, making corners transparent."""
        # Ensure image is square first
        img = self._make_square(img)

        # Convert to RGBA to support transparency
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        # Create a circular mask
        size = img.size[0]
        mask = Image.new("L", (size, size), 0)

        # Draw a white circle on the mask
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)

        # Apply the mask to the alpha channel
        img.putalpha(mask)

        return img

    def _cleanup_old_images(self, directory: Path, entity_id: UUID, current_filename: str) -> None:
        """Remove old images for this entity."""
        prefix = str(entity_id)
        for filepath in directory.glob(f"{prefix}_*.webp"):
            if filepath.name != current_filename:
                filepath.unlink(missing_ok=True)

    def delete_image(self, preset: ImagePreset, filename: str) -> None:
        """Delete a specific image."""
        filepath = self.base_dir / preset.value / filename
        if filepath.exists():
            filepath.unlink(missing_ok=True)
