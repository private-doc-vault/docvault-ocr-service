"""
Tests for Tesseract OCR Integration
Following TDD methodology - these tests define the expected behavior
"""
import pytest
from PIL import Image, ImageDraw, ImageFont
import io
from pathlib import Path
import subprocess

from app.ocr_service import OCRService, OCRResult


def check_tesseract_lang(lang_code):
    """Check if a Tesseract language is installed"""
    try:
        result = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True)
        return lang_code in result.stdout
    except:
        return False


@pytest.fixture
def ocr_service():
    """Create OCR service instance"""
    return OCRService()


@pytest.fixture
def sample_image_with_text():
    """Create a sample image with text for testing"""
    # Create a white image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)

    # Add text
    text = "Hello World\nThis is a test"
    draw.text((10, 50), text, fill='black')

    # Convert to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes


@pytest.fixture
def sample_multilingual_image():
    """Create a sample image with multilingual text"""
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)

    # Add text (Tesseract can recognize this even without special fonts)
    text = "Hello World"
    draw.text((10, 50), text, fill='black')

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes


class TestOCRServiceInitialization:
    """Test OCR service initialization"""

    def test_ocr_service_can_be_instantiated(self):
        """Test that OCR service can be created"""
        service = OCRService()
        assert service is not None

    def test_ocr_service_has_default_language(self):
        """Test that OCR service has default language set"""
        service = OCRService()
        assert service.default_language == "eng"

    def test_ocr_service_can_set_custom_language(self):
        """Test that OCR service can be initialized with custom language"""
        service = OCRService(language="deu")
        assert service.default_language == "deu"


class TestBasicOCR:
    """Test basic OCR functionality"""

    def test_extract_text_from_image(self, ocr_service, sample_image_with_text):
        """Test extracting text from a simple image"""
        result = ocr_service.extract_text(sample_image_with_text)

        assert isinstance(result, OCRResult)
        assert result.text is not None
        assert len(result.text) > 0
        assert "Hello" in result.text or "World" in result.text

    def test_extract_text_returns_confidence_score(self, ocr_service, sample_image_with_text):
        """Test that OCR returns confidence score"""
        result = ocr_service.extract_text(sample_image_with_text)

        assert result.confidence is not None
        assert 0.0 <= result.confidence <= 100.0

    def test_extract_text_from_empty_image(self, ocr_service):
        """Test OCR on image with no text"""
        # Create blank white image
        img = Image.new('RGB', (100, 100), color='white')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        result = ocr_service.extract_text(img_bytes)

        assert isinstance(result, OCRResult)
        # Blank image should return empty or whitespace-only text
        assert len(result.text.strip()) == 0 or result.confidence < 10.0


class TestMultiLanguageSupport:
    """Test multi-language OCR support"""

    def test_ocr_with_english_language(self, ocr_service, sample_image_with_text):
        """Test OCR with English language specified"""
        result = ocr_service.extract_text(sample_image_with_text, language="eng")

        assert result.text is not None
        assert result.language == "eng"

    @pytest.mark.skipif(not check_tesseract_lang('deu'), reason="German language pack not installed")
    def test_ocr_with_german_language(self, ocr_service, sample_multilingual_image):
        """Test OCR with German language specified"""
        result = ocr_service.extract_text(sample_multilingual_image, language="deu")

        assert result.text is not None
        assert result.language == "deu"

    @pytest.mark.skipif(not check_tesseract_lang('fra'), reason="French language pack not installed")
    def test_ocr_with_french_language(self, ocr_service, sample_multilingual_image):
        """Test OCR with French language specified"""
        result = ocr_service.extract_text(sample_multilingual_image, language="fra")

        assert result.text is not None
        assert result.language == "fra"

    @pytest.mark.skipif(not check_tesseract_lang('spa'), reason="Spanish language pack not installed")
    def test_ocr_with_spanish_language(self, ocr_service, sample_multilingual_image):
        """Test OCR with Spanish language specified"""
        result = ocr_service.extract_text(sample_multilingual_image, language="spa")

        assert result.text is not None
        assert result.language == "spa"

    @pytest.mark.skipif(not check_tesseract_lang('deu'), reason="German language pack not installed")
    def test_ocr_with_multiple_languages(self, ocr_service, sample_multilingual_image):
        """Test OCR with multiple languages combined"""
        result = ocr_service.extract_text(sample_multilingual_image, language="eng+deu")

        assert result.text is not None
        assert "eng+deu" in result.language or result.language == "eng+deu"


