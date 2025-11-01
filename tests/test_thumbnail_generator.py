"""
Tests for Thumbnail Generation
Following TDD methodology - these tests define the expected behavior for thumbnail generation
"""
import pytest
from PIL import Image
import io

from app.thumbnail_generator import ThumbnailGenerator, ThumbnailResult


@pytest.fixture
def thumbnail_generator():
    """Create thumbnail generator instance"""
    return ThumbnailGenerator()


@pytest.fixture
def sample_image():
    """Create a sample image for testing"""
    img = Image.new('RGB', (1000, 1000), color='white')
    return img


@pytest.fixture
def sample_large_image():
    """Create a large sample image"""
    img = Image.new('RGB', (3000, 4000), color='blue')
    return img


class TestThumbnailGeneratorInitialization:
    """Test thumbnail generator initialization"""

    def test_generator_can_be_instantiated(self):
        """Test that thumbnail generator can be created"""
        generator = ThumbnailGenerator()
        assert generator is not None

    def test_generator_has_default_size(self, thumbnail_generator):
        """Test that generator has default thumbnail size"""
        assert hasattr(thumbnail_generator, 'default_size')
        assert thumbnail_generator.default_size > 0


class TestBasicThumbnailGeneration:
    """Test basic thumbnail generation"""

    def test_generate_thumbnail_from_image(self, thumbnail_generator, sample_image):
        """Test generating thumbnail from PIL Image"""
        result = thumbnail_generator.generate(sample_image)

        assert isinstance(result, ThumbnailResult)
        assert result.thumbnail is not None
        assert isinstance(result.thumbnail, Image.Image)

    def test_thumbnail_is_smaller_than_original(self, thumbnail_generator, sample_image):
        """Test that thumbnail is smaller than original"""
        result = thumbnail_generator.generate(sample_image)

        original_size = sample_image.size
        thumbnail_size = result.thumbnail.size

        # Thumbnail should be smaller in at least one dimension
        assert thumbnail_size[0] <= original_size[0]
        assert thumbnail_size[1] <= original_size[1]

    def test_thumbnail_maintains_aspect_ratio(self, thumbnail_generator, sample_large_image):
        """Test that thumbnail maintains aspect ratio"""
        result = thumbnail_generator.generate(sample_large_image)

        original_ratio = sample_large_image.width / sample_large_image.height
        thumbnail_ratio = result.thumbnail.width / result.thumbnail.height

        # Allow for small floating point differences
        assert abs(original_ratio - thumbnail_ratio) < 0.01


class TestThumbnailSizes:
    """Test different thumbnail sizes"""

    def test_generate_small_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating small thumbnail"""
        result = thumbnail_generator.generate(sample_image, max_size=100)

        assert result.thumbnail.width <= 100
        assert result.thumbnail.height <= 100

    def test_generate_medium_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating medium thumbnail"""
        result = thumbnail_generator.generate(sample_image, max_size=300)

        assert result.thumbnail.width <= 300
        assert result.thumbnail.height <= 300

    def test_generate_large_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating large thumbnail"""
        result = thumbnail_generator.generate(sample_image, max_size=500)

        assert result.thumbnail.width <= 500
        assert result.thumbnail.height <= 500

    def test_custom_thumbnail_size(self, thumbnail_generator, sample_image):
        """Test generating thumbnail with custom size"""
        custom_size = 250
        result = thumbnail_generator.generate(sample_image, max_size=custom_size)

        assert max(result.thumbnail.size) <= custom_size


class TestThumbnailQuality:
    """Test thumbnail quality settings"""

    def test_generate_high_quality_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating high quality thumbnail"""
        result = thumbnail_generator.generate(sample_image, quality='high')

        assert result.thumbnail is not None
        assert result.quality == 'high'

    def test_generate_medium_quality_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating medium quality thumbnail"""
        result = thumbnail_generator.generate(sample_image, quality='medium')

        assert result.thumbnail is not None
        assert result.quality == 'medium'

    def test_generate_low_quality_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating low quality thumbnail"""
        result = thumbnail_generator.generate(sample_image, quality='low')

        assert result.thumbnail is not None
        assert result.quality == 'low'


class TestThumbnailFormats:
    """Test different output formats"""

    def test_generate_png_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating PNG thumbnail"""
        result = thumbnail_generator.generate(sample_image, output_format='PNG')

        assert result.thumbnail is not None
        assert result.format == 'PNG'

    def test_generate_jpeg_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating JPEG thumbnail"""
        result = thumbnail_generator.generate(sample_image, output_format='JPEG')

        assert result.thumbnail is not None
        assert result.format == 'JPEG'

    def test_generate_webp_thumbnail(self, thumbnail_generator, sample_image):
        """Test generating WebP thumbnail"""
        result = thumbnail_generator.generate(sample_image, output_format='WEBP')

        assert result.thumbnail is not None
        assert result.format == 'WEBP'


