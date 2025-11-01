"""
Polish language patterns for document categorization and metadata extraction
Polskie wzorce dla kategoryzacji dokumentów i ekstrakcji metadanych
"""
from . import LanguageConfig, CategorizationPatterns, register_language


# Polish language configuration
polish_config = LanguageConfig(
    language_code="pl",
    language_name="Polish / Polski",

    # Document categorization patterns
    categories={
        "invoice": CategorizationPatterns(
            keywords=[
                "faktura", "faktura vat", "faktura nr", "nr faktury", "fv", "fs",
                "sprzedawca", "nabywca", "kwota do zapłaty", "termin płatności",
                "data wystawienia", "data sprzedaży", "suma", "razem", "wartość brutto",
                "netto", "vat", "należność", "płatność"
            ],
            patterns=[
                r"faktura\s+(?:vat|nr|numer)?[:#\s]*[\w\-/]+",
                r"f(?:v|s)[/#\-]\s*\d+",
                r"nip\s*:?\s*\d{10}",
                r"kwota\s+do\s+zapłaty",
                r"termin\s+płatności"
            ],
            description="Faktura handlowa"
        ),
        "receipt": CategorizationPatterns(
            keywords=[
                "paragon", "paragon fiskalny", "kwit", "dowód zakupu", "sklep",
                "suma", "wartość", "zapłacono", "reszta", "gotówka", "karta",
                "transakcja", "nr paragonu", "podziękowanie", "dziękujemy"
            ],
            patterns=[
                r"paragon\s+(?:fiskalny|nr)?",
                r"suma\s*:?\s*[\d,]+\s*(?:zł|PLN)",
                r"zapłacono\s*:?\s*[\d,]+",
                r"dziękujemy\s+za\s+zakup"
            ],
            description="Paragon sprzedaży"
        ),
        "contract": CategorizationPatterns(
            keywords=[
                "umowa", "kontrakt", "ugoda", "porozumienie", "warunki umowy",
                "strona", "strony", "niniejsza umowa", "zawiera", "zobowiązuje się",
                "postanowienia", "okres obowiązywania", "rozwiązanie", "wypowiedzenie",
                "podpis", "akceptacja", "przedmiot umowy"
            ],
            patterns=[
                r"umowa\s+(?:o\s+)?(?:pracę|zlecenie|dzieło|najmu|sprzedaży)",
                r"niniejsza\s+umowa",
                r"strona\s+(?:pierwsza|druga)",
                r"zobowiązuje\s+się\s+do",
                r"w\s+świadectwie\s+powyższego"
            ],
            description="Umowa prawna"
        ),
        "letter": CategorizationPatterns(
            keywords=[
                "szanowny", "szanowna", "drogi", "droga", "uprzejmie", "z poważaniem",
                "łączę pozdrowienia", "serdeczne pozdrowienia", "z wyrazami szacunku",
                "do wiadomości", "w załączeniu", "informuję", "zwracam się"
            ],
            patterns=[
                r"szanown(?:y|a)\s+(?:pan|pani|państwo)",
                r"z\s+poważaniem",
                r"łączę\s+(?:wyrazy|pozdrowienia)",
                r"zwracam\s+się\s+z\s+(?:prośbą|zapytaniem)"
            ],
            description="List formalny lub biznesowy"
        ),
        "report": CategorizationPatterns(
            keywords=[
                "raport", "sprawozdanie", "zestawienie", "analiza", "podsumowanie",
                "wstęp", "wprowadzenie", "wnioski", "rekomendacje", "zakończenie",
                "kwartalny", "roczny", "miesięczny", "przegląd", "dane", "wyniki"
            ],
            patterns=[
                r"raport\s+(?:kwartalny|roczny|miesięczny)",
                r"sprawozdanie\s+(?:finansowe|zarządu)",
                r"(?:rozdział|punkt)\s+\d+",
                r"\d+\.\s+(?:wstęp|wnioski|zakończenie)"
            ],
            description="Raport biznesowy lub techniczny"
        ),
        "form": CategorizationPatterns(
            keywords=[
                "formularz", "wniosek", "ankieta", "wypełnić", "proszę uzupełnić",
                "imię i nazwisko:", "adres:", "telefon:", "e-mail:", "podpis:",
                "data:", "wnioskodawca", "rejestracja", "zgłoszenie"
            ],
            patterns=[
                r"formularz\s+(?:wniosku|zgłoszeniowy|rejestracyjny)",
                r"(?:imię|nazwisko|adres|telefon)\s*:?\s*_{3,}",
                r"proszę\s+(?:wypełnić|uzupełnić)",
                r"\[\s*\]\s*(?:tak|nie|zgadzam się)"
            ],
            description="Formularz lub wniosek"
        ),
        "memo": CategorizationPatterns(
            keywords=[
                "notatka", "notatka służbowa", "do:", "od:", "data:", "dotyczy:",
                "temat:", "dw:", "wewnętrzne", "poufne", "służbowe"
            ],
            patterns=[
                r"notatka\s+służbowa",
                r"do\s*:\s*\w+.*od\s*:\s*\w+",
                r"(?:data|dotyczy|temat)\s*:.*"
            ],
            description="Notatka służbowa"
        ),
        "certificate": CategorizationPatterns(
            keywords=[
                "certyfikat", "świadectwo", "zaświadczenie", "poświadcza",
                "nadaje", "przyznaje", "ukończenie", "osiągnięcie",
                "niniejszym potwierdza", "zaświadcza się", "akredytowany"
            ],
            patterns=[
                r"(?:certyfikat|świadectwo|zaświadczenie)\s+(?:ukończenia|udziału)",
                r"niniejszym\s+(?:potwierdza|zaświadcza)\s+(?:się|że)",
                r"nadaje\s+(?:tytuł|certyfikat)"
            ],
            description="Certyfikat lub świadectwo"
        ),
        "statement": CategorizationPatterns(
            keywords=[
                "wyciąg", "wyciąg z konta", "wyciąg bankowy", "zestawienie",
                "saldo", "transakcje", "operacje", "saldo początkowe", "saldo końcowe",
                "rachunek", "historia operacji"
            ],
            patterns=[
                r"wyciąg\s+(?:z\s+konta|bankowy)",
                r"saldo\s+(?:początkowe|końcowe|na\s+dzień)",
                r"(?:historia|zestawienie)\s+(?:operacji|transakcji)"
            ],
            description="Wyciąg finansowy lub bankowy"
        )
    },

    # Date patterns
    date_patterns=[
        r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',  # ISO format
        r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b',  # DD.MM.YYYY (common in Poland)
    ],
    month_names=[
        "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
        "lipca", "sierpnia", "września", "października", "listopada", "grudnia"
    ],
    month_abbreviations=["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"],

    # Currency patterns
    currency_symbols=["zł", "PLN"],
    currency_codes=["PLN"],

    # Phone patterns (Polish format)
    phone_patterns=[
        r'\+?48\s*\d{3}[\s\-]?\d{3}[\s\-]?\d{3}',  # +48 123 456 789
        r'\b\d{3}[\s\-]?\d{3}[\s\-]?\d{3}\b',  # 123-456-789
        r'\b\d{9}\b',  # 123456789
    ],

    # Postal code patterns (Polish format: XX-XXX)
    postal_code_patterns=[
        r'\b\d{2}-\d{3}\b',
    ],

    # Invoice/PO patterns
    invoice_patterns=[
        r'\b(?:Faktura|Fakt|FV|FS)[\s#:\/nr]*([A-Z0-9\-\/]+)\b'
    ],
    po_patterns=[
        r'\b(?:Zamówienie|Zam)[\s#:\/nr]*([A-Z0-9\-\/]+)\b'
    ],

    # Tax ID patterns (Polish NIP)
    tax_id_patterns=[
        r'\bNIP\s*:?\s*(\d{10}|\d{3}-\d{3}-\d{2}-\d{2}|\d{3}-\d{2}-\d{2}-\d{3})\b',
    ],

    # Address patterns (Polish format)
    address_patterns=[
        r'\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:ul\.|ulica|al\.|aleja|pl\.|plac))?\s*\d*[A-Za-z]?'
    ],
    street_types=["ul.", "ulica", "al.", "aleja", "pl.", "plac"],

    # Context keywords
    date_context_keywords=[
        "faktura", "termin", "płatność", "wystawiono", "data", "sprzedaż",
        "dnia", "z", "do"
    ],
    amount_context_keywords=[
        "suma", "razem", "kwota", "cena", "koszt", "vat",
        "należność", "zapłacono", "do zapłaty"
    ],
    name_context_keywords=[
        "nabywca", "sprzedawca", "klient", "dostawca", "od", "do",
        "imię", "nazwisko"
    ]
)

# Register Polish language
register_language(polish_config)