class TestLanguageDetection:
    """Test automatic language detection"""

    def test_get_supported_languages(self, ocr_service):
        """Test retrieving list of supported languages"""
        languages = ocr_service.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0
        # Should at least support English
        assert "eng" in languages

    def test_supported_languages_include_common_european_languages(self, ocr_service):
        """Test that common European languages are supported"""
        languages = ocr_service.get_supported_languages()

        # Check for languages that are installed
        # Only eng is guaranteed to be installed in CI
        assert "eng" in languages

        # Check other languages if they're installed
        for lang in ["deu", "fra", "spa", "ita"]:
            if check_tesseract_lang(lang):
                assert lang in languages


class TestOCRConfiguration:
    """Test OCR configuration options"""

    def test_ocr_with_custom_dpi(self, ocr_service, sample_image_with_text):
        """Test OCR with custom DPI setting"""
        result = ocr_service.extract_text(sample_image_with_text, dpi=300)

        assert result.text is not None
        assert result.dpi == 300

    def test_ocr_with_psm_mode(self, ocr_service, sample_image_with_text):
        """Test OCR with custom page segmentation mode"""
        # PSM 6 = Assume a single uniform block of text
        result = ocr_service.extract_text(sample_image_with_text, psm=6)

        assert result.text is not None

    def test_ocr_with_preprocessing(self, ocr_service, sample_image_with_text):
        """Test OCR with image preprocessing enabled"""
        result = ocr_service.extract_text(
            sample_image_with_text,
            preprocess=True
        )

        assert result.text is not None
        assert result.preprocessed is True


class TestOCRErrorHandling:
    """Test error handling in OCR processing"""

    def test_ocr_with_invalid_image_data(self, ocr_service):
        """Test OCR with invalid image data"""
        invalid_data = io.BytesIO(b"not an image")

        with pytest.raises(Exception) as exc_info:
            ocr_service.extract_text(invalid_data)

        assert "image" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    def test_ocr_with_unsupported_language(self, ocr_service, sample_image_with_text):
        """Test OCR with unsupported language code"""
        with pytest.raises(ValueError) as exc_info:
            ocr_service.extract_text(sample_image_with_text, language="invalid_lang")

        assert "language" in str(exc_info.value).lower()

    def test_ocr_with_corrupted_image(self, ocr_service):
        """Test OCR with corrupted image file"""
        # Create partially corrupted image data
        corrupted_data = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"corrupted")

        with pytest.raises(Exception):
            ocr_service.extract_text(corrupted_data)


class TestOCRPerformance:
    """Test OCR performance characteristics"""

    def test_ocr_returns_processing_time(self, ocr_service, sample_image_with_text):
        """Test that OCR result includes processing time"""
        result = ocr_service.extract_text(sample_image_with_text)

        assert result.processing_time is not None
        assert result.processing_time > 0

    def test_ocr_processing_is_reasonably_fast(self, ocr_service, sample_image_with_text):
        """Test that OCR processing completes in reasonable time"""
        result = ocr_service.extract_text(sample_image_with_text)

        # Simple image should process in under 5 seconds
        assert result.processing_time < 5.0


class TestOCROutputFormat:
    """Test OCR output format options"""

    def test_ocr_can_return_raw_text(self, ocr_service, sample_image_with_text):
        """Test OCR returning plain text"""
        result = ocr_service.extract_text(sample_image_with_text, output_format="text")

        assert isinstance(result.text, str)

    def test_ocr_can_return_hocr(self, ocr_service, sample_image_with_text):
        """Test OCR returning hOCR format"""
        result = ocr_service.extract_text(sample_image_with_text, output_format="hocr")

        assert result.hocr is not None
        assert "hocr" in result.hocr.lower() or "<" in result.hocr

    def test_ocr_can_return_word_boxes(self, ocr_service, sample_image_with_text):
        """Test OCR returning word bounding boxes"""
        result = ocr_service.extract_text(sample_image_with_text, include_boxes=True)

        assert result.boxes is not None
        assert isinstance(result.boxes, list)
