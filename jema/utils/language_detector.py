"""
Language detection utility
"""

from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0  # consistent results

class LanguageDetector:
    SUPPORTED_LANGUAGES = {
        'en': 'Respond in English.',
        'sw': 'Jibu kwa Kiswahili.',
    }

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect language from user input."""
        try:
            lang_code = detect(text)
            if lang_code.startswith('sw'):
                return 'swahili'
            return 'english'
        except Exception:
            return 'english'

    @staticmethod
    def get_language_instruction(lang: str) -> str:
        """Return LLM system instruction for a language."""
        if lang.lower() in ['swahili', 'sw']:
            return LanguageDetector.SUPPORTED_LANGUAGES['sw']
        return LanguageDetector.SUPPORTED_LANGUAGES['en']
