"""
Jema Engine - Central Orchestrator
Stateful, API-ready orchestration layer that handles all conversational logic.
This is the only class that API views should call.
"""

import os
import re
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


# Common East African recipes fallback (when not in database)
COMMON_RECIPES = {
    "Beef Stew with Rice": {
        "ingredients": ["rice", "beef", "onion", "tomato", "garlic", "oil", "spices"],
        "country": "East Africa",
        "description": "Hearty beef stew served with fluffy rice"
    },
    "Pilau": {
        "ingredients": ["rice", "onion", "tomato", "beef", "spices"],
        "country": "Kenya/Tanzania",
        "description": "Spiced rice dish cooked with meat and aromatic spices"
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
    }
}


class JemaEngine:
    """
    Central orchestrator for Jema conversations.
    Handles intent classification, recipe matching, and LLM orchestration.
    """

    def __init__(self, excel_path: Optional[str] = None):
        """
        Initialize the Jema Engine.
        
        Args:
            excel_path: Path to Excel recipe file. Defaults to packaged data.
        """
        # Determine Excel path
        if excel_path is None:
            excel_path = str(JEMA_DIR / "data" / "Jema_AI_East_Africa_Core_Meals_Phase1.xlsx")
        
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Recipe file not found: {excel_path}")
        
        # Load data once
        loader = DataLoader(excel_path)
        data = loader.load_all()
        self.recipes_df = data.get("recipes", pd.DataFrame())
        
        if self.recipes_df.empty:
            raise ValueError("No recipe data loaded from Excel file")
        
        # Initialize services
        self.matcher = ExcelRecipeMatcher(self.recipes_df)
        self.substitute_resolver = SubstituteResolver(self.recipes_df)
        self.llm = LLMService()
        self.language_detector = LanguageDetector()
        
        # Load all_ingred.csv for ingredient validation
        try:
            all_ingred_path = JEMA_DIR / "data" / "all_ingred.csv"
            if not all_ingred_path.exists():
                all_ingred_path = Path(__file__).parent.parent / "data" / "all_ingred.csv"
            if all_ingred_path.exists():
                all_ingred_df = pd.read_csv(all_ingred_path)
                # Build a set of known ingredients for fast lookup
                # Normalize to lowercase for matching
                self.known_ingredients = set(
                    all_ingred_df['ingredient'].str.lower().str.strip()
                    if 'ingredient' in all_ingred_df.columns
                    else []
                )
                # Also extract base words from compound names
                # e.g. "White rice (cooked)" → "rice"
                for ing in list(self.known_ingredients):
                    # Extract first meaningful word
                    base = re.sub(r'\(.*?\)', '', ing).strip()
                    base = re.split(r'\s+', base)[0].strip()
                    if len(base) > 2:
                        self.known_ingredients.add(base)
                print(f"Loaded {len(self.known_ingredients)} known ingredients from all_ingred.csv")
            else:
                self.known_ingredients = set()
                print("Warning: all_ingred.csv not found")
        except Exception as e:
            self.known_ingredients = set()
            print(f"Warning: Could not load all_ingred.csv: {e}")
        
        # Conversation state
        self.last_suggested_recipes: List[Dict] = []
        self.rejected_recipes: List[str] = []
        self.last_user_ingredients: set = set()
        self.current_recipe: Optional[Dict] = None
        self.recipe_confirmed: bool = False
        self.awaiting_recipe_choice: bool = False

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
        if community and intent in [Intent.MEAL_IDEA, Intent.INFORMATION, Intent.CHAT_SOCIAL, Intent.RECIPE_REQUEST]:
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
            message = f"I don't have specific recipes from the {community.title()} community in my database yet.\n\nBut I can help you with other East African dishes. What ingredients do you have?"
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
                response = "Hello! I'm Jema, your East African cooking assistant. Tell me what ingredients you have or what you'd like to cook!"
        
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
        selected_recipe = None
        
        # Try numeric selection (1, 2, 3...)
        try:
            choice_num = int(user_input.strip()) - 1
            if 0 <= choice_num < len(self.last_suggested_recipes):
                selected_recipe = self.last_suggested_recipes[choice_num]
        except ValueError:
            # Try name matching
            user_input_lower = user_input.lower()
            for recipe in self.last_suggested_recipes:
                name_lower = recipe.get('meal_name', '').lower()
                if name_lower and (name_lower in user_input_lower or user_input_lower in name_lower):
                    selected_recipe = recipe
                    break
        
        if selected_recipe:
            # Check if this is a common recipe (not from Excel database)
            if selected_recipe.get('is_common_recipe'):
                return self._display_common_recipe_with_llm(selected_recipe, user_input)
            else:
                return self._display_full_recipe(selected_recipe, user_input)
        
        # Clear flag if no match
        self.awaiting_recipe_choice = False
        return None

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
        prompt = f"Suggest 3-4 delicious traditional East African recipes{time_context}. Include the dish name and a brief description of why it's great. Keep it conversational and appetizing."
        
        response = self.llm.general_response(prompt, use_history=False, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_information(self, user_input: str) -> Dict:
        """Handle information/social chat."""
        response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _handle_recipe_request(self, user_input: str) -> Dict:
        """
        Handle direct recipe requests like 'How do I cook pilau?' or 'Give me a chapati recipe'.
        Always uses generate_recipe — never uses general_response for recipe requests.
        """
        # Extract recipe name from the request
        recipe_name = self._extract_recipe_name(user_input)

        if not recipe_name:
            response = self.llm.general_response(user_input, use_history=True, include_cta=True)
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", response)
            return self._build_response(response, [])

        # Clean the recipe name
        recipe_name = re.sub(r'[?!.,;:\'"()\[\]]', '', recipe_name).strip()

        if not recipe_name:
            response = self.llm.general_response(user_input, use_history=True, include_cta=True)
            return self._build_response(response, [])

        # Use _display_full_recipe which handles Groq enrichment
        recipe_data = {
            "meal_name":      recipe_name.title(),
            "cuisine_region": "East Africa",
            "ingredients":    [],
            "steps":          [],
            "introduction":   "",
            "tips":           [],
        }

        return self._display_full_recipe(recipe_data, user_input)

    def _handle_ingredient_based(self, user_input: str, constraints: List) -> Dict:
        """Handle ingredient-based recipe matching."""
        # Extract ingredients
        user_ingredients = IngredientNormalizer.extract_from_string(user_input)
        
        if not user_ingredients:
            response = self.llm.general_response(user_input, use_history=True, include_cta=False)
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", response)
            return self._build_response(response, [])
        
        # Validate ingredients against all_ingred.csv
        # Keep all ingredients — known ones are validated, unknown ones are passed to Groq
        # This ensures we never silently drop ingredients
        if self.known_ingredients:
            normalized_ingredients = [ing.lower().strip() for ing in user_ingredients]
            known = [i for i in normalized_ingredients if i in self.known_ingredients]
            unknown = [i for i in normalized_ingredients if i not in self.known_ingredients]
            if unknown:
                print(f"[INGREDIENT VALIDATION] Known: {known} | Unknown (passing to Groq): {unknown}")
            # Use all ingredients for matching — do not drop unknown ones
            # Unknown ingredients will be handled by Groq suggestion
        
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
        
        # Match recipes
        matches = active_matcher.match(
            user_ingredients=user_ingredients,
            user_constraints=user_constraints,
            min_match_percentage=0.4
        )
        
        # Exclude rejected recipes
        if self.rejected_recipes:
            matches = [m for m in matches if m.name not in self.rejected_recipes]
        
        if not matches:
            return self._handle_no_matches(user_ingredients, active_matcher, user_constraints, user_input)
        
        # Filter high-confidence matches
        good_matches = [m for m in matches if m.match_percentage >= 0.6]
        if not good_matches:
            good_matches = matches[:3]
        
        # Single match - show full recipe
        if len(good_matches) == 1:
            recipe_data = self.recipes_df[self.recipes_df['meal_name'] == good_matches[0].name].iloc[0]
            return self._display_full_recipe(recipe_data, user_input, user_ingredients)
        
        # Multiple matches - show options
        # Deduplicate matches by normalized name before displaying
        seen_names = set()
        deduped_matches = []
        for match in good_matches:
            normalized = self._normalize_recipe_name(match.name)
            if normalized not in seen_names:
                seen_names.add(normalized)
                deduped_matches.append(match)
        
        # Cap at 3 — never show more than 3 suggestions
        deduped_matches = deduped_matches[:3]
        
        options_list = []
        for i, match in enumerate(deduped_matches, 1):
            recipe_row = self.recipes_df[self.recipes_df['meal_name'] == match.name]
            if not recipe_row.empty:
                country = recipe_row.iloc[0].get('country', '') or recipe_row.iloc[0].get('cuisine_region', 'East Africa')
            else:
                country = 'East Africa'
            options_list.append(f"{i}. {match.name} – {country}")

        message = "Hey there, you could try one of the following:\n\n" + "\n".join(options_list)
        message += "\n\nWhich one would you like?"

        self.awaiting_recipe_choice = True
        self.last_suggested_recipes = []
        for m in deduped_matches:
            recipe_row = self.recipes_df[self.recipes_df['meal_name'] == m.name]
            if not recipe_row.empty:
                recipe_obj = recipe_row.iloc[0].to_dict()
                recipe_obj['match_percentage'] = round(m.match_percentage, 2)
                recipe_obj['missing_ingredients'] = m.missing_ingredients
                self.last_suggested_recipes.append(recipe_obj)

        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", message)

        return self._build_response(message, self.last_suggested_recipes)

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
        response = self.llm.general_response(user_input, use_history=True, include_cta=False)
        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", response)
        
        return self._build_response(response, [])

    def _display_full_recipe(self, recipe_data, user_input: str, user_ingredients: set = None) -> Dict:
        """
        Display a full recipe using Groq enrichment.
        Always calls generate_recipe to get rich output — never displays raw CSV data.
        Raw CSV data like 'Fry onions -> Simmer' is unacceptable output.
        """
        # Get recipe name and cuisine from whatever source we have
        if isinstance(recipe_data, dict):
            recipe_name   = recipe_data.get('meal_name') or recipe_data.get('name', '')
            cuisine_region = (recipe_data.get('cuisine_region') or
                             recipe_data.get('country') or
                             'East Africa')
            # Check if this recipe already has rich Groq data (from suggestion pipeline)
            existing_ingredients = recipe_data.get('ingredients', [])
            existing_steps       = recipe_data.get('steps', [])
            existing_intro       = recipe_data.get('introduction', '')
            existing_tips        = recipe_data.get('tips', [])
        else:
            # Pandas Series from CSV
            recipe_name    = recipe_data.get('meal_name', '')
            cuisine_region = (recipe_data.get('cuisine_region') or
                             recipe_data.get('country') or
                             'East Africa')
            existing_ingredients = []
            existing_steps       = []
            existing_intro       = ''
            existing_tips        = []

        if not recipe_name:
            return self._build_response("Could not find that recipe. Please try again.", [])

        # Check if we already have rich Groq data with 4+ steps
        # This happens when recipe came from generate_east_african_recipe_from_ingredients
        has_rich_data = (
            len(existing_steps) >= 4 and
            len(existing_ingredients) >= 3 and
            existing_intro
        )

        if has_rich_data:
            # Use existing rich data — no second Groq call needed
            recipe_dict = {
                "meal_name":      recipe_name,
                "cuisine_region": cuisine_region,
                "introduction":   existing_intro,
                "ingredients":    existing_ingredients,
                "steps":          existing_steps,
                "tips":           existing_tips,
            }
        else:
            # Recipe came from CSV with sparse data — enrich with Groq
            try:
                recipe_dict = self.llm.generate_recipe(
                    recipe_name=recipe_name,
                    cuisine_region=cuisine_region
                )
                if not recipe_dict:
                    raise ValueError("Empty response from generate_recipe")
            except Exception as e:
                print(f"LLM Error during recipe enrichment: {e}")
                # Build minimal response from CSV data as last resort
                recipe_dict = {
                    "cuisine":      cuisine_region,
                    "introduction": "",
                    "ingredients":  [],
                    "steps":        [],
                    "tips":         []
                }

        # Extract all fields
        cuisine      = recipe_dict.get('cuisine') or recipe_dict.get('cuisine_region') or cuisine_region
        introduction = recipe_dict.get('introduction', '')
        ingredients  = recipe_dict.get('ingredients', [])
        steps        = recipe_dict.get('steps', [])
        tips         = recipe_dict.get('tips', [])

        # Build the rich output
        output = f"\nGreat! Here's the recipe for {recipe_name}\n"

        if introduction:
            output += f"\n{introduction}\n"

        output += f"\nCuisine: {cuisine}\n"

        # Ingredients section
        output += "\nEssential Ingredients\n\n"
        for ing in ingredients:
            ing = str(ing).strip()
            if not ing.startswith("*"):
                ing = "* " + ing
            output += ing + "\n"

        # Steps section
        output += "\nStep-by-Step Cooking Instructions\n\n"
        for i, step in enumerate(steps[:6], 1):
            step = str(step).strip()
            step = re.sub(r'^\d+[\.\)]\s*', '', step).strip()
            step = re.sub(r'\*\*', '', step).strip()
            if not step.endswith((".", "!", "?")):
                step += "."
            output += f"{i}. {step}\n"

        # Tips section
        if tips:
            output += f"\nTips for Perfect {recipe_name}\n\n"
            for tip in tips:
                tip = str(tip).strip()
                if not tip.startswith("*"):
                    tip = "* " + tip
                output += tip + "\n"

        output += "\nLet me know if you need any clarification on any step, or if you'd like to try something else!\n"

        # Store as current recipe
        self.current_recipe = {
            "meal_name":      recipe_name,
            "cuisine_region": cuisine,
            "introduction":   introduction,
            "ingredients":    ingredients,
            "steps":          steps,
            "tips":           tips,
        }
        self.recipe_confirmed      = True
        self.awaiting_recipe_choice = False

        self.llm.add_to_history("user", user_input)
        self.llm.add_to_history("assistant", output)

        return self._build_response(output, [self.current_recipe])
    
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

    def _normalize_recipe_name(self, recipe_name: str) -> str:
        """Normalize recipe name for deduplication."""
        # Convert to lowercase and remove special characters
        normalized = recipe_name.lower().strip()
        # Remove articles and common prefixes
        normalized = re.sub(r'^(the|a|an|traditional|east african)\s+', '', normalized)
        # Normalize spacing
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized

    def _extract_recipe_name(self, user_input: str) -> Optional[str]:
        """Extract recipe name from user input."""
        user_input_lower = user_input.lower()
        
        # Common recipe request phrases
        phrases_to_remove = [
            'i would like to make',
            'i want to make',
            'recipe for',
            'how do i make',
            'how to make',
            'show me',
            'i would like',
            'i want',
            'what is',
            'tell me about',
            'ninataka',
            'make me',
            'give me',
            'gimme',
            'can i make',
            'how to cook',
            'cook',
        ]
        
        recipe_name = user_input_lower
        for phrase in phrases_to_remove:
            if phrase in recipe_name:
                recipe_name = recipe_name.replace(phrase, '')
                break
        
        recipe_name = recipe_name.strip()
        
        # If nothing left, try splitting on key words
        if not recipe_name or len(recipe_name) < 2:
            # Try to extract just the dish name
            words = user_input.split()
            if len(words) > 2:
                # Skip articles
                start_idx = 0
                for i, word in enumerate(words):
                    if word.lower() not in ['a', 'an', 'the', 'i', 'to', 'make', 'cook', 'how', 'do']:
                        start_idx = i
                        break
                recipe_name = ' '.join(words[start_idx:]).strip()
        
        # Clean punctuation
        recipe_name = re.sub(r'[?!.,;:\'"()\[\]]', '', recipe_name).strip()
        
        return recipe_name if recipe_name else None
