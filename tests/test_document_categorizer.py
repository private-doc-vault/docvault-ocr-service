"""
Tests for Document Categorization
Following TDD methodology - these tests define the expected behavior for document categorization
"""
import pytest

from app.document_categorizer import DocumentCategorizer, CategoryResult


@pytest.fixture
def categorizer():
    """Create document categorizer instance"""
    return DocumentCategorizer()


class TestCategorizerInitialization:
    """Test categorizer initialization"""

    def test_categorizer_can_be_instantiated(self):
        """Test that categorizer can be created"""
        categorizer = DocumentCategorizer()
        assert categorizer is not None

    def test_categorizer_has_categories(self, categorizer):
        """Test that categorizer has predefined categories"""
        categories = categorizer.get_supported_categories()
        assert isinstance(categories, list)
        assert len(categories) > 0


class TestInvoiceDetection:
    """Test invoice document detection"""

    def test_detect_invoice_by_keywords(self, categorizer):
        """Test invoice detection by keyword matching"""
        text = """
        INVOICE

        Invoice Number: INV-2024-001
        Date: 15/03/2024
        Amount Due: $500.00
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "invoice"
        assert result.confidence > 0.5

    def test_detect_invoice_by_patterns(self, categorizer):
        """Test invoice detection by pattern matching"""
        text = """
        Bill To: John Smith
        Invoice #: 12345
        Total: $1,250.00
        Payment Due: 30 days
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "invoice"

    def test_invoice_confidence_score(self, categorizer):
        """Test that invoice detection has appropriate confidence"""
        text = "INVOICE Number: INV-001 Total: $100.00 Due Date: 01/01/2024"

        result = categorizer.categorize(text)

        assert result.primary_category == "invoice"
        assert 0.0 <= result.confidence <= 1.0


class TestReceiptDetection:
    """Test receipt document detection"""

    def test_detect_receipt_by_keywords(self, categorizer):
        """Test receipt detection"""
        text = """
        RECEIPT

        Store: Acme Store
        Date: 2024-03-15

        Items:
        - Item 1: $10.00
        - Item 2: $15.00

        Subtotal: $25.00
        Tax: $2.50
        Total: $27.50

        Thank you!
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "receipt"
        assert result.confidence > 0.5

    def test_distinguish_receipt_from_invoice(self, categorizer):
        """Test that receipts are distinguished from invoices"""
        receipt_text = "RECEIPT Store: ABC Total: $50.00 Thank you"
        invoice_text = "INVOICE Invoice #: 123 Amount Due: $50.00"

        receipt_result = categorizer.categorize(receipt_text)
        invoice_result = categorizer.categorize(invoice_text)

        assert receipt_result.primary_category == "receipt"
        assert invoice_result.primary_category == "invoice"


class TestContractDetection:
    """Test contract document detection"""

    def test_detect_contract_by_keywords(self, categorizer):
        """Test contract detection"""
        text = """
        EMPLOYMENT CONTRACT

        This agreement is made between...

        Terms and Conditions:
        1. The employee agrees to...
        2. The employer agrees to...

        Signed: _______________
        Date: _______________
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "contract"
        assert result.confidence > 0.4

    def test_detect_agreement_as_contract(self, categorizer):
        """Test that agreements are categorized as contracts"""
        text = """
        SERVICE AGREEMENT

        This agreement is entered into between the parties...
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "contract"


class TestLetterDetection:
    """Test letter document detection"""

    def test_detect_formal_letter(self, categorizer):
        """Test formal letter detection"""
        text = """
        Dear Mr. Smith,

        I am writing to inform you about...

        Thank you for your attention to this matter.

        Sincerely,
        John Doe
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "letter"

    def test_detect_business_letter(self, categorizer):
        """Test business letter detection"""
        text = """
        To Whom It May Concern,

        This letter serves as confirmation...

        Best regards,
        Jane Smith
        Manager
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "letter"


class TestReportDetection:
    """Test report document detection"""

    def test_detect_report_by_structure(self, categorizer):
        """Test report detection"""
        text = """
        QUARTERLY REPORT

        Executive Summary

        1. Introduction
        2. Findings
        3. Recommendations
        4. Conclusion
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "report"


class TestFormDetection:
    """Test form document detection"""

    def test_detect_application_form(self, categorizer):
        """Test form detection"""
        text = """
        APPLICATION FORM

        Name: ______________
        Address: ______________
        Phone: ______________
        Email: ______________

        Please complete all fields.
        """

        result = categorizer.categorize(text)

        assert result.primary_category == "form"


