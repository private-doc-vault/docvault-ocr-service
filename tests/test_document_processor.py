"""
Tests for Document Format Support
Following TDD methodology - these tests define the expected behavior for PDF, JPG, PNG, TIFF processing
"""
import pytest
from PIL import Image, ImageDraw
import io
from pathlib import Path

from app.document_processor import DocumentProcessor, ProcessedDocument


@pytest.fixture
def document_processor():
    """Create document processor instance"""
    return DocumentProcessor()


@pytest.fixture
def sample_png_image():
    """Create a sample PNG image with text"""
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), "PNG Test Image", fill='black')

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes


@pytest.fixture
def sample_jpg_image():
    """Create a sample JPG image with text"""
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), "JPG Test Image", fill='black')

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)

    return img_bytes


@pytest.fixture
def sample_tiff_image():
    """Create a sample TIFF image with text"""
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), "TIFF Test Image", fill='black')

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='TIFF')
    img_bytes.seek(0)

    return img_bytes


@pytest.fixture
def sample_pdf_single_page():
    """Create a sample single-page PDF (simulated as image for now)"""
    # Note: For actual PDF creation, we'd need reportlab or similar
    # For testing, we'll use pdf2image to convert an image to PDF format simulation
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((10, 50), "PDF Test Page", fill='black')

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PDF')
    img_bytes.seek(0)

    return img_bytes


class TestDocumentProcessorInitialization:
    """Test document processor initialization"""

    def test_processor_can_be_instantiated(self):
        """Test that document processor can be created"""
        processor = DocumentProcessor()
        assert processor is not None

    def test_processor_supports_required_formats(self, document_processor):
        """Test that processor supports PDF, JPG, PNG, TIFF"""
        supported = document_processor.supported_formats()

        assert 'pdf' in supported
        assert 'jpg' in supported or 'jpeg' in supported
        assert 'png' in supported
        assert 'tiff' in supported or 'tif' in supported


class TestPNGProcessing:
    """Test PNG image processing"""

    def test_process_png_image(self, document_processor, sample_png_image):
        """Test processing a PNG image"""
        result = document_processor.process(sample_png_image, format='png')

        assert isinstance(result, ProcessedDocument)
        assert result.format == 'png'
        assert result.page_count == 1
        assert len(result.images) == 1

    def test_png_image_conversion(self, document_processor, sample_png_image):
        """Test that PNG is converted to proper format for OCR"""
        result = document_processor.process(sample_png_image, format='png')

        # Should return PIL Image objects
        assert result.images[0] is not None
        assert hasattr(result.images[0], 'size')

    def test_png_preserves_quality(self, document_processor, sample_png_image):
        """Test that PNG processing preserves image quality"""
        result = document_processor.process(sample_png_image, format='png')

        image = result.images[0]
        assert image.size[0] > 0
        assert image.size[1] > 0


class TestJPEGProcessing:
    """Test JPEG/JPG image processing"""

    def test_process_jpg_image(self, document_processor, sample_jpg_image):
        """Test processing a JPG image"""
        result = document_processor.process(sample_jpg_image, format='jpg')

        assert isinstance(result, ProcessedDocument)
        assert result.format in ['jpg', 'jpeg']
        assert result.page_count == 1
        assert len(result.images) == 1

    def test_jpeg_image_conversion(self, document_processor, sample_jpg_image):
        """Test that JPEG is converted properly"""
        result = document_processor.process(sample_jpg_image, format='jpeg')

        assert result.images[0] is not None
        # JPEG might be converted to RGB
        assert result.images[0].mode in ['RGB', 'L']


