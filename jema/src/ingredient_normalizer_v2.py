"""
Ingredient Normalizer v2 - Enhanced with natural language extraction
Normalizes user input and Excel ingredients for accurate matching
"""

import re
from typing import List, Dict, Set


class IngredientNormalizer:
    """Normalize and standardize ingredient names for matching"""
    
    # Singular/plural forms and common variations
    VARIATIONS = {
        # Grains
        'rice': ['rice', 'wali', 'mchele'],
        'maize': ['maize', 'corn', 'mahindi', 'mafu'],
        'wheat': ['wheat', 'ngano'],
        'millet': ['millet', 'wimbi'],
        'flour': ['flour', 'unga'],
        'cassava': ['cassava', 'mhogo', 'cassava flour', 'tapioca'],
        'sorghum': ['sorghum', 'mtama'],
        
        # Legumes
        'beans': ['beans', 'bean', 'maharage', 'maharagwe'],
        'lentils': ['lentils', 'lentil', 'dengu'],
        'peas': ['peas', 'pea', 'ndizi'],
        'chickpeas': ['chickpeas', 'chickpea'],
        'green grams': ['green grams', 'green gram', 'mung beans', 'mung bean', 'nzenga', 'ndengu'],
        'pigeon peas': ['pigeon peas', 'pigeon pea', 'mbaazi'],
        'cowpeas': ['cowpeas', 'cowpea', 'kunde'],
        
        # Vegetables
        'cabbage': ['cabbage', 'kabichi'],
        'tomato': ['tomato', 'tomatoes', 'nyanya'],
        'onion': ['onion', 'onions', 'kitunguu'],
        'carrot': ['carrot', 'carrots', 'karoti'],
        'potato': ['potato', 'potatoes', 'viazi'],
        'sweet potato': ['sweet potato', 'sweet potatoes', 'viazi vya kumimina'],
        'greens': ['greens', 'sukuma wiki', 'collard'],
        'spinach': ['spinach', 'mchicha'],
        'kale': ['kale', 'sukuma wiki'],
        
        # Proteins
        'beef': ['beef', 'nyama ya ng\'ombe'],
        'chicken': ['chicken', 'kuku'],
        'fish': ['fish', 'samaki'],
        'goat': ['goat', 'nyama ya mbuzi'],
        'lamb': ['lamb', 'nyama ya kondoo'],
        'meat': ['meat', 'nyama'],
        'eggs': ['eggs', 'egg', 'mayai'],
        
        # Dairy
        'milk': ['milk', 'maziwa'],
        'butter': ['butter', 'siagi'],
        'yogurt': ['yogurt', 'yoghurt', 'maziwa lala'],
        
        # Oils & fats
        'oil': ['oil', 'cooking oil', 'vegetable oil', 'mafuta'],
        'coconut oil': ['coconut oil', 'mafuta ya nazi'],
        
        # Seasonings (assumed/staple)
        'salt': ['salt', 'chumvi'],
        'pepper': ['pepper', 'pilipili'],
        'garlic': ['garlic', 'kitunguu sumu'],
        'ginger': ['ginger', 'tangawizi'],
        'spice': ['spice', 'spices', 'seasoning', 'kimengenya'],
        'cumin': ['cumin', 'jeera'],
        'turmeric': ['turmeric', 'kurkuma'],
        
        # Common prepared dishes/bread (for matching)
        'chapati': ['chapati', 'roti', 'paratha'],
        'injera': ['injera', 'teff bread'],
        'ugali': ['ugali', 'posho', 'cornmeal'],
        'mandazi': ['mandazi', 'dough balls'],
        'rolex': ['rolex'],
        
        # Fruits & special vegetables
        'banana': ['banana', 'bananas', 'green banana', 'green bananas', 'matoke', 'plantain', 'plantains'],
        'amaranth': ['amaranth', 'amaranth leaves', 'doodo', 'mchicha'],
        'solanum': ['solanum', 'solanum leaves', 'nakati', 'managu', 'black nightshade'],
        'cassava leaves': ['cassava leaves', 'sombe', 'isombe', 'pondu'],
        'pumpkin leaves': ['pumpkin leaves', 'pumpkin greens'],
        
        # Others
        'water': ['water', 'maji'],
        'coconut': ['coconut', 'nazi'],
        'peanut': ['peanut', 'peanuts', 'groundnut', 'groundnuts'],
    }
    
    # Reverse mapping for faster lookup
    _REVERSE_MAP = None
    
    @classmethod
    def _build_reverse_map(cls):
        """Build reverse mapping from variation to canonical form"""
        if cls._REVERSE_MAP is None:
            cls._REVERSE_MAP = {}
            for canonical, variations in cls.VARIATIONS.items():
                for variation in variations:
                    cls._REVERSE_MAP[variation.lower()] = canonical
        return cls._REVERSE_MAP
    
    @staticmethod
    def normalize_single(ingredient: str) -> str:
        """
        Normalize a single ingredient name.
        Returns canonical ingredient name or empty string if not matched.
        """
        if not ingredient:
            return ""
        
        # Clean up
        clean = ingredient.strip().lower()
        
        # Remove non-letter characters (quantities, punctuation) but keep spaces
        # e.g., "2 eggs" -> "eggs", "onion (chopped)" -> "onion chopped"
        clean = re.sub(r"[^a-z\s]", "", clean)
        
        # Remove extra whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        
        # Build reverse map if needed
        reverse_map = IngredientNormalizer._build_reverse_map()
        
        # Direct lookup
        if clean in reverse_map:
            return reverse_map[clean]
        
        # Partial matching - match when a known variation appears within the cleaned text
        for canonical, variations in IngredientNormalizer.VARIATIONS.items():
            for variation in variations:
                v = variation.lower()
                if clean == v:
                    return canonical
                if v in clean:
                    return canonical
        
        return ""
    
    @staticmethod
    def normalize_list(ingredients: List[str]) -> Set[str]:
        """Normalize a list of ingredients; only include matched ones."""
        normalized = set()
        for ing in ingredients:
            canonical = IngredientNormalizer.normalize_single(ing)
            if canonical:
                normalized.add(canonical)
        return normalized
    
    @staticmethod
    def extract_from_string(ingredient_string: str, strict: bool = False) -> Set[str]:
        """
        Extract and normalize ingredients from natural language text.
        Handles both comma-separated and free text.
        Returns ONLY canonical ingredient names that were matched.
        
        Args:
            ingredient_string: The text containing ingredients
            strict: If True, includes unrecognized items as-is (for recipe parsing)
        """
        if not ingredient_string:
            return set()
        
        text = str(ingredient_string).lower()
        
        # Build reverse map
        reverse_map = IngredientNormalizer._build_reverse_map()
        
        # Try comma-separated first (if contains commas)
        if ',' in text:
            ingredients = [ing.strip() for ing in text.split(',') if ing.strip()]
            normalized = set()
            for ing in ingredients:
                canonical = IngredientNormalizer.normalize_single(ing)
                if canonical:
                    normalized.add(canonical)
                elif strict and ing:  # In strict mode, keep unrecognized items
                    # Clean up but keep the ingredient
                    cleaned = re.sub(r'[^a-z\s]', '', ing).strip()
                    if cleaned:
                        normalized.add(cleaned)
            return normalized
        
        # Natural language extraction - search for ingredient keywords
        # Sort by length (longest first) to match compounds before parts
        sorted_ingredients = sorted(
            reverse_map.keys(),
            key=len,
            reverse=True
        )
        
        extracted = set()
        for ingredient_phrase in sorted_ingredients:
            # Match word boundaries for cleaner extraction
            # Allow "eggs" to match "egg", "eggss", etc.
            pattern = r'\b' + re.escape(ingredient_phrase) + r's?\b'
            if re.search(pattern, text):
                canonical = reverse_map[ingredient_phrase]
                extracted.add(canonical)
        
        return extracted
    
    @staticmethod
    def get_canonical_form(ingredient: str) -> str:
        """Get the canonical form of an ingredient for display"""
        result = IngredientNormalizer.normalize_single(ingredient)
        return result if result else ingredient
    
    @staticmethod
    def is_assumed_ingredient(ingredient: str) -> bool:
        """Check if ingredient is assumed/staple (salt, oil, water)"""
        assumed = {'salt', 'water', 'oil', 'pepper', 'spice', 'seasoning'}
        canonical = IngredientNormalizer.normalize_single(ingredient)
        return canonical in assumed
