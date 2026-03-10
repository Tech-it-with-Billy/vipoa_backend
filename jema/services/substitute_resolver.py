from typing import List, Dict, Optional
import pandas as pd

class SubstituteResolver:
    DEFAULT_SUBSTITUTES = {
        'peas': ['beans', 'lentils'],
        'milk': ['coconut milk', 'water'],
        'butter': ['oil'],
        'chicken': ['beef', 'goat', 'fish'],
        'beef': ['goat', 'chicken'],
        'tomatoes': ['tomato sauce', 'tomato paste'],
        'onion': ['garlic'],
        'spinach': ['kale', 'sukuma wiki'],
        'rice': ['maize', 'millet'],
    }

    def __init__(self, recipes_df: pd.DataFrame):
        self.recipes_df = recipes_df

    def get_substitutes(self, recipe_row: pd.Series, missing_ingredient: str) -> Optional[str]:
        substitutes_str = recipe_row.get('substitutes', '')
        if pd.notna(substitutes_str) and missing_ingredient.lower() in substitutes_str.lower():
            return substitutes_str
        return f"You can use {' or '.join(self.DEFAULT_SUBSTITUTES.get(missing_ingredient.lower(), []))} instead."

    def suggest_substitutions(self, recipe_row: pd.Series, missing_ingredients: List[str]) -> Dict[str, str]:
        suggestions = {}
        for ing in missing_ingredients:
            sub = self.get_substitutes(recipe_row, ing)
            if sub:
                suggestions[ing] = sub
        return suggestions

    @staticmethod
    def format_substitution_message(substitutions: Dict[str, str]) -> str:
        if not substitutions:
            return ""
        lines = ["Substitutions:"]
        for ing, sub in substitutions.items():
            lines.append(f"  • {ing.title()}: {sub}")
        return "\n".join(lines)
