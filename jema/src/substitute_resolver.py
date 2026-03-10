"""
Substitute Resolver
Suggests ingredient substitutes from Excel data
"""

from typing import List, Dict, Optional, Tuple
import pandas as pd


class SubstituteResolver:
    """Resolves ingredient substitutes from Excel"""
    
    # Common substitutions (fallback if Excel doesn't have substitutes column)
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
        """
        Initialize with recipes DataFrame.
        
        Args:
            recipes_df: DataFrame containing recipe data with substitutes column
        """
        self.recipes_df = recipes_df
    
    def get_substitutes(self, recipe_row: pd.Series, missing_ingredient: str) -> Optional[str]:
        """
        Get substitute suggestions for a missing ingredient in a recipe.
        
        Args:
            recipe_row: Row from recipes DataFrame
            missing_ingredient: The ingredient that's missing
            
        Returns:
            String of substitute suggestions or None
        """
        # First check Excel substitutes column
        substitutes_str = recipe_row.get('substitutes', '')
        
        if pd.notna(substitutes_str) and str(substitutes_str).strip():
            substitutes_str = str(substitutes_str).strip()
            # Check if the missing ingredient is mentioned in substitutes
            if missing_ingredient.lower() in substitutes_str.lower():
                return substitutes_str
        
        # Fall back to default substitutes
        missing_lower = missing_ingredient.lower().strip()
        if missing_lower in self.DEFAULT_SUBSTITUTES:
            suggestions = self.DEFAULT_SUBSTITUTES[missing_lower]
            return f"You can use {' or '.join(suggestions)} instead."
        
        return None
    
    def suggest_substitutions(
        self,
        recipe_row: pd.Series,
        missing_ingredients: List[str]
    ) -> Dict[str, str]:
        """
        Suggest substitutes for multiple missing ingredients.
        
        Args:
            recipe_row: Row from recipes DataFrame
            missing_ingredients: List of missing ingredient names
            
        Returns:
            Dict mapping missing ingredient → suggestion
        """
        suggestions = {}
        
        for ingredient in missing_ingredients:
            substitute = self.get_substitutes(recipe_row, ingredient)
            if substitute:
                suggestions[ingredient] = substitute
        
        return suggestions
    
    @staticmethod
    def format_substitution_message(substitutions: Dict[str, str]) -> str:
        """
        Format substitution suggestions for display.
        
        Args:
            substitutions: Dict from suggest_substitutions()
            
        Returns:
            Formatted message string
        """
        if not substitutions:
            return ""
        
        lines = ["You can make substitutions:"]
        for ingredient, suggestion in substitutions.items():
            lines.append(f"  • {ingredient.title()}: {suggestion}")
        
        return "\n".join(lines)
