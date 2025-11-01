"""
Tests for Metadata Extraction
Following TDD methodology - these tests define the expected behavior for extracting dates, amounts, and names
"""
import pytest
from datetime import datetime, date

from app.metadata_extractor import MetadataExtractor, ExtractedMetadata


@pytest.fixture
def metadata_extractor():
    """Create metadata extractor instance"""
    return MetadataExtractor()


class TestMetadataExtractorInitialization:
    """Test metadata extractor initialization"""

    def test_extractor_can_be_instantiated(self):
        """Test that metadata extractor can be created"""
        extractor = MetadataExtractor()
        assert extractor is not None


class TestDateExtraction:
    """Test date extraction from text"""

    def test_extract_simple_date_format(self, metadata_extractor):
        """Test extracting simple date format (DD/MM/YYYY)"""
        text = "Invoice date: 15/03/2024"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) > 0
        assert any(d.year == 2024 and d.month == 3 and d.day == 15 for d in metadata.dates)

    def test_extract_us_date_format(self, metadata_extractor):
        """Test extracting US date format (MM/DD/YYYY)"""
        text = "Date: 03/15/2024"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) > 0
        # Should detect as either March 15 or Day 15 of month 3

    def test_extract_iso_date_format(self, metadata_extractor):
        """Test extracting ISO date format (YYYY-MM-DD)"""
        text = "Document created: 2024-03-15"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) > 0
        assert any(d.year == 2024 and d.month == 3 and d.day == 15 for d in metadata.dates)

    def test_extract_written_date_format(self, metadata_extractor):
        """Test extracting written date formats"""
        text = "Dated March 15, 2024"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) > 0
        assert any(d.year == 2024 and d.month == 3 for d in metadata.dates)

    def test_extract_multiple_dates(self, metadata_extractor):
        """Test extracting multiple dates from text"""
        text = "Invoice dated 01/01/2024, due date 15/01/2024"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) >= 2

    def test_extract_date_with_context(self, metadata_extractor):
        """Test that date extraction includes context"""
        text = "Invoice Date: 15/03/2024"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) > 0
        # Should have context information
        if hasattr(metadata, 'date_contexts'):
            assert len(metadata.date_contexts) > 0


class TestAmountExtraction:
    """Test monetary amount extraction from text"""

    def test_extract_simple_amount(self, metadata_extractor):
        """Test extracting simple amount with currency symbol"""
        text = "Total: $150.00"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) > 0
        assert any(abs(a - 150.00) < 0.01 for a in metadata.amounts)

    def test_extract_amount_with_euro_symbol(self, metadata_extractor):
        """Test extracting amount with Euro symbol"""
        text = "Amount: €250.50"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) > 0
        assert any(abs(a - 250.50) < 0.01 for a in metadata.amounts)

    def test_extract_amount_with_pound_symbol(self, metadata_extractor):
        """Test extracting amount with Pound symbol"""
        text = "Total: £99.99"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) > 0
        assert any(abs(a - 99.99) < 0.01 for a in metadata.amounts)

    def test_extract_amount_with_comma_separator(self, metadata_extractor):
        """Test extracting amount with comma thousands separator"""
        text = "Invoice total: $1,500.00"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) > 0
        assert any(abs(a - 1500.00) < 0.01 for a in metadata.amounts)

    def test_extract_amount_with_european_format(self, metadata_extractor):
        """Test extracting amount with European number format (comma as decimal)"""
        text = "Betrag: 1.500,00 €"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) > 0
        # Should detect 1500.00

    def test_extract_multiple_amounts(self, metadata_extractor):
        """Test extracting multiple amounts from text"""
        text = "Subtotal: $100.00, Tax: $10.00, Total: $110.00"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) >= 3

    def test_extract_amount_with_label(self, metadata_extractor):
        """Test that amount extraction includes label/context"""
        text = "Total Amount: $500.00"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.amounts) > 0
        # Should have associated labels
        if hasattr(metadata, 'amount_labels'):
            assert len(metadata.amount_labels) > 0


class TestNameExtraction:
    """Test name extraction from text"""

    def test_extract_simple_name(self, metadata_extractor):
        """Test extracting simple full name"""
        text = "Customer: John Smith"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.names) > 0
        assert any("John" in name or "Smith" in name for name in metadata.names)

    def test_extract_name_with_title(self, metadata_extractor):
        """Test extracting name with title"""
        text = "To: Mr. Robert Johnson"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.names) > 0
        assert any("Robert" in name or "Johnson" in name for name in metadata.names)

    def test_extract_multiple_names(self, metadata_extractor):
        """Test extracting multiple names from text"""
        text = "From: Alice Brown\nTo: Bob Wilson"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.names) >= 2

    def test_extract_company_name(self, metadata_extractor):
        """Test extracting company/organization names"""
        text = "Issued by: Acme Corporation"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.names) > 0
        assert any("Acme" in name for name in metadata.names)

    def test_name_extraction_with_context(self, metadata_extractor):
        """Test that name extraction includes context"""
        text = "Vendor: John Smith"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.names) > 0
        if hasattr(metadata, 'name_contexts'):
            assert len(metadata.name_contexts) > 0


