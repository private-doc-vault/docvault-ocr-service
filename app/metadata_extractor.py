"""
Metadata Extractor
Extracts structured metadata (dates, amounts, names, etc.) from OCR text
"""
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from dateutil import parser as date_parser
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedMetadata:
    """Container for extracted metadata"""
    dates: List[date] = field(default_factory=list)
    amounts: List[float] = field(default_factory=list)
    names: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    addresses: List[str] = field(default_factory=list)
    postal_codes: List[str] = field(default_factory=list)
    invoice_numbers: List[str] = field(default_factory=list)
    po_numbers: List[str] = field(default_factory=list)
    tax_ids: List[str] = field(default_factory=list)  # NIP (Polish) or other tax IDs
    date_contexts: List[str] = field(default_factory=list)
    amount_labels: List[str] = field(default_factory=list)
    name_contexts: List[str] = field(default_factory=list)
    confidence: Optional[float] = None


class MetadataExtractor:
    """Extractor for structured metadata from text"""

    def __init__(self):
        """Initialize metadata extractor with regex patterns (Polish + English)"""
        # Currency symbols (including Polish złoty)
        self.currency_symbols = r'[$€£¥₹]|zł|PLN'

        # Date patterns (English and Polish)
        self.date_patterns = [
            # ISO format: YYYY-MM-DD
            r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',
            # DD/MM/YYYY or MM/DD/YYYY or DD.MM.YYYY (common in Poland)
            r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b',
            # Written format (English): March 15, 2024 or 15 March 2024
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})\b',
            r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{4})\b',
            # Written format (Polish): 15 stycznia 2024 or stycznia 15, 2024
            r'\b(\d{1,2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia|sty|lut|mar|kwi|maj|cze|lip|sie|wrz|paź|lis|gru)\.?\s+(\d{4})\b',
            r'\b(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia|sty|lut|mar|kwi|maj|cze|lip|sie|wrz|paź|lis|gru)\.?\s+(\d{1,2}),?\s+(\d{4})\b',
        ]

        # Amount patterns (with Polish złoty support)
        self.amount_patterns = [
            # Currency symbol followed by amount
            rf'(?:{self.currency_symbols})\s*(\d{{1,3}}(?:[,\.\s]\d{{3}})*(?:[,\.]\d{{2}})?)',
            # Amount followed by currency symbol
            rf'(\d{{1,3}}(?:[,\.\s]\d{{3}})*(?:[,\.]\d{{2}})?)\s*(?:{self.currency_symbols})',
            # Amount with currency code (including Polish złoty)
            r'(\d{1,3}(?:[,\.\s]\d{3})*(?:[,\.]\d{2})?)\s*(USD|EUR|GBP|CAD|AUD|PLN|zł)',
        ]

        # Email pattern
        self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

        # Phone patterns (including Polish format)
        self.phone_patterns = [
            # International format
            r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            # US format
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            # Polish format: +48 123 456 789 or 123-456-789 or 123456789
            r'\+?48\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{3}',
            r'\b\d{3}[\s\-]?\d{3}[\s\-]?\d{3}\b',
            r'\b\d{9}\b',
        ]

        # Name patterns (capitalized words, typically 2-3 words)
        self.name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'

        # Invoice/PO number patterns (English and Polish)
        self.invoice_pattern = r'\b(?:Invoice|INV|INVOICE|Faktura|Fakt|FV|FS)[\s#:\/nr]*([A-Z0-9\-\/]+)\b'
        self.po_pattern = r'\b(?:PO|P\.O\.|Purchase Order|Zamówienie|Zam)[\s#:\/nr]*([A-Z0-9\-\/]+)\b'

        # Postal code patterns (including Polish format)
        self.postal_code_patterns = [
            r'\b\d{5}(?:-\d{4})?\b',  # US ZIP
            r'\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b',  # Canadian postal code
            r'\b\d{2}-\d{3}\b',  # Polish postal code: XX-XXX
        ]

        # Tax ID patterns (including Polish NIP)
        self.tax_id_patterns = [
            r'\bNIP\s*:?\s*(\d{10}|\d{3}-\d{3}-\d{2}-\d{2}|\d{3}-\d{2}-\d{2}-\d{3})\b',  # Polish NIP
            r'\b(?:Tax\s+ID|TIN|EIN)\s*:?\s*(\d{2}-\d{7})\b',  # US EIN
        ]

        # Context patterns for better extraction (English and Polish)
        self.date_context_pattern = r'((?:invoice|bill|due|payment|dated?|issued?|from|to|created?|modified?|effective|faktura|termin|płatność|wystawiono|data|sprzedaż)\s*(?:date|on|dnia|z|do)?)\s*:?\s*'
        self.amount_context_pattern = r'((?:total|subtotal|amount|price|cost|tax|balance|due|paid?|payment|suma|razem|kwota|cena|koszt|vat|należność|zapłacono)\s*(?:amount|due|paid|do\s+zapłaty)?)\s*:?\s*'
        self.name_context_pattern = r'((?:customer|client|vendor|supplier|from|to|bill\s+to|ship\s+to|name|contact|nabywca|sprzedawca|klient|dostawca|od|do|imię|nazwisko)\s*:?\s*)'

    def _extract_dates(self, text: str) -> tuple[List[date], List[str]]:
        """Extract dates from text"""
        dates = []
        contexts = []

        for pattern in self.date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    date_str = match.group(0)
                    parsed_date = date_parser.parse(date_str, fuzzy=True).date()

                    # Validate date is reasonable (between 1900 and 2100)
                    if 1900 <= parsed_date.year <= 2100:
                        dates.append(parsed_date)

                        # Extract context
                        start_pos = max(0, match.start() - 50)
                        context = text[start_pos:match.start()].strip()
                        contexts.append(context[-30:] if len(context) > 30 else context)

                except (ValueError, OverflowError):
                    continue

        return dates, contexts

    def _extract_amounts(self, text: str) -> tuple[List[float], List[str]]:
        """Extract monetary amounts from text"""
        amounts = []
        labels = []

        for pattern in self.amount_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    # Get the amount string (first capturing group)
                    amount_str = match.group(1)

                    # Clean the amount string
                    # Remove spaces
                    amount_str = amount_str.replace(' ', '')

                    # Handle European format (comma as decimal separator)
                    # Check if comma is decimal separator (e.g., 1.500,00)
                    if '.' in amount_str and ',' in amount_str:
                        if amount_str.rindex(',') > amount_str.rindex('.'):
                            # European format: 1.500,00 -> 1500.00
                            amount_str = amount_str.replace('.', '').replace(',', '.')
                        else:
                            # US format: 1,500.00 -> 1500.00
                            amount_str = amount_str.replace(',', '')
                    elif ',' in amount_str and '.' not in amount_str:
                        # Could be European decimal: 500,00 or US thousands: 1,500
                        # If only one comma and 2 digits after, treat as decimal
                        if amount_str.count(',') == 1 and len(amount_str.split(',')[1]) == 2:
                            amount_str = amount_str.replace(',', '.')
                        else:
                            amount_str = amount_str.replace(',', '')
                    else:
                        # Remove any remaining commas
                        amount_str = amount_str.replace(',', '')

                    amount = float(amount_str)

                    # Basic validation (amounts should be reasonable)
                    if 0 < amount < 1000000000:  # Less than 1 billion
                        amounts.append(amount)

                        # Extract label/context
                        start_pos = max(0, match.start() - 30)
                        context = text[start_pos:match.start()].strip()
                        labels.append(context[-20:] if len(context) > 20 else context)

                except (ValueError, IndexError):
                    continue

        return amounts, labels

    def _extract_names(self, text: str) -> tuple[List[str], List[str]]:
        """Extract person/company names from text"""
        names = []
        contexts = []

        # Common titles to remove
        titles = ['Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sir', 'Madam']

        for match in re.finditer(self.name_pattern, text):
            name = match.group(0)

            # Remove common titles
            name_parts = name.split()
            cleaned_parts = [p.rstrip('.') for p in name_parts if p.rstrip('.') not in titles]
            cleaned_name = ' '.join(cleaned_parts)

            if cleaned_name and len(cleaned_name) > 3:  # At least 4 characters
                names.append(cleaned_name)

                # Extract context
                start_pos = max(0, match.start() - 30)
                context = text[start_pos:match.start()].strip()
                contexts.append(context[-20:] if len(context) > 20 else context)

        return names, contexts

    def _extract_emails(self, text: str) -> List[str]:
        """Extract email addresses from text"""
        return list(set(re.findall(self.email_pattern, text)))

    def _extract_phones(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        phones = []
        for pattern in self.phone_patterns:
            phones.extend(re.findall(pattern, text))
        return list(set(phones))

    def _extract_invoice_numbers(self, text: str) -> List[str]:
        """Extract invoice numbers from text"""
        return list(set(re.findall(self.invoice_pattern, text, re.IGNORECASE)))

    def _extract_po_numbers(self, text: str) -> List[str]:
        """Extract purchase order numbers from text"""
        return list(set(re.findall(self.po_pattern, text, re.IGNORECASE)))

    def _extract_postal_codes(self, text: str) -> List[str]:
        """Extract postal/ZIP codes from text"""
        codes = []
        for pattern in self.postal_code_patterns:
            codes.extend(re.findall(pattern, text))
        return list(set(codes))

    def _extract_addresses(self, text: str) -> List[str]:
        """Extract street addresses from text (English and Polish)"""
        # Pattern for English street addresses
        address_pattern_en = r'\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\.?)'
        # Pattern for Polish street addresses
        address_pattern_pl = r'\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:ul\.|ulica|al\.|aleja|pl\.|plac))?\s*\d*[A-Za-z]?'

        addresses = []
        addresses.extend(re.findall(address_pattern_en, text))
        addresses.extend(re.findall(address_pattern_pl, text))
        return list(set(addresses))

    def _extract_tax_ids(self, text: str) -> List[str]:
        """Extract tax identification numbers (including Polish NIP)"""
        tax_ids = []
        for pattern in self.tax_id_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            tax_ids.extend(matches)
        return list(set(tax_ids))

    def _calculate_confidence(self, metadata: ExtractedMetadata, text: str) -> float:
        """Calculate confidence score for extracted metadata"""
        score = 0.0
        max_score = 0.0

        # Award points for each type of metadata found
        if metadata.dates:
            score += 0.2
        max_score += 0.2

        if metadata.amounts:
            score += 0.2
        max_score += 0.2

        if metadata.names:
            score += 0.15
        max_score += 0.15

        if metadata.emails:
            score += 0.15
        max_score += 0.15

        if metadata.phones:
            score += 0.1
        max_score += 0.1

        if metadata.invoice_numbers or metadata.po_numbers:
            score += 0.1
        max_score += 0.1

        if metadata.addresses or metadata.postal_codes:
            score += 0.1
        max_score += 0.1

        if metadata.tax_ids:
            score += 0.1
        max_score += 0.1

        return score / max_score if max_score > 0 else 0.0

    def extract(self, text: str) -> ExtractedMetadata:
        """
        Extract all metadata from text

        Args:
            text: Input text from OCR

        Returns:
            ExtractedMetadata with all extracted information
        """
        metadata = ExtractedMetadata()

        try:
            # Extract dates
            dates, date_contexts = self._extract_dates(text)
            metadata.dates = dates
            metadata.date_contexts = date_contexts

            # Extract amounts
            amounts, amount_labels = self._extract_amounts(text)
            metadata.amounts = amounts
            metadata.amount_labels = amount_labels

            # Extract names
            names, name_contexts = self._extract_names(text)
            metadata.names = names
            metadata.name_contexts = name_contexts

            # Extract other metadata
            metadata.emails = self._extract_emails(text)
            metadata.phones = self._extract_phones(text)
            metadata.addresses = self._extract_addresses(text)
            metadata.postal_codes = self._extract_postal_codes(text)
            metadata.invoice_numbers = self._extract_invoice_numbers(text)
            metadata.po_numbers = self._extract_po_numbers(text)
            metadata.tax_ids = self._extract_tax_ids(text)

            # Calculate confidence
            metadata.confidence = self._calculate_confidence(metadata, text)

        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")

        return metadata
