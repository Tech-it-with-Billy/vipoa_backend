"""
Jema Cooking Assistant - Production Modelling Pipeline

A stateless, importable module exposing:
- Ingredient-based recipe recommendation with fuzzy matching
- Time filtering and persona-aware scoring
- Multilingual (English/Swahili) support
- Groq NLG integration for explanations
- RAG-based nutrition document retrieval using FAISS

Safe to import from FastAPI. No global state modifications.
"""

import os
import re
import json
from pathlib import Path
from difflib import SequenceMatcher
from typing import List, Dict, Set, Optional, Tuple, Any
from collections import defaultdict

import pandas as pd
import numpy as np

try:
    import faiss
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:
    faiss = None
    TfidfVectorizer = None

try:
    from groq import Groq
except ImportError:
    Groq = None


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Module configuration (read-only)"""
    DATA_DIR = Path(__file__).parent.parent
    RECIPE_CSV = DATA_DIR / "data" / "final_african_recipes.csv"
    INGREDIENTS_CSV = DATA_DIR / "data" / "all_ingred.csv"
    
    GROQ_MODEL = "llama-3.3-70b-versatile"
    FUZZY_MATCH_THRESHOLD = 0.72  # Lowered from 0.85 to better catch ingredient variants like spinach, fish, etc.
    SUBSTITUTION_THRESHOLD = 0.8
    RAG_TOP_K = 3
    RECIPE_TOP_K = 5


# ============================================================================
# SWAHILI-ENGLISH INGREDIENT ALIASES
# ============================================================================

SW_ALIAS = {
    "vitunguu": "onion",
    "kitunguu": "onion",
    "nyanya": "tomato",
    "mayai": "eggs",
    "mafuta": "oil",
    "pilipili": "chili",
    "vitunguu saumu": "garlic",
    "sukuma wiki": "collards",
    "mchicha": "spinach",
    "karanga": "groundnuts",
    "mahindi": "maize",
    "maharagwe": "beans",
    "ndulele": "okra",
}

SW_MARKERS = {
    "nina", "na", "kupika", "chakula",
    "mayai", "nyanya", "vitunguu", "dakika",
    "muda", "viungo", "karibu"
}

PROTEIN_INGREDIENTS = {
    "chicken", "kuku", "beef", "meat", "fish", "tilapia",
    "shrimp", "prawn", "prawns", "goat", "lamb", "pork",
    "eggs", "egg", "beans", "lentils", "tofu", "turkey"
}

LEAFY_GREENS = {
    "kale", "sukuma wiki", "spinach", "mchicha", "collards", "cabbage", "leafy greens", "sukuma"
}

ALTERNATIVES_KEYWORDS = {
    "alternative", "alternatives", "instead", "other options", "others", "different", "swap", "substitute"
}


# ============================================================================
# EAST AFRICAN RECIPE LIBRARY (Fallback Library)
# ============================================================================

EAST_AFRICAN_RECIPE_LIBRARY = [
    {
        "name": "Ugali Mayai",
        "core": ["eggs", "onions"],
        "ingredients": ["eggs", "onions", "tomatoes", "oil", "ugali"],
        "region": "east_africa",
        "cook_time": 20
    },
    {
        "name": "Rolex",
        "core": ["eggs", "chapati"],
        "ingredients": ["eggs", "chapati", "onions", "tomatoes"],
        "region": "east_africa",
        "cook_time": 15
    },
    {
        "name": "Chapati Mayai",
        "core": ["eggs", "chapati"],
        "ingredients": ["eggs", "chapati", "onions"],
        "region": "east_africa",
        "cook_time": 10
    },
    {
        "name": "Pilau",
        "core": ["rice", "onions", "pilau masala"],
        "ingredients": ["rice", "onions", "pilau masala", "spices", "oil"],
        "region": "east_africa",
        "cook_time": 45
    },
    {
        "name": "Biryani",
        "core": ["rice", "beef", "onions"],
        "ingredients": ["rice", "beef", "onions", "yogurt", "ginger", "garlic", "spices"],
        "region": "east_africa",
        "cook_time": 50
    },
    {
        "name": "Rice and Beef Stew",
        "core": ["rice", "beef", "onions"],
        "ingredients": ["rice", "beef", "onions", "tomatoes", "carrots"],
        "region": "east_africa",
        "cook_time": 40
    },
    {
        "name": "Wali wa Nazi",
        "core": ["rice", "coconut milk"],
        "ingredients": ["rice", "coconut milk", "onions"],
        "region": "east_africa",
        "cook_time": 25
    },
    {
        "name": "Beans Stew",
        "core": ["beans", "onions", "tomatoes"],
        "ingredients": ["beans", "onions", "tomatoes", "garlic"],
        "region": "east_africa",
        "cook_time": 60
    },
    {
        "name": "Githeri",
        "core": ["maize", "beans"],
        "ingredients": ["maize", "beans", "onions", "tomatoes"],
        "region": "east_africa",
        "cook_time": 45
    },
    {
        "name": "Sukuma Wiki",
        "core": ["kale", "onions", "tomatoes"],
        "ingredients": ["kale", "onions", "tomatoes"],
        "region": "east_africa",
        "cook_time": 15
    },
    {
        "name": "Nyama Choma",
        "core": ["meat", "onions"],
        "ingredients": ["meat", "onions", "lemon", "spices"],
        "region": "east_africa",
        "cook_time": 30
    },
    {
        "name": "Ugali",
        "core": ["maize flour"],
        "ingredients": ["maize flour", "water", "salt"],
        "region": "east_africa",
        "cook_time": 20
    },
    {
        "name": "Mandazi",
        "core": ["flour", "eggs"],
        "ingredients": ["flour", "eggs", "sugar", "oil"],
        "region": "east_africa",
        "cook_time": 20
    }
]


# ============================================================================
# HELPER FUNCTIONS (needed by initialization)
# ============================================================================

def _parse_substitutes(text: str) -> Set[str]:
    """Extract and normalize substitute ingredients from recipe text."""
    if not isinstance(text, str):
        return set()
    
    text = text.lower()
    text = re.sub(r"[^a-z,\s]", " ", text)
    parts = [p.strip() for p in text.split(",")]
    return set([p for p in parts if p])


# ============================================================================
# DATA LOADING & INITIALIZATION (Singleton Pattern)
# ============================================================================

def _load_recipes_and_ingredients() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load recipe and ingredient data.
    
    Returns:
        (recipes_features_df, kcal_df)
    """
    # Load raw recipes
    recipes_df = pd.read_csv(Config.RECIPE_CSV)
    recipes_df = recipes_df.reset_index().rename(columns={"index": "recipe_id"})
    
    # Feature engineering
    recipes_features_df = recipes_df.copy()
    
    # Number of ingredients
    recipes_features_df["num_ingredients"] = (
        recipes_features_df["core_ingredients"]
        .str.split(",")
        .apply(len)
    )
    
    # Has spices (binary)
    recipes_features_df["has_spices"] = (
        recipes_features_df["spices_seasoning"]
        .str.strip()
        .ne("")
        .astype("int")
    )
    
    # Cook time buckets
    recipes_features_df["cook_time_bucket"] = np.where(
        recipes_features_df["cook_time_minutes"] == 0,
        "no_cook",
        pd.cut(
            recipes_features_df["cook_time_minutes"],
            bins=[0, 20, 45, 90, 10_000],
            labels=["quick", "medium", "long", "very_long"],
            right=True
        )
    )
    
    # Persona suitability flags
    recipes_features_df["suitable_dada"] = (
        (recipes_features_df["num_ingredients"] <= 6) &
        (recipes_features_df["cook_time_minutes"] <= 45)
    ).astype(int)
    
    recipes_features_df["suitable_kaka"] = (
        (recipes_features_df["cook_time_minutes"] <= 30)
    ).astype(int)
    
    recipes_features_df["suitable_mama"] = (
        recipes_features_df["has_spices"] == 1
    ).astype(int)
    
    recipes_features_df["suitable_baba"] = (
        (recipes_features_df["cook_time_minutes"].between(15, 60)) &
        (~recipes_features_df["meal_type"].str.lower().isin(["snack"]))
    ).astype(int)
    
    # Parse substitutes
    recipes_features_df["parsed_substitutes"] = (
        recipes_features_df["substitutes"]
        .apply(_parse_substitutes)
    )
    
    # Load calorie data
    kcal_df = pd.read_csv(Config.INGREDIENTS_CSV, index_col=0)
    
    return recipes_features_df, kcal_df


def _build_ingredient_structures(recipes_features_df: pd.DataFrame) -> Tuple[List[str], Dict, Dict]:
    """
    Build fast lookup structures for ingredient matching.
    
    Returns:
        (INGREDIENT_VOCAB, recipe_ingredient_map, recipe_substitute_map)
    """
    # Explode recipes into ingredients
    ingredient_bridge_df = (
        recipes_features_df[["meal_name", "core_ingredients", "recipe_id"]]
        .assign(
            ingredient=lambda x: (
                x["core_ingredients"]
                .str.lower()
                .str.split(",")
            )
        )
        .explode("ingredient")
        .assign(
            ingredient=lambda x: x["ingredient"].str.strip()
        )
    )
    
    # Ingredient vocabulary
    INGREDIENT_VOCAB = sorted(
        ingredient_bridge_df["ingredient"].str.lower().str.strip().unique().tolist()
    )
    
    # Recipe -> Set[ingredients]
    recipe_ingredient_map = (
        ingredient_bridge_df.groupby("recipe_id")["ingredient"]
        .apply(set)
        .to_dict()
    )
    
    # Recipe -> Set[substitutes]
    recipe_substitute_map = dict(
        zip(
            recipes_features_df["recipe_id"],
            recipes_features_df["parsed_substitutes"]
        )
    )
    
    return INGREDIENT_VOCAB, recipe_ingredient_map, recipe_substitute_map


