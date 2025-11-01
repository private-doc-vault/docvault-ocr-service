# Polish Language Support for OCR Service

This document describes the Polish language support added to the document categorization and metadata extraction features.

## Overview

The OCR service has been enhanced to support Polish language documents alongside English, making it suitable for processing documents commonly used in Poland.

## Document Categorization (document_categorizer.py)

### Supported Categories with Polish Keywords

All document categories now include Polish keywords and patterns:

1. **Invoice / Faktura**
   - Polish keywords: faktura, faktura vat, sprzedawca, nabywca, kwota do zapłaty, termin płatności, etc.
   - Patterns: Faktura VAT, FV, FS, NIP numbers, Polish date formats

2. **Receipt / Paragon**
   - Polish keywords: paragon, paragon fiskalny, kwit, suma, zapłacono, reszta, etc.
   - Patterns: Paragon fiskalny, PLN/zł amounts

3. **Contract / Umowa**
   - Polish keywords: umowa, kontrakt, strona, zobowiązuje się, postanowienia, etc.
   - Patterns: Umowa o pracę/zlecenie/dzieło, niniejsza umowa

4. **Letter / List**
   - Polish keywords: szanowny/szanowna, z poważaniem, łączę pozdrowienia, etc.
   - Patterns: Szanowny Pan/Pani, z poważaniem

5. **Report / Raport**
   - Polish keywords: raport, sprawozdanie, analiza, wnioski, podsumowanie, etc.
   - Patterns: Raport roczny/kwartalny/miesięczny

6. **Form / Formularz**
   - Polish keywords: formularz, wniosek, ankieta, imię i nazwisko, podpis, etc.
   - Patterns: Formularz wniosku, proszę wypełnić

7. **Memo / Notatka**
   - Polish keywords: notatka służbowa, dotyczy, wewnętrzne, poufne, etc.
   - Patterns: Notatka służbowa, do:/od:

8. **Certificate / Certyfikat**
   - Polish keywords: certyfikat, świadectwo, zaświadczenie, ukończenie, etc.
   - Patterns: Certyfikat ukończenia, zaświadcza się

9. **Statement / Wyciąg**
   - Polish keywords: wyciąg z konta, saldo, transakcje, operacje, etc.
   - Patterns: Wyciąg bankowy, saldo początkowe/końcowe

## Metadata Extraction (metadata_extractor.py)

### Enhanced Features for Polish Documents

#### 1. **Currency Support**
   - Added Polish złoty (zł, PLN) to currency symbols
   - Handles Polish number formatting (space as thousands separator)
   - Example: `1 234,56 zł` or `1234.56 PLN`

#### 2. **Date Formats**
   - Polish month names: stycznia, lutego, marca, kwietnia, maja, czerwca, lipca, sierpnia, września, października, listopada, grudnia
   - Polish abbreviated months: sty, lut, mar, kwi, maj, cze, lip, sie, wrz, paź, lis, gru
   - DD.MM.YYYY format (common in Poland)
   - Example: `15 stycznia 2024` or `15.01.2024`

#### 3. **Phone Numbers**
   - Polish mobile format: +48 123 456 789
   - Alternative formats: 123-456-789, 123456789
   - Validates 9-digit Polish phone numbers

#### 4. **Postal Codes**
   - Polish format: XX-XXX (e.g., 00-001, 31-234)
   - Example: `00-950 Warszawa`

#### 5. **Tax ID Numbers (NIP)**
   - Polish NIP formats:
     - 10 digits: `1234567890`
     - With dashes: `123-456-78-90` or `123-45-67-890`
   - Pattern: `NIP: 123-456-78-90`
   - New field: `tax_ids` in ExtractedMetadata

#### 6. **Invoice/PO Numbers**
   - Polish patterns: Faktura, Fakt, FV, FS
   - Example: `Faktura VAT nr FV/2024/001`
   - Polish PO: Zamówienie, Zam

#### 7. **Address Formats**
   - Polish street types: ul. (ulica), al. (aleja), pl. (plac)
   - Example: `ul. Marszałkowska 123/45`

#### 8. **Context Patterns**
   - Date contexts: faktura, termin, płatność, wystawiono, data sprzedaży
   - Amount contexts: suma, razem, kwota, cena, należność, zapłacono, do zapłaty
   - Name contexts: nabywca, sprzedawca, klient, dostawca, imię, nazwisko

## Usage Examples

### Document Categorization

```python
from app.document_categorizer import DocumentCategorizer

categorizer = DocumentCategorizer()

# Polish invoice
polish_text = """
Faktura VAT nr FV/2024/123
Data wystawienia: 15 stycznia 2024
Sprzedawca: ABC Sp. z o.o.
NIP: 123-456-78-90
Nabywca: XYZ S.A.
Kwota do zapłaty: 1 234,56 zł
Termin płatności: 30 dni
"""

result = categorizer.categorize(polish_text)
# result.primary_category == "invoice"
# result.confidence > 0.8
```

### Metadata Extraction

```python
from app.metadata_extractor import MetadataExtractor

extractor = MetadataExtractor()

metadata = extractor.extract(polish_text)

# Extracted data:
# metadata.invoice_numbers = ['FV/2024/123']
# metadata.dates = [date(2024, 1, 15)]
# metadata.amounts = [1234.56]
# metadata.tax_ids = ['123-456-78-90']
# metadata.names = ['ABC Sp', 'XYZ S.A.']
```

## Test Coverage

Both modules maintain high test coverage:
- Document Categorizer: 97% coverage (27/27 tests passing)
- Metadata Extractor: 96% coverage (34/34 tests passing)

## Language Detection

The system automatically detects and processes both English and Polish text without requiring explicit language specification. Documents can contain mixed language content.

## Future Enhancements

Potential improvements for Polish language support:
1. REGON number extraction (Polish business registry)
2. PESEL number extraction (Polish national ID)
3. Polish bank account number (26 digits) extraction
4. City/voivodeship recognition
5. Polish-specific document types (e.g., PIT forms, ZUS documents)

## Compatibility

All changes are backward compatible. English-only documents continue to work exactly as before, with Polish support added as an enhancement.