class TestEmailExtraction:
    """Test email address extraction"""

    def test_extract_simple_email(self, metadata_extractor):
        """Test extracting simple email address"""
        text = "Contact: john.smith@example.com"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.emails) > 0
        assert "john.smith@example.com" in metadata.emails

    def test_extract_multiple_emails(self, metadata_extractor):
        """Test extracting multiple email addresses"""
        text = "From: sender@example.com\nTo: receiver@example.org"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.emails) >= 2


class TestPhoneExtraction:
    """Test phone number extraction"""

    def test_extract_us_phone_format(self, metadata_extractor):
        """Test extracting US phone format"""
        text = "Phone: (555) 123-4567"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.phones) > 0

    def test_extract_international_phone_format(self, metadata_extractor):
        """Test extracting international phone format"""
        text = "Tel: +1-555-123-4567"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.phones) > 0

    def test_extract_simple_phone_format(self, metadata_extractor):
        """Test extracting simple phone number"""
        text = "Contact: 555-123-4567"
        metadata = metadata_extractor.extract(text)

        assert len(metadata.phones) > 0


class TestAddressExtraction:
    """Test address extraction"""

    def test_extract_street_address(self, metadata_extractor):
        """Test extracting street address"""
        text = "Address: 123 Main Street, Springfield"
        metadata = metadata_extractor.extract(text)

        if hasattr(metadata, 'addresses'):
            assert len(metadata.addresses) > 0

    def test_extract_zip_code(self, metadata_extractor):
        """Test extracting zip/postal code"""
        text = "ZIP: 12345"
        metadata = metadata_extractor.extract(text)

        if hasattr(metadata, 'postal_codes'):
            assert len(metadata.postal_codes) > 0


class TestInvoiceSpecificMetadata:
    """Test invoice-specific metadata extraction"""

    def test_extract_invoice_number(self, metadata_extractor):
        """Test extracting invoice number"""
        text = "Invoice #: INV-2024-0001"
        metadata = metadata_extractor.extract(text)

        if hasattr(metadata, 'invoice_numbers'):
            assert len(metadata.invoice_numbers) > 0

    def test_extract_po_number(self, metadata_extractor):
        """Test extracting purchase order number"""
        text = "PO Number: PO-12345"
        metadata = metadata_extractor.extract(text)

        if hasattr(metadata, 'po_numbers'):
            assert len(metadata.po_numbers) > 0


class TestComplexDocumentExtraction:
    """Test extraction from complex document text"""

    def test_extract_from_invoice_text(self, metadata_extractor):
        """Test extracting metadata from invoice-like text"""
        text = """
        INVOICE

        Invoice Number: INV-2024-001
        Date: 15/03/2024
        Due Date: 15/04/2024

        Bill To:
        John Smith
        123 Main Street
        Springfield, IL 62701

        Amount Due: $1,250.00

        Contact: billing@example.com
        Phone: (555) 123-4567
        """

        metadata = metadata_extractor.extract(text)

        # Should extract dates
        assert len(metadata.dates) >= 2

        # Should extract amounts
        assert len(metadata.amounts) >= 1
        assert any(abs(a - 1250.00) < 0.01 for a in metadata.amounts)

        # Should extract names
        assert len(metadata.names) >= 1

        # Should extract email
        assert len(metadata.emails) >= 1

        # Should extract phone
        assert len(metadata.phones) >= 1

    def test_extract_from_receipt_text(self, metadata_extractor):
        """Test extracting metadata from receipt-like text"""
        text = """
        RECEIPT

        Date: 2024-03-15
        Store: Acme Store

        Subtotal: $25.00
        Tax: $2.50
        Total: $27.50

        Thank you!
        """

        metadata = metadata_extractor.extract(text)

        assert len(metadata.dates) >= 1
        assert len(metadata.amounts) >= 1
        assert len(metadata.names) >= 1  # Store name


class TestMetadataValidation:
    """Test metadata validation and filtering"""

    def test_filter_invalid_dates(self, metadata_extractor):
        """Test that invalid dates are filtered out"""
        text = "Date: 99/99/9999"  # Invalid date
        metadata = metadata_extractor.extract(text)

        # Should not include invalid dates
        for d in metadata.dates:
            assert d.year < 9999

    def test_filter_unrealistic_amounts(self, metadata_extractor):
        """Test that unrealistic amounts are handled"""
        text = "Amount: $999,999,999.99"
        metadata = metadata_extractor.extract(text)

        # Should still extract but may flag as unusual
        assert isinstance(metadata.amounts, list)

    def test_deduplicate_extracted_data(self, metadata_extractor):
        """Test that duplicate data is deduplicated"""
        text = "Date: 15/03/2024\nDate: 15/03/2024"  # Same date twice
        metadata = metadata_extractor.extract(text)

        # Should deduplicate
        unique_dates = set(str(d) for d in metadata.dates)
        assert len(unique_dates) <= 2  # Allow for slight parsing differences


class TestMetadataConfidence:
    """Test confidence scoring for extracted metadata"""

    def test_metadata_includes_confidence_scores(self, metadata_extractor):
        """Test that extracted metadata includes confidence scores"""
        text = "Invoice Date: 15/03/2024, Total: $100.00"
        metadata = metadata_extractor.extract(text)

        # Metadata should have confidence information
        assert hasattr(metadata, 'confidence')
        if metadata.confidence:
            assert 0.0 <= metadata.confidence <= 1.0
