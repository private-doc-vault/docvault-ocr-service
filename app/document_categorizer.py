"""
Document Categorizer
Automatically categorizes documents based on content pattern recognition
"""
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class CategoryResult:
    """Result of document categorization"""
    primary_category: str
    confidence: float
    all_categories: Dict[str, float] = field(default_factory=dict)
    indicators: List[str] = field(default_factory=list)


class DocumentCategorizer:
    """Categorizes documents based on content patterns"""

    def __init__(self):
        """Initialize document categorizer with category patterns (Polish + English)"""
        self.categories = {
            "invoice": {
                "keywords": [
                    # English
                    "invoice", "bill to", "invoice number", "invoice #", "inv #", "inv-",
                    "amount due", "payment due", "payment terms", "due date", "bill date",
                    "invoice date", "total due", "balance due", "remittance",
                    # Polish
                    "faktura", "faktura vat", "faktura nr", "nr faktury", "fv", "fs",
                    "sprzedawca", "nabywca", "kwota do zapłaty", "termin płatności",
                    "data wystawienia", "data sprzedaży", "suma", "razem", "wartość brutto",
                    "netto", "vat", "należność", "płatność"
                ],
                "patterns": [
                    # English patterns
                    r"invoice\s*(?:number|#|no\.?)[:#\s]*[\w\-]+",
                    r"inv[-#]\s*\d+",
                    r"amount\s+due\s*:?\s*[$€£]\s*[\d,]+\.?\d*",
                    r"payment\s+terms",
                    r"net\s+\d+\s+days",
                    # Polish patterns
                    r"faktura\s+(?:vat|nr|numer)?[:#\s]*[\w\-/]+",
                    r"f(?:v|s)[/#\-]\s*\d+",
                    r"nip\s*:?\s*\d{10}",
                    r"kwota\s+do\s+zapłaty",
                    r"termin\s+płatności"
                ],
                "description": "Commercial invoice or bill for goods/services / Faktura handlowa"
            },
            "receipt": {
                "keywords": [
                    # English
                    "receipt", "store", "thank you", "subtotal", "tax", "change",
                    "cash", "credit", "debit", "payment received", "paid", "transaction",
                    # Polish
                    "paragon", "paragon fiskalny", "kwit", "dowód zakupu", "sklep",
                    "suma", "wartość", "zapłacono", "reszta", "gotówka", "karta",
                    "transakcja", "nr paragonu", "podziękowanie", "dziękujemy"
                ],
                "patterns": [
                    # English patterns
                    r"receipt\s*(?:number|#|no\.?)?",
                    r"thank\s+you\s+for\s+(?:your|shopping)",
                    r"(?:sub)?total\s*:?\s*[$€£]\s*[\d,]+\.?\d*",
                    r"change\s*:?\s*[$€£]\s*[\d,]+\.?\d*",
                    # Polish patterns
                    r"paragon\s+(?:fiskalny|nr)?",
                    r"suma\s*:?\s*[\d,]+\s*(?:zł|PLN)",
                    r"zapłacono\s*:?\s*[\d,]+",
                    r"dziękujemy\s+za\s+zakup"
                ],
                "description": "Sales receipt or proof of purchase / Paragon sprzedaży"
            },
            "contract": {
                "keywords": [
                    # English
                    "contract", "agreement", "terms and conditions", "this agreement",
                    "party", "parties", "whereas", "hereby", "entered into", "binding",
                    "executed", "effective date", "term", "terminate", "termination",
                    # Polish
                    "umowa", "kontrakt", "ugoda", "porozumienie", "warunki umowy",
                    "strona", "strony", "niniejsza umowa", "zawiera", "zobowiązuje się",
                    "postanowienia", "okres obowiązywania", "rozwiązanie", "wypowiedzenie",
                    "podpis", "akceptacja", "przedmiot umowy"
                ],
                "patterns": [
                    # English patterns
                    r"(?:employment|service|sales|lease)\s+(?:contract|agreement)",
                    r"this\s+agreement\s+is\s+(?:made|entered)",
                    r"terms\s+and\s+conditions",
                    r"party\s+of\s+the\s+(?:first|second)\s+part",
                    r"whereas.*(?:agrees?|undertakes?)",
                    # Polish patterns
                    r"umowa\s+(?:o\s+)?(?:pracę|zlecenie|dzieło|najmu|sprzedaży)",
                    r"niniejsza\s+umowa",
                    r"strona\s+(?:pierwsza|druga)",
                    r"zobowiązuje\s+się\s+do",
                    r"w\s+świadectwie\s+powyższego"
                ],
                "description": "Legal contract or agreement / Umowa prawna"
            },
            "letter": {
                "keywords": [
                    # English
                    "dear", "sincerely", "regards", "yours truly", "respectfully",
                    "to whom it may concern", "best regards", "kind regards", "yours faithfully",
                    # Polish
                    "szanowny", "szanowna", "drogi", "droga", "uprzejmie", "z poważaniem",
                    "łączę pozdrowienia", "serdeczne pozdrowienia", "z wyrazami szacunku",
                    "do wiadomości", "w załączeniu", "informuję", "zwracam się"
                ],
                "patterns": [
                    # English patterns
                    r"dear\s+(?:mr|mrs|ms|dr|prof)\.?\s+\w+",
                    r"(?:sincerely|regards|respectfully)\s*,?\s*$",
                    r"yours\s+(?:truly|faithfully|sincerely)",
                    r"to\s+whom\s+it\s+may\s+concern",
                    # Polish patterns
                    r"szanown(?:y|a)\s+(?:pan|pani|państwo)",
                    r"z\s+poważaniem",
                    r"łączę\s+(?:wyrazy|pozdrowienia)",
                    r"zwracam\s+się\s+z\s+(?:prośbą|zapytaniem)"
                ],
                "description": "Formal or business letter / List formalny lub biznesowy"
            },
            "report": {
                "keywords": [
                    # English
                    "report", "executive summary", "introduction", "findings",
                    "recommendations", "conclusion", "analysis", "quarterly", "annual",
                    "monthly", "summary", "overview", "background",
                    # Polish
                    "raport", "sprawozdanie", "zestawienie", "analiza", "podsumowanie",
                    "wstęp", "wprowadzenie", "wnioski", "rekomendacje", "zakończenie",
                    "kwartalny", "roczny", "miesięczny", "przegląd", "dane", "wyniki"
                ],
                "patterns": [
                    # English patterns
                    r"(?:quarterly|annual|monthly|weekly)\s+report",
                    r"executive\s+summary",
                    r"(?:section|chapter)\s+\d+",
                    r"\d+\.\s+(?:introduction|findings|conclusion)",
                    # Polish patterns
                    r"raport\s+(?:kwartalny|roczny|miesięczny)",
                    r"sprawozdanie\s+(?:finansowe|zarządu)",
                    r"(?:rozdział|punkt)\s+\d+",
                    r"\d+\.\s+(?:wstęp|wnioski|zakończenie)"
                ],
                "description": "Business or technical report / Raport biznesowy lub techniczny"
            },
            "form": {
                "keywords": [
                    # English
                    "application form", "form", "please complete", "fill in",
                    "name:", "address:", "phone:", "email:", "signature:",
                    "date:", "applicant", "registration",
                    # Polish
                    "formularz", "wniosek", "ankieta", "wypełnić", "proszę uzupełnić",
                    "imię i nazwisko:", "adres:", "telefon:", "e-mail:", "podpis:",
                    "data:", "wnioskodawca", "rejestracja", "zgłoszenie"
                ],
                "patterns": [
                    # English patterns
                    r"(?:application|registration)\s+form",
                    r"(?:name|address|phone|email)\s*:?\s*_{3,}",
                    r"please\s+(?:complete|fill\s+(?:in|out))",
                    r"\[\s*\]\s*(?:yes|no|agree|disagree)",
                    # Polish patterns
                    r"formularz\s+(?:wniosku|zgłoszeniowy|rejestracyjny)",
                    r"(?:imię|nazwisko|adres|telefon)\s*:?\s*_{3,}",
                    r"proszę\s+(?:wypełnić|uzupełnić)",
                    r"\[\s*\]\s*(?:tak|nie|zgadzam się)"
                ],
                "description": "Application or registration form / Formularz lub wniosek"
            },
            "memo": {
                "keywords": [
                    # English
                    "memorandum", "memo", "to:", "from:", "date:", "re:", "subject:",
                    "cc:", "internal", "confidential",
                    # Polish
                    "notatka", "notatka służbowa", "do:", "od:", "data:", "dotyczy:",
                    "temat:", "dw:", "wewnętrzne", "poufne", "służbowe"
                ],
                "patterns": [
                    # English patterns
                    r"(?:memorandum|memo)\s*$",
                    r"to\s*:\s*\w+.*from\s*:\s*\w+",
                    r"(?:date|re|subject)\s*:.*",
                    # Polish patterns
                    r"notatka\s+służbowa",
                    r"do\s*:\s*\w+.*od\s*:\s*\w+",
                    r"(?:data|dotyczy|temat)\s*:.*"
                ],
                "description": "Internal memorandum / Notatka służbowa"
            },
            "certificate": {
                "keywords": [
                    # English
                    "certificate", "certify", "certification", "awarded", "completion",
                    "achievement", "hereby certifies", "this certifies", "accredited",
                    # Polish
                    "certyfikat", "świadectwo", "zaświadczenie", "poświadcza",
                    "nadaje", "przyznaje", "ukończenie", "osiągnięcie",
                    "niniejszym potwierdza", "zaświadcza się", "akredytowany"
                ],
                "patterns": [
                    # English patterns
                    r"certificate\s+of\s+(?:completion|achievement|attendance)",
                    r"(?:this|hereby)\s+certifies\s+that",
                    r"awarded\s+(?:to|on)",
                    # Polish patterns
                    r"(?:certyfikat|świadectwo|zaświadczenie)\s+(?:ukończenia|udziału)",
                    r"niniejszym\s+(?:potwierdza|zaświadcza)\s+(?:się|że)",
                    r"nadaje\s+(?:tytuł|certyfikat)"
                ],
                "description": "Certificate or credential / Certyfikat lub świadectwo"
            },
            "statement": {
                "keywords": [
                    # English
                    "statement", "account statement", "bank statement", "credit card statement",
                    "balance", "transactions", "beginning balance", "ending balance",
                    # Polish
                    "wyciąg", "wyciąg z konta", "wyciąg bankowy", "zestawienie",
                    "saldo", "transakcje", "operacje", "saldo początkowe", "saldo końcowe",
                    "rachunek", "historia operacji"
                ],
                "patterns": [
                    # English patterns
                    r"(?:account|bank|credit\s+card)\s+statement",
                    r"(?:beginning|ending|closing)\s+balance",
                    r"statement\s+(?:period|date)",
                    # Polish patterns
                    r"wyciąg\s+(?:z\s+konta|bankowy)",
                    r"saldo\s+(?:początkowe|końcowe|na\s+dzień)",
                    r"(?:historia|zestawienie)\s+(?:operacji|transakcji)"
                ],
                "description": "Financial or account statement / Wyciąg finansowy lub bankowy"
            }
        }

    def get_supported_categories(self) -> List[str]:
        """Get list of supported document categories"""
        return list(self.categories.keys()) + ["unknown", "other"]

    def get_category_descriptions(self) -> Dict[str, str]:
        """Get descriptions for all categories"""
        descriptions = {cat: info["description"] for cat, info in self.categories.items()}
        descriptions["unknown"] = "Document type could not be determined"
        descriptions["other"] = "Document type not in predefined categories"
        return descriptions

    def _calculate_category_score(self, text: str, category_info: dict) -> tuple[float, List[str]]:
        """
        Calculate score for a specific category

        Returns:
            Tuple of (score, indicators) where indicators are matched keywords/patterns
        """
        text_lower = text.lower()
        score = 0.0
        indicators = []

        # Check keywords
        keyword_matches = 0
        for keyword in category_info["keywords"]:
            if keyword.lower() in text_lower:
                keyword_matches += 1
                indicators.append(keyword)

        # Weight keyword matches
        if keyword_matches > 0:
            # Score increases with more keywords, but with diminishing returns
            score += min(keyword_matches * 0.15, 0.6)

        # Check patterns
        pattern_matches = 0
        for pattern in category_info["patterns"]:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                pattern_matches += 1
                indicators.append(f"pattern:{pattern[:30]}...")

        # Weight pattern matches (patterns are stronger indicators)
        if pattern_matches > 0:
            score += min(pattern_matches * 0.2, 0.7)

        # Normalize score to 0-1 range
        score = min(score, 1.0)

        return score, indicators

    def categorize(self, text: str) -> CategoryResult:
        """
        Categorize a document based on its text content

        Args:
            text: OCR extracted text from document

        Returns:
            CategoryResult with primary category and confidence
        """
        if not text or len(text.strip()) < 3:
            return CategoryResult(
                primary_category="unknown",
                confidence=0.0,
                all_categories={"unknown": 0.0},
                indicators=[]
            )

        # Calculate scores for all categories
        category_scores = {}
        all_indicators = {}

        for category, category_info in self.categories.items():
            score, indicators = self._calculate_category_score(text, category_info)
            category_scores[category] = score
            all_indicators[category] = indicators

        # Find category with highest score
        if category_scores:
            primary_category = max(category_scores, key=category_scores.get)
            confidence = category_scores[primary_category]
        else:
            primary_category = "unknown"
            confidence = 0.0

        # If confidence is too low, mark as unknown
        if confidence < 0.25:
            primary_category = "unknown"

        # Get indicators for primary category
        indicators = all_indicators.get(primary_category, [])

        return CategoryResult(
            primary_category=primary_category,
            confidence=confidence,
            all_categories=category_scores,
            indicators=indicators
        )
