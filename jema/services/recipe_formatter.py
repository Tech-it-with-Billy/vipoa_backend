import re
from typing import List, Optional
import pandas as pd
from jema.services.llm_service import LLMService

class RecipeFormatter:
    """Format and display recipes in a user-friendly way."""

    @staticmethod
    def _clean_step_text(step: str) -> str:
        if pd.isna(step):
            return ""
        cleaned = str(step).strip()
        cleaned = re.sub(r'^\s*["\']+|["\']+\s*$', '', cleaned)
        cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned

    @staticmethod
    def parse_steps(recipe_text: str) -> List[str]:
        if pd.isna(recipe_text) or not recipe_text.strip():
            return []
        text = str(recipe_text).strip()
        # Handle arrows
        for arrow in ['→', '->', '-->']:
            text = text.replace(arrow, '|||')
        steps = [s.strip() for s in text.split('|||') if s.strip()]
        if not steps:
            # Split by newlines
            steps = [s.strip() for s in text.split('\n') if s.strip()]
        return steps

    @staticmethod
    def format_steps(steps: List[str], numbered: bool = True) -> str:
        if not steps:
            return ""
        clean_steps = [RecipeFormatter._clean_step_text(s) for s in steps if s.strip()]
        formatted = []
        for i, step in enumerate(clean_steps, 1):
            if numbered:
                formatted.append(f"{i}) {step}")
            else:
                formatted.append(f"• {step}")
        return "\n\n".join(formatted)

    @staticmethod
    def format_ingredients(ingredients_str: str) -> str:
        if pd.isna(ingredients_str) or not ingredients_str.strip():
            return "No ingredients listed"
        ingredients = [ing.strip() for ing in ingredients_str.split(',') if ing.strip()]
        formatted_list = "\n".join(f"  • {ing.title()}" for ing in ingredients)
        if len(ingredients) <= 2:
            formatted_list += "\n  • Salt, oil, and spices (as needed)"
        return formatted_list

    @staticmethod
    def format_recipe_display(recipe_details: dict, llm_service: Optional[LLMService] = None, enhance_steps: bool = True) -> str:
        output = []
        name = recipe_details.get('name', 'this recipe')
        country = recipe_details.get('country', '')
        meal_type = recipe_details.get('meal_type', '')
        intro = f"{name} from {country}" if country else f"{name}"
        if meal_type:
            intro += f" - {meal_type} dish"
        output.append(intro)

        # Ingredients
        output.append("\nIngredients:")
        output.append(RecipeFormatter.format_ingredients(recipe_details.get('ingredients', '')))

        # Steps
        steps = RecipeFormatter.parse_steps(recipe_details.get('recipe', ''))
        if enhance_steps and llm_service:
            steps = llm_service.enhance_recipe_steps(name, steps, recipe_details.get('ingredients', ''))
        output.append("\nSteps:")
        output.append(RecipeFormatter.format_steps(steps))
        return "\n".join(output)
