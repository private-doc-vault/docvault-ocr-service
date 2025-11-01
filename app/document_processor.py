"""
Document Processor
Handles conversion of various document formats (PDF, JPG, PNG, TIFF) to images for OCR processing
Supports native PDF text extraction for better accuracy
"""
from PIL import Image
import io
from typing import BinaryIO, List, Optional, Dict, Any
from dataclasses import dataclass
import magic
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFPageCountError, PDFInfoNotInstalledError
from pypdf import PdfReader
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProcessedDocument:
    """Processed document with images ready for OCR"""
    format: str
    page_count: int
    images: List[Image.Image]
    file_size: int
    dpi: Optional[int] = None
    color_mode: Optional[str] = None
    native_text: Optional[List[str]] = None  # Native text extracted from PDF (per page)
    has_native_text: bool = False  # Whether PDF has extractable text


class DocumentProcessor:
    """Processor for converting various document formats to images"""

    def __init__(self):
        """Initialize document processor"""
        self._supported_formats = ['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif']

    def supported_formats(self) -> List[str]:
        """
        Get list of supported document formats

        Returns:
            List of supported format extensions
        """
        return self._supported_formats

    def detect_format(self, file_data: BinaryIO) -> str:
        """
        Detect file format from file data

        Args:
            file_data: Binary file data

        Returns:
            Detected format (lowercase)

        Raises:
            ValueError: If format cannot be detected
        """
        # Read a portion of the file for detection
        file_data.seek(0)
        header = file_data.read(2048)
        file_data.seek(0)

        try:
            # Use python-magic for MIME type detection
            mime_type = magic.from_buffer(header, mime=True)

            # Map MIME types to formats
            mime_to_format = {
                'application/pdf': 'pdf',
                'image/jpeg': 'jpeg',
                'image/jpg': 'jpg',
                'image/png': 'png',
                'image/tiff': 'tiff',
                'image/x-tiff': 'tiff',
            }

            detected = mime_to_format.get(mime_type)
            if detected:
                return detected

            # Fallback: check magic bytes
            if header.startswith(b'%PDF'):
                return 'pdf'
            elif header.startswith(b'\x89PNG'):
                return 'png'
            elif header.startswith(b'\xff\xd8\xff'):
                return 'jpeg'
            elif header.startswith(b'II*\x00') or header.startswith(b'MM\x00*'):
                return 'tiff'

            raise ValueError("Unable to detect file format")

        except Exception as e:
            raise ValueError(f"Format detection failed: {str(e)}")

    def _process_image(
        self,
        file_data: BinaryIO,
        format: str,
        dpi: Optional[int] = None,
        color_mode: Optional[str] = None
    ) -> ProcessedDocument:
        """
        Process image files (PNG, JPG, TIFF)

        Args:
            file_data: Binary file data
            format: File format
            dpi: DPI for processing
            color_mode: Color mode (grayscale, rgb, etc.)

        Returns:
            ProcessedDocument with image data
        """
        file_data.seek(0)
        file_size = len(file_data.read())
        file_data.seek(0)

        try:
            # Open image with PIL
            image = Image.open(file_data)

            images = []
            page_count = 0

            # Handle multi-page TIFF
            if format in ['tiff', 'tif']:
                try:
                    # Get number of frames (pages)
                    page_count = getattr(image, 'n_frames', 1)

                    for i in range(page_count):
                        image.seek(i)
                        # Create a copy of the current frame
                        frame = image.copy()

                        # Apply color mode conversion if specified
                        if color_mode == 'grayscale' and frame.mode not in ['L', 'LA']:
                            frame = frame.convert('L')

                        images.append(frame)

                except (EOFError, AttributeError):
                    # Single page TIFF or error reading frames
                    image.load()  # Force load to avoid file handle issues
                    img_copy = image.copy()
                    if color_mode == 'grayscale' and img_copy.mode not in ['L', 'LA']:
                        img_copy = img_copy.convert('L')
                    images.append(img_copy)
                    page_count = 1
            else:
                # Single page image (PNG, JPG)
                # IMPORTANT: Load and copy the image to avoid "seek of closed file" errors
                # when the file handle is closed but image is used later
                image.load()  # Force load image data into memory
                img_copy = image.copy()  # Create a copy to detach from file handle

                if color_mode == 'grayscale' and img_copy.mode not in ['L', 'LA']:
                    img_copy = img_copy.convert('L')
                images.append(img_copy)
                page_count = 1

            return ProcessedDocument(
                format=format,
                page_count=page_count,
                images=images,
                file_size=file_size,
                dpi=dpi,
                color_mode=color_mode
            )

        except Exception as e:
            raise Exception(f"Failed to process image: {str(e)}")

    def _extract_native_pdf_text(self, file_data: BinaryIO) -> tuple[List[str], bool]:
        """
        Extract native text from PDF (if available)

        Args:
            file_data: Binary PDF data

        Returns:
            Tuple of (list of text per page, has_text flag)
        """
        try:
            file_data.seek(0)
            reader = PdfReader(file_data)

            page_texts = []
            total_chars = 0

            for page in reader.pages:
                text = page.extract_text()
                page_texts.append(text)
                total_chars += len(text.strip())

            # Consider PDF has native text if we extracted at least 100 characters
            # This filters out PDFs with minimal/metadata text only
            has_text = total_chars >= 100

            if has_text:
                logger.info(f"Extracted {total_chars} characters of native text from {len(page_texts)} pages")
            else:
                logger.info(f"PDF has minimal native text ({total_chars} chars), will rely on OCR")

            return page_texts, has_text

        except Exception as e:
            logger.warning(f"Failed to extract native PDF text: {e}")
            return [], False

    def _process_pdf(
        self,
        file_data: BinaryIO,
        dpi: Optional[int] = None,
        color_mode: Optional[str] = None
    ) -> ProcessedDocument:
        """
        Process PDF files by converting to images and extracting native text

        Args:
            file_data: Binary PDF data
            dpi: DPI for rendering (default: 300 - increased from 200 for better OCR accuracy)
            color_mode: Color mode (grayscale, rgb, etc.)

        Returns:
            ProcessedDocument with images from PDF pages and native text (if available)
        """
        file_data.seek(0)
        file_size = len(file_data.read())
        file_data.seek(0)

        # Default DPI for PDF rendering - increased to 300 for better OCR accuracy
        if dpi is None:
            dpi = 300

        # Extract native text from PDF first
        native_text, has_native_text = self._extract_native_pdf_text(file_data)

        try:
            # Convert PDF to images
            file_data.seek(0)
            images = convert_from_bytes(
                file_data.read(),
                dpi=dpi,
                fmt='png'
            )

            # Apply color mode if specified
            if color_mode == 'grayscale':
                images = [img.convert('L') if img.mode not in ['L', 'LA'] else img for img in images]

            return ProcessedDocument(
                format='pdf',
                page_count=len(images),
                images=images,
                file_size=file_size,
                dpi=dpi,
                color_mode=color_mode,
                native_text=native_text if native_text else None,
                has_native_text=has_native_text
            )

        except (PDFPageCountError, PDFInfoNotInstalledError) as e:
            raise Exception(f"PDF processing error: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to process PDF: {str(e)}")

    def process(
        self,
        file_data: BinaryIO,
        format: Optional[str] = None,
        dpi: Optional[int] = None,
        color_mode: Optional[str] = None
    ) -> ProcessedDocument:
        """
        Process a document file and convert to images

        Args:
            file_data: Binary file data
            format: File format (optional, will be auto-detected if not provided)
            dpi: DPI for processing (applies to PDFs mainly)
            color_mode: Color mode for conversion (grayscale, rgb, etc.)

        Returns:
            ProcessedDocument with processed images

        Raises:
            ValueError: If format is unsupported
            Exception: If processing fails
        """
        # Auto-detect format if not provided
        if format is None:
            format = self.detect_format(file_data)

        # Normalize format
        format = format.lower()

        # Validate format
        if format not in self._supported_formats:
            raise ValueError(f"Unsupported format: {format}. Supported formats: {', '.join(self._supported_formats)}")

        # Process based on format
        if format == 'pdf':
            return self._process_pdf(file_data, dpi=dpi, color_mode=color_mode)
        else:
            return self._process_image(file_data, format=format, dpi=dpi, color_mode=color_mode)