def _init_groq_client(api_key: Optional[str] = None) -> Optional[Any]:
    """
    Initialize Groq client from API key or environment variable.
    Returns None if Groq is not available.
    """
    if Groq is None:
        return None
    
    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        return None
    
    try:
        return Groq(api_key=key)
    except Exception:
        return None


def _init_rag_index() -> Tuple[Optional[Any], Optional[Any], List[Dict]]:
    """
    Initialize FAISS index for RAG document retrieval.
    
    Returns:
        (faiss_index, vectorizer, rag_documents)
    """
    if faiss is None or TfidfVectorizer is None:
        return None, None, []
    
    # Define nutrition documents
    rag_documents = [
        {
            "id": "dash",
            "text": """DASH diet focuses on reducing sodium and increasing intake of vegetables, fruits,
whole grains, lean proteins and low-fat dairy. It is commonly recommended for people with high blood pressure."""
        },
        {
            "id": "low_fodmap",
            "text": """Low-FODMAP diet limits fermentable carbohydrates such as certain fruits, dairy,
wheat and legumes. It is often used to manage digestive disorders and bloating."""
        },
        {
            "id": "diabetes",
            "text": """Diabetes nutrition guidance emphasizes controlling carbohydrate portions,
choosing low glycaemic index foods, balancing meals with protein and fibre and limiting added sugars."""
        },
        {
            "id": "religious",
            "text": """Religious dietary constraints may include halal food rules, kosher food rules,
fasting periods and restrictions on pork, alcohol or certain animal products."""
        },
        {
            "id": "anti_inflammatory",
            "text": """Anti-inflammatory eating focuses on foods such as vegetables, fruits, whole grains,
nuts, seeds, olive oil and fatty fish while limiting ultra-processed foods and added sugar."""
        }
    ]
    
    try:
        # Build TF-IDF embeddings
        doc_texts = [d["text"] for d in rag_documents]
        vectorizer = TfidfVectorizer(max_features=200, stop_words='english', lowercase=True)
        doc_embeddings = vectorizer.fit_transform(doc_texts).toarray().astype('float32')
        
        # Normalize for FAISS IndexFlatIP
        norms = np.linalg.norm(doc_embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        doc_embeddings = doc_embeddings / norms
        
        # Create FAISS index
        dimension = doc_embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(doc_embeddings)
        
        return index, vectorizer, rag_documents
    except Exception:
        return None, None, rag_documents


# ============================================================================
# MODULE-LEVEL INITIALIZATION (read-only, no mutations)
# ============================================================================

# Load data once at module import time
recipes_features_df, _kcal_df = _load_recipes_and_ingredients()
INGREDIENT_VOCAB, recipe_ingredient_map, recipe_substitute_map = _build_ingredient_structures(recipes_features_df)

# Initialize external services
_groq_client = _init_groq_client()
_faiss_index, _tfidf_vectorizer, rag_documents = _init_rag_index()


# ============================================================================
# UTILITY FUNCTIONS: TEXT NORMALIZATION & LANGUAGE
# ============================================================================

def _apply_sw_aliases(text: str) -> str:
    """Apply Swahili-to-English ingredient aliases."""
    text = text.lower()
    for k, v in SW_ALIAS.items():
        text = text.replace(k, v)
    return text


def _infer_primary_ingredient(user_ingredients: Set[str], user_text: str) -> Optional[str]:
    """Infer primary ingredient (usually protein) from user input."""
    text = user_text.lower()
    # Prefer explicit ingredient mentions from text in order
    for protein in PROTEIN_INGREDIENTS:
        if protein in text and protein in user_ingredients:
            return protein

    # Fallback to any protein ingredient present
    for protein in PROTEIN_INGREDIENTS:
        if protein in user_ingredients:
            return protein

    return None


def _detect_leafy_green(user_ingredients: Set[str]) -> Optional[str]:
    """Detect if the user has a leafy green (for cohesive meal pairing)."""
    for green in LEAFY_GREENS:
        if green in user_ingredients:
            return green
    return None


def _asked_for_alternatives(user_text: str) -> bool:
    """Check if the user explicitly requested alternatives."""
    low = user_text.lower()
    return any(word in low for word in ALTERNATIVES_KEYWORDS)


def _generate_structured_recommendations(
    results: List[Dict[str, Any]],
    user_ingredients: Set[str],
    primary_ingredient: Optional[str],
    leafy_green: Optional[str]
) -> List[Dict[str, str]]:
    """Generate structured JSON recommendation list with origin labels."""
    structured = []
    seen = set()

    # If user asks for protein + leafy green, prefer a combined meal pairing
    if primary_ingredient and leafy_green:
        main_recipe = None
        side_recipe = None

        for r in results:
            name = r.get('meal_name', '')
            if not name or name in seen:
                continue

            # Use matched info or recipe text to infer ingredients
            matched = set(r.get('matched', []))
            if isinstance(matched, list):
                matched = set(matched)

            # Prefer recipe with both primary and leafy green in matched set
            if primary_ingredient in matched and leafy_green in matched and main_recipe is None:
                main_recipe = r

        if not main_recipe:
            # Pick main by protein presence and highest coverage
            for r in results:
                matched = set(r.get('matched', []))
                if primary_ingredient in matched and main_recipe is None:
                    main_recipe = r
                if leafy_green in matched and side_recipe is None:
                    side_recipe = r
            # If we found meat+green in one recipe, use as both
            if main_recipe and leafy_green in set(main_recipe.get('matched', [])):
                side_recipe = None

        if main_recipe:
            structured.append({
                "dish_name": main_recipe.get("meal_name", "Unknown Dish"),
                "origin": main_recipe.get("cuisine_region", "East Africa") or "East Africa"
            })
            seen.add(main_recipe.get("meal_name", ""))

        if side_recipe and side_recipe.get('meal_name', '') not in seen:
            structured.append({
                "dish_name": side_recipe.get("meal_name", "Side Dish"),
                "origin": side_recipe.get("cuisine_region", "East Africa") or "East Africa"
            })

    # Append top ranked results if we still need entries
    for r in results:
        if len(structured) >= 3:
            break
        name = r.get('meal_name', '')
        origin = r.get('cuisine_region', '') or r.get('country', '') or "East Africa"
        if name and name not in seen:
            structured.append({"dish_name": name, "origin": origin})
            seen.add(name)

    # If we have protein + leafy green in user request, ensure we include a leafy green side
    if primary_ingredient and leafy_green:
        has_leafy = any(
            leafy_green in str(r.get('matched', [])).lower() or leafy_green in str(r.get('meal_name', '')).lower()
            for r in results
        )
        if not has_leafy and len(structured) > 0:
            # Add traditional leafy green side if not already present
            side_name = "Sukuma Wiki"
            if all(s.get('dish_name') != side_name for s in structured):
                structured.append({"dish_name": side_name, "origin": "Kenya"})

    return structured


def _generate_ngrams(tokens: List[str], n: int) -> List[str]:
    """Generate n-grams from token list."""
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]
    """Generate n-grams from token list."""
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]


def _fuzzy_match_one(phrase: str, vocabulary: List[str], threshold: float = 0.72) -> Optional[str]:
    """Fuzzy match single phrase against vocabulary. Lower threshold catches more variants."""
    best_score = 0
    best_match = None
    
    for v in vocabulary:
        score = SequenceMatcher(None, phrase, v).ratio()
        if score > best_score:
            best_score = score
            best_match = v
    
    return best_match if best_score >= threshold else None


def detect_language(text: str) -> str:
    """
    Detect language: 'sw' (Swahili) or 'en' (English).
    
    Args:
        text: User input text
        
    Returns:
        'sw' or 'en'
    """
    tokens = set(text.lower().split())
    return "sw" if len(tokens & SW_MARKERS) > 0 else "en"


def extract_user_ingredients(text: str) -> Set[str]:
    """
    Extract normalized ingredients from user text.
    
    Applies Swahili aliases, then fuzzy matches against vocabulary.
    
    Args:
        text: Raw user input
        
    Returns:
        Set of matched ingredient names
    """
    # Apply Swahili aliases
    text = _apply_sw_aliases(text)
    
    # Normalize: lowercase, remove special chars, tokenize
    text = text.lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = [t for t in text.split() if len(t) > 2]

    # Generate candidate phrases (unigrams, bigrams, trigrams)
    candidates: Set[str] = set(tokens)

    # Quick direct ingredient synonyms for important veggies/proteins missed by fuzzy matching
    quick_add = {"kale", "sukuma wiki", "mchicha", "collards", "spinach", "beef", "chicken", "fish", "beans"}
    for w in quick_add:
        if w in text:
            candidates.add(w)
    candidates.update(_generate_ngrams(tokens, 2))
    candidates.update(_generate_ngrams(tokens, 3))
    
    # Match each candidate against vocabulary
    matched_ingredients: Set[str] = set()
    for phrase in candidates:
        # Direct fallback for high-priority ingredients
        if phrase in {"kale", "sukuma wiki", "mchicha", "collards", "spinach", "chicken", "beef", "fish", "beans"}:
            matched_ingredients.add(phrase)
        match = _fuzzy_match_one(phrase, INGREDIENT_VOCAB, threshold=Config.FUZZY_MATCH_THRESHOLD)
        if match is not None:
            matched_ingredients.add(match)
    
    return matched_ingredients


