"""
Language detection utility
"""

import re

class LanguageDetector:
    SUPPORTED_LANGUAGES = {
        'en': 'Respond in English.',
        'sw': 'Jibu kwa Kiswahili.',
    }

    SWAHILI_MARKERS = {
        'habari', 'jambo', 'asante', 'karibu', 'tafadhali', 'kupika',
        'nina', 'naweza', 'chakula', 'sana', 'kwa', 'kuna', 'mimi'
    }

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect language using simple Swahili keyword heuristics."""
        if not text or not text.strip():
            return 'english'
        words = set(re.findall(r"\b\w+\b", text.lower()))
        if len(words & LanguageDetector.SWAHILI_MARKERS) >= 1:
            return 'swahili'
        return 'english'

    @staticmethod
    def get_language_instruction(lang: str) -> str:
        """Return LLM system instruction for a language."""
        if lang.lower() in ['swahili', 'sw']:
            return LanguageDetector.SUPPORTED_LANGUAGES['sw']
        return LanguageDetector.SUPPORTED_LANGUAGES['en']
