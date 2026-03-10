import re
from typing import Literal


class LanguageDetector:
    """Detect whether user input is in English or Swahili."""
    
    # Common Swahili words and patterns (excluding food names)
    SWAHILI_WORDS = {
        # Greetings
        'habari', 'jambo', 'salama', 'asante', 'karibu', 'tafadhali', 'shikamoo',
        # Common verbs (action words - clear indicators of Swahili)
        'kutengeneza', 'kula', 'kupika', 'kutaka', 'kuwa', 'kufanya',
        'ninataka', 'ninaitaka', 'naweza', 'ninaweza', 'wanaeza',
        'napenda', 'ningependa', 'natafuta',
        # Question words
        'je', 'nini', 'nani', 'wapi', 'kwanini', 'namna', 'vipi', 'lini',
        # Common words
        'sana', 'kila', 'kote', 'leo', 'kesho', 'jana', 'kabisa',
        # Pronouns
        'mimi', 'wewe', 'yeye', 'sisi', 'ninyi', 'wao', 'yangu', 'yako', 'yake',
        # Prepositions/conjunctions
        'kwa', 'katika', 'kwenye', 'pamoja', 'lakini', 'au',
    }
    
    # Food names that should NOT trigger Swahili detection
    FOOD_NAMES = {
        'ugali', 'sukuma', 'wiki', 'nyama', 'samaki', 'pilau', 'biriani', 'biryani',
        'chapati', 'mandazi', 'matoke', 'isombe', 'githeri', 'mukimo', 'irio',
        'mishkaki', 'bhajia', 'sambusa', 'maharagwe', 'kunde', 'dengu', 'ndengu',
    }
    
    # Swahili language patterns
    SWAHILI_PATTERNS = [
        r'\bku[a-z]+\b',  # Infinitive verbs (ku-)
        r'\bni[a-z]+\b',  # Present tense (ni-)
        r'\bwa[a-z]+\b',  # Plural/they verbs (wa-)
        r'\bm[a-z]o[a-z]*\b',  # Noun patterns (mo-)
        r'\bki[a-z]+\b',  # Noun patterns (ki-)
        r'\bvi[a-z]+\b',  # Plural patterns (vi-)
        r'\bma[a-z]+\b',  # Plural patterns (ma-)
    ]
    
    @staticmethod
    def detect_language(text: str) -> Literal['english', 'swahili']:
        """
        Detect if text is in English or Swahili.
        
        Args:
            text: User input text
            
        Returns:
            'english' or 'swahili'
        """
        if not text or not text.strip():
            return 'english'
        
        text_lower = text.lower()
        words = text_lower.split()
        
        # Count Swahili indicators
        swahili_count = 0
        total_words = len(words)
        
        # Check for Swahili words (excluding food names)
        for word in words:
            # Remove punctuation for comparison
            clean_word = re.sub(r'[^\w]', '', word)
            
            # Skip if it's a food name
            if clean_word in LanguageDetector.FOOD_NAMES:
                continue
                
            if clean_word in LanguageDetector.SWAHILI_WORDS:
                swahili_count += 2  # Weight actual Swahili words heavily
        
        # Check for Swahili patterns (excluding food names)
        for pattern in LanguageDetector.SWAHILI_PATTERNS:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                # Skip if match is a food name
                if match not in LanguageDetector.FOOD_NAMES:
                    swahili_count += 0.5  # Weight patterns less than exact words
        
        # If Swahili indicators > 30% of words, classify as Swahili
        # Increased threshold to require more Swahili markers
        swahili_ratio = swahili_count / max(total_words, 1)
        
        if swahili_ratio >= 0.4 or 'swahili' in text_lower:
            return 'swahili'
        
        return 'english'
    
    @staticmethod
    def get_language_instruction(language: Literal['english', 'swahili']) -> str:
        """
        Get language-specific instruction for the LLM.
        
        Args:
            language: 'english' or 'swahili'
            
        Returns:
            Instruction string for the LLM
        """
        if language == 'swahili':
            return "Respond entirely in Swahili. Use authentic Swahili language for greetings, cooking terms, and all responses."
        else:
            return "Respond in English."