def extract_time_limit(text: str) -> Optional[int]:
    """
    Extract cooking time limit from user text.
    
    Looks for patterns like "20 minutes", "30 dakika", etc.
    
    Args:
        text: User input
        
    Returns:
        Time limit in minutes, or None
    """
    m = re.search(r"(\d+)\s*(min|minutes|dakika)", text.lower())
    return int(m.group(1)) if m else None


# ============================================================================
# RECIPE SCORING & RANKING
# ============================================================================

def _is_substitutable(ingredient: str, substitute_set: Set[str], threshold: float = 0.8) -> bool:
    """Check if ingredient has substitutable alternative."""
    for s in substitute_set:
        if SequenceMatcher(None, ingredient, s).ratio() >= threshold:
            return True
    return False


# ============================================================================
# SINGULAR/PLURAL INGREDIENT NORMALIZATION
# ============================================================================

SINGULAR_PLURAL_MAPPING = {
    # Vegetables
    "onion": "onion", "onions": "onion",
    "tomato": "tomato", "tomatoes": "tomato",
    "egg": "egg", "eggs": "egg",
    "potato": "potato", "potatoes": "potato",
    "bean": "bean", "beans": "bean",
    "pea": "pea", "peas": "pea",
    "carrot": "carrot", "carrots": "carrot",
    "garlic": "garlic", "garlics": "garlic",
    "pepper": "pepper", "peppers": "pepper",
    "cabbage": "cabbage", "cabbages": "cabbage",
    "spinach": "spinach",
    "kale": "kale",
    "corn": "corn",
    "maize": "maize",
    "rice": "rice",
    # Proteins
    "beef": "beef",
    "chicken": "chicken",
    "fish": "fish",
    "meat": "meat",
    "lentil": "lentil", "lentils": "lentil",
    # Dairy & Staples
    "milk": "milk",
    "butter": "butter",
    "cheese": "cheese",
    "flour": "flour",
    "sugar": "sugar",
    "salt": "salt",
    "oil": "oil",
    "water": "water",
    # Other
    "greens": "greens",
    "chapati": "chapati",
    "pilau masala": "pilau masala",
    "coconut milk": "coconut milk",
    "soy sauce": "soy sauce",
    "lemon": "lemon",
    "lemons": "lemon",
}


def _normalize_ingredient_form(ingredient: str) -> str:
    """
    Normalize ingredient names to singular form for consistent matching.
    
    Examples:
    - "onions" → "onion"
    - "tomatoes" → "tomato"
    - "eggs" → "egg"
    
    Args:
        ingredient: Raw ingredient name
        
    Returns:
        Normalized ingredient name
    """
    ingredient_lower = ingredient.lower().strip()
    
    # Remove punctuation
    ingredient_lower = re.sub(r'[^\w\s]', '', ingredient_lower).strip()
    
    # Check mapping first
    if ingredient_lower in SINGULAR_PLURAL_MAPPING:
        return SINGULAR_PLURAL_MAPPING[ingredient_lower]
    
    # Fallback: return as-is
    return ingredient_lower


def _normalize_library_ingredients(ingredients_list: List[str]) -> Set[str]:
    """
    Normalize a list of ingredients for consistent matching.
    
    Args:
        ingredients_list: List of ingredient names
        
    Returns:
        Set of normalized ingredient names
    """
    return set(_normalize_ingredient_form(ing) for ing in ingredients_list)


def _calculate_recipe_match_score(
    user_ingredients: Set[str],
    recipe_ingredients: Set[str]
) -> float:
    """
    Calculate match score: matched_ingredients / recipe_ingredients
    
    Score represents the portion of recipe ingredients that the user has.
    Score >= 0.5 is considered valid (50% threshold).
    
    Args:
        user_ingredients: Normalized user ingredients
        recipe_ingredients: Normalized recipe ingredients
        
    Returns:
        Match score (0.0 to 1.0)
    """
    if not recipe_ingredients:
        return 0.0
    
    matched = user_ingredients.intersection(recipe_ingredients)
    return len(matched) / len(recipe_ingredients)