class TestTIFFProcessing:
    """Test TIFF image processing"""

    def test_process_tiff_image(self, document_processor, sample_tiff_image):
        """Test processing a TIFF image"""
        result = document_processor.process(sample_tiff_image, format='tiff')

        assert isinstance(result, ProcessedDocument)
        assert result.format in ['tiff', 'tif']
        assert result.page_count == 1
        assert len(result.images) == 1

    def test_multi_page_tiff_support(self, document_processor):
        """Test that multi-page TIFF files are supported"""
        # Create a multi-page TIFF
        images = []
        for i in range(3):
            img = Image.new('RGB', (400, 200), color='white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 50), f"Page {i+1}", fill='black')
            images.append(img)

        # Save as multi-page TIFF
        tiff_bytes = io.BytesIO()
        images[0].save(tiff_bytes, format='TIFF', save_all=True, append_images=images[1:])
        tiff_bytes.seek(0)

        result = document_processor.process(tiff_bytes, format='tiff')

        assert result.page_count == 3
        assert len(result.images) == 3


class TestPDFProcessing:
    """Test PDF processing"""

    def test_process_pdf_single_page(self, document_processor, sample_pdf_single_page):
        """Test processing a single-page PDF"""
        result = document_processor.process(sample_pdf_single_page, format='pdf')

        assert isinstance(result, ProcessedDocument)
        assert result.format == 'pdf'
        assert result.page_count >= 1
        assert len(result.images) >= 1

    def test_pdf_to_images_conversion(self, document_processor, sample_pdf_single_page):
        """Test that PDF is converted to images"""
        result = document_processor.process(sample_pdf_single_page, format='pdf')

        # Each page should be converted to an image
        for image in result.images:
            assert hasattr(image, 'size')
            assert image.size[0] > 0
            assert image.size[1] > 0

    def test_pdf_page_count(self, document_processor, sample_pdf_single_page):
        """Test that PDF page count is accurate"""
        result = document_processor.process(sample_pdf_single_page, format='pdf')

        assert result.page_count > 0
        assert result.page_count == len(result.images)


class TestFormatDetection:
    """Test automatic format detection"""

    def test_detect_png_format(self, document_processor, sample_png_image):
        """Test automatic PNG format detection"""
        format_detected = document_processor.detect_format(sample_png_image)
        assert format_detected == 'png'

    def test_detect_jpg_format(self, document_processor, sample_jpg_image):
        """Test automatic JPEG format detection"""
        format_detected = document_processor.detect_format(sample_jpg_image)
        assert format_detected in ['jpg', 'jpeg']

    def test_detect_tiff_format(self, document_processor, sample_tiff_image):
        """Test automatic TIFF format detection"""
        format_detected = document_processor.detect_format(sample_tiff_image)
        assert format_detected in ['tiff', 'tif']

    def test_detect_pdf_format(self, document_processor, sample_pdf_single_page):
        """Test automatic PDF format detection"""
        format_detected = document_processor.detect_format(sample_pdf_single_page)
        assert format_detected == 'pdf'


class TestProcessingOptions:
    """Test processing options and configurations"""

    def test_process_with_dpi_option(self, document_processor, sample_png_image):
        """Test processing with custom DPI"""
        result = document_processor.process(sample_png_image, format='png', dpi=300)

        assert result.dpi == 300

    def test_process_pdf_with_dpi(self, document_processor, sample_pdf_single_page):
        """Test PDF processing with custom DPI"""
        result = document_processor.process(sample_pdf_single_page, format='pdf', dpi=200)

        assert result.dpi == 200
        # Images should be rendered at specified DPI

    def test_process_with_color_mode(self, document_processor, sample_png_image):
        """Test processing with specific color mode"""
        result = document_processor.process(
            sample_png_image,
            format='png',
            color_mode='grayscale'
        )

        # Should convert to grayscale
        assert result.images[0].mode in ['L', 'LA']


class TestErrorHandling:
    """Test error handling for various formats"""

    def test_process_unsupported_format(self, document_processor):
        """Test processing unsupported file format"""
        invalid_data = io.BytesIO(b"unsupported data")

        with pytest.raises(ValueError) as exc_info:
            document_processor.process(invalid_data, format='unsupported')

        assert 'unsupported' in str(exc_info.value).lower() or 'format' in str(exc_info.value).lower()

    def test_process_corrupted_pdf(self, document_processor):
        """Test processing corrupted PDF"""
        corrupted_pdf = io.BytesIO(b"%PDF-1.4\ncorrupted data")

        with pytest.raises(Exception):
            document_processor.process(corrupted_pdf, format='pdf')

    def test_process_corrupted_image(self, document_processor):
        """Test processing corrupted image"""
        corrupted_image = io.BytesIO(b"\x89PNG\r\n\x1a\ncorrupted")

        with pytest.raises(Exception):
            document_processor.process(corrupted_image, format='png')


class TestProcessedDocumentMetadata:
    """Test metadata in processed documents"""

    def test_processed_document_contains_format(self, document_processor, sample_png_image):
        """Test that processed document contains format info"""
        result = document_processor.process(sample_png_image, format='png')

        assert hasattr(result, 'format')
        assert result.format is not None

    def test_processed_document_contains_page_count(self, document_processor, sample_png_image):
        """Test that processed document contains page count"""
        result = document_processor.process(sample_png_image, format='png')

        assert hasattr(result, 'page_count')
        assert result.page_count > 0

    def test_processed_document_contains_images(self, document_processor, sample_png_image):
        """Test that processed document contains image list"""
        result = document_processor.process(sample_png_image, format='png')

        assert hasattr(result, 'images')
        assert isinstance(result.images, list)
        assert len(result.images) > 0

    def test_processed_document_contains_size_info(self, document_processor, sample_png_image):
        """Test that processed document contains size information"""
        result = document_processor.process(sample_png_image, format='png')

        assert hasattr(result, 'file_size')
        assert result.file_size is not None
        assert result.file_size > 0


class TestMemoryEfficiency:
    """Test memory-efficient processing"""

    def test_large_pdf_processing_doesnt_crash(self, document_processor):
        """Test that large PDFs can be processed without memory issues"""
        # Create a moderately sized image (not too large for tests)
        img = Image.new('RGB', (2000, 2000), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((100, 500), "Large Image Test", fill='black')

        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Should process without issues
        result = document_processor.process(img_bytes, format='png')
        assert result is not None
        assert len(result.images) == 1
