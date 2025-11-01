"""
Document Categorizer V2 - Multi-language support
Automatically categorizes documents based on content pattern recognition
Uses language-specific patterns from the languages module
"""
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging

from .languages import get_all_languages, get_language
from .languages.loader import load_all_languages

logger = logging.getLogger(__name__)


@dataclass
class CategoryResult:
    """Result of document categorization"""
    primary_category: str
    confidence: float
    all_categories: Dict[str, float] = field(default_factory=dict)
    indicators: List[str] = field(default_factory=list)
    detected_languages: List[str] = field(default_factory=list)


class DocumentCategorizer:
    """
    Categorizes documents based on content patterns

    Supports multiple languages and automatically detects document language
    """

    def __init__(self, languages: Optional[List[str]] = None):
        """
        Initialize document categorizer

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

        logger.info(f"DocumentCategorizer initialized with languages: {list(self.languages.keys())}")

        # Build combined category patterns from all languages
        self.categories = self._build_combined_categories()

    def _build_combined_categories(self) -> Dict[str, Dict]:
        """
        Build combined category patterns from all enabled languages

        Returns:
            Dictionary of categories with combined patterns
        """
        combined = {}

        # Get all unique category names across all languages
        category_names = set()
        for lang_config in self.languages.values():
            category_names.update(lang_config.categories.keys())

        # Combine patterns for each category
        for category_name in category_names:
            all_keywords = []
            all_patterns = []
            description = ""

            for lang_code, lang_config in self.languages.items():
                if category_name in lang_config.categories:
                    cat_patterns = lang_config.categories[category_name]
                    all_keywords.extend(cat_patterns.keywords)
                    all_patterns.extend(cat_patterns.patterns)
                    if not description:
                        description = cat_patterns.description

            combined[category_name] = {
                "keywords": all_keywords,
                "patterns": all_patterns,
                "description": description
            }

        return combined

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
            try:
                if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                    pattern_matches += 1
                    indicators.append(f"pattern:{pattern[:30]}...")
            except re.error:
                logger.warning(f"Invalid regex pattern: {pattern}")
                continue

        # Weight pattern matches (patterns are stronger indicators)
        if pattern_matches > 0:
            score += min(pattern_matches * 0.2, 0.7)

        # Normalize score to 0-1 range
        score = min(score, 1.0)

        return score, indicators

    def _detect_languages(self, text: str) -> List[str]:
        """
        Detect which languages are present in the text

        Args:
            text: Document text

        Returns:
            List of detected language codes
        """
        detected = []
        text_lower = text.lower()

        for lang_code, lang_config in self.languages.items():
            # Check for language-specific keywords
            keyword_count = 0

            # Check date context keywords
            for keyword in lang_config.date_context_keywords:
                if keyword.lower() in text_lower:
                    keyword_count += 1

            # Check amount context keywords
            for keyword in lang_config.amount_context_keywords:
                if keyword.lower() in text_lower:
                    keyword_count += 1

            # Check month names
            for month in lang_config.month_names:
                if month.lower() in text_lower:
                    keyword_count += 2  # Month names are strong indicators

            # If enough language-specific keywords found, consider language detected
            if keyword_count >= 3:
                detected.append(lang_code)

        return detected if detected else list(self.languages.keys())

    def categorize(self, text: str, metadata: Optional[Dict] = None) -> str:
        """
        Categorize a document based on its text content

        Args:
            text: OCR extracted text from document
            metadata: Optional metadata dictionary (for future use)

        Returns:
            String with primary category name (flat structure for metadata)
        """
        result = self.categorize_detailed(text)
        return result.primary_category

    def categorize_detailed(self, text: str) -> CategoryResult:
        """
        Categorize a document with detailed results

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
                indicators=[],
                detected_languages=[]
            )

        # Detect languages in text
        detected_languages = self._detect_languages(text)

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
            indicators=indicators,
            detected_languages=detected_languages
        )

# Alias for backward compatibility
DocumentCategorizerV2 = DocumentCategorizer