def _search_east_african_library(
    user_ingredients: Set[str],
    min_coverage: float = 0.33,
    top_n: int = 3,
    user_ingredients_original: Optional[Set[str]] = None,
    primary_ingredient: Optional[str] = None,
    debug_log: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Search EAST_AFRICAN_RECIPE_LIBRARY using flexible matching logic.
    
    Prioritizes recipes where user has the CORE ingredients.
    Filters recipes with match_score >= min_coverage (33% by default for leniency).
    Returns up to top_n recipes, sorted by coverage and core ingredient match (highest first).
    
    Uses both normalized and fuzzy matching for robustness.
    
    Args:
        user_ingredients: Normalized user ingredients
        min_coverage: Minimum match score threshold (default 0.5 = 50%)
        top_n: Maximum number of recipes to return
        user_ingredients_original: Optional original (non-normalized) ingredients to try
        debug_log: Optional list to append debug messages to
        
    Returns:
        List of matching recipe dicts, sorted by core ingredient match + coverage
    """
    if debug_log is None:
        debug_log = []
    
    matches = []
    
    # Combine both ingredient sets for more flexible matching
    all_user_ingredients = user_ingredients.copy()
    if user_ingredients_original:
        all_user_ingredients.update(user_ingredients_original)
    
    debug_log.append(f"[Library] Searching recipes with user ingredients: {sorted(list(user_ingredients))}")
    
    for recipe in EAST_AFRICAN_RECIPE_LIBRARY:
        # Normalize recipe ingredients
        recipe_ingredients = _normalize_library_ingredients(recipe["ingredients"])
        
        # PRIORITIZE: Check if user has the core ingredients
        recipe_core = _normalize_library_ingredients(recipe.get("core", []))
        core_matched = user_ingredients.intersection(recipe_core)
        core_match_score = len(core_matched) / len(recipe_core) if recipe_core else 0
        
        # Calculate match score with normalized user ingredients
        score = _calculate_recipe_match_score(user_ingredients, recipe_ingredients)
        best_score = score
        best_matched = user_ingredients.intersection(recipe_ingredients)
        
        # If normalized doesn't work well, try with combined set
        if best_score < min_coverage and user_ingredients_original:
            score_combined = _calculate_recipe_match_score(
                all_user_ingredients, recipe_ingredients
            )
            if score_combined > best_score:
                best_score = score_combined
                best_matched = all_user_ingredients.intersection(recipe_ingredients)
        
        # Also try fuzzy matching as a fallback for better coverage
        if best_score < min_coverage:
            matched_fuzzy = set()
            for user_ing in all_user_ingredients:
                for recipe_ing in recipe_ingredients:
                    # Check for exact substring match (case-insensitive)
                    if (user_ing.lower() in recipe_ing.lower() or 
                        recipe_ing.lower() in user_ing.lower()):
                        matched_fuzzy.add(recipe_ing)
                        break
            
            if matched_fuzzy:
                fuzzy_score = len(matched_fuzzy) / len(recipe_ingredients)
                if fuzzy_score > best_score:
                    best_score = fuzzy_score
                    best_matched = matched_fuzzy
        
        # Only include recipes meeting minimum coverage threshold
        if best_score < min_coverage:
            continue

        # Enforce primary ingredient if requested
        if primary_ingredient and primary_ingredient not in recipe_ingredients:
            continue

        # Find all missing ingredients
        missing = recipe_ingredients - best_matched
        
        # Build result dict in same format as CSV recipes
        recipe_result = {
            "recipe_id": hash(recipe["name"]) & 0x7fffffff,  # Generate consistent ID
            "meal_name": recipe["name"],
            "cuisine_region": recipe["region"],
            "coverage": best_score,
            "core_match_score": core_match_score,  # NEW: track core ingredient match
            "matched": best_matched,
            "missing": missing,
            "missing_with_sub": set(),  # East African lib doesn't have substitutes
            "missing_without_sub": missing,
            "cook_time_minutes": recipe.get("cook_time", 30),
            "score": best_score * 10,  # For sorting compatibility
        }
        
        matches.append(recipe_result)
        debug_log.append(f"  → {recipe['name']}: coverage={best_score:.1%}, core_match={core_match_score:.1%}, matched={sorted(list(best_matched))}")
    
    # Sort by: (1) core ingredient match (descending), (2) coverage (descending), (3) name
    matches.sort(key=lambda x: (-x["core_match_score"], -x["coverage"], x["meal_name"]))
    
    debug_log.append(f"[Library] Returning top {min(len(matches), top_n)} recipes")
    
    return matches[:top_n]


def _is_weak_result(
    csv_results: List[Dict[str, Any]],
    user_ingredients: Optional[Set[str]] = None,
    min_coverage_per_recipe: float = 0.5,
    min_recipe_count: int = 3
) -> bool:
    """
    Determine if CSV recipe results are weak.
    
    A result is weak if:
    - Fewer than min_recipe_count recipes found (default 3), OR
    - All recipes have coverage < 50% (poor ingredient match quality), OR
    - User provided multiple ingredients (3+) but no recipe matches multiple ingredients
    
    This helps catch cases like:
    - Query: "beef, rice, onions" (3 ingredients)
    - CSV results: single-ingredient matches (beef only, rice only, onions only)
    → These are weak, prefer library with multi-ingredient recipes
    
    Args:
        csv_results: List of ranked CSV recipe results
        user_ingredients: Set of user ingredients (optional, for multi-ingredient check)
        min_coverage_per_recipe: Minimum individual recipe coverage threshold (used for safety)
        min_recipe_count: Minimum number of recipes threshold (default 3)
        
    Returns:
        True if results are weak, False if strong
    """
    # If we don't have enough recipes, it's weak
    if len(csv_results) < min_recipe_count:
        return True
    
    # Check average and max coverage
    avg_coverage = sum(r.get("coverage", 0) for r in csv_results) / len(csv_results)
    max_coverage = max(r.get("coverage", 0) for r in csv_results)
    
    # Weak if: average coverage is poor AND max coverage is only mediocre
    if avg_coverage < 0.5 and max_coverage < 0.75:
        return True
    
    # For multi-ingredient queries (3+ ingredients), check if recipes match multiple ingredients
    if user_ingredients and len(user_ingredients) >= 3:
        # Check if ANY recipe matches 2+ ingredients
        has_multi_ingredient_match = False
        for result in csv_results:
            matched = result.get("matched", set())
            if len(matched) >= 2:
                has_multi_ingredient_match = True
                break
        
        # If user provided 3+ ingredients but no recipe matches 2+ of them, it's weak
        if not has_multi_ingredient_match:
            return True
    
    return False


def _generate_recipes_with_groq_fallback(
    user_ingredients: Set[str],
    user_ingredients_list: List[str],
    language: str = "en"
) -> List[Dict[str, Any]]:
    """
    Generate recipes using Groq when both CSV and East African library fail.
    
    Creates realistic meal suggestions based on user's ingredients,
    avoiding hallucinated dishes and prioritizing East African recipes.
    
    Args:
        user_ingredients: Set of normalized user ingredients
        user_ingredients_list: Original list of user ingredients for display
        language: 'en' or 'sw'
        
    Returns:
        List of generated recipe dicts (up to 3)
    """
    if _groq_client is None:
        # Return empty list if Groq unavailable
        return []
    
    # Build prompt
    ingredients_str = ", ".join(list(user_ingredients_list)[:10])
    
    if language == "sw":
        prompt = f"""Wewe ni msaidizi wa kupika Kiafrika. 
Tafadhali pendekeza vyakula 3 vya kweli vinavyotumia viungo hivi: {ingredients_str}

Maelezo:
- Tumia vyakula halisi tu (si vya kufanya)
- Pendekeza vyakula vya Kenyan au East African kama iwezekanavyo
- Format: "1. Dish Name – region"
- Tisaini vyakula kamili (mapishi yanayokamatia)

Output:
1. Dish Name – region
2. Dish Name – region
3. Dish Name – region"""
    else:
        prompt = f"""You are an African cooking assistant. 
Suggest 3 realistic meals using these ingredients: {ingredients_str}

Instructions:
- Use only REAL dishes (not made-up)
- Prefer Kenyan or East African dishes when possible
- Format as: "1. Dish Name – region"
- Return only dish names and regions (no full recipes)

Output:
1. Dish Name – region
2. Dish Name – region
3. Dish Name – region"""
    
    try:
        completion = _groq_client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7
        )
        
        response_text = completion.choices[0].message.content
        
        # Parse the response
        results = []
        lines = response_text.strip().split('\n')
        
        for line in lines:
            # Extract "Dish Name – region" format
            line = line.strip()
            if not line or not any(c.isalpha() for c in line):
                continue
            
            # Remove leading number and period
            line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            
            # Split by em-dash, en-dash, or hyphen
            parts = re.split(r'\s*–\s*|\s*-\s*', line)
            
            if len(parts) >= 2:
                dish_name = parts[0].strip()
                region = parts[1].strip().lower()
            else:
                dish_name = line
                region = "international"
            
            if dish_name:
                results.append({
                    "recipe_id": hash(dish_name) & 0x7fffffff,
                    "meal_name": dish_name,
                    "cuisine_region": region,
                    "coverage": 0.5,  # Groq-generated recipes get neutral score
                    "matched": set(),
                    "missing": set(user_ingredients),
                    "missing_with_sub": set(),
                    "missing_without_sub": set(user_ingredients),
                    "cook_time_minutes": 30,
                    "is_groq_generated": True,
                    "score": 3.0
                })
        
        return results[:3]
    
    except Exception:
        # If Groq generation fails, return empty list
        return []


# ============================================================================
# IMPROVED INGREDIENT-BASED RECOMMENDATION ALGORITHM
# ============================================================================

def recommend_recipes_by_ingredients(
    user_ingredients: List[str],
    recipes_df: pd.DataFrame,
    top_n: int = 3,
    cuisine_priority: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Recommend recipes based on intelligent ingredient matching.
    
    Scoring algorithm:
    1. Score each recipe by ingredient overlap:
       - Main ingredients (first 3 user ingredients) = +3 points each
       - Additional ingredients = +1 point each
    2. Filter out recipes with 0 matching ingredients
    3. Apply cuisine priority bonus
    4. Sort by total score (descending)
    5. Return top N recipes
    
    Args:
        user_ingredients: List of user ingredients (normalized)
        recipes_df: Recipe dataframe
        top_n: Number of recipes to return (default 3)
        cuisine_priority: Optional dict mapping cuisine -> priority score
                         Example: {"kenya": 5, "east_africa": 4, ...}
    
    Returns:
        List of top N recipe dicts with scores, sorted by title and cuisine
    """
    
    # Default cuisine priority if not provided
    if cuisine_priority is None:
        cuisine_priority = {
            "kenya": 5,
            "kenyan": 5,
            "east africa": 4,
            "east_africa": 4,
            "eastern africa": 4,
            "tanzania": 3,
            "tanzanian": 3,
            "uganda": 2,
            "ugandan": 2,
        }
    
    scored_recipes = []
    
    # Iterate through all recipes and score them
    for idx, row in recipes_df.iterrows():
        recipe_id = row.get("recipe_id", idx)
        recipe_name = row.get("meal_name", "")
        cuisine = row.get("cuisine_region", "")
        ingredients_str = row.get("core_ingredients", "")
        
        # Extract and normalize recipe ingredients
        recipe_ingredients = []
        if isinstance(ingredients_str, str):
            # Split by comma and clean
            recipe_ingredients = [
                ing.strip().lower() for ing in ingredients_str.split(",")
                if ing.strip()
            ]
        
        # Score by ingredient matching
        ingredient_score = 0
        matched_ingredients = []
        
        # Main ingredients (first 3 user ingredients) worth 3 points each
        for idx_user, user_ing in enumerate(user_ingredients[:3]):
            user_ing_norm = user_ing.lower().strip()
            for recipe_ing in recipe_ingredients:
                recipe_ing_norm = recipe_ing.lower().strip()
                # Check for exact match or substring match
                if user_ing_norm in recipe_ing_norm or user_ing_norm == recipe_ing_norm:
                    ingredient_score += 3
                    matched_ingredients.append(user_ing)
                    break
        
        # Additional ingredients worth 1 point each
        for user_ing in user_ingredients[3:]:
            user_ing_norm = user_ing.lower().strip()
            for recipe_ing in recipe_ingredients:
                recipe_ing_norm = recipe_ing.lower().strip()
                if user_ing_norm in recipe_ing_norm or user_ing_norm == recipe_ing_norm:
                    ingredient_score += 1
                    matched_ingredients.append(user_ing)
                    break
        
        # Skip recipes with no matching ingredients
        if ingredient_score == 0:
            continue
        
        # Apply cuisine priority bonus
        cuisine_bonus = 0
        if cuisine:
            cuisine_lower = cuisine.lower().strip()
            # Direct lookup
            if cuisine_lower in cuisine_priority:
                cuisine_bonus = cuisine_priority[cuisine_lower]
            else:
                # Partial matching
                for cuisine_key, priority in cuisine_priority.items():
                    if cuisine_key in cuisine_lower or cuisine_lower in cuisine_key:
                        cuisine_bonus = priority
                        break
                # Default for African cuisines
                if "africa" in cuisine_lower:
                    cuisine_bonus = 1
        
        total_score = ingredient_score + cuisine_bonus
        
        # Build recipe dict
        recipe_dict = {
            "recipe_id": recipe_id,
            "meal_name": recipe_name,
            "cuisine_region": cuisine,
            "ingredients_str": ingredients_str,
            "ingredient_score": ingredient_score,
            "cuisine_bonus": cuisine_bonus,
            "total_score": total_score,
            "matched_ingredients": list(set(matched_ingredients)),
            "core_ingredients": row.get("core_ingredients", ""),
            "recipes": row.get("recipes", ""),
            "cook_time_minutes": row.get("cook_time_minutes", 0),
            "notes": row.get("notes", ""),
        }
        
        scored_recipes.append(recipe_dict)
    
    # Sort by total score (descending), then by cuisine priority (descending)
    scored_recipes.sort(
        key=lambda x: (-x["total_score"], -x["cuisine_bonus"], x["meal_name"])
    )
    
    # Return top N recipes
    return scored_recipes[:top_n]


def _score_recipe(recipe_id: int, user_ingredients: Set[str]) -> Dict[str, Any]:
    """
    Score a single recipe against user ingredients.
    
    Returns matched, missing (with/without substitutes), and coverage.
    
    Args:
        recipe_id: Recipe index
        user_ingredients: Normalized user ingredients
        
    Returns:
        Dict with recipe_id, coverage, matched, missing, missing_with_sub, missing_without_sub
    """
    recipe_ingredients = recipe_ingredient_map[recipe_id]
    substitutes = recipe_substitute_map.get(recipe_id, set())
    
    matched = recipe_ingredients & user_ingredients
    missing = recipe_ingredients - user_ingredients
    
    missing_with_sub = set()
    missing_without_sub = set()
    
    for m in missing:
        if _is_substitutable(m, substitutes, Config.SUBSTITUTION_THRESHOLD):
            missing_with_sub.add(m)
        else:
            missing_without_sub.add(m)
    
    coverage = len(matched) / len(recipe_ingredients) if recipe_ingredients else 0.0
    
    return {
        "recipe_id": recipe_id,
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "missing_with_sub": missing_with_sub,
        "missing_without_sub": missing_without_sub
    }


def rank_recipes(
    user_ingredients: Set[str],
    recipes_df: pd.DataFrame,
    time_limit: Optional[int] = None,
    top_k: int = 5,
    religious_rules: Optional[List[str]] = None,
    min_coverage: float = 0.5,
    primary_ingredient: Optional[str] = None,
    force_primary: bool = False,
    allow_alternatives: bool = False
) -> List[Dict[str, Any]]:
    """
    Score and rank recipes by ingredient coverage and time.

    Adds strong primary ingredient enforcement and user-list utilization prioritization.
    """
    scored = []

    if not user_ingredients:
        return []

    for rid in recipe_ingredient_map.keys():
        meta = recipes_df.loc[recipes_df["recipe_id"] == rid].iloc[0]
        cook_minutes = meta["cook_time_minutes"]
        recipe_name = meta["meal_name"]
        recipe_text = meta.get("recipes", "")

        # Check religious rules
        if religious_rules and _recipe_has_forbidden_ingredient(recipe_name, recipe_text, religious_rules):
            continue

        # Time filter
        if time_limit is not None and cook_minutes > time_limit:
            continue

        # Score recipe
        score_dict = _score_recipe(rid, user_ingredients)
        score_dict["cook_time_minutes"] = cook_minutes
        score_dict["meal_name"] = recipe_name

        # Primary ingredient enforcement
        if primary_ingredient and not allow_alternatives:
            # Recipe must include primary ingredient directly in its ingredients
            recipe_ings = recipe_ingredient_map.get(rid, set())
            normalized_recipe_ings = set(_normalize_ingredient_form(ri) for ri in recipe_ings)
            if primary_ingredient not in normalized_recipe_ings:
                continue

        # CRITICAL FILTERING: Only include recipes with sufficient coverage
        if score_dict["coverage"] < min_coverage:
            continue

        # Calculate user list utilization ratio
        user_util_ratio = len(score_dict["matched"]) / len(user_ingredients)
        score_dict["user_util_ratio"] = user_util_ratio

        # Keep track of match quality for preference
        score_dict["primary_match"] = (
            primary_ingredient in score_dict["matched"] if primary_ingredient else False
        )

        scored.append(score_dict)

    # Sort using hierarchy: primary match, user utilization, coverage, fewer missing non-substitutable, cook time
    ranked = sorted(
        scored,
        key=lambda x: (
            -int(x.get("primary_match", False)),
            -x.get("user_util_ratio", 0),
            -x["coverage"],
            len(x["missing_without_sub"]),
            x["cook_time_minutes"]
        )
    )

    # Ensure we return at most top_k
    return ranked[:top_k]


# ============================================================================
# HEALTH CONSTRAINT EXTRACTION
# ============================================================================

def extract_health_constraints(text: str) -> List[str]:
    """
    Extract health constraints/diet restrictions from query text.
    
    Detects mentions of:
    - Diabetes
    - Anti-inflammatory conditions
    - DASH diet
    - Low FODMAP
    - Other common health concerns
    
    Args:
        text: User query text
        
    Returns:
        List of detected constraints (lowercase)
    """
    text_lower = text.lower()
    constraints = []
    
    # Diabetes keywords
    if any(word in text_lower for word in ['diabetes', 'diabetic', 'blood sugar', 'glucose']):
        constraints.append('diabetes')
    
    # Anti-inflammatory keywords
    if any(word in text_lower for word in ['anti-inflammatory', 'inflammation', 'inflammatory', 'inflame', 'arthritis']):
        constraints.append('anti_inflammatory')
    
    # DASH diet keywords
    if any(word in text_lower for word in ['dash diet', 'blood pressure', 'hypertension', 'low sodium']):
        constraints.append('dash')
    
    # Low FODMAP keywords
    if any(word in text_lower for word in ['low fodmap', 'fodmap', 'ibs', 'irritable bowel', 'digestive']):
        constraints.append('low_fodmap')
    
    # Pregnancy keywords
    if any(word in text_lower for word in ['pregnant', 'pregnancy']):
        constraints.append('pregnancy')
    
    # Vegan/Vegetarian keywords
    if any(word in text_lower for word in ['vegan', 'vegetarian', 'no meat', 'no fish']):
        constraints.append('vegan' if 'vegan' in text_lower else 'vegetarian')
    
    # Gluten-free keywords
    if any(word in text_lower for word in ['gluten-free', 'gluten free', 'celiac', 'coeliac']):
        constraints.append('gluten_free')
    
    # Dairy-free keywords
    if any(word in text_lower for word in ['dairy-free', 'dairy free', 'lactose intolerant', 'lactose-free']):
        constraints.append('dairy_free')
    
    return list(set(constraints))  # Remove duplicates


# ============================================================================
# RELIGIOUS & DIETARY RULE EXTRACTION
# ============================================================================

def extract_religious_constraints(text: str) -> List[str]:
    """
    Extract religious/dietary rules from query text.
    
    Detects mentions of:
    - Halal
    - Kosher
    - No pork
    - No beef
    - No shellfish
    
    Args:
        text: User query text
        
    Returns:
        List of detected rules (lowercase)
    """
    text_lower = text.lower()
    rules = []
    
    # Halal keywords
    if any(word in text_lower for word in ['halal', 'muslim', 'islam']):
        rules.append('halal')
    
    # No pork keywords
    if any(word in text_lower for word in ['no pork', 'without pork', 'pork', '!pork']):
        rules.append('no_pork')
    
    # No beef keywords
    if any(word in text_lower for word in ['no beef', 'without beef', 'vegetarian'] ):
        rules.append('no_beef')
    
    # No shellfish keywords
    if any(word in text_lower for word in ['no shellfish', 'no shrimp', 'no prawn']):
        rules.append('no_shellfish')
    
    # Kosher keywords
    if any(word in text_lower for word in ['kosher', 'jewish']):
        rules.append('kosher')
    
    return list(set(rules))  # Remove duplicates


def _recipe_has_forbidden_ingredient(recipe_name: str, recipe_text: str, religious_rules: List[str]) -> bool:
    """
    Check if recipe contains forbidden ingredients based on religious rules.
    
    Args:
        recipe_name: Recipe name
        recipe_text: Full recipe text
        religious_rules: List of rules (halal, no_pork, etc.)
        
    Returns:
        True if recipe violates any rules, False otherwise
    """
    if not religious_rules:
        return False
    
    text_full = (recipe_name + " " + recipe_text).lower()
    
    forbidden_patterns = {
        'no_pork': ['pork', 'pig', 'bacon', 'ham'],
        'no_beef': ['beef', 'cow'],
        'no_shellfish': ['shrimp', 'prawn', 'mussel', 'clam'],
        'halal': [],  # Assumes all recipes are halal unless explicitly marked otherwise
    }
    
    for rule in religious_rules:
        forbidden_words = forbidden_patterns.get(rule, [])
        for word in forbidden_words:
            if word in text_full:
                return True
    
    return False


# ============================================================================
# MAIN PIPELINE: RUN JEMA MODEL
# ============================================================================

def run_jema_model(
    user_text: str,
    recipes_df: pd.DataFrame,
    top_k: int = 5,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Main recipe recommendation pipeline with three-level fallback.
    
    SYSTEM PIPELINE:
    1. User provides ingredients
    2. CSV recipe search (rank_recipes with 50% coverage threshold)
    3. If weak results → search EAST_AFRICAN_RECIPE_LIBRARY
    4. If still weak → use Groq to generate realistic recipes
    
    WEAK RESULT DEFINITION:
    - Fewer than 3 matching recipes found
    - OR no recipe meets >= 50% ingredient coverage
    
    Args:
        user_text: User query (e.g., "I have tomatoes, onions and 30 minutes")
        recipes_df: Recipe dataframe (should be recipes_features_df)
        top_k: Number of results to return
        debug: If True, include detailed debug info in response
        
    Returns:
        Dict with language, user_ingredients, results, pipeline_source, and optionally debug info
    """
    # Initialize debug log
    debug_log = [] if debug else None
    
    def log_debug(msg: str):
        if debug and debug_log is not None:
            debug_log.append(msg)
            print(f"[DEBUG] {msg}")
    
    # Detect language
    language = detect_language(user_text)
    log_debug(f"Language detected: {language}")
    
    # Extract user ingredients - returns normalized set
    user_ingredients = extract_user_ingredients(user_text)
    log_debug(f"Extracted user ingredients: {sorted(list(user_ingredients))}")

    # Normalize for library search (handle plurals, punctuation)
    user_ingredients_normalized = set(
        _normalize_ingredient_form(ing) for ing in user_ingredients
    )
    log_debug(f"Normalized user ingredients: {sorted(list(user_ingredients_normalized))}")

    # Infer key constraints for recommendations
    primary_ingredient = _infer_primary_ingredient(user_ingredients_normalized, user_text)
    leafy_green = _detect_leafy_green(user_ingredients_normalized)
    allow_alternatives = _asked_for_alternatives(user_text)

    log_debug(f"Primary ingredient: {primary_ingredient}")
    log_debug(f"Leafy green: {leafy_green}")
    log_debug(f"Allow alternatives: {allow_alternatives}")

    # Extract time limit
    time_limit = extract_time_limit(user_text)
    log_debug(f"Time limit: {time_limit} minutes")
    
    # Extract religious constraints
    religious_rules = extract_religious_constraints(user_text)
    log_debug(f"Religious constraints: {religious_rules if religious_rules else 'None'}")
    
    # ========================================================================
    # STEP 1: Try CSV Recipe Search
    # ========================================================================
    log_debug("=" * 60)
    log_debug("STEP 1: CSV Recipe Search")
    log_debug("=" * 60)
    
    ranked = rank_recipes(
        user_ingredients,
        recipes_df,
        time_limit=time_limit,
        top_k=top_k,
        religious_rules=religious_rules if religious_rules else None,
        min_coverage=0.5,
        primary_ingredient=primary_ingredient,
        force_primary=bool(primary_ingredient and not allow_alternatives),
        allow_alternatives=allow_alternatives
    )
    
    log_debug(f"CSV returned {len(ranked)} recipes")
    if ranked:
        for idx, recipe in enumerate(ranked, 1):
            log_debug(f"  {idx}. {recipe['meal_name']} (coverage: {recipe['coverage']:.2%}, matched: {sorted(list(recipe['matched']))})")
    else:
        log_debug(f"  (no CSV recipes found)")
    
    pipeline_source = "csv"
    
    # ========================================================================
    # STEP 1: Check if CSV results are sufficient (>= 3 recipes)
    # ========================================================================
    is_csv_weak = _is_weak_result(ranked, user_ingredients=user_ingredients, min_recipe_count=3)
    log_debug(f"CSV results weak? {is_csv_weak} (need >= 3 recipes with good quality, got {len(ranked)})")
    
    if is_csv_weak:
        # CSV has fewer than 3 recipes → proceed to Step 2
        
        # ====================================================================
        # STEP 2: Search EAST_AFRICAN_RECIPE_LIBRARY with normalized ingredients
        # ====================================================================
        log_debug("=" * 60)
        log_debug("STEP 2: East African Recipe Library Search")
        log_debug("=" * 60)
        
        library_results = _search_east_african_library(
            user_ingredients_normalized,
            min_coverage=0.33,  # Lenient threshold for library (33% vs CSV's 50%)
            top_n=top_k,
            user_ingredients_original=user_ingredients,  # Also try original for robustness
            primary_ingredient=primary_ingredient,
            debug_log=debug_log  # Pass debug log to see matching details
        )
        
        log_debug(f"Library returned {len(library_results)} recipes")
        for idx, recipe in enumerate(library_results, 1):
            log_debug(f"  {idx}. {recipe['meal_name']} (core_match={recipe.get('core_match_score', 0):.1%}, coverage={recipe['coverage']:.2%}, matched={sorted(list(recipe['matched']))})")
        
        # If library has any results (1 or more), use them instead of Groq
        if library_results:
            ranked = library_results
            pipeline_source = "east_african_library"
            log_debug(f"✓ Using East African library results (pipeline_source = '{pipeline_source}')")
        else:
            # ================================================================
            # STEP 3: Library also returned nothing → use Groq as final fallback
            # ================================================================
            log_debug("=" * 60)
            log_debug("STEP 3: Groq Fallback (Library returned nothing)")
            log_debug("=" * 60)
            
            groq_results = _generate_recipes_with_groq_fallback(
                user_ingredients_normalized,
                list(user_ingredients),
                language=language
            )
            
            log_debug(f"Groq returned {len(groq_results)} recipes")
            for idx, recipe in enumerate(groq_results, 1):
                log_debug(f"  {idx}. {recipe['meal_name']}")
            
            if groq_results:
                ranked = groq_results
                pipeline_source = "groq_generated"
                log_debug(f"✓ Using Groq results (pipeline_source = '{pipeline_source}')")
            else:
                # Final fallback: return CSV results even if weak
                pipeline_source = "csv_weak_results"
                log_debug(f"✗ Groq failed, returning weak CSV results (pipeline_source = '{pipeline_source}')")
    else:
        log_debug(f"✓ CSV has {len(ranked)} recipes (>= 3), using them (pipeline_source = '{pipeline_source}')")
    
    # Format results with deduplication
    results = []
    seen_names = set()
    user_ingredients_list = list(user_ingredients)
    
    for r in ranked:
        recipe_name = r["meal_name"]
        recipe_id = r["recipe_id"]
        
        # Skip if we've already added this recipe name
        if recipe_name in seen_names:
            continue
        
        seen_names.add(recipe_name)
        
        # Try to get full recipe details from CSV
        recipe_row_data = recipes_df[recipes_df["recipe_id"] == recipe_id]
        
        if not recipe_row_data.empty:
            recipe_row = recipe_row_data.iloc[0]
            cuisine_region = recipe_row.get("cuisine_region", r.get("cuisine_region", ""))
            raw_steps = recipe_row.get("recipes", "")
            cook_time = recipe_row.get("cook_time_minutes", r.get("cook_time_minutes", 30))
            
            # Convert to step list
            if isinstance(raw_steps, str) and len(raw_steps) > 0:
                step_list = [
                    s.strip() for s in re.split(r"[.\n]", raw_steps)
                    if len(s.strip()) > 3
                ]
            else:
                step_list = []
            
            # Expand steps if too short
            step_list = expand_recipe_steps(recipe_name, step_list)
        else:
            # Recipe not in CSV (Groq-generated or library)
            cuisine_region = r.get("cuisine_region", "")
            cook_time = r.get("cook_time_minutes", 30)
            step_list = []
        
        # Convert sets to sorted lists for JSON serialization
        matched = sorted(list(r.get("matched", set())))
        missing = sorted(list(r.get("missing", set())))
        missing_with_sub = sorted(list(r.get("missing_with_sub", set())))
        missing_without_sub = sorted(list(r.get("missing_without_sub", set())))
        
        results.append({
            "recipe_id": recipe_id,
            "meal_name": recipe_name,
            "cuisine_region": cuisine_region,
            "coverage": r.get("coverage", 0.5),
            "matched": matched,
            "missing": missing,
            "missing_with_sub": missing_with_sub,
            "missing_without_sub": missing_without_sub,
            "cook_time_minutes": cook_time,
            "recipe_steps": step_list,
            "is_groq_generated": r.get("is_groq_generated", False)
        })
    
    # Build structured recipe recommendations (dish_name/origin)
    structured_recommendations = _generate_structured_recommendations(
        results,
        user_ingredients,
        primary_ingredient=primary_ingredient,
        leafy_green=leafy_green
    )

    # Build conversational message text for UI friendliness
    if results:
        suggestion_lines = [f"{i+1}. {r['meal_name']}" for i, r in enumerate(results[:3])]
        conversation_text = (
            f"Hey there, you could try one of the following:\n" +
            "\n".join(suggestion_lines) +
            "\nWhich one would you like?"
        )
    else:
        conversation_text = "I couldn't find a recipe with those ingredients. Can you add or change one ingredient?"

    result = {
        "language": language,
        "user_ingredients": sorted(user_ingredients_list),
        "pipeline_source": pipeline_source,
        "results": results,
        "structured_recommendations": structured_recommendations,
        "conversation_text": conversation_text
    }
    
    # Add debug info if requested
    if debug and debug_log:
        result["debug"] = debug_log
    
    return result


# ============================================================================
# GROQ LLM INTEGRATION
# ============================================================================

def _build_groq_prompt(
    recipe_row: pd.Series,
    match_info: Dict[str, Any],
    language: str,
    persona: Optional[str] = None,
    health_constraints: Optional[List[str]] = None
) -> str:
    """
    Build rich prompt for Groq LLM with persona and health awareness.
    
    Args:
        recipe_row: Recipe data from dataframe
        match_info: Dict with matched/missing ingredients
        language: 'en' or 'sw'
        persona: Optional persona (dada/kaka/mama/baba)
        health_constraints: Optional list of health constraints (diabetes, anti_inflammatory, etc.)
    """
    matched_str = ", ".join(match_info.get("matched", []))
    missing_str = ", ".join(match_info.get("missing", []))
    missing_sub_str = ", ".join(match_info.get("missing_with_sub", []))
    
    # Persona instructions with enhanced detail
    persona_instructions = {
        "dada": (
            "You are a friendly cooking advisor for a budget-conscious student. "
            "Be encouraging, practical, and show how to make meals affordable and quick. "
            "Suggest ingredient substitutions to save money."
        ),
        "kaka": (
            "You are a quick cooking advisor for a busy professional. "
            "Be direct, efficient, and emphasize speed and convenience. "
            "Focus on time-saving cooking tips."
        ),
        "mama": (
            "You are an enthusiastic food explorer advisor. "
            "Be adventurous, highlight flavor profiles and variety, encourage trying new ingredients. "
            "Suggest modifications to enhance taste."
        ),
        "baba": (
            "You are a health-focused nutrition advisor. "
            "Be informative, highlight nutritional benefits and health impacts, "
            "and suggest balanced meal strategies."
        )
    }
    
    persona_instruction = persona_instructions.get(
        persona,
        "You are a helpful, warm cooking advisor."
    )
    
    # Health constraint context
    health_context = ""
    if health_constraints and len(health_constraints) > 0:
        constraint_str = ", ".join(health_constraints)
        if language == "sw":
            health_context = f"\nVyakula vya mtu anayeyekuwa: {constraint_str}"
        else:
            health_context = f"\nHealth context: {constraint_str}"
    
    if language == "sw":
        return f"""
{persona_instruction}

Jina la chakula: {recipe_row['meal_name']}
Muda wa kupika: {int(recipe_row['cook_time_minutes'])} dakika{health_context}

Viungo ulivyo navyo: {matched_str if matched_str else 'hamna'}
Viungo unavyokosa: {missing_str if missing_str else 'hamna'}
Viungo vinaweza kubadilishwa: {missing_sub_str if missing_sub_str else 'hamna'}

Tafadhali andika pendekezo la chakula katika Kiswahili (sentensi 2–3):
1. Eleza kwa nini chakula hiki ni chaguo zuri
2. Taja mbadala wa viungo ikiwa upo
3. Lenga mahitaji ya persona na afya
"""
    else:
        return f"""
{persona_instruction}

Recipe: {recipe_row['meal_name']}
Cooking time: {int(recipe_row['cook_time_minutes'])} minutes{health_context}

You have: {matched_str if matched_str else 'nothing on this list'}
Missing: {missing_str if missing_str else 'nothing'}
Can substitute: {missing_sub_str if missing_sub_str else 'nothing'}

Write a warm, brief recommendation (2–3 sentences):
1. Explain why this is a great choice for the user
2. Mention substitution options if any are available
3. Connect to the user's specific needs (persona + health goals)
"""


def _generate_groq_explanation_mock(
    recipe_row: pd.Series,
    match_info: Dict[str, Any],
    language: str = "en",
    persona: Optional[str] = None,
    health_constraints: Optional[List[str]] = None
) -> str:
    """Enhanced fallback mock explanation when Groq is unavailable."""
    matched = list(match_info.get("matched", []))
    missing = list(match_info.get("missing", []))
    
    # Better persona-aware explanations with health awareness
    if language == "sw":
        if persona == "baba":
            base = f"Karibu! {recipe_row['meal_name']} ni chaguo nzuri sana kwa afia"
        elif persona == "mama":
            base = f"Karibu! {recipe_row['meal_name']} ni chakula kizuri na kamili"
        elif persona == "dada":
            base = f"Karibu! {recipe_row['meal_name']} ni rahisi kufanya kwa bei nzuri"
        else:  # kaka or default
            base = f"Karibu! {recipe_row['meal_name']} ni haraka na mouthwatering"
        
        if matched:
            base += f" Una tayari: {', '.join(matched[:3])}."
        if missing:
            base += f" Lakini kosa: {', '.join(missing[:2])}."
        return base
    else:  # English
        if persona == "baba":
            base = f"{recipe_row['meal_name']} is a nutritious choice with excellent health benefits"
        elif persona == "mama":
            base = f"{recipe_row['meal_name']} is a delicious and balanced meal"
        elif persona == "dada":
            base = f"{recipe_row['meal_name']} is quick to make and budget-friendly"
        else:  # kaka or default
            base = f"{recipe_row['meal_name']} is fast to prepare and satisfying"
        
        if matched:
            base += f". You already have: {', '.join(matched[:3])}."
        if missing:
            base += f" You'll need: {', '.join(missing[:2])}."
        if health_constraints:
            constraint_text = ", ".join(health_constraints[:2])
            if persona == "baba":
                base += f" Great for {constraint_text}."
        return base


def _generate_groq_explanation(
    recipe_row: pd.Series,
    match_info: Dict[str, Any],
    language: str = "en",
    persona: Optional[str] = None,
    health_constraints: Optional[List[str]] = None
) -> str:
    """
    Generate natural language explanation using Groq LLM.
    Falls back to mock if Groq unavailable.
    
    Args:
        recipe_row: Recipe data
        match_info: Ingredient match information
        language: 'en' or 'sw'
        persona: Optional persona
        health_constraints: Optional health constraints
    """
    if _groq_client is None:
        return _generate_groq_explanation_mock(
            recipe_row, match_info, language, persona, health_constraints
        )
    
    try:
        prompt = _build_groq_prompt(
            recipe_row,
            match_info,
            language,
            persona,
            health_constraints=health_constraints
        )
        
        completion = _groq_client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300
        )
        
        return completion.choices[0].message.content
    except Exception:
        return _generate_groq_explanation_mock(
            recipe_row, match_info, language, persona, health_constraints
        )


def enrich_results_with_groq(
    jema_output: Dict[str, Any],
    recipes_df: pd.DataFrame,
    persona: Optional[str] = None,
    user_query: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enrich recipe results with Groq natural language explanations.
    
    Args:
        jema_output: Output from run_jema_model()
        recipes_df: Recipe dataframe
        persona: Optional persona filter (dada/kaka/mama/baba)
        user_query: Optional user query to extract health constraints from
        
    Returns:
        jema_output with 'groq_explanation' added to each result
    """
    language = jema_output["language"]
    
    # Extract health constraints from user query if provided
    health_constraints = extract_health_constraints(user_query) if user_query else []
    
    for result in jema_output["results"]:
        recipe_row = recipes_df[
            recipes_df["recipe_id"] == result["recipe_id"]
        ].iloc[0]
        
        explanation = _generate_groq_explanation(
            recipe_row,
            {
                "matched": result["matched"],
                "missing": result["missing"],
                "missing_with_sub": result["missing_with_sub"]
            },
            language=language,
            persona=persona,
            health_constraints=health_constraints if health_constraints else None
        )
        
        result["groq_explanation"] = explanation
    
    return jema_output


def generate_recipe_with_llm(recipe_name: str) -> Optional[List[str]]:
    """
    Generate a complete recipe using Groq LLM when recipe is not in dataset.
    
    Args:
        recipe_name: Name of the recipe to generate
        
    Returns:
        List of cooking steps (5-7 steps), or None if generation failed
    """
    if _groq_client is None:
        return None
    
    prompt = f"""
    You are an African cooking expert.

    Write a clear home-cooking recipe for:{recipe_name}

    Requirements:
    - 5 to 7 steps
    - Beginner friendly
    - Realistic home cooking
    - Include timing and cooking cues
    - Steps should be practical

    Format exactly like:

    1. Step
    2. Step
    3. Step

    Do NOT include introduction or ingredients.
    Return only the numbered steps.
    """
    
    try:
        completion = _groq_client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        
        response_text = completion.choices[0].message.content
        
        # Parse response into steps
        step_pattern = r'^\d+[\.\)]\s+(.+?)(?=^\d+[\.\)]|$)'
        matches = re.findall(step_pattern, response_text, re.MULTILINE | re.DOTALL)
        
        if matches:
            generated_steps = []
            for match in matches:
                step = match.strip()
                # Clean up step text
                step = re.sub(r'\n+', ' ', step).strip()
                if step and len(step) > 3:
                    # Ensure proper formatting
                    if not step.endswith(('.', '!', '?')):
                        step = step + '.'
                    generated_steps.append(step)
            
            # Return generated steps if we got a reasonable number
            if len(generated_steps) >= 5:
                return generated_steps
        
        return None
    
    except Exception:
        return None


def expand_recipe_steps(recipe_name: str, short_steps: List[str]) -> List[str]:
    """
    Expand short recipe instructions into clear, practical steps using Groq LLM.
    
    Creates 4-6 detailed steps suitable for home cooking (realistic and practical).
    Only expands when there are fewer than 3 steps.
    
    Args:
        recipe_name: Name of the recipe
        short_steps: List of short instruction steps
        
    Returns:
        List of expanded cooking steps (4-6 detailed steps), or original if already detailed
    """
    # If already has 3+ steps, return as-is (good starting point)
    if len(short_steps) >= 3:
        return short_steps
    
    # If completely empty, return original
    if not short_steps:
        return short_steps
    
    # Build prompt for expansion with practical home cooking focus
    steps_text = "\n".join([f"- {s}" for s in short_steps])
    
    prompt = f"""You are an experienced home cook teaching someone to prepare {recipe_name}.

Original instructions:
{steps_text}

**Create practical cooking steps** for a home cook:
- Provide exactly 4-6 clear, numbered steps
- Make steps realistic and time-appropriate for home cooking
- Include specific details: temperatures, cooking times, visual cues (brown, soft, etc.)
- Be beginner-friendly but detailed
- Each step should be 1-2 sentences
- Format as: "1. Step", "2. Step", etc.

Return ONLY the numbered steps. Start immediately with "1. " and do not include recipe title or ingredients."""

    # Try to use Groq client
    if _groq_client is None:
        # Return original steps if no LLM available
        return short_steps
    
    try:
        completion = _groq_client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        
        response_text = completion.choices[0].message.content
        
        # Parse response into steps
        # Extract numbered steps from response
        step_pattern = r'^\d+[\.\)]\s+(.+?)(?=^\d+[\.\)]|$)'
        matches = re.findall(step_pattern, response_text, re.MULTILINE | re.DOTALL)
        
        if matches:
            expanded_steps = []
            for match in matches:
                step = match.strip()
                # Clean up step text
                step = re.sub(r'\n+', ' ', step).strip()
                if step and len(step) > 3:
                    # Ensure proper formatting
                    if not step.endswith(('.', '!', '?')):
                        step = step + '.'
                    expanded_steps.append(step)
            
            # Return expanded steps if we got 4-6 detailed steps
            if 4 <= len(expanded_steps) <= 6:
                return expanded_steps
            elif len(expanded_steps) > 6:
                # If too many, take first 6 (most important steps)
                return expanded_steps[:6]
            elif len(expanded_steps) >= 3:
                # If 3, that's okay too
                return expanded_steps
        
        # If parsing failed, return original
        return short_steps
    
    except Exception:
        # On any error, return original steps
        return short_steps


# ============================================================================
# RAG: NUTRITION QUESTION ANSWERING
# ============================================================================

def _retrieve_context(user_query: str, top_k: int = 3) -> List[Dict[str, str]]:
    """
    Retrieve relevant nutrition documents using FAISS + TF-IDF.
    
    Args:
        user_query: Nutrition question
        top_k: Number of documents to retrieve
        
    Returns:
        List of relevant document dicts
    """
    if _faiss_index is None or _tfidf_vectorizer is None:
        return rag_documents[:top_k]
    
    try:
        # Encode query
        query_embedding = _tfidf_vectorizer.transform([user_query]).toarray().astype('float32')
        
        # Normalize
        query_norm = np.linalg.norm(query_embedding)
        if query_norm > 0:
            query_embedding = query_embedding / query_norm
        
        # Search FAISS index
        distances, indices = _faiss_index.search(query_embedding, min(top_k, len(rag_documents)))
        
        # Retrieve documents
        context_docs = []
        for idx in indices[0]:
            if 0 <= idx < len(rag_documents):
                context_docs.append(rag_documents[idx])
        
        return context_docs
    except Exception:
        return rag_documents[:top_k]


def _build_rag_prompt(
    user_query: str,
    context_docs: List[Dict[str, str]],
    language: str = "en"
) -> str:
    """Build RAG prompt with retrieved documents."""
    context_block = "\n\n".join(
        [f"- {d['text']}" for d in context_docs]
    )
    
    if language == "sw":
        return f"""
Wewe ni msaidizi wa lishe.

Tumia taarifa zifuatazo pekee kujibu swali.

Taarifa:
{context_block}

Swali:
{user_query}

Jibu kwa Kiswahili kwa ufupi na kwa vitendo.
"""
    else:
        return f"""
You are a nutrition assistant.

Use ONLY the information below to answer the question.

Context:
{context_block}

Question:
{user_query}

Give a short, practical answer.
"""


def answer_with_rag(
    user_query: str,
    language: str = "en"
) -> Dict[str, Any]:
    """
    Answer nutrition/diet question using RAG (retrieval-augmented generation).
    
    Args:
        user_query: Nutrition question (e.g., "Is this good for diabetes?")
        language: 'en' or 'sw'
        
    Returns:
        Dict with answer and context_docs
    """
    # Retrieve relevant documents
    context_docs = _retrieve_context(user_query, top_k=Config.RAG_TOP_K)
    
    # Build prompt
    prompt = _build_rag_prompt(user_query, context_docs, language=language)
    
    # If Groq unavailable, return mock answer
    if _groq_client is None:
        return {
            "answer": "I'm unable to process this query at the moment.",
            "context_docs": context_docs
        }
    
    try:
        # Call Groq LLM
        completion = _groq_client.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350
        )
        
        answer = completion.choices[0].message.content
    except Exception:
        answer = "I'm unable to process this query at the moment."
    
    return {
        "answer": answer,
        "context_docs": context_docs
    }


# ============================================================================
# INTEGRATED SYSTEM: RECIPE RECOMMENDATIONS + HEALTH CONTEXT + GROQ EXPLANATIONS
# ============================================================================

def _build_integrated_prompt(
    recommendations: List[Dict],
    health_context: List[Dict],
    language: str = "en",
    persona: Optional[str] = None
) -> str:
    """
    Build a unified prompt that grounds Groq's explanation in both:
    1. Ranked recipe recommendations (deterministic)
    2. Retrieved health/nutrition context (RAG)
    
    This prevents hallucination by ensuring Groq only references sourced information.
    """
    
    # Format recommendations
    if language == "sw":
        recommend_block = "Chakula Zilizoratibiwa:\n"
    else:
        recommend_block = "Recommended Recipes:\n"
    
    for i, recipe in enumerate(recommendations, 1):
        match_count = len(recipe.get("matched", []))
        total_ing = match_count + len(recipe.get("missing", []))
        coverage = (match_count / total_ing * 100) if total_ing > 0 else 0
        
        if language == "sw":
            recommend_block += f"  {i}. {recipe['meal_name']} ({int(coverage)}% umfani)\n"
        else:
            recommend_block += f"  {i}. {recipe['meal_name']} ({int(coverage)}% match)\n"
    
    # Format health context with source documentation
    if language == "sw":
        context_block = "Kumbukumbu za Afya:\n"
    else:
        context_block = "Health & Nutrition Context:\n"
    
    for i, doc in enumerate(health_context, 1):
        context_text = doc["text"][:150] + "..." if len(doc["text"]) > 150 else doc["text"]
        context_block += f"  {i}. {doc['id'].upper()}: {context_text}\n"
    
    # Build persona instruction
    persona_map = {
        "dada": "budget-conscious student" if language == "en" else "mwanafunzi anayependa kuokoa",
        "kaka": "busy professional" if language == "en" else "mjumbe mwenye haraka",
        "mama": "adventurous food explorer" if language == "en" else "mjumbe yenye majaribio",
        "baba": "health-conscious person" if language == "en" else "mjumbe anayefikiria afya"
    }
    
    persona_desc = persona_map.get(persona, "")
    persona_line = f"for a {persona_desc}" if language == "en" else f"kwa {persona_desc}"
    
    if language == "sw":
        prompt = f"""Wewe ni msaidizi mahususi wa kupika Kiafrika.

Umepokea maelezo yafuatayo:

{recommend_block}

{context_block}

Tafadhali andika hekima fupi (sentensi 2-3) kuhusu makundi haya {persona_line}:
1. Eleza kwa nini chakula hiki ni nzuri
2. Unganisha sehemu ya afya kutoka kwa muktadha
3. Sema ni vyakula gani vya kuanzia na kwa nini
"""
    else:
        prompt = f"""You are a specialized African cooking advisor.

You have received the following information:

{recommend_block}

{context_block}

Please write a brief, grounded recommendation (2-3 sentences) {persona_line}:
1. Explain why these recipes are a good fit
2. Connect the health context to the recommendations
3. Suggest which recipe to start with and why
"""
    
    return prompt


def answer_with_integrated_pipeline(
    user_query: str,
    language: Optional[str] = None,
    persona: Optional[str] = None,
    top_recipes: int = 2,
    top_contexts: int = 3,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Full integrated pipeline combining:
    1. Deterministic recipe recommendations
    2. Relevant health context retrieval (RAG)
    3. Grounded Groq explanations that reference both
    
    This ensures explanations are contextual and evidence-backed.
    
    Args:
        user_query: User's question or ingredient list
        language: 'en' or 'sw' (auto-detected if None)
        persona: 'dada', 'kaka', 'mama', 'baba' (optional)
        top_recipes: Number of recipe recommendations to include
        top_contexts: Number of health documents to retrieve
        debug: If True, include detailed pipeline debug info in response
        
    Returns:
        Dict with recommendations, health_context, diet_constraints, and integrated explanation
    """
    # Auto-detect language if not provided
    if language is None:
        language = detect_language(user_query)
    
    # Extract health constraints from query
    diet_constraints = extract_health_constraints(user_query)
    
    # Step 1: Get deterministic recipe recommendations (with debug if requested)
    jema_result = run_jema_model(user_query, recipes_features_df, top_k=top_recipes, debug=debug)
    recommendations = jema_result.get("results", [])
    debug_info = jema_result.get("debug", None)
    
    # Step 2: Retrieve relevant health context
    health_context = _retrieve_context(user_query, top_k=top_contexts)
    
    # Step 3: Build integrated prompt combining both
    integrated_prompt = _build_integrated_prompt(
        recommendations,
        health_context,
        language=language,        
        persona=persona
    )
    
    # Step 4: Generate grounded explanation via Groq
    if _groq_client is None:
        # Generate enhanced fallback explanation based on recommendations
        if recommendations:
            top_recipe = recommendations[0]
            matched_count = len(top_recipe.get("matched", []))
            recipe_name = top_recipe.get("meal_name", "These recipes")
            
            if language == "sw":
                if diet_constraints:
                    constraint_text = ", ".join(diet_constraints)
                    explanation = f"{recipe_name} ni nzuri sana. Una viungo {matched_count} tayari na inafaa {constraint_text}."
                else:
                    explanation = f"{recipe_name} ni chaguo nzuri. Una viungo mengi tayari kufanya hii."
            else:
                if diet_constraints:
                    constraint_text = ", ".join(diet_constraints)
                    explanation = f"Based on your needs ({constraint_text}), {recipe_name} is an excellent choice. You already have {matched_count} ingredients ready."
                else:
                    explanation = f"{recipe_name} is a great option. You have several ingredients ready to prepare this meal."
        else:
            explanation = "Recommendations based on your available ingredients and health preferences."
    else:
        try:
            completion = _groq_client.chat.completions.create(
                model=Config.GROQ_MODEL,
                messages=[{"role": "user", "content": integrated_prompt}],
                max_tokens=400
            )
            explanation = completion.choices[0].message.content
        except Exception as e:
            explanation = f"Unable to generate explanation at this moment."
    
    # Return comprehensive integrated result
    result = {
        "language": language,
        "user_query": user_query,
        "persona": persona,
        "diet_constraints": diet_constraints,
        "recommendations": recommendations,
        "health_context": health_context,
        "integrated_prompt": integrated_prompt,
        "grounded_explanation": explanation
    }
    
    # Add debug info if available
    if debug_info:
        result["debug"] = debug_info
    
    return result


# ============================================================================
# MODULE EXPORTS (Public API)
# ============================================================================

__all__ = [
    # Data exports
    "recipes_features_df",
    "rag_documents",
    "INGREDIENT_VOCAB",
    "EAST_AFRICAN_RECIPE_LIBRARY",  # Kenyan/East African recipe fallback library
    
    # Main pipeline functions
    "run_jema_model",
    "enrich_results_with_groq",
    "answer_with_rag",
    "answer_with_integrated_pipeline",
    
    # Recipe generation and expansion
    "generate_recipe_with_llm",
    "expand_recipe_steps",
    
    # Ingredient-based recommendation (NEW)
    "recommend_recipes_by_ingredients",
    
    # Utility functions
    "detect_language",
    "extract_user_ingredients",
    "extract_time_limit",
    "extract_health_constraints",
    "extract_religious_constraints",
    
    # Internal exports for CLI
    "_generate_groq_explanation",
    "_retrieve_context",
    "_groq_client",
    "rank_recipes",
]
