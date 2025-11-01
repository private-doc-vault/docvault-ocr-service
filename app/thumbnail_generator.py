"""
Thumbnail Generator
Generates thumbnails from images with various size and quality options
"""
from PIL import Image
import io
from typing import Optional, Union
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ThumbnailResult:
    """Result from thumbnail generation"""
    thumbnail: Image.Image
    width: int
    height: int
    original_width: int
    original_height: int
    format: str
    quality: str
    file_size: Optional[int] = None

    def to_bytes(self, format: Optional[str] = None) -> bytes:
        """
        Convert thumbnail to bytes

        Args:
            format: Output format (PNG, JPEG, WEBP), uses result format if not specified

        Returns:
            Thumbnail as bytes
        """
        output_format = format or self.format

        # Convert to RGB if saving as JPEG (JPEG doesn't support transparency)
        image = self.thumbnail
        if output_format == 'JPEG' and image.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            rgb_image = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = rgb_image

        # Determine quality parameter
        quality_map = {
            'high': 95,
            'medium': 85,
            'low': 70
        }
        quality_value = quality_map.get(self.quality, 85)

        # Save to bytes
        buffer = io.BytesIO()
        if output_format == 'JPEG':
            image.save(buffer, format=output_format, quality=quality_value, optimize=True)
        elif output_format == 'WEBP':
            image.save(buffer, format=output_format, quality=quality_value)
        else:  # PNG
            image.save(buffer, format=output_format, optimize=True)

        return buffer.getvalue()


class ThumbnailGenerator:
    """Generator for creating thumbnails from images"""

    def __init__(self, default_size: int = 300):
        """
        Initialize thumbnail generator

        Args:
            default_size: Default maximum dimension for thumbnails
        """
        self.default_size = default_size
        self.valid_qualities = ['high', 'medium', 'low']
        self.valid_formats = ['PNG', 'JPEG', 'WEBP']

    def generate(
        self,
        image: Image.Image,
        max_size: Optional[int] = None,
        quality: str = 'medium',
        output_format: str = 'JPEG'
    ) -> ThumbnailResult:
        """
        Generate thumbnail from image

        Args:
            image: PIL Image to create thumbnail from
            max_size: Maximum dimension (width or height) in pixels
            quality: Quality setting ('high', 'medium', 'low')
            output_format: Output format ('PNG', 'JPEG', 'WEBP')

        Returns:
            ThumbnailResult with generated thumbnail

        Raises:
            ValueError: If parameters are invalid
        """
        if max_size is not None and max_size <= 0:
            raise ValueError("max_size must be positive")

        if quality not in self.valid_qualities:
            logger.warning(f"Invalid quality '{quality}', using 'medium'")
            quality = 'medium'

        if output_format not in self.valid_formats:
            logger.warning(f"Invalid format '{output_format}', using 'JPEG'")
            output_format = 'JPEG'

        # Use default size if not specified
        if max_size is None:
            max_size = self.default_size

        # Store original dimensions
        original_width, original_height = image.size

        # Calculate thumbnail size maintaining aspect ratio
        thumbnail_size = self._calculate_thumbnail_size(
            original_width,
            original_height,
            max_size
        )

        # Create thumbnail
        # Make a copy to avoid modifying the original
        thumbnail = image.copy()

        # Only resize if the image is larger than max_size
        if original_width > max_size or original_height > max_size:
            # Use high-quality resampling
            thumbnail.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)

        # Get actual size after thumbnail operation
        thumb_width, thumb_height = thumbnail.size

        # Calculate file size
        file_size = self._calculate_file_size(thumbnail, output_format, quality)

        return ThumbnailResult(
            thumbnail=thumbnail,
            width=thumb_width,
            height=thumb_height,
            original_width=original_width,
            original_height=original_height,
            format=output_format,
            quality=quality,
            file_size=file_size
        )

    def _calculate_thumbnail_size(
        self,
        width: int,
        height: int,
        max_size: int
    ) -> tuple[int, int]:
        """
        Calculate thumbnail size maintaining aspect ratio

        Args:
            width: Original width
            height: Original height
            max_size: Maximum dimension

        Returns:
            Tuple of (width, height) for thumbnail
        """
        # Don't upscale images
        if width <= max_size and height <= max_size:
            return (width, height)

        # Calculate aspect ratio
        aspect_ratio = width / height

        if width > height:
            # Landscape: width is limiting
            new_width = max_size
            new_height = int(max_size / aspect_ratio)
        else:
            # Portrait: height is limiting
            new_height = max_size
            new_width = int(max_size * aspect_ratio)

        return (new_width, new_height)

    def _calculate_file_size(
        self,
        image: Image.Image,
        output_format: str,
        quality: str
    ) -> int:
        """
        Calculate approximate file size of thumbnail

        Args:
            image: Thumbnail image
            output_format: Output format
            quality: Quality setting

        Returns:
            Approximate file size in bytes
        """
        try:
            buffer = io.BytesIO()

            # Prepare image for format
            save_image = image
            if output_format == 'JPEG' and image.mode in ('RGBA', 'LA', 'P'):
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    save_image = image.convert('RGBA')
                else:
                    save_image = image
                if save_image.mode in ('RGBA', 'LA'):
                    rgb_image.paste(save_image, mask=save_image.split()[-1])
                save_image = rgb_image

            # Quality mapping
            quality_map = {'high': 95, 'medium': 85, 'low': 70}
            quality_value = quality_map.get(quality, 85)

            # Save to buffer
            if output_format == 'JPEG':
                save_image.save(buffer, format=output_format, quality=quality_value)
            elif output_format == 'WEBP':
                save_image.save(buffer, format=output_format, quality=quality_value)
            else:  # PNG
                save_image.save(buffer, format=output_format, optimize=True)

            return len(buffer.getvalue())
        except Exception as e:
            logger.warning(f"Could not calculate file size: {e}")
            return 0
