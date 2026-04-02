"""
Jema Engine - Central Orchestrator
Stateful, API-ready orchestration layer that handles all conversational logic.
This is the only class that API views should call.
"""

import os
import re
import random
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Project paths
JEMA_DIR = Path(__file__).parent.parent

# Core imports from src/ (until fully migrated to services/)
from jema.src.data_loader import DataLoader
from jema.src.ingredient_normalizer_v2 import IngredientNormalizer
from jema.src.excel_recipe_matcher import ExcelRecipeMatcher
from jema.src.intent_classifier import IntentClassifier, Intent, Constraint
from jema.src.substitute_resolver import SubstituteResolver
from jema.src.response_formatter import CTAFormatter, ResponseType
from jema.src.language_detector import LanguageDetector

# Services imports
from jema.services.llm_service import LLMService


# Common African recipes fallback (when not in database) - diverse cuisines from across Africa
COMMON_RECIPES = {
    # East African
    "Beef Stew with Rice": {
        "ingredients": ["rice", "beef", "onion", "tomato", "garlic", "oil", "spices"],
        "country": "East Africa",
        "description": "Hearty beef stew served with fluffy rice"
    },
    "Pilau": {
        "ingredients": ["rice", "onion", "spices", "oil"],
        "country": "Kenya/Tanzania",
        "description": "Fragrant spiced rice dish cooked with aromatics, onions, and pilau masala. Can be made with or without meat."
    },
    "Biryani": {
        "ingredients": ["rice", "onion", "tomato", "chicken", "yogurt", "spices"],
        "country": "Kenya/Tanzania",
        "description": "Layered rice dish with marinated meat and fragrant spices"
    },
    "Coconut Rice": {
        "ingredients": ["rice", "coconut milk", "onion"],
        "country": "East Africa",
        "description": "Fragrant rice cooked in coconut milk"
    },
    "Fried Rice": {
        "ingredients": ["rice", "onion", "tomato", "vegetables", "egg"],
        "country": "Kenya",
        "description": "Stir-fried rice with vegetables and eggs"
    },
    "Chapati": {
        "ingredients": ["flour", "water", "oil"],
        "country": "Kenya/Tanzania/Uganda",
        "description": "Soft flatbread, perfect accompaniment to stews"
    },
    "Ugali": {
        "ingredients": ["maize flour", "water"],
        "country": "Kenya/Tanzania/Uganda",
        "description": "Staple cornmeal dish, firm and filling"
    },
    # West African
    "Jollof Rice": {
        "ingredients": ["rice", "tomato", "onion", "pepper", "chicken", "oil", "spices"],
        "country": "Nigeria/Ghana",
        "description": "Vibrant red rice dish cooked in tomato and spices"
    },
    "Fufu": {
        "ingredients": ["plantain", "yam", "cassava", "salt", "water"],
        "country": "West Africa",
        "description": "Pounded starchy root vegetable, served with soups"
    },
    "Peanut Butter Stew": {
        "ingredients": ["peanut butter", "chicken", "tomato", "onion", "vegetable", "water"],
        "country": "West Africa",
        "description": "Rich creamy stew with meat and vegetables"
    },
    # Southern African
    "Sadza": {
        "ingredients": ["maize meal", "water", "salt"],
        "country": "Zimbabwe/Botswana",
        "description": "Thick cornmeal porridge, staple food from Southern Africa"
    },
    "Pap and Relish": {
        "ingredients": ["maize meal", "water", "tomato", "onion", "vegetables"],
        "country": "South Africa",
        "description": "Creamy maize porridge with vegetable accompaniment"
    },
    # North African
    "Tagine": {
        "ingredients": ["lamb", "apricot", "onion", "cinnamon", "ginger", "oil", "water"],
        "country": "Morocco",
        "description": "Slow-cooked aromatic stew with meat and fruits"
    },
    "Couscous": {
        "ingredients": ["couscous", "vegetable", "broth", "chickpea", "spice"],
        "country": "North Africa",
        "description": "Light fluffy grain dish served with stews and vegetables"
    },
    # Central African
    "Cassava Leaves Stew": {
        "ingredients": ["cassava leaves", "groundnut", "onion", "garlic", "water", "oil"],
        "country": "Central Africa",
        "description": "Nutritious green leafy stew with peanut sauce"
    }
}


def split_steps_paragraph(paragraph: str) -> list:
    if not paragraph or not paragraph.strip():
        return []

    # Normalize all line endings first
    paragraph = paragraph.replace('\r\n', '\n').replace('\r', '\n')

    # Remove leading method/steps prefix e.g. "Method: Boil\nSteps:" or "Steps:"
    paragraph = re.sub(r'^(Method:[^\n]*\n)?Steps?:\s*', '', paragraph.strip(), flags=re.IGNORECASE)

    # Strategy 1: Newline-separated steps (Title: content\nTitle: content)
    # Each non-empty line is its own step
    lines = [line.strip() for line in paragraph.split('\n') if line.strip() and len(line.strip()) > 5]
    if len(lines) >= 3:
        return lines

    # Strategy 2: Paragraph with action-header pattern (Title: content. Title: content.)
    # Split on pattern: period or newline followed by a capitalized word and colon
    action_splits = re.split(r'(?<=\.)\s+(?=[A-Z][a-zA-Z\s\(\)]+:)', paragraph)
    action_steps = [s.strip() for s in action_splits if s.strip() and len(s.strip()) > 5]
    if len(action_steps) >= 3:
        return action_steps

    # Strategy 3: Plain sentence splitting (fallback)
    sentences = re.split(r'\.\s+', paragraph.strip())
    steps = []
    for s in sentences:
        s = s.strip()
        if s and len(s) > 5:
            if not s.endswith('.'):
                s = s + '.'
            steps.append(s)
    return steps


