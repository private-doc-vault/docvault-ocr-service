"""
English language patterns for document categorization and metadata extraction
"""
from . import LanguageConfig, CategorizationPatterns, register_language


# English language configuration
english_config = LanguageConfig(
    language_code="en",
    language_name="English",

    # Document categorization patterns
    categories={
        "invoice": CategorizationPatterns(
            keywords=[
                "invoice", "bill to", "invoice number", "invoice #", "inv #", "inv-",
                "amount due", "payment due", "payment terms", "due date", "bill date",
                "invoice date", "total due", "balance due", "remittance"
            ],
            patterns=[
                r"invoice\s*(?:number|#|no\.?)[:#\s]*[\w\-]+",
                r"inv[-#]\s*\d+",
                r"amount\s+due\s*:?\s*[$€£]\s*[\d,]+\.?\d*",
                r"payment\s+terms",
                r"net\s+\d+\s+days"
            ],
            description="Commercial invoice or bill for goods/services"
        ),
        "receipt": CategorizationPatterns(
            keywords=[
                "receipt", "store", "thank you", "subtotal", "tax", "change",
                "cash", "credit", "debit", "payment received", "paid", "transaction"
            ],
            patterns=[
                r"receipt\s*(?:number|#|no\.?)?",
                r"thank\s+you\s+for\s+(?:your|shopping)",
                r"(?:sub)?total\s*:?\s*[$€£]\s*[\d,]+\.?\d*",
                r"change\s*:?\s*[$€£]\s*[\d,]+\.?\d*"
            ],
            description="Sales receipt or proof of purchase"
        ),
        "contract": CategorizationPatterns(
            keywords=[
                "contract", "agreement", "terms and conditions", "this agreement",
                "party", "parties", "whereas", "hereby", "entered into", "binding",
                "executed", "effective date", "term", "terminate", "termination"
            ],
            patterns=[
                r"(?:employment|service|sales|lease)\s+(?:contract|agreement)",
                r"this\s+agreement\s+is\s+(?:made|entered)",
                r"terms\s+and\s+conditions",
                r"party\s+of\s+the\s+(?:first|second)\s+part",
                r"whereas.*(?:agrees?|undertakes?)"
            ],
            description="Legal contract or agreement"
        ),
        "letter": CategorizationPatterns(
            keywords=[
                "dear", "sincerely", "regards", "yours truly", "respectfully",
                "to whom it may concern", "best regards", "kind regards", "yours faithfully"
            ],
            patterns=[
                r"dear\s+(?:mr|mrs|ms|dr|prof)\.?\s+\w+",
                r"(?:sincerely|regards|respectfully)\s*,?\s*$",
                r"yours\s+(?:truly|faithfully|sincerely)",
                r"to\s+whom\s+it\s+may\s+concern"
            ],
            description="Formal or business letter"
        ),
        "report": CategorizationPatterns(
            keywords=[
                "report", "executive summary", "introduction", "findings",
                "recommendations", "conclusion", "analysis", "quarterly", "annual",
                "monthly", "summary", "overview", "background"
            ],
            patterns=[
                r"(?:quarterly|annual|monthly|weekly)\s+report",
                r"executive\s+summary",
                r"(?:section|chapter)\s+\d+",
                r"\d+\.\s+(?:introduction|findings|conclusion)"
            ],
            description="Business or technical report"
        ),
        "form": CategorizationPatterns(
            keywords=[
                "application form", "form", "please complete", "fill in",
                "name:", "address:", "phone:", "email:", "signature:",
                "date:", "applicant", "registration"
            ],
            patterns=[
                r"(?:application|registration)\s+form",
                r"(?:name|address|phone|email)\s*:?\s*_{3,}",
                r"please\s+(?:complete|fill\s+(?:in|out))",
                r"\[\s*\]\s*(?:yes|no|agree|disagree)"
            ],
            description="Application or registration form"
        ),
        "memo": CategorizationPatterns(
            keywords=[
                "memorandum", "memo", "to:", "from:", "date:", "re:", "subject:",
                "cc:", "internal", "confidential"
            ],
            patterns=[
                r"(?:memorandum|memo)\s*$",
                r"to\s*:\s*\w+.*from\s*:\s*\w+",
                r"(?:date|re|subject)\s*:.*"
            ],
            description="Internal memorandum"
        ),
        "certificate": CategorizationPatterns(
            keywords=[
                "certificate", "certify", "certification", "awarded", "completion",
                "achievement", "hereby certifies", "this certifies", "accredited"
            ],
            patterns=[
                r"certificate\s+of\s+(?:completion|achievement|attendance)",
                r"(?:this|hereby)\s+certifies\s+that",
                r"awarded\s+(?:to|on)"
            ],
            description="Certificate or credential"
        ),
        "statement": CategorizationPatterns(
            keywords=[
                "statement", "account statement", "bank statement", "credit card statement",
                "balance", "transactions", "beginning balance", "ending balance"
            ],
            patterns=[
                r"(?:account|bank|credit\s+card)\s+statement",
                r"(?:beginning|ending|closing)\s+balance",
                r"statement\s+(?:period|date)"
            ],
            description="Financial or account statement"
        )
    },

    # Date patterns
    date_patterns=[
        r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',  # ISO format
        r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b',  # DD/MM/YYYY or MM/DD/YYYY
    ],
    month_names=[
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ],
    month_abbreviations=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],

    # Currency patterns
    currency_symbols=["$", "€", "£", "¥", "₹"],
    currency_codes=["USD", "EUR", "GBP", "CAD", "AUD"],

    # Phone patterns
    phone_patterns=[
        r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    ],

    # Postal code patterns
    postal_code_patterns=[
        r'\b\d{5}(?:-\d{4})?\b',  # US ZIP
        r'\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b',  # Canadian postal code
    ],

    # Invoice/PO patterns
    invoice_patterns=[
        r'\b(?:Invoice|INV|INVOICE)[\s#:]*([A-Z0-9\-]+)\b'
    ],
    po_patterns=[
        r'\b(?:PO|P\.O\.|Purchase Order)[\s#:]*([A-Z0-9\-]+)\b'
    ],

    # Tax ID patterns
    tax_id_patterns=[
        r'\b(?:Tax\s+ID|TIN|EIN)\s*:?\s*(\d{2}-\d{7})\b',  # US EIN
    ],

    # Address patterns
    address_patterns=[
        r'\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\.?)'
    ],
    street_types=["Street", "St", "Avenue", "Ave", "Road", "Rd", "Boulevard", "Blvd", "Lane", "Ln", "Drive", "Dr", "Court", "Ct"],

    # Context keywords
    date_context_keywords=[
        "invoice", "bill", "due", "payment", "date", "dated", "issued",
        "from", "to", "created", "modified", "effective"
    ],
    amount_context_keywords=[
        "total", "subtotal", "amount", "price", "cost", "tax",
        "balance", "due", "paid", "payment"
    ],
    name_context_keywords=[
        "customer", "client", "vendor", "supplier", "from", "to",
        "bill to", "ship to", "name", "contact"
    ]
)

# Register English language
register_language(english_config)
