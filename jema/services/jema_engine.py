"""
Jema Engine - Central Orchestrator
Stateful, API-ready orchestration layer that handles all conversational logic.
This is the only class that API views should call.
"""

import os
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
            message += f"\n\nWhich one would you like to try?"
            
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
        """Handle specific recipe requests (I want to make X)."""
        # Extract recipe query
        recipe_query = user_input.lower()
        for phrase in ['i would like to make', 'i want to make', 'recipe for', 'how do i make', 'show me', 'ninataka', 'i would like', 'i want']:
            recipe_query = recipe_query.replace(phrase, '').strip()
        
        # Try to split query by "and" to handle pairing requests (e.g., "ugali and greens")
        query_parts = [q.strip() for q in recipe_query.split(' and ')]
        found_recipes = []
        
        # Search database for each part
        for part in query_parts:
            part_matches = []
            for idx, recipe in self.recipes_df.iterrows():
                meal_name = recipe.get('meal_name', '')
                if pd.isna(meal_name):
                    continue
                meal_name_lower = str(meal_name).lower()
                # Exact or partial match
                if part in meal_name_lower or meal_name_lower in part:
                    part_matches.append(recipe)
            
            if part_matches:
                # Take best match for this part
                found_recipes.append(part_matches[0])
            elif len(query_parts) == 1:
                # Single dish not found - will generate via LLM below
                found_recipes = []
                break
        
        # If we found at least one recipe from the database
        if found_recipes:
            if len(found_recipes) == 1:
                # Single recipe found
                return self._display_full_recipe(found_recipes[0], user_input)
            else:
                # Multiple recipes found - display as a meal pairing
                return self._display_meal_pairing(found_recipes, user_input)
        else:
            # No database matches - Generate recipe for specific dish request using LLM
            # This handles requests like "rice and beef stew" or "ugali and greens"
            prompt = f"""Generate a complete traditional East African recipe for '{recipe_query}'. 

Provide:
1. Brief description (1-2 sentences)
2. Full ingredient list with quantities
3. Step-by-step cooking instructions (numbered)
4. 2-3 practical cooking tips

Format as plain text, no markdown. Be specific with measurements and timing."""

            llm_response = self.llm.general_response(prompt, use_history=False, include_cta=False)
            
            message = f"🍽️ {recipe_query.title()}\n\n{llm_response}"
            message += "\n\nLet me know if you need any clarification, or if you'd like to try something else!"
            
            # Lock in recipe
            self.current_recipe = {"meal_name": recipe_query.title()}
            self.recipe_confirmed = True
            self.awaiting_recipe_choice = False
            
            self.llm.add_to_history("user", user_input)
            self.llm.add_to_history("assistant", message)
            
            return self._build_response(message, [self.current_recipe])

    def _handle_ingredient_based(self, user_input: str, constraints: List) -> Dict:
        """Handle ingredient-based recipe matching."""
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
        options_list = []
        for i, match in enumerate(good_matches[:5], 1):
            missing_str = f" (add: {', '.join(match.missing_ingredients[:2])})" if match.missing_ingredients else ""
            options_list.append(f"{i}. {match.name} - {int(match.match_percentage * 100)}% match{missing_str}")
        
        message = "Here are some dishes you can make:\n\n" + "\n".join(options_list)
        message += "\n\nWhich one would you like to make?"
        
        self.awaiting_recipe_choice = True
        self.last_suggested_recipes = [
            self.recipes_df[self.recipes_df['meal_name'] == m.name].iloc[0].to_dict()
            for m in good_matches[:5]
        ]
        
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
            
            message = "You can make:\n\n" + "\n".join(recipe_list)
            message += "\n\nWhich one interests you? I can give you the recipe!"
            
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
                missing_str = f" (add: {', '.join(match.missing_ingredients[:3])})" if match.missing_ingredients else ""
                near_match_list.append(f"{i}. {match.name} - {int(match.match_percentage * 100)}% match{missing_str}")
            
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

    def _display_full_recipe(self, recipe_row, user_input: str, user_ingredients: Optional[set] = None) -> Dict:
        """Format and display a complete recipe."""
        recipe_data = recipe_row.to_dict() if not isinstance(recipe_row, dict) else recipe_row
        
        recipe_name = recipe_data.get('meal_name', 'Unknown')
        country = recipe_data.get('country', '')
        cook_time = recipe_data.get('cook_time', '')
        ingredients = recipe_data.get('core_ingredients', '')
        steps = recipe_data.get('recipes', '')
        
        recipe_msg = []
        
        # Relate user's ingredients if provided
        if user_ingredients and pd.notna(ingredients) and ingredients:
            recipe_ing_list = [s.strip() for s in str(ingredients).split(',') if s.strip()]
            recipe_ing_set = IngredientNormalizer.normalize_list(recipe_ing_list)
            have = sorted(list(recipe_ing_set.intersection(user_ingredients)))
            missing = [
                ing for ing in recipe_ing_set 
                if ing not in user_ingredients and not IngredientNormalizer.is_assumed_ingredient(ing)
            ]
            if have:
                recipe_msg.append(f"Great! Based on what you have ({', '.join(have)}), here's an easy recipe:")
            if missing:
                recipe_msg.append(f"(You may need: {', '.join(missing)})")
        
        # Header
        recipe_msg.append(f"\n{recipe_name}")
        if pd.notna(country) and country:
            recipe_msg.append(f"From: {country}")
        if pd.notna(cook_time) and cook_time:
            recipe_msg.append(f"Time: {cook_time} minutes")
        
        # Ingredients
        if pd.notna(ingredients) and ingredients:
            recipe_msg.append("\nIngredients")
            safe_ingredients = ingredients.replace('→', '->').replace('•', '-').replace('✓', '*')
            ingredient_list = [ing.strip() for ing in safe_ingredients.split(',')]
            for ing in ingredient_list:
                if ing:
                    recipe_msg.append(f"  * {ing}")
        
        # Steps
        if pd.notna(steps) and steps:
            recipe_msg.append("\nSteps")
            safe_steps = steps.replace('→', '->').replace('•', '-').replace('✓', '*')
            safe_steps = safe_steps.replace('Method: Fry', '').replace('Method: Stew', '').replace('Method: Boil', '')
            safe_steps = safe_steps.replace('Steps: ', '').replace('Time: ', '')
            safe_steps = safe_steps.replace('30–40 min', '').replace('35–45 min', '').replace('45–60 min', '').replace('20–30 min', '')
            
            step_list = [step.strip() for step in safe_steps.split('->')]
            step_num = 1
            for step in step_list:
                if step and step.lower() not in ['', 'fry', 'stew', 'boil'] and 'min' not in step.lower():
                    recipe_msg.append(f"  {step_num}. {step}")
                    step_num += 1
        
        # Tips from LLM
        recipe_msg.append("\nCooking Tips")
        tips_prompt = f"Give me 2-3 practical cooking tips for making {recipe_name} from East Africa. Include tips like timing, texture, common mistakes to avoid. Keep it brief (2-3 sentences each). No markdown, plain text."
        tips_response = self.llm.general_response(tips_prompt, use_history=False, include_cta=False)
        tip_lines = tips_response.strip().split('\n')
        for tip_line in tip_lines:
            if tip_line.strip():
                recipe_msg.append(f"  • {tip_line.strip()}")
        
        # Build final message
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
