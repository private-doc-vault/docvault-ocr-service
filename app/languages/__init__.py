"""
Language-specific patterns for document categorization and metadata extraction
"""
from typing import Dict, List
from dataclasses import dataclass, field


@dataclass
class CategorizationPatterns:
    """Patterns for document categorization"""
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class LanguageConfig:
    """
    Language-specific configuration for OCR processing

    Each language should provide patterns for:
    - Document categorization (keywords and regex patterns per category)
    - Metadata extraction (dates, amounts, addresses, etc.)
    """

    # Language metadata
    language_code: str = ""
    language_name: str = ""

    # Document categorization patterns
    categories: Dict[str, CategorizationPatterns] = field(default_factory=dict)

    # Metadata extraction patterns
    date_patterns: List[str] = field(default_factory=list)
    month_names: List[str] = field(default_factory=list)
    month_abbreviations: List[str] = field(default_factory=list)

    amount_patterns: List[str] = field(default_factory=list)
    currency_symbols: List[str] = field(default_factory=list)
    currency_codes: List[str] = field(default_factory=list)

    phone_patterns: List[str] = field(default_factory=list)
    postal_code_patterns: List[str] = field(default_factory=list)

    invoice_patterns: List[str] = field(default_factory=list)
    po_patterns: List[str] = field(default_factory=list)
    tax_id_patterns: List[str] = field(default_factory=list)

    address_patterns: List[str] = field(default_factory=list)
    street_types: List[str] = field(default_factory=list)

    # Context patterns for better extraction
    date_context_keywords: List[str] = field(default_factory=list)
    amount_context_keywords: List[str] = field(default_factory=list)
    name_context_keywords: List[str] = field(default_factory=list)


# Registry of available languages
_language_registry: Dict[str, LanguageConfig] = {}


def register_language(config: LanguageConfig):
    """Register a language configuration"""
    _language_registry[config.language_code] = config


def get_language(language_code: str) -> LanguageConfig:
    """Get language configuration by code"""
    return _language_registry.get(language_code)


def get_available_languages() -> List[str]:
    """Get list of available language codes"""
    return list(_language_registry.keys())


def get_all_languages() -> Dict[str, LanguageConfig]:
    """Get all registered language configurations"""
    return _language_registry.copy()
