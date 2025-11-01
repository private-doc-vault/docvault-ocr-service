"""
Tesseract OCR Service
Handles OCR processing with multiple language support and advanced image preprocessing
"""
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io
import time
from typing import Optional, List, BinaryIO, Dict, Any
from dataclasses import dataclass
import subprocess
import cv2
import numpy as np


@dataclass
class OCRResult:
    """Result from OCR processing"""
    text: str
    confidence: float
    language: str
    processing_time: float
    dpi: Optional[int] = None
    preprocessed: bool = False
    hocr: Optional[str] = None
    boxes: Optional[List[Dict[str, Any]]] = None


class OCRService:
    """Service for performing OCR on images and documents"""

    def __init__(self, language: str = "pol"):
        """
        Initialize OCR service

        Args:
            language: Default language for OCR (default: pol)
        """
        self.default_language = language
        self._supported_languages = None

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported Tesseract languages

        Returns:
            List of language codes
        """
        if self._supported_languages is not None:
            return self._supported_languages

        try:
            # Get installed languages from Tesseract
            result = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True,
                text=True,
                check=True
            )

            # Parse output - first line is header, rest are language codes
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                # Skip the header line
                languages = [line.strip() for line in lines[1:] if line.strip()]
                self._supported_languages = languages
                return languages
            else:
                # Fallback to known installed languages
                self._supported_languages = ["eng", "deu", "fra", "spa", "ita", "por", "pol", "osd"]
                return self._supported_languages

        except Exception:
            # Fallback to known installed languages from Dockerfile
            self._supported_languages = ["eng", "deu", "fra", "spa", "ita", "por", "pol", "osd"]
            return self._supported_languages

    def _validate_language(self, language: str) -> None:
        """
        Validate that language is supported

        Args:
            language: Language code to validate

        Raises:
            ValueError: If language is not supported
        """
        # Handle combined languages (e.g., "eng+deu")
        if "+" in language:
            langs = language.split("+")
            supported = self.get_supported_languages()
            for lang in langs:
                if lang not in supported:
                    raise ValueError(f"Unsupported language: {lang}")
        else:
            supported = self.get_supported_languages()
            if language not in supported:
                raise ValueError(f"Unsupported language: {language}. Supported languages: {', '.join(supported)}")

    def _analyze_image_quality(self, img_array: np.ndarray) -> dict:
        """
        Analyze image quality to determine optimal preprocessing

        Args:
            img_array: Grayscale image as numpy array

        Returns:
            Dictionary with quality metrics
        """
        # Calculate image sharpness (Laplacian variance)
        laplacian = cv2.Laplacian(img_array, cv2.CV_64F)
        sharpness = laplacian.var()

        # Calculate contrast (standard deviation)
        contrast = img_array.std()

        # Calculate brightness (mean)
        brightness = img_array.mean()

        # Detect if image is very dark or very bright
        is_low_contrast = contrast < 50
        is_dark = brightness < 80
        is_bright = brightness > 180

        return {
            'sharpness': sharpness,
            'contrast': contrast,
            'brightness': brightness,
            'is_low_contrast': is_low_contrast,
            'is_dark': is_dark,
            'is_bright': is_bright,
            'needs_enhancement': is_low_contrast or is_dark or is_bright
        }

    def _preprocess_image(self, image: Image.Image, enhance_level: str = "medium") -> Image.Image:
        """
        Preprocess image to improve OCR accuracy with advanced techniques
        Uses adaptive processing based on image quality analysis

        Args:
            image: PIL Image to preprocess
            enhance_level: Enhancement level - "light", "medium", "aggressive", or "auto"

        Returns:
            Preprocessed PIL Image
        """
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')

        # Convert to numpy array for analysis
        img_array = np.array(image)

        # Analyze image quality for adaptive processing
        quality = self._analyze_image_quality(img_array)

        # Auto-select enhancement level based on quality
        # Be conservative - most modern images work better with light processing
        if enhance_level == "auto":
            # Only use aggressive for truly problematic images
            if quality['is_dark'] and quality['is_low_contrast']:
                enhance_level = "aggressive"
            elif quality['needs_enhancement'] or quality['sharpness'] < 80:
                enhance_level = "medium"
            else:
                enhance_level = "light"

        if enhance_level == "light":
            # Light preprocessing: just sharpen
            image = image.filter(ImageFilter.SHARPEN)
            return image

        # STEP 1: Contrast enhancement for low contrast images
        if quality['is_low_contrast'] or quality['is_dark']:
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            img_array = clahe.apply(img_array)

        # STEP 2: Brightness correction
        if quality['is_dark']:
            # Increase brightness for dark images
            img_array = cv2.convertScaleAbs(img_array, alpha=1.3, beta=30)
        elif quality['is_bright']:
            # Reduce brightness for overexposed images
            img_array = cv2.convertScaleAbs(img_array, alpha=0.8, beta=-20)

        # STEP 3: Noise reduction (bilateral filter preserves edges better than Gaussian)
        if quality['sharpness'] < 100 and enhance_level == "aggressive":
            img_array = cv2.bilateralFilter(img_array, 5, 50, 50)

        # STEP 4: Adaptive thresholding - ONLY for very problematic images
        # For most images, Tesseract works better with grayscale than binary
        apply_thresholding = False

        if enhance_level == "aggressive" and (quality['is_low_contrast'] or quality['is_dark']):
            # Only apply thresholding for images that really need it
            # Use Otsu's method which is more adaptive than fixed thresholding
            _, img_array = cv2.threshold(
                img_array,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            apply_thresholding = True
        elif enhance_level == "medium" and quality['is_low_contrast']:
            # For medium enhancement, only threshold very low contrast images
            # Use adaptive threshold with conservative parameters
            img_array = cv2.adaptiveThreshold(
                img_array,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,  # Large block size for smoother results
                10   # Higher constant for more conservative thresholding
            )
            apply_thresholding = True

        if enhance_level == "aggressive" and apply_thresholding:
            # STEP 5: Noise removal using morphological operations
            # Only apply to binary images (after thresholding)
            # Use smaller kernel to avoid removing small text
            kernel = np.ones((1, 1), np.uint8)
            img_array = cv2.morphologyEx(img_array, cv2.MORPH_CLOSE, kernel)
            img_array = cv2.morphologyEx(img_array, cv2.MORPH_OPEN, kernel)

            # STEP 6: Deskewing (correct rotation)
            coords = np.column_stack(np.where(img_array > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle

                # Only deskew if angle is significant (> 0.5 degrees)
                if abs(angle) > 0.5:
                    (h, w) = img_array.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    img_array = cv2.warpAffine(
                        img_array,
                        M,
                        (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE
                    )

        # Convert back to PIL Image
        processed_image = Image.fromarray(img_array)

        # STEP 7: Final sharpening to enhance text edges
        # Only apply sharpening to grayscale images, not binary
        if not apply_thresholding:
            # Use UnsharpMask for better edge enhancement on grayscale
            processed_image = processed_image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        elif enhance_level == "light" or enhance_level == "medium":
            # Light sharpening for binary images
            processed_image = processed_image.filter(ImageFilter.SHARPEN)

        return processed_image

    def _determine_optimal_psm(self, image: Image.Image) -> int:
        """
        Determine optimal Tesseract PSM (Page Segmentation Mode) based on image characteristics

        PSM modes:
        0 = Orientation and script detection (OSD) only
        1 = Automatic page segmentation with OSD
        3 = Fully automatic page segmentation, but no OSD (Default)
        4 = Assume a single column of text of variable sizes
        6 = Assume a single uniform block of text
        11 = Sparse text. Find as much text as possible in no particular order
        12 = Sparse text with OSD
        13 = Raw line. Treat the image as a single text line

        Args:
            image: PIL Image to analyze

        Returns:
            Optimal PSM mode
        """
        width, height = image.size
        aspect_ratio = width / height

        # Very wide images (like single lines of text)
        if aspect_ratio > 5:
            return 13  # Raw line

        # Very tall/narrow images (like single columns)
        if aspect_ratio < 0.3:
            return 4  # Single column

        # Standard document-like images
        if aspect_ratio > 0.7 and aspect_ratio < 1.5:
            return 6  # Single uniform block of text

        # Default for mixed layouts
        return 3  # Fully automatic

    def extract_text(
        self,
        image_data: BinaryIO,
        language: Optional[str] = None,
        dpi: Optional[int] = None,
        psm: Optional[int] = None,
        preprocess: bool = False,
        enhance_level: str = "auto",
        output_format: str = "text",
        include_boxes: bool = False
    ) -> OCRResult:
        """
        Extract text from image using Tesseract OCR with adaptive optimization

        Args:
            image_data: Binary image data
            language: Language code (default: service default)
            dpi: DPI for OCR processing
            psm: Page segmentation mode (auto-detected if not specified)
            preprocess: Whether to preprocess image (recommended: True)
            enhance_level: Enhancement level - "light", "medium", "aggressive", or "auto" (default)
            output_format: Output format (text, hocr)
            include_boxes: Whether to include word bounding boxes

        Returns:
            OCRResult with extracted text and metadata

        Raises:
            ValueError: If language is not supported
            Exception: If image processing fails
        """
        start_time = time.time()

        # Use default language if not specified
        if language is None:
            language = self.default_language

        # Validate language
        self._validate_language(language)

        # Load image
        try:
            image = Image.open(image_data)
        except Exception as e:
            raise Exception(f"Invalid image data: {str(e)}")

        # Preprocess if requested
        if preprocess:
            image = self._preprocess_image(image, enhance_level=enhance_level)

        # Auto-determine PSM if not specified
        if psm is None:
            psm = self._determine_optimal_psm(image)

        # Build Tesseract config with optimized parameters
        config_parts = [f"--psm {psm}"]

        if dpi is not None:
            config_parts.append(f"--dpi {dpi}")

        # Add Tesseract engine optimization flags
        # OEM 3 = Default, based on what is available (LSTM + Legacy)
        # OEM 1 = Neural nets LSTM engine only (better for most cases)
        config_parts.append("--oem 3")

        config = " ".join(config_parts)

        try:
            # Extract text
            text = pytesseract.image_to_string(image, lang=language, config=config)

            # Get confidence score
            try:
                data = pytesseract.image_to_data(image, lang=language, config=config, output_type=pytesseract.Output.DICT)
                # Calculate average confidence of detected words
                confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                confidence = sum(confidences) / len(confidences) if confidences else 0.0
            except Exception:
                # Fallback confidence
                confidence = 50.0 if text.strip() else 0.0

            # Get additional data if requested
            hocr_data = None
            if output_format == "hocr":
                hocr_data = pytesseract.image_to_pdf_or_hocr(image, lang=language, config=config, extension='hocr').decode('utf-8')

            boxes_data = None
            if include_boxes:
                try:
                    box_data = pytesseract.image_to_data(image, lang=language, config=config, output_type=pytesseract.Output.DICT)
                    boxes_data = []
                    n_boxes = len(box_data['text'])
                    for i in range(n_boxes):
                        if int(box_data['conf'][i]) > 0:  # Only include detected words
                            boxes_data.append({
                                'text': box_data['text'][i],
                                'left': box_data['left'][i],
                                'top': box_data['top'][i],
                                'width': box_data['width'][i],
                                'height': box_data['height'][i],
                                'conf': box_data['conf'][i]
                            })
                except Exception:
                    boxes_data = []

            processing_time = time.time() - start_time

            return OCRResult(
                text=text,
                confidence=confidence,
                language=language,
                processing_time=processing_time,
                dpi=dpi,
                preprocessed=preprocess,
                hocr=hocr_data,
                boxes=boxes_data
            )

        except pytesseract.TesseractError as e:
            raise Exception(f"Tesseract OCR failed: {str(e)}")
