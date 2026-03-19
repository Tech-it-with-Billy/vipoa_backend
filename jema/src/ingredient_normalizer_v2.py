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
        # ── Grains ───────────────────────────────────────────────────────────────
        'rice': ['rice', 'wali', 'mchele', 'basmati', 'basmati rice',
                 'pishori', 'pishori rice', 'long grain rice', 'white rice'],
        'maize': ['maize', 'corn', 'mahindi', 'mafu', 'hominy'],
        'wheat': ['wheat', 'ngano'],
        'millet': ['millet', 'wimbi'],
        'flour': ['flour', 'unga', 'wheat flour', 'maize flour'],
        'cassava': ['cassava', 'mhogo', 'mihogo', 'cassava flour', 'tapioca'],
        'sorghum': ['sorghum', 'mtama'],

        # ── Legumes ───────────────────────────────────────────────────────────────
        'beans': ['beans', 'bean', 'maharage', 'maharagwe', 'kidney beans',
                  'red beans', 'black beans', 'dry beans'],
        # FIXED: lentils must NOT include dengu or ndengu — those are green grams
        'lentils': ['lentils', 'lentil', 'red lentils', 'brown lentils',
                    'green lentils', 'yellow lentils', 'split lentils'],
        'peas': ['peas', 'pea', 'njegere', 'garden peas', 'green peas'],
        # FIXED: ndizi removed from peas — ndizi is banana, not peas
        # FIXED: ndengu and dengu moved here from lentils — ndengu is green grams
        'green grams': ['green grams', 'green gram', 'mung beans', 'mung bean',
                        'nzenga', 'ndengu', 'dengu', 'kunde'],
        'chickpeas': ['chickpeas', 'chickpea', 'garbanzo', 'garbanzo beans'],
        'pigeon peas': ['pigeon peas', 'pigeon pea', 'mbaazi'],
        'cowpeas': ['cowpeas', 'cowpea', 'black eyed peas', 'black eyed pea'],
        'groundnuts': ['groundnuts', 'groundnut', 'peanut', 'peanuts',
                       'njugu', 'groundnut paste', 'peanut butter'],

        # ── Vegetables ────────────────────────────────────────────────────────────
        'cabbage': ['cabbage', 'kabichi'],
        'tomato': ['tomato', 'tomatoes', 'nyanya', 'cherry tomato',
                   'cherry tomatoes', 'roma tomato'],
        'onion': ['onion', 'onions', 'kitunguu', 'red onion', 'red onions',
                  'white onion', 'yellow onion', 'spring onion', 'spring onions'],
        'carrot': ['carrot', 'carrots', 'karoti'],
        'potato': ['potato', 'potatoes', 'viazi', 'irish potato', 'irish potatoes'],
        'sweet potato': ['sweet potato', 'sweet potatoes', 'viazi vitamu',
                         'viazi vya kumimina'],
        'greens': ['greens', 'collard', 'collard greens', 'leafy greens'],
        'spinach': ['spinach', 'mchicha', 'amaranth', 'amaranth leaves', 'doodo'],
        'kale': ['kale', 'sukuma wiki', 'sukuma'],
        # NEW — bell pepper was completely missing from the map
        'bell pepper': ['bell pepper', 'bell peppers', 'green pepper',
                        'green peppers', 'green bell pepper', 'green bell peppers',
                        'red pepper', 'red peppers', 'yellow pepper',
                        'hoho', 'pilipili hoho', 'capsicum'],
        'eggplant': ['eggplant', 'aubergine', 'bilinganya'],
        'zucchini': ['zucchini', 'courgette'],
        'cucumber': ['cucumber', 'tango'],
        'pumpkin': ['pumpkin', 'boga', 'pumpkin leaves', 'pumpkin greens'],

        # ── Proteins ──────────────────────────────────────────────────────────────
        # FIXED: beef now includes common short forms so "beef" is never dropped
        'beef': ['beef', "nyama ya ng'ombe", 'nyama', 'steak',
                 'minced beef', 'ground beef', 'beef chunks', 'beef pieces',
                 'beef stew meat', 'diced beef', 'beef strips'],
        'chicken': ['chicken', 'kuku', 'chicken pieces', 'chicken thighs',
                    'chicken breast', 'whole chicken', 'kuku kienyeji'],
        'fish': ['fish', 'samaki', 'tilapia', 'dagaa', 'omena',
                 'dried fish', 'fresh fish'],
        'goat': ['goat', "nyama ya mbuzi", 'goat meat', 'mutton'],
        'lamb': ['lamb', "nyama ya kondoo", 'lamb chops'],
        'pork': ['pork', 'nguruwe', 'bacon', 'ham'],
        'eggs': ['eggs', 'egg', 'mayai', 'boiled egg', 'boiled eggs',
                 'fried egg', 'fried eggs', 'scrambled eggs'],
        'octopus': ['octopus', 'pweza'],
        'shrimp': ['shrimp', 'prawns', 'kamba'],

        # ── Dairy ─────────────────────────────────────────────────────────────────
        'milk': ['milk', 'maziwa', 'whole milk', 'full fat milk'],
        'butter': ['butter', 'siagi', 'ghee'],
        'yogurt': ['yogurt', 'yoghurt', 'maziwa lala', 'sour milk'],
        'cream': ['cream', 'heavy cream', 'double cream'],
        'cheese': ['cheese', 'jibini'],

        # ── Oils and fats ─────────────────────────────────────────────────────────
        'oil': ['oil', 'cooking oil', 'vegetable oil', 'mafuta',
                'sunflower oil', 'corn oil'],
        'coconut oil': ['coconut oil', 'mafuta ya nazi'],

        # ── Seasonings ────────────────────────────────────────────────────────────
        'salt': ['salt', 'chumvi'],
        'pepper': ['pepper', 'pilipili', 'black pepper', 'white pepper',
                   'chili', 'chilli', 'pilipili kali'],
        'garlic': ['garlic', 'kitunguu sumu', 'garlic cloves', 'minced garlic'],
        'ginger': ['ginger', 'tangawizi', 'fresh ginger', 'ground ginger'],
        'cumin': ['cumin', 'jeera', 'ground cumin', 'cumin seeds'],
        'turmeric': ['turmeric', 'kurkuma', 'ground turmeric'],
        'coriander': ['coriander', 'dhania', 'cilantro', 'coriander leaves'],
        'cardamom': ['cardamom', 'iliki'],
        'cinnamon': ['cinnamon', 'mdalasini'],
        'cloves': ['cloves', 'karafuu'],
        'pilau masala': ['pilau masala', 'pilau spice', 'biryani masala'],
        'curry powder': ['curry powder', 'curry', 'spice mix'],
        'spice': ['spice', 'spices', 'seasoning', 'kimengenya', 'mixed spice'],

        # ── Coconut ───────────────────────────────────────────────────────────────
        'coconut': ['coconut', 'nazi', 'desiccated coconut', 'coconut flakes'],
        'coconut milk': ['coconut milk', 'maziwa ya nazi', 'coconut cream'],

        # ── Fruits ───────────────────────────────────────────────────────────────
        # FIXED: ndizi correctly mapped here only — removed from peas
        'banana': ['banana', 'bananas', 'green banana', 'green bananas',
                   'ndizi', 'matoke', 'plantain', 'plantains', 'cooking banana'],
        'mango': ['mango', 'maembe'],
        'avocado': ['avocado', 'parachichi'],
        'lemon': ['lemon', 'ndimu', 'lime'],
        'passion fruit': ['passion fruit', 'passionfruit', 'granadilla'],
        'pineapple': ['pineapple', 'nanasi'],
        'papaya': ['papaya', 'pawpaw', 'papai'],

        # ── Specialty vegetables ──────────────────────────────────────────────────
        'cassava leaves': ['cassava leaves', 'sombe', 'isombe', 'pondu'],
        'solanum': ['solanum', 'solanum leaves', 'nakati', 'managu',
                    'black nightshade'],
        'bamboo shoots': ['bamboo shoots', 'malewa'],
        'okra': ['okra', 'bamia', 'lady fingers'],
        'arrow roots': ['arrow roots', 'arrowroot', 'nduma'],

        # ── Bread and prepared staples ────────────────────────────────────────────
        'chapati': ['chapati', 'roti', 'paratha', 'flatbread'],
        'ugali': ['ugali', 'posho', 'cornmeal', 'stiff porridge'],
        'mandazi': ['mandazi', 'dough balls', 'maandazi'],
        'rolex': ['rolex'],
        'injera': ['injera', 'teff bread'],

        # ── Liquids ───────────────────────────────────────────────────────────────
        'water': ['water', 'maji'],
        'broth': ['broth', 'stock', 'mchuzi', 'beef broth', 'chicken broth',
                  'vegetable broth'],
        'tomato paste': ['tomato paste', 'tomato puree', 'tomato sauce'],
    }
    
    # Reverse mapping for faster lookup
    _REVERSE_MAP = None
    
    @classmethod
    def _build_reverse_map(cls):
        """
        Build reverse mapping from every variation string to its canonical name.
        Handles multi-word variations like 'green bell pepper' and 'pilau masala'.
        Longer variations are matched first to prevent partial matches.
        """
        if cls._REVERSE_MAP is None:
            cls._REVERSE_MAP = {}
            for canonical, variations in cls.VARIATIONS.items():
                for variation in variations:
                    variation_lower = variation.lower().strip()
                    # If a variation maps to multiple canonicals, keep the
                    # more specific one (longer canonical name wins)
                    if variation_lower not in cls._REVERSE_MAP:
                        cls._REVERSE_MAP[variation_lower] = canonical
                    else:
                        existing = cls._REVERSE_MAP[variation_lower]
                        if len(canonical) > len(existing):
                            cls._REVERSE_MAP[variation_lower] = canonical
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
        Extract and normalize ingredients from a natural language string.

        Handles all these formats correctly:
        - "onion, beef and rice"
        - "onion, eggs and tomato"
        - "lentils, onion and green bell pepper"
        - "I have beef, rice and onion"
        - "Nina nyama, mchele na vitunguu"
        - "beef & onion & tomato"

        The previous version was dropping ingredients that appeared after
        the word "and" when combined with a preceding word (e.g. "beef and rice"
        was being parsed as a single token "beef and rice" which matched nothing).

        Args:
            ingredient_string: Raw user input string
            strict: If True, only return ingredients that exactly match
                    known variations. If False, also return unrecognized
                    words that might be ingredients.

        Returns:
            Set of normalized canonical ingredient names
        """
        if not ingredient_string:
            return set()

        # Build reverse map if not already built
        reverse_map = IngredientNormalizer._build_reverse_map()

        # Step 1 — lowercase and strip
        text = ingredient_string.lower().strip()

        # Step 2 — remove common filler phrases that are not ingredients
        filler_phrases = [
            "i have", "i've got", "i got", "we have", "there is", "there are",
            "i need", "i want to cook with", "i want to use", "using",
            "what can i cook with", "what can i make with", "cook with",
            "i only have", "i just have", "all i have is", "i have some",
            "hey jema", "hey", "jema", "hi", "hello",
            "nina", "ninazo", "nina nazo",  # Swahili: "I have"
        ]
        for phrase in filler_phrases:
            text = text.replace(phrase, " ")

        # Step 3 — replace all delimiters with commas
        # This is the critical fix — "and", "na" (Swahili), "&", "/" all become commas
        # so "beef and rice" becomes "beef, rice" and both are extracted correctly
        text = re.sub(r'\band\b', ',', text)   # English "and"
        text = re.sub(r'\bna\b', ',', text)    # Swahili "na" (and)
        text = re.sub(r'\bor\b', ',', text)    # English "or"
        text = re.sub(r'&', ',', text)         # ampersand
        text = re.sub(r'\bwith\b', ',', text)  # "with"
        text = re.sub(r'\bplus\b', ',', text)  # "plus"

        # Step 4 — split on commas to get raw tokens
        raw_tokens = [t.strip() for t in text.split(',') if t.strip()]

        # Step 5 — for each token, try to match against known variations
        # Try longest match first (e.g. "green bell pepper" before "pepper")
        # This prevents "green bell pepper" being split into "green" + "pepper"
        extracted = set()

        for token in raw_tokens:
            token = token.strip()

            if not token or len(token) < 2:
                continue

            # Remove quantities and measurements from token
            # e.g. "2 cups rice" → "rice", "500g beef" → "beef"
            token = re.sub(
                r'^\d+\s*(?:g|kg|ml|l|cups?|tbsp|tsp|oz|lbs?|pieces?|cloves?|medium|large|small|fresh|dried)?\s*',
                '', token
            ).strip()

            if not token:
                continue

            matched = False

            # Try to match the full token first (handles multi-word ingredients)
            if token in reverse_map:
                extracted.add(reverse_map[token])
                matched = True
                continue

            # Try matching sub-phrases within the token (longest first)
            # This handles cases like "green bell pepper" where the full phrase
            # is in the map but individual words are not
            all_variations = sorted(reverse_map.keys(), key=len, reverse=True)
            for variation in all_variations:
                # Match whole word/phrase — not partial
                pattern = r'\b' + re.escape(variation) + r'\b'
                if re.search(pattern, token):
                    extracted.add(reverse_map[variation])
                    matched = True
                    break

            # If no match found and strict is False, include the raw token
            # so unknown ingredients are not silently dropped
            if not matched and not strict:
                # Only include if it looks like a real ingredient word
                # (not a number, not a single letter, not just common words)
                common_words = {
                    'the', 'a', 'an', 'some', 'any', 'few', 'little',
                    'my', 'our', 'your', 'this', 'that', 'these', 'those',
                    'what', 'which', 'how', 'can', 'do', 'did', 'have',
                    'has', 'had', 'is', 'are', 'was', 'were', 'be', 'been',
                    'cook', 'make', 'prepare', 'use', 'need', 'want', 'get',
                }
                
                # Check if token is mostly punctuation and common words
                # Extract only alphabetic words from token
                token_words = re.findall(r'\b[a-z]+\b', token.lower())
                
                # Only add if:
                # 1. Token is not empty after cleanup
                # 2. Has at least one word that isn't a common word
                if token_words and any(w not in common_words for w in token_words):
                    extracted.add(token)

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
