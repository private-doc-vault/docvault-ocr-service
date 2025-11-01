"""
Metadata Extractor V2 - Multi-language support
Extracts structured metadata (dates, amounts, names, etc.) from OCR text
Uses language-specific patterns from the languages module
"""
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from dateutil import parser as date_parser
import logging

from .languages import get_all_languages
from .languages.loader import load_all_languages

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
    tax_ids: List[str] = field(default_factory=list)
    date_contexts: List[str] = field(default_factory=list)
    amount_labels: List[str] = field(default_factory=list)
    name_contexts: List[str] = field(default_factory=list)
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to flat dictionary structure for API responses.
        Date objects are converted to ISO format strings.
        """
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, list) and value and isinstance(value[0], date):
                # Convert date objects to ISO format strings
                result[key] = [d.isoformat() if isinstance(d, date) else d for d in value]
            else:
                result[key] = value
        return result


class MetadataExtractor:
    """
    Extractor for structured metadata from text

    Supports multiple languages and automatically uses patterns
    from all enabled languages
    """

    def __init__(self, languages: Optional[List[str]] = None):
        """
        Initialize metadata extractor

        Args:
            languages: List of language codes to use (e.g., ['en', 'pl'])
                      If None, uses all available languages
        """
        # Ensure languages are loaded
        load_all_languages()

        # Get language configurations
        all_langs = get_all_languages()

        if languages:
            self.languages = {code: all_langs[code] for code in languages if code in all_langs}
        else:
            self.languages = all_langs

        if not self.languages:
            raise ValueError("No language configurations available")

        logger.info(f"MetadataExtractor initialized with languages: {list(self.languages.keys())}")

        # Build combined patterns from all languages
        self._build_patterns()

        # Email pattern (language-independent)
        self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

        # Name pattern (language-independent)
        self.name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'

    def _build_patterns(self):
        """Build combined patterns from all language configurations"""
        # Combine patterns from all languages
        self.date_patterns = []
        self.month_names = []
        self.amount_patterns = []
        self.currency_symbols = []
        self.phone_patterns = []
        self.postal_code_patterns = []
        self.invoice_patterns = []
        self.po_patterns = []
        self.tax_id_patterns = []
        self.address_patterns = []
        self.date_context_keywords = []
        self.amount_context_keywords = []
        self.name_context_keywords = []

        for lang_config in self.languages.values():
            self.date_patterns.extend(lang_config.date_patterns)
            self.month_names.extend(lang_config.month_names)
            self.month_names.extend(lang_config.month_abbreviations)
            self.currency_symbols.extend(lang_config.currency_symbols)
            self.phone_patterns.extend(lang_config.phone_patterns)
            self.postal_code_patterns.extend(lang_config.postal_code_patterns)
            self.invoice_patterns.extend(lang_config.invoice_patterns)
            self.po_patterns.extend(lang_config.po_patterns)
            self.tax_id_patterns.extend(lang_config.tax_id_patterns)
            self.address_patterns.extend(lang_config.address_patterns)
            self.date_context_keywords.extend(lang_config.date_context_keywords)
            self.amount_context_keywords.extend(lang_config.amount_context_keywords)
            self.name_context_keywords.extend(lang_config.name_context_keywords)

        # Build month pattern
        month_pattern = "|".join(self.month_names)
        self.date_patterns.extend([
            rf'\b(\d{{1,2}})\s+({month_pattern})\.?\s+(\d{{4}})\b',
            rf'\b({month_pattern})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b',
        ])

        # Build currency pattern
        currency_pattern = "|".join(re.escape(sym) for sym in self.currency_symbols)
        self.amount_patterns = [
            rf'(?:{currency_pattern})\s*(\d{{1,3}}(?:[,\.\s]\d{{3}})*(?:[,\.]\d{{2}})?)',
            rf'(\d{{1,3}}(?:[,\.\s]\d{{3}})*(?:[,\.]\d{{2}})?)\s*(?:{currency_pattern})',
        ]

        # Build context patterns
        date_ctx = "|".join(self.date_context_keywords)
        amount_ctx = "|".join(self.amount_context_keywords)
        name_ctx = "|".join(self.name_context_keywords)

        self.date_context_pattern = rf'((?:{date_ctx})\s*(?:date|on|dnia|z|do)?)\s*:?\s*'
        self.amount_context_pattern = rf'((?:{amount_ctx})\s*(?:amount|due|paid|do\s+zapłaty)?)\s*:?\s*'
        self.name_context_pattern = rf'((?:{name_ctx})\s*:?\s*)'

    def _extract_dates(self, text: str) -> tuple[List[date], List[str]]:
        """Extract dates from text"""
        dates = []
        contexts = []

        for pattern in self.date_patterns:
            try:
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
            except re.error:
                logger.warning(f"Invalid date pattern: {pattern}")
                continue

        return dates, contexts

    def _extract_amounts(self, text: str) -> tuple[List[float], List[str]]:
        """Extract monetary amounts from text"""
        amounts = []
        labels = []

        for pattern in self.amount_patterns:
            try:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    try:
                        # Get the amount string (first capturing group)
                        amount_str = match.group(1)

                        # Clean the amount string
                        amount_str = amount_str.replace(' ', '')

                        # Handle European format (comma as decimal separator)
                        if '.' in amount_str and ',' in amount_str:
                            if amount_str.rindex(',') > amount_str.rindex('.'):
                                # European format: 1.500,00 -> 1500.00
                                amount_str = amount_str.replace('.', '').replace(',', '.')
                            else:
                                # US format: 1,500.00 -> 1500.00
                                amount_str = amount_str.replace(',', '')
                        elif ',' in amount_str and '.' not in amount_str:
                            # Could be European decimal: 500,00 or US thousands: 1,500
                            if amount_str.count(',') == 1 and len(amount_str.split(',')[1]) == 2:
                                amount_str = amount_str.replace(',', '.')
                            else:
                                amount_str = amount_str.replace(',', '')
                        else:
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
            except re.error:
                logger.warning(f"Invalid amount pattern: {pattern}")
                continue

        return amounts, labels

    def _extract_names(self, text: str) -> tuple[List[str], List[str]]:
        """Extract person/company names from text"""
        names = []
        contexts = []

        # Common titles to remove
        titles = ['Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sir', 'Madam', 'Pan', 'Pani']

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
            try:
                phones.extend(re.findall(pattern, text))
            except re.error:
                logger.warning(f"Invalid phone pattern: {pattern}")
                continue
        return list(set(phones))

    def _extract_invoice_numbers(self, text: str) -> List[str]:
        """Extract invoice numbers from text"""
        numbers = []
        for pattern in self.invoice_patterns:
            try:
                numbers.extend(re.findall(pattern, text, re.IGNORECASE))
            except re.error:
                logger.warning(f"Invalid invoice pattern: {pattern}")
                continue
        return list(set(numbers))

    def _extract_po_numbers(self, text: str) -> List[str]:
        """Extract purchase order numbers from text"""
        numbers = []
        for pattern in self.po_patterns:
            try:
                numbers.extend(re.findall(pattern, text, re.IGNORECASE))
            except re.error:
                logger.warning(f"Invalid PO pattern: {pattern}")
                continue
        return list(set(numbers))

    def _extract_postal_codes(self, text: str) -> List[str]:
        """Extract postal/ZIP codes from text"""
        codes = []
        for pattern in self.postal_code_patterns:
            try:
                codes.extend(re.findall(pattern, text))
            except re.error:
                logger.warning(f"Invalid postal code pattern: {pattern}")
                continue
        return list(set(codes))

    def _extract_addresses(self, text: str) -> List[str]:
        """Extract street addresses from text"""
        addresses = []
        for pattern in self.address_patterns:
            try:
                addresses.extend(re.findall(pattern, text))
            except re.error:
                logger.warning(f"Invalid address pattern: {pattern}")
                continue
        return list(set(addresses))

    def _extract_tax_ids(self, text: str) -> List[str]:
        """Extract tax identification numbers"""
        tax_ids = []
        for pattern in self.tax_id_patterns:
            try:
                matches = re.findall(pattern, text, re.IGNORECASE)
                tax_ids.extend(matches)
            except re.error:
                logger.warning(f"Invalid tax ID pattern: {pattern}")
                continue
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

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extract all metadata from text and return as flat dictionary

        Args:
            text: Input text from OCR

        Returns:
            Dictionary with all extracted metadata (flat structure)
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

        # Return flat dictionary structure
        return metadata.to_dict()

# Alias for backward compatibility
MetadataExtractorV2 = MetadataExtractor