class TestThumbnailBytes:
    """Test generating thumbnail as bytes"""

    def test_get_thumbnail_as_bytes(self, thumbnail_generator, sample_image):
        """Test getting thumbnail as bytes"""
        result = thumbnail_generator.generate(sample_image)
        thumbnail_bytes = result.to_bytes()

        assert isinstance(thumbnail_bytes, bytes)
        assert len(thumbnail_bytes) > 0

    def test_thumbnail_bytes_can_be_loaded(self, thumbnail_generator, sample_image):
        """Test that thumbnail bytes can be loaded back as image"""
        result = thumbnail_generator.generate(sample_image)
        thumbnail_bytes = result.to_bytes()

        # Load bytes back as image
        loaded_image = Image.open(io.BytesIO(thumbnail_bytes))
        assert loaded_image is not None
        assert loaded_image.size == result.thumbnail.size


class TestMultipleThumbnails:
    """Test generating multiple thumbnails"""

    def test_generate_multiple_sizes(self, thumbnail_generator, sample_image):
        """Test generating multiple thumbnail sizes"""
        sizes = [100, 200, 300]
        results = []

        for size in sizes:
            result = thumbnail_generator.generate(sample_image, max_size=size)
            results.append(result)

        assert len(results) == 3
        # Each should be progressively larger
        assert results[0].thumbnail.width <= results[1].thumbnail.width
        assert results[1].thumbnail.width <= results[2].thumbnail.width


class TestEdgeCases:
    """Test edge cases"""

    def test_generate_thumbnail_from_small_image(self, thumbnail_generator):
        """Test generating thumbnail from very small image"""
        small_image = Image.new('RGB', (50, 50), color='red')
        result = thumbnail_generator.generate(small_image, max_size=200)

        # Small image should not be upscaled
        assert result.thumbnail.size[0] <= 50
        assert result.thumbnail.size[1] <= 50

    def test_generate_thumbnail_from_portrait_image(self, thumbnail_generator):
        """Test generating thumbnail from portrait orientation"""
        portrait = Image.new('RGB', (500, 1000), color='green')
        result = thumbnail_generator.generate(portrait, max_size=300)

        # Height should be the limiting dimension
        assert result.thumbnail.height <= 300
        # Aspect ratio should be maintained
        assert result.thumbnail.width < result.thumbnail.height

    def test_generate_thumbnail_from_landscape_image(self, thumbnail_generator):
        """Test generating thumbnail from landscape orientation"""
        landscape = Image.new('RGB', (1000, 500), color='yellow')
        result = thumbnail_generator.generate(landscape, max_size=300)

        # Width should be the limiting dimension
        assert result.thumbnail.width <= 300
        # Aspect ratio should be maintained
        assert result.thumbnail.width > result.thumbnail.height

    def test_generate_thumbnail_from_square_image(self, thumbnail_generator):
        """Test generating thumbnail from square image"""
        square = Image.new('RGB', (800, 800), color='purple')
        result = thumbnail_generator.generate(square, max_size=200)

        # Both dimensions should be equal
        assert result.thumbnail.width == result.thumbnail.height
        assert result.thumbnail.width <= 200


class TestThumbnailMetadata:
    """Test thumbnail metadata"""

    def test_thumbnail_result_contains_size(self, thumbnail_generator, sample_image):
        """Test that result contains size information"""
        result = thumbnail_generator.generate(sample_image)

        assert hasattr(result, 'width')
        assert hasattr(result, 'height')
        assert result.width > 0
        assert result.height > 0

    def test_thumbnail_result_contains_original_size(self, thumbnail_generator, sample_image):
        """Test that result contains original size"""
        result = thumbnail_generator.generate(sample_image)

        assert hasattr(result, 'original_width')
        assert hasattr(result, 'original_height')
        assert result.original_width == sample_image.width
        assert result.original_height == sample_image.height

    def test_thumbnail_result_contains_file_size(self, thumbnail_generator, sample_image):
        """Test that result contains file size"""
        result = thumbnail_generator.generate(sample_image)

        if hasattr(result, 'file_size'):
            assert result.file_size > 0


class TestPerformance:
    """Test performance characteristics"""

    def test_thumbnail_generation_is_fast(self, thumbnail_generator, sample_large_image):
        """Test that thumbnail generation completes quickly"""
        import time

        start = time.time()
        result = thumbnail_generator.generate(sample_large_image)
        elapsed = time.time() - start

        # Should complete in under 1 second for typical images
        assert elapsed < 1.0
        assert result.thumbnail is not None


class TestErrorHandling:
    """Test error handling"""

    def test_generate_with_invalid_quality(self, thumbnail_generator, sample_image):
        """Test handling invalid quality parameter"""
        # Should use default quality or raise appropriate error
        try:
            result = thumbnail_generator.generate(sample_image, quality='invalid')
            # If it doesn't raise, it should use a default
            assert result.thumbnail is not None
        except ValueError:
            # ValueError is acceptable for invalid quality
            pass

    def test_generate_with_zero_size(self, thumbnail_generator, sample_image):
        """Test handling zero or negative size"""
        with pytest.raises((ValueError, AssertionError)):
            thumbnail_generator.generate(sample_image, max_size=0)

    def test_generate_with_negative_size(self, thumbnail_generator, sample_image):
        """Test handling negative size"""
        with pytest.raises((ValueError, AssertionError)):
            thumbnail_generator.generate(sample_image, max_size=-100)
