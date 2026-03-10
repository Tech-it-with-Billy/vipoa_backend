"""
Excel-Aware Recipe Matcher
Scores and matches recipes based on Excel data (core_ingredients, cook_time, etc.)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
from jema.src.ingredient_normalizer_v2 import IngredientNormalizer


@dataclass
class ExcelRecipeScore:
    """Score for a recipe from Excel data"""
    recipe_id: int
    name: str
    country: str
    meal_type: str
    cook_time: Optional[int]
    
    # Scoring components
    ingredient_matches: int
    ingredient_misses: int
    assumed_missing: int
    
    # Scores
    match_percentage: float      # 0-1: ingredients user has
    ingredient_score: int        # Raw ingredient match score
    time_score: int              # +1 if quick, 0 otherwise
    total_score: int             # Overall ranking score
    
    # Info for display
    missing_ingredients: List[str]
    substitutes: Optional[str]


class ExcelRecipeMatcher:
    """Match user ingredients against Excel recipes"""
    
    def __init__(self, recipes_df: pd.DataFrame):
        """
        Initialize with recipes DataFrame.
        
        Args:
            recipes_df: DataFrame with columns: meal_name, core_ingredients, cook_time, country, etc.
        """
        self.recipes_df = recipes_df
    
    @staticmethod
    def score_recipe(
        recipe_row: pd.Series,
        user_ingredients: set,
        user_constraints: Dict = None,
        recipe_id: int = 0
    ) -> Optional[ExcelRecipeScore]:
        """
        Score a single recipe against user ingredients.
        
        Args:
            recipe_row: Row from recipes DataFrame
            user_ingredients: Set of normalized user ingredients
            user_constraints: Dict with 'meal_type', 'quick', etc.
            recipe_id: Index of recipe in DataFrame
            
        Returns:
            ExcelRecipeScore or None if scoring fails
        """
        try:
            # Extract recipe data
            recipe_name = recipe_row.get('meal_name', 'Unknown')
            core_ingredients_str = recipe_row.get('core_ingredients', '')
            country = recipe_row.get('country', '')
            meal_type = recipe_row.get('meal_type ', '')  # Note: trailing space in Excel
            cook_time = recipe_row.get('cook_time', None)
            substitutes = recipe_row.get('substitutes', '')
            
            # Handle NaN values
            if pd.isna(core_ingredients_str):
                return None
            if pd.isna(meal_type):
                meal_type = ''
            if pd.isna(cook_time):
                cook_time = None
            
            # Extract and normalize recipe ingredients (strict mode to catch unrecognized items)
            recipe_ingredients = IngredientNormalizer.extract_from_string(core_ingredients_str, strict=True)
            
            if not recipe_ingredients:
                return None
            
            # Calculate matches
            matches = recipe_ingredients & user_ingredients
            misses = recipe_ingredients - user_ingredients
            
            # IMPORTANT: Recipe must contain at least ONE user ingredient to be relevant
            if not matches:
                return None
            
            # Count assumed missing (salt, oil, water, etc.)
            assumed_missing_count = sum(
                1 for ing in misses 
                if IngredientNormalizer.is_assumed_ingredient(ing)
            )
            actual_missing = len(misses) - assumed_missing_count
            
            # Ingredient score: heavily favor recipes that USE user's ingredients
            # +5 per match (strong bonus for using what they have)
            # -2 per actual missing (minor penalty for needing extras)
            ingredient_score = (len(matches) * 5) - (actual_missing * 2)
            
            # Match percentage (exclude assumed ingredients from denominator)
            total_needed = len(recipe_ingredients) - assumed_missing_count
            if total_needed > 0:
                match_percentage = len(matches) / total_needed
            else:
                match_percentage = 1.0
            
            # Time score: +1 if cook_time <= 30 minutes
            time_score = 1 if (cook_time and cook_time <= 30) else 0
            
            # Constraint bonuses
            constraint_bonus = 0
            if user_constraints:
                if user_constraints.get('meal_type') and meal_type.lower() == user_constraints['meal_type'].lower():
                    constraint_bonus += 2
                if user_constraints.get('quick') and cook_time and cook_time <= 30:
                    constraint_bonus += 1
            
            # Total score
            total_score = ingredient_score + time_score + constraint_bonus
            
            # Get missing ingredient names (for display)
            missing_names = list(misses - {m for m in misses if IngredientNormalizer.is_assumed_ingredient(m)})
            
            return ExcelRecipeScore(
                recipe_id=recipe_id,
                name=recipe_name,
                country=country,
                meal_type=meal_type,
                cook_time=cook_time,
                ingredient_matches=len(matches),
                ingredient_misses=actual_missing,
                assumed_missing=assumed_missing_count,
                match_percentage=match_percentage,
                ingredient_score=ingredient_score,
                time_score=time_score,
                total_score=total_score,
                missing_ingredients=missing_names,
                substitutes=substitutes if not pd.isna(substitutes) else None
            )
        
        except Exception as e:
            print(f"Error scoring recipe {recipe_row.get('meal_name', 'Unknown')}: {e}")
            return None
    
    def match(
        self,
        user_ingredients: List[str],
        user_constraints: Dict = None,
        min_match_percentage: float = 0.5
    ) -> List[ExcelRecipeScore]:
        """
        Find and score all matching recipes.
        
        Args:
            user_ingredients: List of user's ingredients (raw strings)
            user_constraints: Dict with optional 'meal_type', 'quick', etc.
            min_match_percentage: Minimum match % to include (0-1)
            
        Returns:
            Sorted list of ExcelRecipeScore (best first)
        """
        # Normalize user ingredients
        normalized_user_ingredients = IngredientNormalizer.normalize_list(user_ingredients)
        
        if not normalized_user_ingredients:
            return []
        
        scores = []
        
        # Score all recipes
        for idx, recipe_row in self.recipes_df.iterrows():
            score = self.score_recipe(
                recipe_row,
                normalized_user_ingredients,
                user_constraints,
                recipe_id=idx
            )
            
            if score and score.match_percentage >= min_match_percentage:
                scores.append(score)
        
        # Sort by total_score (descending), then by match_percentage (descending)
        scores.sort(key=lambda s: (s.total_score, s.match_percentage), reverse=True)
        
        return scores
    
    def match_by_name(self, recipe_name: str) -> Optional[ExcelRecipeScore]:
        """
        Find a recipe by name.
        
        Args:
            recipe_name: Name of recipe to find
            
        Returns:
            ExcelRecipeScore or None
        """
        recipe_name_lower = recipe_name.lower().strip()
        
        for idx, recipe_row in self.recipes_df.iterrows():
            if recipe_row.get('meal_name', '').lower().strip() == recipe_name_lower:
                # For name-based lookup, just return basic score
                return self.score_recipe(recipe_row, set(), recipe_id=idx)
        
        return None
    
    def filter_by_country(self, country: str) -> 'ExcelRecipeMatcher':
        """
        Filter recipes to a specific country.
        
        Args:
            country: Country name
            
        Returns:
            New ExcelRecipeMatcher with filtered DataFrame
        """
        filtered_df = self.recipes_df[
            self.recipes_df['country'].str.lower() == country.lower()
        ]
        return ExcelRecipeMatcher(filtered_df)
    
    def filter_by_cook_time(self, max_minutes: int) -> 'ExcelRecipeMatcher':
        """
        Filter recipes by maximum cook time.
        
        Args:
            max_minutes: Maximum cooking time in minutes
            
        Returns:
            New ExcelRecipeMatcher with filtered DataFrame
        """
        filtered_df = self.recipes_df[
            (self.recipes_df['cook_time'].isna()) | 
            (self.recipes_df['cook_time'] <= max_minutes)
        ]
        return ExcelRecipeMatcher(filtered_df)
    
    def filter_by_meal_type(self, meal_type: str) -> 'ExcelRecipeMatcher':
        """
        Filter recipes by meal type (Main, Side, Appetizer, etc.).
        
        Args:
            meal_type: Type of meal
            
        Returns:
            New ExcelRecipeMatcher with filtered DataFrame
        """
        filtered_df = self.recipes_df[
            self.recipes_df['meal_type '].str.lower() == meal_type.lower()
        ]
        return ExcelRecipeMatcher(filtered_df)
    
    def filter_by_community(self, community: str) -> 'ExcelRecipeMatcher':
        """
        Filter recipes by community/ethnic group.
        
        Args:
            community: Community/ethnic group name (e.g., 'Kikuyu', 'Swahili')
            
        Returns:
            New ExcelRecipeMatcher with filtered DataFrame
        """
        if 'community' not in self.recipes_df.columns:
            return self  # No community column, return unfiltered
        
        filtered_df = self.recipes_df[
            self.recipes_df['community'].str.lower() == community.lower()
        ]
        return ExcelRecipeMatcher(filtered_df)
    
    def exclude_beverages(self) -> 'ExcelRecipeMatcher':
        """
        Filter out beverages (when user asks for "meals").
        
        Returns:
            New ExcelRecipeMatcher excluding beverages
        """
        if 'meal_type ' not in self.recipes_df.columns:
            return self
        
        filtered_df = self.recipes_df[
            self.recipes_df['meal_type '].str.lower() != 'beverage'
        ]
        return ExcelRecipeMatcher(filtered_df)