class JemaEngine:
    """
    Central orchestrator for Jema conversations.
    Handles intent classification, recipe matching, and LLM orchestration.
    """

    RECIPE_NAME_ALIASES = {
        # Spelling variants of the same dish
        "biriani": "biryani",
        "beef pilau": "pilau",
        "rice pilau": "pilau",
        "chicken pilau": "pilau",
        # Chicken dish aliases
        "kuku stew": "kuku mchuzi",
        "chicken stew": "kuku mchuzi",
        "kuku wa nazi": "kuku mchuzi",
        # Bean dish aliases
        "maharage": "maharagwe",
        "bean stew": "beans stew",
        # Fish dish aliases
        "fish curry": "samaki wa kupaka",
        "samaki wa nazi": "samaki wa kupaka",
        # Egg dish aliases
        "egg stew": "egg and tomato stew",
        "eggs and tomato": "egg and tomato stew",
        # Rice dish aliases
        "coconut rice": "wali wa nazi",
        "rice and coconut": "wali wa nazi",
    }

    def _load_user_profile(self, user) -> Optional[Dict]:
        """
        Load user profile context from the Profile model.
        
        Returns dict with user preferences for personalization, or None if not available.
        """
        try:
            from profiles.services import get_user_profile_context
            return get_user_profile_context(user)
        except Exception as e:
            if self.debug_mode:
                print(f"[JemaEngine] Warning: Could not load user profile: {e}")
            return None
    
    def _normalize_recipe_name(self, name: str) -> str:
        """Normalize recipe name to canonical form to prevent duplicates."""
        return self.RECIPE_NAME_ALIASES.get(name.lower().strip(), name.lower().strip())

    def _get_recipe_region(self, recipe: Dict) -> str:
        """Extract the region/country from a recipe dict."""
        # Try multiple field names
        region = recipe.get("cuisine_region") or recipe.get("country") or recipe.get("region") or ""
        return str(region).strip()

    def _is_region_overdone(self, region: str, max_repeats: int = 1) -> bool:
        """
        Check if a region has been suggested too many times recently.
        Prevents repetition from same region in current session.
        
        Returns True if region should be avoided.
        """
        if not region:
            return False
        region_lower = region.lower()
        count = sum(1 for r in self.suggested_regions if r.lower() == region_lower)
        return count >= max_repeats

    def _select_diverse_recipes(
        self, 
        candidate_recipes: List[Dict], 
        num_to_select: int = 3,
        prefer_new_regions: bool = True
    ) -> List[Dict]:
        """
        Intelligently select recipes with regional diversity.
        
        Args:
            candidate_recipes: List of candidate recipes to select from
            num_to_select: How many recipes to return (typically 3)
            prefer_new_regions: If True, avoid regions already suggested
            
        Returns:
            List of selected recipes, prioritizing regional diversity
        """
        if len(candidate_recipes) <= num_to_select:
            return candidate_recipes
        
        if not prefer_new_regions:
            # Just randomly select
            return random.sample(candidate_recipes, num_to_select)
        
        # Sort by region freshness: recipes from unseen regions first
        def region_score(recipe):
            region = self._get_recipe_region(recipe)
            is_overdone = self._is_region_overdone(region)
            # Return negative so overdone regions sort last
            return 0 if not is_overdone else -1
        
        sorted_recipes = sorted(candidate_recipes, key=region_score, reverse=True)
        
        # If we have enough recipes from diverse regions, use them
        selected = sorted_recipes[:num_to_select]
        
        # Track the regions of selected recipes
        for recipe in selected:
            region = self._get_recipe_region(recipe)
            if region:
                self.suggested_regions.append(region)
        
        return selected

    def __init__(self, excel_path: Optional[str] = None, debug_mode: bool = False, user=None):
        """
        Initialize the Jema Engine.
        
        Args:
            excel_path: Deprecated. Kept for backward compatibility.
            debug_mode: Enable debug output for accuracy tracking.
            user: Optional Django User object. If provided, loads user profile for personalization.
        """
        # Use CSV as the source of truth
        csv_path = str(JEMA_DIR / "data" / "final_african_recipes.csv")
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Recipe CSV not found: {csv_path}")
        
        # Load data once
        loader = DataLoader(csv_path=csv_path)
        data = loader.load_all()
        self.recipes_df = data.get("recipes", pd.DataFrame())
        
        if self.recipes_df.empty:
            raise ValueError("No recipe data loaded from CSV file")
        
        # Log DataFrame columns for debugging CSV column mismatches
        print(f"[JemaEngine] CSV columns available: {list(self.recipes_df.columns)}")
        
        # Initialize services
        self.matcher = ExcelRecipeMatcher(self.recipes_df)
        self.substitute_resolver = SubstituteResolver(self.recipes_df)
        self.llm = LLMService()
        self.language_detector = LanguageDetector()
        
        # Load user profile context for personalization
        self.user = user
        self.user_profile = self._load_user_profile(user) if user else None
        
        # Conversation state
        self.last_suggested_recipes: List[Dict] = []
        self.rejected_recipes: List[str] = []
        self.last_user_ingredients: set = set()
        self.current_recipe: Optional[Dict] = None
        self.recipe_confirmed: bool = False
        self.awaiting_recipe_choice: bool = False
        self.debug_mode: bool = debug_mode
        
        # Regional diversity tracking (prevent repetition from same region)
        self.suggested_regions: List[str] = []  # Track regions of suggested recipes in this session

    def _lookup_csv_recipe(self, recipe_name: str) -> Optional[Dict]:
        """
        Look up a recipe in the CSV database.
        
        Matching strategy:
        1. Exact match (case-insensitive, whitespace trimmed)
        2. Compound meal detection
        3. Close match with guards (cutoff 0.8, length/word checks)
        
        Returns the recipe dict (with all CSV columns) if found, None otherwise.
        """
        if not recipe_name or self.recipes_df.empty:
            return None
        
        query_lower = recipe_name.strip().lower()
        meal_names = self.recipes_df['meal_name'].dropna().tolist()
        meal_names_lower = [name.strip().lower() for name in meal_names]
        
        # Priority 1: Exact full name match (case-insensitive, whitespace stripped)
        for idx, row in self.recipes_df.iterrows():
            if str(row.get('meal_name', '')).strip().lower() == query_lower:
                matched_row = row.to_dict()
                print(f"[CSV DEBUG] Exact match found for '{recipe_name}'")
                return matched_row
        
        # Priority 2: Compound meal detection
        compound = self.detect_compound_meal(recipe_name, self.recipes_df)
        if compound:
            return compound
        
        # Priority 3: Close match with guards (cutoff 0.8 to prevent false positives)
        matches = difflib.get_close_matches(
            query_lower,
            meal_names_lower,
            n=1,
            cutoff=0.8
        )

        if matches:
            matched_lower = matches[0]

            # Guard 1: Reject if matched name differs in length by more than 3 characters
            if abs(len(matched_lower) - len(query_lower)) > 3:
                print(f"[CSV DEBUG] Rejected close match '{matched_lower}' — length too different from '{query_lower}'")
                return None

            # Guard 2: Reject if query has more words than matched name (prevents Ugali Mayai → Ugali)
            if len(query_lower.split()) > len(matched_lower.split()) + 1:
                print(f"[CSV DEBUG] Rejected close match '{matched_lower}' — query has more words than match")
                return None

            # Find and return the actual row
            original_idx = meal_names_lower.index(matched_lower)
            matched_row = self.recipes_df.iloc[original_idx].to_dict()
            print(f"[CSV DEBUG] Close match found for '{recipe_name}' → '{matched_lower}'")
            return matched_row

        return None
    
    def detect_compound_meal(self, recipe_name: str, df: pd.DataFrame) -> Optional[Dict]:
        """
        Check if a recipe name is a compound of two known recipes.
        Returns a dict with is_compound flag and component data, or None.
        """
        query_lower = recipe_name.strip().lower()
        meal_names_lower = [str(n).strip().lower() for n in df['meal_name'].dropna()]

        words = query_lower.split()
        if len(words) < 2:
            return None

        # Try every split point: first word(s) as component 1, rest as component 2
        for i in range(1, len(words)):
            part1 = " ".join(words[:i])
            part2 = " ".join(words[i:])

            match1 = difflib.get_close_matches(part1, meal_names_lower, n=1, cutoff=0.85)
            match2 = difflib.get_close_matches(part2, meal_names_lower, n=1, cutoff=0.85)

            if match1 and match2:
                idx1 = meal_names_lower.index(match1[0])
                idx2 = meal_names_lower.index(match2[0])
                row1 = df.iloc[idx1]
                row2 = df.iloc[idx2]
                print(f"[CSV DEBUG] Compound meal detected: '{match1[0]}' + '{match2[0]}'")
                return {
                    "is_compound": True,
                    "component_1_name": row1.get('meal_name', ''),
                    "component_1_ingredients": row1.get('core_ingredients', ''),
                    "component_1_steps": row1.get('recipes', ''),
                    "component_2_name": row2.get('meal_name', ''),
                    "component_2_ingredients": row2.get('core_ingredients', ''),
                    "component_2_steps": row2.get('recipes', ''),
                }

        return None

    def _csv_search_by_ingredient(self, ingredient: str, count: int) -> list:
        """
        Search the CSV for recipes whose core_ingredients contain the given ingredient.
        Returns up to `count` matching recipe dicts.
        """
        ingredient_lower = ingredient.strip().lower()
        matches = []

        for idx, row in self.recipes_df.iterrows():
            core = str(row.get('core_ingredients', '')).lower()
            if ingredient_lower in core:
                matches.append({
                    'meal_name': row.get('meal_name', ''),
                    'cuisine_region': row.get('cuisine_region', ''),
                    'country': row.get('country', '')
                })
            if len(matches) >= count:
                break

        return matches

    def _lookup_with_modifier(self, recipe_name: str) -> tuple:
        """
        Returns (row, modifier) where modifier is the variant requested.
        e.g. "Fish Pepper Soup" → (pepper_soup_row, "fish")
        
        Returns (None, None) if no match found.
        """
        query_lower = recipe_name.strip().lower()

        # Try exact match first
        for idx, row in self.recipes_df.iterrows():
            if str(row.get('meal_name', '')).strip().lower() == query_lower:
                return row, None

        # Try stripping common modifier words from the front
        common_modifiers = [
            'fish', 'chicken', 'beef', 'goat', 'lamb', 'vegetable',
            'vegan', 'spicy', 'fried', 'grilled', 'smoked'
        ]

        words = query_lower.split()
        if len(words) > 1:
            for modifier in common_modifiers:
                if words[0] == modifier:
                    base_name = ' '.join(words[1:])
                    for idx, row in self.recipes_df.iterrows():
                        if str(row.get('meal_name', '')).strip().lower() == base_name:
                            print(f"[CSV DEBUG] Modifier match: '{modifier}' + '{base_name}'")
                            return row, modifier

        return None, None

    def _split_csv_steps_into_sentences(self, steps_text: str) -> str:
        """
        Split a paragraph of steps into individual sentences.
        
        When CSV steps arrive as a paragraph (long string without numbering),
        split by period followed by space and return as numbered list.
        
        Args:
            steps_text: Raw steps text from CSV (may be a paragraph)
        
        Returns:
            Formatted text with each sentence on its own line for Groq to number and title
        """
        if not steps_text or not isinstance(steps_text, str):
            return ""
        
        steps_text = steps_text.strip()
        
        # Check if already numbered (contains "1.", "2.", etc.) or bulleted
        if any(f"{i}." in steps_text or f"{i})" in steps_text for i in range(1, 10)):
            # Already formatted as numbered steps, return as-is
            return steps_text
        
        if steps_text.startswith(("-", "•", "*")):
            # Already bulleted, return as-is
            return steps_text
        
        # Split by period followed by space
        # Then clean and filter out empty sentences
        sentences = [s.strip() for s in steps_text.split(". ")]
        
        # Reconstruct with periods and join with newlines
        # so each sentence is on its own line for Groq to handle
        cleaned_sentences = []
        for sentence in sentences:
            if not sentence:
                continue
            # Add period back if not present
            if not sentence.endswith((".", "!", "?")):
                sentence = sentence + "."
            cleaned_sentences.append(sentence)
        
        # Return as newline-separated lines (Groq will see each as a step to title and number)
        return "\n".join(cleaned_sentences)

    def process_message(self, user_input: str) -> Dict:
        """
        Process a user message and return a response.
        
        Args:
            user_input: User's natural language input
        
        Returns:
            Dictionary with:
                - message: str (main response text)
                - recipes: List[Dict] (suggested recipes if any)
                - language: str (detected language)
                - cta: str (call-to-action message)
                - state: Dict (current conversation state for debugging)
        """
        user_input = user_input.strip()
        
        # Handle reset commands
        if user_input.lower() in ["clear", "reset", "new conversation"]:
            return self._reset_conversation()
        
        # Handle exit commands
        if user_input.lower() in ["quit", "exit"]:
            return self._build_response("Goodbye! Hope Jema was helpful!", [])
        
        # Detect language
        self.llm.update_language(user_input)
        
        # Classify intent and constraints
        intent, constraints, community, confidence = IntentClassifier.classify(user_input)
        
        # Route to handler based on intent
        # Only route to community handler if NOT currently awaiting a recipe selection
        # When awaiting_recipe_choice is True, the user is selecting a recipe — not requesting community recipes
        if community and intent in [Intent.MEAL_IDEA, Intent.INFORMATION, Intent.CHAT_SOCIAL, Intent.RECIPE_REQUEST]:
            if not (self.awaiting_recipe_choice and self.last_suggested_recipes):
                return self._handle_community_request(user_input, community)
        
        if intent == Intent.GREETING:
            return self._handle_greeting(user_input)
        
        if intent == Intent.REJECTION:
            return self._handle_rejection(user_input)
        
        if intent == Intent.ACCOMPANIMENT:
            return self._handle_accompaniment(user_input)
        
        if intent == Intent.FOLLOW_UP and len(self.llm.conversation_history) > 0:
            return self._handle_follow_up(user_input)
        
        if self.awaiting_recipe_choice and self.last_suggested_recipes:
            result = self._handle_recipe_selection(user_input)
            if result:
                return result
        
        if intent == Intent.MEAL_IDEA:
            return self._handle_meal_idea(user_input)
        
        if intent in [Intent.INFORMATION, Intent.CHAT_SOCIAL]:
            return self._handle_information(user_input)
        
        if intent == Intent.RECIPE_REQUEST:
            return self._handle_recipe_request(user_input)
        
        if intent == Intent.INGREDIENT_BASED or intent == Intent.MEAL_IDEA:
            return self._handle_ingredient_based(user_input, constraints)
        
        # Fallback
        return self._handle_fallback(user_input)

    def _reset_conversation(self) -> Dict:
        """Reset conversation state."""
        self.llm.clear_history()
        self.last_suggested_recipes = []
        self.rejected_recipes = []
        self.last_user_ingredients = set()
        self.current_recipe = None
        self.recipe_confirmed = False
        self.awaiting_recipe_choice = False
        self.suggested_regions = []  # Reset regional tracking
        
        message = "Conversation cleared. Let's start fresh!"
        self.llm.add_to_history("user", "reset")
        self.llm.add_to_history("assistant", message)
        
        return self._build_response(message, [])

    def _handle_community_request(self, user_input: str, community: str) -> Dict:
        """Handle requests for specific community/ethnic cuisines."""
        community_matcher = self.matcher.filter_by_community(community).exclude_beverages()
        all_community_recipes = self.recipes_df[
            self.recipes_df['community'].str.lower() == community.lower()
        ] if 'community' in self.recipes_df.columns else pd.DataFrame()
        
        if not all_community_recipes.empty:
            top_recipes = all_community_recipes.head(5)
            recipe_list = []
            formatted_recipes = []
            
            for i, (idx, recipe) in enumerate(top_recipes.iterrows(), 1):
                meal_type = recipe.get('meal_type', 'dish')
                cook_time = recipe.get('cook_time', '')
                time_str = f" ({cook_time} min)" if pd.notna(cook_time) and cook_time else ""
                
                recipe_dict = recipe.to_dict()
                recipe_dict['number'] = i
                recipe_list.append(recipe_dict)
                formatted_recipes.append(f"{i}. {recipe['meal_name']}{time_str}")
            
            message = f"Here are some traditional {community.title()} dishes:\n\n" + "\n".join(formatted_recipes)
            message += f"\n\nWhich one would you like?"
            
            self.last_suggested_recipes = recipe_list
            self.awaiting_recipe_choice = True
            
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", message)
            
            return self._build_response(message, recipe_list)
        else:
            message = f"I don't have specific recipes from the {community.title()} community in my database yet.\n\nBut I can help you with many African dishes from across the continent. What ingredients do you have?"
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", message)
            
            return self._build_response(message, [])

    def _handle_greeting(self, user_input: str) -> Dict:
        """Handle greeting intents."""
        if self.recipe_confirmed and self.current_recipe:
            response = self.llm.general_response(
                f"User said: '{user_input}' (they're working on {self.current_recipe.get('meal_name', 'a recipe')})",
                use_history=False,
                include_cta=False
            )
        elif len(self.llm.conversation_history) > 0:
            response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        else:
            if self.llm.current_language == 'swahili':
                response = "Habari! Mimi ni Jema. Niambie viungo unavyonazo au chakula unachotaka!"
            else:
                response = "Hello! I'm Jema, your African cooking assistant. Tell me what ingredients you have or what you'd like to cook!"
        
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_rejection(self, user_input: str) -> Dict:
        """Handle rejection intents (user doesn't like suggestion)."""
        self.current_recipe = None
        self.recipe_confirmed = False
        
        if self.last_suggested_recipes:
            self.rejected_recipes.extend([r.get('meal_name', '') for r in self.last_suggested_recipes[:1]])
            
            # Find alternatives
            alternatives = []
            for idx, recipe in self.recipes_df.iterrows():
                if recipe.get('meal_name', '') not in self.rejected_recipes:
                    alternatives.append(recipe)
                if len(alternatives) >= 3:
                    break
            
            if alternatives:
                alternatives_list = []
                for i, recipe in enumerate(alternatives[:3], 1):
                    cook_time = recipe.get('cook_time', '')
                    meal_type = recipe.get('meal_type', 'dish')
                    alternatives_list.append(f"{i}. {recipe['meal_name']} - {meal_type} ({cook_time} min)")
                
                message = "No problem! Here are some alternatives:\n\n" + "\n".join(alternatives_list)
                message += "\n\nWhich one interests you?"
                
                self.last_suggested_recipes = [r.to_dict() for r in alternatives[:3]]
                self.awaiting_recipe_choice = True
                
                self.llm.add_to_history("user", user_input)
                self.llm.add_to_history("assistant", message)
                
                return self._build_response(message, self.last_suggested_recipes)
        
        # Fallback
        response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_accompaniment(self, user_input: str) -> Dict:
        """Handle accompaniment queries (what goes with X?)."""
        response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_follow_up(self, user_input: str) -> Dict:
        """Handle follow-up questions."""
        if self.recipe_confirmed and self.current_recipe:
            response = self.llm.general_response(
                f"{user_input} (Answer in context of {self.current_recipe.get('meal_name', 'this recipe')})",
                use_history=False,
                include_cta=False
            )
        else:
            response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_recipe_selection(self, user_input: str) -> Optional[Dict]:
        """Handle user selecting from suggested recipes."""
        selected = None
        selection_lower = user_input.lower().strip()

        # ── Match by number: "1", "2", "3" ──────────────────────────────────────────
        if selection_lower.isdigit():
            idx = int(selection_lower) - 1
            if 0 <= idx < len(self.last_suggested_recipes):
                selected = self.last_suggested_recipes[idx]

        # ── Match by name if numeric failed ─────────────────────────────────────────
        if not selected:
            for recipe in self.last_suggested_recipes:
                # Safely get meal name — handle both dict keys and pandas Series
                if isinstance(recipe, dict):
                    recipe_name = recipe.get("meal_name", recipe.get("name", "")).lower().strip()
                else:
                    try:
                        recipe_name = str(recipe.get("meal_name", "")).lower().strip()
                    except Exception:
                        recipe_name = ""

                # Exact match
                if selection_lower == recipe_name:
                    selected = recipe
                    break

                # Partial match — user typed part of the name
                if selection_lower in recipe_name or recipe_name in selection_lower:
                    selected = recipe
                    break

        # ── No match — prompt user to choose again ───────────────────────────────────
        if not selected:
            recipe_lines = []
            for i, r in enumerate(self.last_suggested_recipes, 1):
                if isinstance(r, dict):
                    name = r.get("meal_name", r.get("name", ""))
                else:
                    name = str(r.get("meal_name", ""))
                recipe_lines.append(f"{i}. {name}")

            message = (
                f"I didn't catch that. Please choose from:\n\n"
                + "\n".join(recipe_lines)
                + "\n\nType the number or the recipe name."
            )
            return self._build_response(message, self.last_suggested_recipes)

        # ── Recipe found — display it ──────────────────────────────────────────────────
        return self._display_full_recipe(selected, user_input, self.last_user_ingredients)

    def _handle_meal_idea(self, user_input: str) -> Dict:
        """Handle meal idea queries (what should I make for breakfast?)."""
        # Extract meal time if mentioned
        meal_time = ""
        if "breakfast" in user_input.lower():
            meal_time = "breakfast"
        elif "lunch" in user_input.lower():
            meal_time = "lunch"
        elif "dinner" in user_input.lower():
            meal_time = "dinner"
        
        time_context = f" for {meal_time}" if meal_time else ""
        prompt = f"Suggest 3-4 delicious traditional African recipes{time_context} from across the continent. Include the dish name and a brief description of why it's great. Keep it conversational and appetizing."
        
        response = self.llm.general_response(prompt, use_history=False, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_information(self, user_input: str) -> Dict:
        """Handle information/social chat."""
        # Check if this might be a recipe request that wasn't caught by RECIPE_REQUEST intent
        recipe_name = self._extract_recipe_name(user_input)
        if recipe_name:
            # Route to recipe handler
            return self._handle_recipe_request(user_input)
        
        response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _extract_recipe_name(self, user_input: str) -> str:
        """
        Extract recipe name from a direct recipe request.

        Handles patterns like:
        - "How do I cook pilau?"
        - "Give me a recipe for chapati"
        - "How to make ugali"
        - "Recipe for biryani"
        - "How can I cook matoke?"
        """
        query = user_input.lower().strip()

        # Remove common request prefixes — longest first to avoid partial matches
        prefixes = [
            "give me a recipe for ",
            "give me the recipe for ",
            "how do i cook ",
            "how can i cook ",
            "how do i make ",
            "how can i make ",
            "how to cook ",
            "how to make ",
            "recipe for ",
            "recipe of ",
            "show me how to cook ",
            "show me how to make ",
            "i want to cook ",
            "i want to make ",
            "steps for ",
            "instructions for ",
            "cook ",
            "make ",
        ]

        for prefix in prefixes:
            if prefix in query:
                name = query.split(prefix, 1)[-1].strip()
                # Remove trailing punctuation and filler words
                name = re.sub(r'[?!.,;:\'"]+$', '', name).strip()
                name = re.sub(r'\s+', ' ', name).strip()
                if name and len(name) > 1:
                    return name.title()

        # Fallback — check if any known recipe name appears in the query
        for _, row in self.recipes_df.iterrows():
            meal_name = str(row.get('meal_name', '')).lower()
            if meal_name and meal_name in query:
                return str(row.get('meal_name', '')).title()

        return ""

    def _handle_recipe_request(self, user_input: str) -> Dict:
        """
        Handle direct recipe requests like:
        - "How do I cook pilau?"
        - "Give me a recipe for chapati"
        - "How to make ugali"

        Source priority:
        1. CSV database with exact/close match — steps are authoritative
        2. PDF recipe store
        3. Tavily web search
        4. Groq generation (constrained)
        """
        # Extract recipe name from the request
        recipe_name = self._extract_recipe_name(user_input)

        if not recipe_name:
            response = self.llm.general_response(
                user_input, use_history=True, include_cta=True
            )
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", response)
            return self._build_response(response, [])

        # Clean the recipe name
        recipe_name = re.sub(r'[?!.,;:\'"()\[\]]', '', recipe_name).strip()

        if not recipe_name:
            response = self.llm.general_response(
                user_input, use_history=True, include_cta=True
            )
            return self._build_response(response, [])

        # ─────────────────────────────────────────────────────────────────────────────
        # STEP 1: Try CSV lookup first (authoritative source)
        # ─────────────────────────────────────────────────────────────────────────────
        csv_recipe, variant_modifier = self._lookup_with_modifier(recipe_name)
        
        try:
            if csv_recipe is not None:
                # CSV found — extract the raw ingredients and steps
                csv_cuisine_region = csv_recipe.get("cuisine_region", "East Africa")
                
                # Debug: Show ALL available columns and values
                print(f"\n[CSV DEBUG] Recipe found: {recipe_name}")
                print(f"[CSV DEBUG] Available columns in row: {list(csv_recipe.keys())}")
                for col, val in csv_recipe.items():
                    if val and isinstance(val, str):
                        preview = str(val)[:150].replace("\n", " ")
                        print(f"[CSV DEBUG]   {col}: {preview}...")
                
                # Try multiple possible column names for steps and ingredients
                csv_steps_paragraph = csv_recipe.get("recipes", "") or csv_recipe.get("steps", "") or csv_recipe.get("instructions", "") or csv_recipe.get("method", "")
                csv_ingredients_raw = csv_recipe.get("core_ingredients", "") or csv_recipe.get("ingredients", "") or csv_recipe.get("ingredient_list", "")
                
                # Filter water and other cooking mediums from ingredient display
                SKIP_INGREDIENTS = {'water', 'boiling water', 'cold water', 'hot water'}
                ingredient_parts = [
                    part.strip() for part in csv_ingredients_raw.split(',')
                    if part.strip().lower() not in SKIP_INGREDIENTS
                ]
                csv_ingredients = ', '.join(ingredient_parts)
                
                print(f"[CSV DEBUG] Found steps: {len(csv_steps_paragraph)} chars")
                print(f"[CSV DEBUG] Found ingredients: {len(csv_ingredients)} chars")
                
                if not csv_steps_paragraph:
                    print(f"[CSV DEBUG] ERROR: No steps found in any column!")
                
                # Split paragraph steps into individual sentences
                csv_steps = split_steps_paragraph(csv_steps_paragraph)
                print(f"[CSV DEBUG] After split: {len(csv_steps)} individual steps")
                
                # FIX 3: Add full debug output for each step
                for i, step in enumerate(csv_steps):
                    print(f"[CSV DEBUG] Full step {i+1} ({len(step)} chars): {step}")
                
                # Handle compound meals
                if csv_recipe.get("is_compound"):
                    message = self.llm.generate_recipe(
                        recipe_name=recipe_name,
                        cuisine_region=csv_cuisine_region,
                        language=self.llm.current_language,
                        source="CSV_COMPOUND",
                        compound_data=csv_recipe,
                        user_profile=self.user_profile,
                    )
                else:
                    # Regular CSV recipe
                    message = self.llm.generate_recipe(
                        recipe_name=recipe_name,
                        cuisine_region=csv_cuisine_region,
                        language=self.llm.current_language,
                        source="CSV",
                        csv_steps=csv_steps,
                        csv_ingredients=csv_ingredients,
                        csv_row=csv_recipe,
                        user_profile=self.user_profile,
                        variant_modifier=variant_modifier,
                    )
                
                if message:
                    # Store recipe data for context
                    recipe_data = {
                        "meal_name": recipe_name,
                        "cuisine_region": csv_cuisine_region,
                        "source": "CSV",
                    }
                    
                    self.current_recipe = recipe_data
                    self.recipe_confirmed = True
                    self.last_suggested_recipes = [recipe_data]
                    self.awaiting_recipe_choice = False
                    
                    self.llm.add_to_history("user", user_input)
                    self.llm.add_to_history("assistant", message)
                    
                    return self._build_response(message, [recipe_data])
            
            # ─────────────────────────────────────────────────────────────────────────
            # STEP 2: CSV miss — try PDF, Tavily, then Groq (handled in generate_recipe)
            # ─────────────────────────────────────────────────────────────────────────
            message = self.llm.generate_recipe(
                recipe_name, 
                cuisine_region="East Africa",
                user_profile=self.user_profile
            )
            
            if message:
                # Store recipe data for context
                recipe_data = {
                    "meal_name": recipe_name,
                    "cuisine_region": "East Africa",
                    "source": "pdf/web/groq",
                }
                
                self.current_recipe = recipe_data
                self.recipe_confirmed = True
                self.last_suggested_recipes = [recipe_data]
                self.awaiting_recipe_choice = False
                
                self.llm.add_to_history("user", user_input)
                self.llm.add_to_history("assistant", message)
                
                return self._build_response(message, [recipe_data])
            else:
                # Fallback if recipe generation failed
                response = self.llm.general_response(
                    user_input, use_history=True, include_cta=True
                )
                return self._build_response(response, [])
        
        except Exception as e:
            print(f"[Recipe Request Error] {e}")
            response = self.llm.general_response(
                user_input, use_history=True, include_cta=True
            )
            return self._build_response(response, [])

    def _handle_ingredient_based(self, user_input: str, constraints: List) -> Dict:
        """Handle ingredient-based recipe matching across African cuisines with deduplication."""
        # Extract ingredients
        user_ingredients = IngredientNormalizer.extract_from_string(user_input)
        
        if not user_ingredients:
            response = self.llm.general_response(user_input, use_history=True, include_cta=False)
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", response)
            return self._build_response(response, [])
        
        # Remember ingredients
        self.last_user_ingredients = set(user_ingredients)
        
        # Build constraints
        user_constraints = {}
        if Constraint.QUICK in constraints:
            user_constraints['quick'] = True
        
        # Exclude beverages unless explicitly requested
        beverage_terms = ['drink', 'beverage', 'juice', 'tea', 'coffee', 'soda', 'chai']
        active_matcher = self.matcher
        if not any(term in user_input.lower() for term in beverage_terms):
            active_matcher = active_matcher.exclude_beverages()
        
        # STEP 0: Try direct CSV ingredient search first for primary ingredients
        # This ensures recipes containing the requested ingredient are found directly
        normalized_ingredients = [ing.lower().strip() for ing in user_ingredients]
        raw_csv_results = []
        
        # Search each primary ingredient for direct matches
        PRIMARY_INGREDIENTS = {
            "eggs", "egg", "beef", "chicken", "kuku", "fish", "samaki",
            "lamb", "goat", "pork", "meat", "nyama", "shrimp", "prawns",
            "beans", "maharagwe", "lentils", "ndengu", "peas", "chickpeas",
            "groundnuts", "groundnut", "peanut", "peanuts",
            "rice", "mchele", "wali", "potato", "viazi", "maize", "mahindi",
            "banana", "ndizi", "plantain", "cassava", "mihogo", "ugali",
            "flour", "chapati", "spinach", "kale", "sukuma", "cabbage"
        }
        
        # Try direct search for primary ingredients first
        for ingredient in normalized_ingredients:
            if ingredient in PRIMARY_INGREDIENTS:
                direct_matches = self._csv_search_by_ingredient(ingredient, count=10)
                for match in direct_matches:
                    # Fetch full recipe row from CSV
                    recipe_row = self.recipes_df[self.recipes_df['meal_name'] == match['meal_name']]
                    if not recipe_row.empty:
                        row = recipe_row.iloc[0]
                        full_recipe = {
                            "meal_name": str(row.get("meal_name", "") if hasattr(row, 'get') else row["meal_name"]),
                            "cuisine_region": str(row.get("cuisine_region", "") if hasattr(row, 'get') else row["cuisine_region"]),
                            "core_ingredients": str(row.get("core_ingredients", "") if hasattr(row, 'get') else row["core_ingredients"]),
                            "recipe": str(row.get("recipes", "") if hasattr(row, 'get') else row.get("recipes", "")),
                            "cook_time_minutes": row.get("cook_time_minutes", 0) if hasattr(row, 'get') else 0,
                            "notes": str(row.get("notes", "") if hasattr(row, 'get') else ""),
                            "country": str(row.get("country", "") if hasattr(row, 'get') else ""),
                        }
                        # Only add if not already in results
                        if not any(r['meal_name'] == full_recipe['meal_name'] for r in raw_csv_results):
                            raw_csv_results.append(full_recipe)
        
        # If direct search didn't find enough, fall back to matcher
        if len(raw_csv_results) < 3:
            # STEP 1: Get CSV results via matcher (fallback)
            matches = active_matcher.match(
                user_ingredients=user_ingredients,
                user_constraints=user_constraints,
                min_match_percentage=0.4
            )
            
            # Exclude rejected recipes
            if self.rejected_recipes:
                matches = [m for m in matches if m.name not in self.rejected_recipes]
            
            # Get raw CSV results — convert to dicts immediately
            for match in matches:
                recipe_row = self.recipes_df[self.recipes_df['meal_name'] == match.name]
                if not recipe_row.empty:
                    row = recipe_row.iloc[0]
                    full_recipe = {
                        "meal_name": str(row.get("meal_name", "") if hasattr(row, 'get') else row["meal_name"]),
                        "cuisine_region": str(row.get("cuisine_region", "") if hasattr(row, 'get') else row["cuisine_region"]),
                        "core_ingredients": str(row.get("core_ingredients", "") if hasattr(row, 'get') else row["core_ingredients"]),
                        "recipe": str(row.get("recipes", "") if hasattr(row, 'get') else row.get("recipes", "")),
                        "cook_time_minutes": row.get("cook_time_minutes", 0) if hasattr(row, 'get') else 0,
                        "notes": str(row.get("notes", "") if hasattr(row, 'get') else ""),
                        "country": str(row.get("country", "") if hasattr(row, 'get') else ""),
                    }
                    # Only add if not already in results
                    if not any(r['meal_name'] == full_recipe['meal_name'] for r in raw_csv_results):
                        raw_csv_results.append(full_recipe)
        
        # ── STEP 1: Include all African recipes from CSV (no regional filtering) ──────────────────────────
        # All African cuisines are welcome, so we use all results
        ea_results = raw_csv_results

        # ── STEP 2: Score CSV results by primary ingredient relevance ────────────────
        # A recipe only qualifies if:
        # (a) it contains the user's PRIMARY ingredient (eggs, beef, chicken, fish, beans, potato)
        # (b) it matches at least 2 of the user's ingredients total
        PRIMARY_INGREDIENTS = {
            # Proteins
            "eggs", "egg", "beef", "chicken", "kuku", "fish", "samaki",
            "lamb", "goat", "pork", "meat", "nyama", "shrimp", "prawns",
            # Legumes — these are primary ingredients, not supporting
            "beans", "maharagwe", "lentils", "ndengu", "peas", "chickpeas",
            "groundnuts", "groundnut", "peanut", "peanuts",
            # Starches — primary when user mentions them
            "rice", "mchele", "wali", "potato", "viazi", "maize", "mahindi",
            "banana", "ndizi", "plantain", "cassava", "mihogo", "ugali",
            "flour", "chapati",
            # Vegetables that are primary when user specifically mentions them
            "spinach", "kale", "sukuma", "cabbage"
        }

        normalized_set = [ing.lower().strip() for ing in normalized_ingredients]

        def count_primary_matches(recipe):
            """
            A recipe qualifies ONLY if ALL of the user's ingredients appear
            in its core_ingredients field as whole words.

            This ensures:
            - rice + beef + onion → Biriani passes (has rice, meat/beef, onions)
            - rice + beef + onion → Ndizi Nyama fails (has beef, onion but NO rice)
            - rice + beef + onion → Sekela fails (has beef, onion but NO rice)
            - rice + beef + onion → Wali wa Nazi fails (has rice, onion but NO beef)
            """
            import re

            # Use core_ingredients field only — not notes or substitutes
            core_ings = str(recipe.get("core_ingredients", "")).lower()

            def exact_match(ingredient: str, text: str) -> bool:
                """Whole word match only — prevents partial matches."""
                pattern = r'\b' + re.escape(ingredient) + r'\b'
                return bool(re.search(pattern, text))

            # Check each user ingredient
            matched = [ing for ing in normalized_set if exact_match(ing, core_ings)]
            missing = [ing for ing in normalized_set if not exact_match(ing, core_ings)]
            match_count = len(matched)

            # ALL user ingredients must be present
            all_present = len(missing) == 0

            # Primary ingredient must also be present
            primary_matched = any(
                exact_match(ing, core_ings)
                for ing in normalized_set
                if ing in PRIMARY_INGREDIENTS
            )

            return match_count, all_present and primary_matched

        strong_csv = []
        for r in ea_results:
            match_count, all_ingredients_present = count_primary_matches(r)
            if all_ingredients_present:
                strong_csv.append((match_count, r))

        # Sort by match count descending — most ingredient matches first
        strong_csv.sort(key=lambda x: x[0], reverse=True)
        csv_results = [recipe for _, recipe in strong_csv][:3]

        # Build seen names from CSV results
        seen_names = {
            self._normalize_recipe_name(r.get("meal_name", ""))
            for r in csv_results
        }

        # Determine how many slots Groq must fill
        groq_needed = 3 - len(csv_results)
        groq_recipes = []

        if groq_needed > 0:
            try:
                groq_recipes = self.llm.generate_african_recipe_from_ingredients(
                    user_ingredients=normalized_ingredients,
                    exclude_names=list(seen_names),
                    count=groq_needed,
                    language=self.llm.current_language
                )
            except Exception as e:
                print(f"Groq gap-fill error: {e}")
                groq_recipes = []

        # Merge CSV and Groq results without duplicates
        all_recipes = list(csv_results)
        for recipe in groq_recipes:
            name_key = self._normalize_recipe_name(recipe.get("meal_name", ""))
            if name_key and name_key not in seen_names:
                all_recipes.append(recipe)
                seen_names.add(name_key)

        # Final deduplication pass and cap at 3
        final_recipes = []
        final_names = set()
        for recipe in all_recipes:
            name_key = self._normalize_recipe_name(recipe.get("meal_name", ""))
            if name_key and name_key not in final_names:
                final_recipes.append(recipe)
                final_names.add(name_key)
        all_recipes = final_recipes[:3]

        # If still fewer than 3 after merge, fill with defaults based on ingredients
        if len(all_recipes) < 3:
            existing_names = {self._normalize_recipe_name(r.get("meal_name", "")) for r in all_recipes}
            normalized_set_lower = set(normalized_ingredients)

            # Default fallback recipes mapped to common ingredient combinations
            INGREDIENT_DEFAULTS = [
                ({"rice", "beef", "onion"},    [
                    {"meal_name": "Pilau",             "cuisine_region": "Kenya"},
                    {"meal_name": "Biriani",            "cuisine_region": "Tanzania"},
                    {"meal_name": "Rice and Beef Stew", "cuisine_region": "Kenya"},
                ]),
                ({"eggs", "onion"},            [
                    {"meal_name": "Ugali Mayai",  "cuisine_region": "Kenya"},
                    {"meal_name": "Rolex",        "cuisine_region": "Uganda"},
                    {"meal_name": "Chapati Mayai","cuisine_region": "Kenya"},
                ]),
                ({"beans", "onion", "tomato"}, [
                    {"meal_name": "Beans Stew",  "cuisine_region": "Kenya"},
                    {"meal_name": "Githeri",     "cuisine_region": "Kenya"},
                    {"meal_name": "Maharagwe",   "cuisine_region": "Tanzania"},
                ]),
                ({"chicken", "onion", "tomato"},[  
                    {"meal_name": "Kuku Mchuzi",    "cuisine_region": "Kenya"},
                    {"meal_name": "Kuku wa Kupaka", "cuisine_region": "Kenya"},
                ]),
                ({"potato", "onion"},          [
                    {"meal_name": "Irio",       "cuisine_region": "Kenya"},
                    {"meal_name": "Mukimo",     "cuisine_region": "Kenya"},
                    {"meal_name": "Viazi Karai","cuisine_region": "Kenya"},
                ]),
                ({"lentils", "onion"},         [
                    {"meal_name": "Ndengu",    "cuisine_region": "Kenya"},
                    {"meal_name": "Misir Wot", "cuisine_region": "Ethiopia"},
                ]),
                ({"kale", "onion"},            [
                    {"meal_name": "Sukuma Wiki","cuisine_region": "Kenya"},
                    {"meal_name": "Githeri",   "cuisine_region": "Kenya"},
                ]),
            ]

            for ingredient_set, defaults in INGREDIENT_DEFAULTS:
                if ingredient_set.issubset(normalized_set_lower):
                    for default in defaults:
                        name_key = self._normalize_recipe_name(default["meal_name"])
                        if name_key not in existing_names and len(all_recipes) < 3:
                            all_recipes.append(default)
                            existing_names.add(name_key)
                    break

        # Apply regional diversity to final recipe selection
        # This ensures we don't repeat recipes from the same region
        if len(all_recipes) >= 3:
            all_recipes = self._select_diverse_recipes(all_recipes, num_to_select=3, prefer_new_regions=True)
        else:
            # Track regions even if we have fewer than 3 recipes
            for recipe in all_recipes:
                region = self._get_recipe_region(recipe)
                if region:
                    self.suggested_regions.append(region)

        # Store full recipes in session state
        self.last_suggested_recipes = all_recipes
        self.awaiting_recipe_choice = True

        # Accuracy debug
        self._debug_groq_accuracy(
            user_ingredients=normalized_ingredients,
            suggested_recipes=all_recipes,
            source="groq+csv"
        )

        # Format suggestion list
        if self.llm.current_language == "sw":
            output = "\nUnaweza kupika mojawapo ya vyakula hivi:\n\n"
        else:
            output = "\nHey there, you could try one of the following:\n\n"

        for i, recipe in enumerate(all_recipes, 1):
            meal_name = recipe.get("meal_name", "")
            cuisine = recipe.get("cuisine_region", "")
            output += f"{i}. {meal_name} – {cuisine}\n"

        if self.llm.current_language == "sw":
            output += "\nUngependa kuweka ipi?\n"
        else:
            output += "\nWhich one would you like?\n"

        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", output)

        return self._build_response(output, all_recipes)

    def _handle_no_matches(self, user_ingredients: set, matcher, user_constraints: Dict, user_input: str) -> Dict:
        """Handle when no recipes match user ingredients."""
        # First, check common recipes fallback
        common_matches = self._match_common_recipes(user_ingredients)
        
        if common_matches:
            # Build response with common recipes
            recipe_list = []
            recipe_objects = []
            
            for i, (name, match_info) in enumerate(common_matches[:3], 1):
                missing = match_info['missing']
                missing_str = f" (add: {', '.join(missing[:2])})" if missing else ""
                recipe_list.append(f"{i}. {name}{missing_str}")
                
                # Create recipe object that can be handled later
                recipe_obj = {
                    "meal_name": name,
                    "country": match_info['country'],
                    "description": match_info.get('description', ''),
                    "is_common_recipe": True,  # Flag for LLM generation
                    "matched_ingredients": match_info['matched'],
                    "missing_ingredients": match_info['missing'],
                }
                recipe_objects.append(recipe_obj)
            
            message = "Hey there, you could try one of the following:\n\n" + "\n".join(recipe_list)
            message += "\n\nWhich one would you like?"
            
            self.last_suggested_recipes = recipe_objects
            self.awaiting_recipe_choice = True
            
            return self._build_response(message, recipe_objects)
        
        # Try near-matches from database with lower threshold
        near_matches = matcher.match(
            user_ingredients=user_ingredients,
            user_constraints=user_constraints,
            min_match_percentage=0.3
        )
        
        if self.rejected_recipes:
            near_matches = [m for m in near_matches if m.name not in self.rejected_recipes]
        
        if near_matches:
            near_match_list = []
            for i, match in enumerate(near_matches[:3], 1):
                near_match_list.append(f"{i}. {match.name}")
            
            message = "You're close! With a few more ingredients, you could make:\n\n" + "\n".join(near_match_list)
            message += "\n\nInterested in any of these?"
            
            self.last_suggested_recipes = [
                self.recipes_df[self.recipes_df['meal_name'] == m.name].iloc[0].to_dict()
                for m in near_matches[:3]
            ]
            self.awaiting_recipe_choice = True
            
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", message)
            
            return self._build_response(message, self.last_suggested_recipes)
        
        # No matches - suggest substitutes
        message = "I don't have recipes that match those exact ingredients.\n"
        
        substitutes_found = False
        ingredient_list = list(user_ingredients)
        for ingredient in ingredient_list[:2]:
            if ingredient in SubstituteResolver.DEFAULT_SUBSTITUTES:
                subs = SubstituteResolver.DEFAULT_SUBSTITUTES[ingredient]
                message += f"\nFor {ingredient}, you could try: {', '.join(subs[:3])}"
                substitutes_found = True
        
        if substitutes_found:
            message += "\n\nWould you like recipes with these substitutes?"
        else:
            message += "\nTry a different combination or let me know what else you have available."
        
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", message)
        
        return self._build_response(message, [])

    def _handle_fallback(self, user_input: str) -> Dict:
        """Handle unrecognized intents."""
        # Check if this might be a recipe request
        recipe_name = self._extract_recipe_name(user_input)
        if recipe_name:
            # Route to recipe handler
            return self._handle_recipe_request(user_input)
        
        response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _display_full_recipe(self, recipe_row, user_input: str, user_ingredients: Optional[set] = None) -> Dict:
        """Format and display a complete recipe (handles both CSV and Groq-generated formats)."""
        recipe_data = recipe_row.to_dict() if not isinstance(recipe_row, dict) else recipe_row
        
        recipe_name = recipe_data.get('meal_name', 'Unknown')
        country = recipe_data.get('country', '') or recipe_data.get('cuisine_region', '')
        
        # Check if this is a Groq-generated recipe (has introduction, steps with titles)
        is_groq_recipe = (
            isinstance(recipe_data.get('introduction'), str) and recipe_data.get('introduction')
        ) or (
            isinstance(recipe_data.get('steps'), list) and 
            recipe_data.get('steps') and 
            any(':' in str(step) for step in recipe_data.get('steps', []))
        )
        
        # If we have a Groq recipe, format it directly
        if is_groq_recipe:
            output = f"\nGreat! Here's the recipe for {recipe_name}\n"
            
            # Add introduction if available
            if recipe_data.get('introduction'):
                output += f"\n{recipe_data['introduction']}\n"
            
            # Add cuisine
            cuisine_str = recipe_data.get('cuisine_region', country or 'East Africa')
            output += f"\nCuisine: {cuisine_str}\n"
            
            # Add ingredients
            if recipe_data.get('ingredients'):
                output += "\nEssential Ingredients\n\n"
                for ing in recipe_data.get('ingredients', []):
                    ing = ing.strip()
                    # Remove any existing bullet formatting
                    ing = ing.lstrip('* -').strip()
                    # Skip empty category lines
                    parts = ing.split(":", 1)
                    if len(parts) == 2 and not parts[1].strip():
                        continue
                    output += ing + "\n"
            
            # Add steps
            if recipe_data.get('steps'):
                output += "\nStep-by-Step Cooking Instructions\n\n"
                for i, step in enumerate(recipe_data.get('steps', [])[:6], 1):
                    step = step.strip()
                    if ':' in step:
                        output += f"{i}. {step}\n"
                    else:
                        if not step.endswith((".", "!", "?")):
                            step += "."
                        output += f"{i}. {step}\n"
            
            # Add tips
            if recipe_data.get('tips'):
                output += "\nTips for Perfect {}\n\n".format(recipe_name)
                for tip in recipe_data['tips']:
                    tip = tip.strip()
                    # Remove any existing bullet formatting
                    tip = tip.lstrip('* -').strip()
                    output += tip + "\n"
            
            message = output
        else:
            # Try to generate a rich recipe using the new generate_recipe method for CSV recipes
            if self.llm.client is not None:
                rich_recipe = self.llm.generate_recipe(recipe_name, country)
                if rich_recipe:
                    # generate_recipe() now returns a fully formatted string
                    message = rich_recipe
                else:
                    # Fallback to original format if LLM generation failed or unavailable
                    # Handle both CSV format (core_ingredients, recipes) and Groq format (ingredients, steps)
                    if isinstance(recipe_data.get('ingredients'), list):
                        # Groq format: ingredients and steps are already lists
                        ingredients_list = recipe_data.get('ingredients', [])
                        steps_list = recipe_data.get('steps', [])
                    else:
                        # CSV format: core_ingredients and recipes are strings
                        ingredients = recipe_data.get('core_ingredients', '')
                        steps = recipe_data.get('recipes', '')
                        
                        # Parse CSV strings into lists
                        if pd.notna(ingredients) and ingredients:
                            safe_ingredients = ingredients.replace('→', '->').replace('•', '-').replace('✓', '*')
                            ingredients_list = [ing.strip() for ing in safe_ingredients.split(',') if ing.strip()]
                        else:
                            ingredients_list = []
                        
                        if pd.notna(steps) and steps:
                            safe_steps = steps.replace('→', '->').replace('•', '-').replace('✓', '*')
                            safe_steps = safe_steps.replace('Method: Fry', '').replace('Method: Stew', '').replace('Method: Boil', '')
                            safe_steps = safe_steps.replace('Steps: ', '').replace('Time: ', '')
                            safe_steps = safe_steps.replace('30–40 min', '').replace('35–45 min', '').replace('45–60 min', '').replace('20–30 min', '')
                            
                            step_candidates = re.split(r'[\n\.]+', safe_steps)
                            steps_list = [step.strip() for step in step_candidates if step.strip()]
                        else:
                            steps_list = []
                    
                    recipe_msg = []
                    
                    # Relate user's ingredients if provided
                    if user_ingredients and ingredients_list:
                        recipe_ing_list = [s.strip() for s in ingredients_list if s.strip()]
                        recipe_ing_set = IngredientNormalizer.normalize_list(recipe_ing_list)
                        have = sorted(list(recipe_ing_set.intersection(user_ingredients)))
                        missing = [
                            ing for ing in recipe_ing_set 
                            if ing not in user_ingredients and not IngredientNormalizer.is_assumed_ingredient(ing)
                        ]
                        if have:
                            recipe_msg.append(f"Based on what you have ({', '.join(have)}), here's an easy recipe:")
                        if missing:
                            recipe_msg.append(f"(You may need: {', '.join(missing)})")
                    
                    # Header
                    recipe_msg.append(f"\nGreat! Here's the recipe for {recipe_name}")
                    if country:
                        recipe_msg.append(f"From: {country}")
                    
                    cook_time = recipe_data.get('cook_time', '')
                    if pd.notna(cook_time) and cook_time:
                        recipe_msg.append(f"Time: {cook_time} minutes")
                    
                    # Ingredients
                    if ingredients_list:
                        recipe_msg.append("\nEssential Ingredients")
                        for ing in ingredients_list:
                            if not ing.startswith("*"):
                                ing = "* " + ing
                            recipe_msg.append(ing)
                    
                    # Steps
                    if steps_list:
                        recipe_msg.append("\nStep-by-Step Cooking Instructions")
                        for i, step in enumerate(steps_list[:6], 1):
                            recipe_msg.append(f"{i}. {step}")
                    
                    message = "\n".join(recipe_msg)
            else:
                # Fallback to original format if LLM client not available
                # Handle both CSV format (core_ingredients, recipes) and Groq format (ingredients, steps)
                if isinstance(recipe_data.get('ingredients'), list):
                    # Groq format: ingredients and steps are already lists
                    ingredients_list = recipe_data.get('ingredients', [])
                    steps_list = recipe_data.get('steps', [])
                else:
                    # CSV format: core_ingredients and recipes are strings
                    ingredients = recipe_data.get('core_ingredients', '')
                    steps = recipe_data.get('recipes', '')
                    
                    # Parse CSV strings into lists
                    if pd.notna(ingredients) and ingredients:
                        safe_ingredients = ingredients.replace('→', '->').replace('•', '-').replace('✓', '*')
                        ingredients_list = [ing.strip() for ing in safe_ingredients.split(',') if ing.strip()]
                    else:
                        ingredients_list = []
                    
                    if pd.notna(steps) and steps:
                        safe_steps = steps.replace('→', '->').replace('•', '-').replace('✓', '*')
                        safe_steps = safe_steps.replace('Method: Fry', '').replace('Method: Stew', '').replace('Method: Boil', '')
                        safe_steps = safe_steps.replace('Steps: ', '').replace('Time: ', '')
                        safe_steps = safe_steps.replace('30–40 min', '').replace('35–45 min', '').replace('45–60 min', '').replace('20–30 min', '')
                        
                        step_candidates = re.split(r'[\n\.]+', safe_steps)
                        steps_list = [step.strip() for step in step_candidates if step.strip()]
                    else:
                        steps_list = []
                
                recipe_msg = []
                
                # Relate user's ingredients if provided
                if user_ingredients and ingredients_list:
                    recipe_ing_list = [s.strip() for s in ingredients_list if s.strip()]
                    recipe_ing_set = IngredientNormalizer.normalize_list(recipe_ing_list)
                    have = sorted(list(recipe_ing_set.intersection(user_ingredients)))
                    missing = [
                        ing for ing in recipe_ing_set 
                        if ing not in user_ingredients and not IngredientNormalizer.is_assumed_ingredient(ing)
                    ]
                    if have:
                        recipe_msg.append(f"Based on what you have ({', '.join(have)}), here's an easy recipe:")
                    if missing:
                        recipe_msg.append(f"(You may need: {', '.join(missing)})")
                
                # Header
                recipe_msg.append(f"\nGreat! Here's the recipe for {recipe_name}")
                if country:
                    recipe_msg.append(f"From: {country}")
                
                cook_time = recipe_data.get('cook_time', '')
                if pd.notna(cook_time) and cook_time:
                    recipe_msg.append(f"Time: {cook_time} minutes")
                
                # Ingredients
                if ingredients_list:
                    recipe_msg.append("\nEssential Ingredients")
                    for ing in ingredients_list:
                        if not ing.startswith("*"):
                            ing = "* " + ing
                        recipe_msg.append(ing)
                
                # Steps
                if steps_list:
                    recipe_msg.append("\nStep-by-Step Cooking Instructions")
                    for i, step in enumerate(steps_list[:6], 1):
                        recipe_msg.append(f"{i}. {step}")
                
                message = "\n".join(recipe_msg)
        
        message += "\n\nLet me know if you need any clarification on any step, or if you'd like to try something else!"
        
        # Lock in recipe
        self.current_recipe = recipe_data
        self.recipe_confirmed = True
        self.last_suggested_recipes = [recipe_data]
        self.awaiting_recipe_choice = False
        
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", message)
        
        return self._build_response(message, [recipe_data])
    
    def _display_common_recipe_with_llm(self, recipe_data: Dict, user_input: str) -> Dict:
        """Generate and display a recipe for a common dish using LLM."""
        recipe_name = recipe_data.get('meal_name', 'Unknown')
        country = recipe_data.get('country', 'East Africa')
        matched = recipe_data.get('matched_ingredients', [])
        missing = recipe_data.get('missing_ingredients', [])
        
        # Build prompt for LLM to generate recipe
        prompt = f"""Generate a traditional {recipe_name} recipe from {country}. 
        
User has: {', '.join(matched)}
User needs: {', '.join(missing) if missing else 'nothing else'}

Provide:
1. Brief description (1-2 sentences)
2. Full ingredient list with quantities
3. Step-by-step cooking instructions (numbered)
4. 2-3 practical cooking tips

Format as plain text, no markdown. Be specific with measurements and timing."""

        llm_response = self.llm.general_response(prompt, use_history=False, include_cta=False)
        
        # Build final message
        header = f"🍽️ {recipe_name} ({country})\n"
        if matched:
            header += f"\n✓ You have: {', '.join(matched)}\n"
        if missing:
            header += f"🛒 You'll need: {', '.join(missing)}\n"
        
        message = header + "\n" + llm_response
        message += "\n\nLet me know if you need any clarification, or if you'd like to try something else!"
        
        # Lock in recipe
        self.current_recipe = recipe_data
        self.recipe_confirmed = True
        self.last_suggested_recipes = [recipe_data]
        self.awaiting_recipe_choice = False
        
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", message)
        
        return self._build_response(message, [recipe_data])

    def _display_meal_pairing(self, recipes: List, user_input: str) -> Dict:
        """Display multiple recipes as a complete meal pairing."""
        message = "🍽️ Complete Meal Pairing\n\n"
        all_recipes = []
        
        for i, recipe_row in enumerate(recipes, 1):
            recipe_data = recipe_row.to_dict() if not isinstance(recipe_row, dict) else recipe_row
            meal_name = recipe_data.get('meal_name', 'Unknown')
            country = recipe_data.get('country', '')
            cook_time = recipe_data.get('cook_time', '')
            ingredients = recipe_data.get('core_ingredients', '')
            steps = recipe_data.get('recipes', '')
            
            message += f"\n{'='*50}\n"
            message += f"{i}. {meal_name}"
            if country:
                message += f" (From: {country})"
            if cook_time:
                message += f" - {cook_time} minutes"
            message += "\n"
            
            if ingredients:
                message += f"\nIngredients: {ingredients}\n"
            
            if steps:
                message += f"Preparation: {steps}\n"
            
            all_recipes.append(recipe_data)
        
        message += f"\n{'='*50}\n"
        message += "\nThis is a complete meal pairing! Let me know if you need clarification on any recipe, or if you'd like to try something else!"
        
        # Lock in recipes
        self.current_recipe = all_recipes[0]
        self.recipe_confirmed = True
        self.last_suggested_recipes = all_recipes
        self.awaiting_recipe_choice = False
        
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", message)
        
        return self._build_response(message, all_recipes)

    def _match_common_recipes(self, user_ingredients: set) -> List[Tuple[str, Dict]]:
        """Match user ingredients against common recipes fallback."""
        matches = []
        
        for recipe_name, recipe_data in COMMON_RECIPES.items():
            # Normalize recipe ingredients
            recipe_ingredients = set(IngredientNormalizer.normalize_list(recipe_data['ingredients']))
            
            # Find matches and missing
            matched = user_ingredients & recipe_ingredients
            missing = recipe_ingredients - user_ingredients
            
            # Only include if user has at least 1 ingredient from this recipe
            if matched:
                # Remove assumed ingredients from missing
                missing_actual = [ing for ing in missing if not IngredientNormalizer.is_assumed_ingredient(ing)]
                
                # Score: number of matches (more matches = better)
                score = len(matched)
                
                matches.append((recipe_name, {
                    'matched': list(matched),
                    'missing': missing_actual,
                    'score': score,
                    'country': recipe_data['country'],
                    'description': recipe_data['description']
                }))
        
        # Sort by score (most matches first)
        matches.sort(key=lambda x: x[1]['score'], reverse=True)
        
        return matches

    def _build_response(self, message: str, recipes: List[Dict]) -> Dict:
        """Build a standardized response dictionary."""
        # Clean NaN values from recipes for JSON serialization
        cleaned_recipes = self._clean_recipes(recipes)
        
        return {
            "message": message,
            "recipes": cleaned_recipes,
            "language": self.llm.current_language,
            "cta": "",  # CTA can be embedded in message
            "state": {
                "recipe_confirmed": self.recipe_confirmed,
                "awaiting_recipe_choice": self.awaiting_recipe_choice,
                "current_recipe": self.current_recipe.get('meal_name', '') if self.current_recipe else None,
            }
        }

    def _clean_recipes(self, recipes: List[Dict]) -> List[Dict]:
        """Clean NaN values from recipe dictionaries for JSON serialization."""
        import math
        cleaned = []
        for recipe in recipes:
            cleaned_recipe = {}
            for key, value in recipe.items():
                # Replace NaN with None, which becomes null in JSON
                if isinstance(value, float) and math.isnan(value):
                    cleaned_recipe[key] = None
                else:
                    cleaned_recipe[key] = value
            cleaned.append(cleaned_recipe)
        return cleaned

    def _debug_groq_accuracy(
        self,
        user_ingredients: list,
        suggested_recipes: list,
        source: str = "groq"
    ) -> None:
        """
        Measures and prints accuracy of recipe suggestions against user ingredients.
        Only runs when self.debug_mode is True.
        
        Checks for each suggested recipe:
        1. How many user ingredients appear in recipe ingredients
        2. Whether primary ingredient is present
        3. Whether dish is from East Africa
        4. Accuracy score as percentage
        """
        if not self.debug_mode:
            return

        PRIMARY_INGREDIENTS = {
            "eggs", "egg", "beef", "chicken", "fish", "beans", "lentils",
            "ndengu", "potato", "rice", "banana", "maize", "lamb", "goat",
            "pork", "meat", "groundnut", "peanut", "spinach", "kale",
            "cabbage", "peas", "chickpeas", "shrimp", "prawns"
        }

        normalized_user = [ing.lower().strip() for ing in user_ingredients]
        primary_user = [ing for ing in normalized_user if ing in PRIMARY_INGREDIENTS]

        total_score = 0

        for i, recipe in enumerate(suggested_recipes, 1):
            meal_name = recipe.get("meal_name", "unknown")
            cuisine = recipe.get("cuisine_region", "unknown")

            # For CSV recipes use core_ingredients field only — not notes or substitutes
            # For Groq recipes use the ingredients list
            if recipe.get("ingredients"):
                # Groq recipe — ingredients is a list of strings
                recipe_ings = " ".join(recipe.get("ingredients", [])).lower()
            else:
                # CSV recipe — use core_ingredients field only, not notes/substitutes
                recipe_ings = str(recipe.get("core_ingredients", "")).lower()

            # Helper function for word boundary matching
            def _exact_match(ingredient: str, text: str) -> bool:
                """Match whole word only — prevents partial matches inside longer phrases."""
                import re
                pattern = r'\b' + re.escape(ingredient) + r'\b'
                return bool(re.search(pattern, text))

            # Check 1 — which user ingredients appear in recipe
            matched = [ing for ing in normalized_user if _exact_match(ing, recipe_ings)]
            missing = [ing for ing in normalized_user if not _exact_match(ing, recipe_ings)]
            ingredient_score = (len(matched) / len(normalized_user) * 100) if normalized_user else 0

            # Check 2 — primary ingredient present
            primary_present = any(_exact_match(ing, recipe_ings) for ing in primary_user)

            # Check 3 — East African origin
            ea_countries = {"kenya", "tanzania", "uganda", "rwanda", "burundi", "somalia"}
            is_east_african = any(c in cuisine.lower() for c in ea_countries)

            # Overall accuracy — heavy penalty if primary ingredient missing
            accuracy = ingredient_score
            if not primary_present and primary_user:
                accuracy -= 40
            accuracy = max(0, min(100, accuracy))
            total_score += accuracy

    def get_state(self) -> Dict:
        """Get current conversation state (for debugging/persistence)."""
        return {
            "current_recipe": self.current_recipe,
            "recipe_confirmed": self.recipe_confirmed,
            "awaiting_recipe_choice": self.awaiting_recipe_choice,
            "last_suggested_recipes": [r.get('meal_name', '') for r in self.last_suggested_recipes],
            "rejected_recipes": self.rejected_recipes,
            "conversation_history_length": len(self.llm.conversation_history),
        }