class TestOtherDocumentTypes:
    """Test other document type detection"""

    def test_detect_memo(self, categorizer):
        """Test memo detection"""
        text = """
        MEMORANDUM

        To: All Staff
        From: Management
        Date: 2024-03-15
        Re: Office Policy Update

        Please note the following changes...
        """

        result = categorizer.categorize(text)

        assert result.primary_category in ["memo", "letter", "other"]

    def test_detect_certificate(self, categorizer):
        """Test certificate detection"""
        text = """
        CERTIFICATE OF COMPLETION

        This certifies that John Smith
        has successfully completed...

        Awarded on: March 15, 2024
        """

        result = categorizer.categorize(text)

        assert result.primary_category in ["certificate", "other"]


class TestMultiCategoryDetection:
    """Test documents that might fit multiple categories"""

    def test_get_all_matching_categories(self, categorizer):
        """Test getting all matching categories with scores"""
        text = """
        INVOICE RECEIPT

        Invoice #: 123
        Date: 2024-03-15
        Total: $100.00
        """

        result = categorizer.categorize(text)

        # Should identify both invoice and receipt
        assert hasattr(result, 'all_categories')
        assert len(result.all_categories) >= 1


class TestConfidenceScoring:
    """Test confidence scoring for categorization"""

    def test_high_confidence_for_clear_documents(self, categorizer):
        """Test high confidence for clearly identifiable documents"""
        text = """
        INVOICE
        Invoice Number: INV-2024-001
        Invoice Date: 15/03/2024
        Amount Due: $500.00
        Payment Terms: Net 30
        """

        result = categorizer.categorize(text)

        assert result.confidence > 0.7

    def test_lower_confidence_for_ambiguous_documents(self, categorizer):
        """Test lower confidence for ambiguous documents"""
        text = """
        Some text that doesn't clearly identify the document type.
        It has some words and numbers but no clear patterns.
        """

        result = categorizer.categorize(text)

        assert result.confidence < 0.5

    def test_confidence_based_on_pattern_matches(self, categorizer):
        """Test that confidence increases with more pattern matches"""
        weak_text = "Invoice"
        strong_text = "INVOICE Number: 123 Date: 01/01/2024 Total: $100 Due Date: 02/01/2024"

        weak_result = categorizer.categorize(weak_text)
        strong_result = categorizer.categorize(strong_text)

        assert strong_result.confidence > weak_result.confidence


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_categorize_empty_text(self, categorizer):
        """Test categorization of empty text"""
        result = categorizer.categorize("")

        assert result.primary_category == "unknown"
        assert result.confidence < 0.3

    def test_categorize_very_short_text(self, categorizer):
        """Test categorization of very short text"""
        result = categorizer.categorize("abc")

        assert result.primary_category == "unknown"
        assert result.confidence < 0.5

    def test_categorize_nonsensical_text(self, categorizer):
        """Test categorization of nonsensical text"""
        text = "asdfjkl qwerty zxcvbn 12345"
        result = categorizer.categorize(text)

        assert result.primary_category == "unknown"

    def test_categorize_with_special_characters(self, categorizer):
        """Test categorization with special characters"""
        text = "INVOICE Number: 123 Total: $100.00 Due Date: 01/01/2024"
        result = categorizer.categorize(text)

        # Should detect invoice with reasonable special character noise
        assert result.primary_category == "invoice"


class TestCategoryMetadata:
    """Test category metadata extraction"""

    def test_extract_document_type_indicators(self, categorizer):
        """Test extraction of document type indicators"""
        text = "INVOICE Number: 123"
        result = categorizer.categorize(text)

        if hasattr(result, 'indicators'):
            assert len(result.indicators) > 0

    def test_category_result_includes_all_scores(self, categorizer):
        """Test that result includes scores for all categories"""
        text = "INVOICE Total: $100"
        result = categorizer.categorize(text)

        assert hasattr(result, 'all_categories')
        assert isinstance(result.all_categories, dict)


class TestSupportedCategories:
    """Test supported categories"""

    def test_get_supported_categories_list(self, categorizer):
        """Test getting list of supported categories"""
        categories = categorizer.get_supported_categories()

        assert "invoice" in categories
        assert "receipt" in categories
        assert "contract" in categories
        assert "letter" in categories

    def test_category_descriptions(self, categorizer):
        """Test that categories have descriptions"""
        if hasattr(categorizer, 'get_category_descriptions'):
            descriptions = categorizer.get_category_descriptions()
            assert isinstance(descriptions, dict)
            assert "invoice" in descriptions
