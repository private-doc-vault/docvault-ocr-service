# Multi-Language Support for OCR Service

This directory contains language-specific patterns for document categorization and metadata extraction.

## Architecture

The multi-language system uses a modular architecture where each language is defined in its own file with patterns for:
- Document categorization (keywords and regex patterns)
- Metadata extraction (dates, amounts, addresses, etc.)

### Components

- `__init__.py` - Base classes and language registry
- `loader.py` - Auto-loads all language modules
- `en.py` - English language patterns
- `pl.py` - Polish language patterns
- `[lang].py` - Additional language files

## Adding a New Language

To add support for a new language, follow these steps:

### 1. Create a New Language File

Create a new file named `{language_code}.py` (e.g., `de.py` for German, `fr.py` for French)

### 2. Define Language Configuration

```python
"""
German language patterns for document categorization and metadata extraction
Deutsche Sprachmuster für Dokumentenkategorisierung und Metadatenextraktion
"""
from . import LanguageConfig, CategorizationPatterns, register_language


# German language configuration
german_config = LanguageConfig(
    language_code="de",
    language_name="German / Deutsch",

    # Document categorization patterns
    categories={
        "invoice": CategorizationPatterns(
            keywords=[
                "rechnung", "rechnungsnummer", "rechnungsdatum",
                "betrag", "zahlbar", "fällig", "mehrwertsteuer", "mwst"
            ],
            patterns=[
                r"rechnung\s+(?:nr|nummer)?[:#\s]*[\w\-/]+",
                r"rechnungsdatum",
                r"zahlbar\s+bis"
            ],
            description="Rechnung"
        ),
        # ... add other categories
    },

    # Date patterns
    date_patterns=[
        r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b',  # DD.MM.YYYY
    ],
    month_names=[
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ],
    month_abbreviations=["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],

    # Currency patterns
    currency_symbols=["€"],
    currency_codes=["EUR"],

    # Phone patterns (German format)
    phone_patterns=[
        r'\+?49\s*\d{3,4}[\s\-]?\d{6,7}',  # +49 xxx xxxxxxx
        r'\b0\d{3,4}[\s\-]?\d{6,7}\b',     # 0xxx xxxxxxx
    ],

    # Postal code patterns (German format: XXXXX)
    postal_code_patterns=[
        r'\b\d{5}\b',
    ],

    # Invoice/PO patterns
    invoice_patterns=[
        r'\b(?:Rechnung|Rech|RG)[\s#:\/nr]*([A-Z0-9\-\/]+)\b'
    ],
    po_patterns=[
        r'\b(?:Bestellung|Best)[\s#:\/nr]*([A-Z0-9\-\/]+)\b'
    ],

    # Tax ID patterns (German USt-IdNr)
    tax_id_patterns=[
        r'\b(?:USt-IdNr|UID)\s*:?\s*DE\s*\d{9}\b',
    ],

    # Address patterns
    address_patterns=[
        r'\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Straße|Str\.|Weg|Platz|Allee))?\s*\d*[A-Za-z]?'
    ],
    street_types=["Straße", "Str.", "Weg", "Platz", "Allee"],

    # Context keywords
    date_context_keywords=[
        "rechnung", "datum", "fällig", "zahlung", "ausgestellt", "von", "bis"
    ],
    amount_context_keywords=[
        "summe", "betrag", "preis", "kosten", "steuer", "mwst", "gesamt", "zahlung"
    ],
    name_context_keywords=[
        "kunde", "lieferant", "käufer", "verkäufer", "von", "an", "name"
    ]
)

# Register German language
register_language(german_config)
```

### 3. Import in Loader

Add the import to `loader.py`:

```python
def load_all_languages():
    try:
        from . import en  # English
        from . import pl  # Polish
        from . import de  # German  <-- Add this line

        logger.info("Loaded languages: en, pl, de")
    except ImportError as e:
        logger.error(f"Failed to load language configuration: {e}")
        raise
```

### 4. Test Your Language

The language will be automatically available in both `DocumentCategorizer` and `MetadataExtractor`:

```python
from app.document_categorizer_v2 import DocumentCategorizer
from app.metadata_extractor_v2 import MetadataExtractor

# Use all languages (including your new one)
categorizer = DocumentCategorizer()

# Or use specific languages
categorizer = DocumentCategorizer(languages=['de', 'en'])
extractor = MetadataExtractor(languages=['de', 'en'])
```

## Pattern Guidelines

### Document Categories

Include patterns for these standard categories:
- `invoice` - Commercial invoices/bills
- `receipt` - Sales receipts
- `contract` - Legal contracts/agreements
- `letter` - Formal letters
- `report` - Business/technical reports
- `form` - Application/registration forms
- `memo` - Internal memos
- `certificate` - Certificates/credentials
- `statement` - Financial statements

### Date Patterns

- Include common date formats for your language
- Add month names and abbreviations
- Consider regional variations

### Currency Patterns

- Add currency symbols used in your region
- Include currency codes (ISO 4217)
- Handle number formatting (comma vs period as decimal separator)

### Phone Patterns

- Include country code format (+XX)
- Include local formats
- Consider mobile vs landline patterns

### Address Patterns

- Include street type keywords (Street, Avenue, etc.)
- Handle building numbers
- Consider apartment/unit numbers

### Context Keywords

These help improve extraction accuracy:
- **Date contexts**: Keywords that appear before dates (e.g., "invoice date", "due date")
- **Amount contexts**: Keywords before monetary amounts (e.g., "total", "amount due")
- **Name contexts**: Keywords before person/company names (e.g., "customer", "vendor")

## Testing Your Language

1. Create test documents in your language
2. Test categorization accuracy
3. Test metadata extraction for:
   - Dates
   - Amounts
   - Phone numbers
   - Addresses
   - Invoice numbers
   - Tax IDs

4. Verify mixed-language documents work correctly

## Language Codes

Use ISO 639-1 language codes:
- `en` - English
- `pl` - Polish
- `de` - German
- `fr` - French
- `es` - Spanish
- `it` - Italian
- `pt` - Portuguese
- `nl` - Dutch
- `sv` - Swedish
- etc.

## Best Practices

1. **Keywords**: Include both formal and informal terms
2. **Patterns**: Use specific patterns (e.g., invoice numbers) for better accuracy
3. **Testing**: Test with real documents in your language
4. **Documentation**: Add comments in both English and the target language
5. **Regex**: Be careful with special characters in patterns
6. **Context**: Include context keywords for better metadata extraction

## Backward Compatibility

The system maintains backward compatibility:
- Old code using `DocumentCategorizer` / `MetadataExtractor` will continue to work
- New code can use `DocumentCategorizer_v2` / `MetadataExtractor_v2` for language-specific features

## Future Enhancements

Potential improvements:
- Automatic language detection using NLP
- Language-specific confidence scoring
- Support for right-to-left languages
- Multi-script support (Cyrillic, Arabic, etc.)
- Dialect variations within languages
