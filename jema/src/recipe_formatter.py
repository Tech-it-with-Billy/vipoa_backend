import re
from typing import List, Optional, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from llm_service import LLMService


class RecipeFormatter:
    """Format and display recipe information in a user-friendly way."""
    
    @staticmethod
    def _clean_step_text(step: str) -> str:
        """Soften formatting noise (quotes, bold markers) for a friendlier tone."""
        if pd.isna(step):
            return ""
        cleaned = str(step).strip()
        cleaned = re.sub(r'^\s*["\']+|["\']+\s*$', '', cleaned)
        cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned

    @staticmethod
    def _friendly_swap_text(variations: str, ingredients: str) -> str:
        """Turn a raw variations field into a conversational swap suggestion."""
        raw = str(variations).strip()
        if not raw:
            return ""
        first_option = raw.split(',')[0].strip().rstrip('.')
        if not first_option or first_option.lower() in {"-", "—", "n/a", "na", "none"}:
            return ""
        ingredients_lower = str(ingredients or '').lower()
        base_protein = None
        for protein in ["beef", "chicken", "fish", "goat", "lamb", "pork", "mutton", "turkey", "duck"]:
            if protein in ingredients_lower:
                base_protein = protein
                break
        first_option_lower = first_option.lower()
        if base_protein and first_option_lower == base_protein:
            return ""
        if base_protein and first_option_lower != base_protein:
            return f"You could use {first_option} instead of {base_protein}."
        return f"You could swap in {first_option} if you like."
    
    @staticmethod
    def parse_steps(recipe_text: str) -> List[str]:
        """
        Parse recipe text into individual steps.
        
        Handles various formats:
        - Arrow notation (→, ->, -->)
        - Numbered steps (1., 2., 1), 2), Step 1:, etc.)
        - Bulleted steps (-, *, •)
        - Paragraph breaks (double newlines)
        
        Args:
            recipe_text: Raw recipe instructions text
            
        Returns:
            List of individual step strings
        """
        if pd.isna(recipe_text) or not str(recipe_text).strip():
            return []
        
        text = str(recipe_text).strip()
        steps = []
        
        # Pattern 0: Arrow-based steps (→, ->, -->)
        if '→' in text or '->' in text or '-->' in text:
            # Replace arrow variants with a common separator
            text = text.replace('→', '|||').replace('-->', '|||').replace('->', '|||')
            parts = text.split('|||')
            steps = [step.strip() for step in parts if step.strip()]
        
        # Pattern 1: Numbered steps (1. Step, 2. Step, etc.)
        elif re.search(r'(?:^|\n)\s*(?:\d+[\.\)]\s*|Step\s+\d+:?\s*)', text):
            parts = re.split(r'(?:^|\n)\s*(?:\d+[\.\)]\s*|Step\s+\d+:?\s*)', text)
            steps = [step.strip() for step in parts if step.strip()]
        
        # Pattern 2: Bulleted steps (-, *, •)
        elif re.search(r'(?:^|\n)\s*[-*•]\s+', text):
            parts = re.split(r'(?:^|\n)\s*[-*•]\s+', text)
            steps = [step.strip() for step in parts if step.strip()]
        
        # Pattern 3: Split by multiple newlines (paragraphs)
        elif '\n\n' in text:
            steps = [step.strip() for step in text.split('\n\n') if step.strip()]
        
        # Pattern 4: Split by single newlines if they start sentences
        elif '\n' in text:
            potential_steps = text.split('\n')
            # Keep lines that look like steps (start with capital or action verb)
            steps = [s.strip() for s in potential_steps 
                    if s.strip() and (s.strip()[0].isupper() or len(s.strip()) > 20)]
        
        # If no patterns matched, treat entire text as one step
        if not steps:
            steps = [text]
        
        return steps
    
    @staticmethod
    def format_steps(steps: List[str], numbered: bool = True) -> str:
        """
        Format steps with nice numbering and spacing.
        
        Args:
            steps: List of step strings
            numbered: Whether to add step numbers
            
        Returns:
            Formatted string with all steps
        """
        if not steps:
            return ""
        
        clean_steps = [RecipeFormatter._clean_step_text(step) for step in steps if str(step).strip()]
        if not clean_steps:
            return ""
        
        formatted = []
        for i, step in enumerate(clean_steps, 1):
            if numbered:
                formatted.append(f"{i}) {step}")
            else:
                formatted.append(f"• {step}")
        
        return "\n\n".join(formatted)
    
    @staticmethod
    def format_ingredients(ingredients_str: str, include_note: bool = True) -> str:
        """
        Format ingredient list for better display.
        
        Args:
            ingredients_str: Comma-separated ingredients
            include_note: Whether to add note about basic seasonings
            
        Returns:
            Formatted ingredient list
        """
        if pd.isna(ingredients_str) or not str(ingredients_str).strip():
            return "No ingredients listed"
        
        ingredients = [ing.strip() for ing in str(ingredients_str).split(',') if ing.strip()]
        
        if not ingredients:
            return "No ingredients listed"
        
        formatted_list = "\n".join(f"  • {ing.title()}" for ing in ingredients)
        
        # Add note about basic seasonings if the list is minimal
        if include_note and len(ingredients) <= 2:
            formatted_list += "\n  • Salt, oil, and spices (as needed)"
        
        return formatted_list
    
    @staticmethod
    def format_recipe_display(recipe_details: dict, include_steps: bool = True, 
                             llm_service: Optional['LLMService'] = None, 
                             enhance_steps: bool = True,
                             user_requested: bool = False) -> str:
        """
        Create a beautifully formatted recipe display.
        
        Args:
            recipe_details: Recipe dictionary from RecipeEngine
            include_steps: Whether to include cooking steps
            llm_service: Optional LLM service for enhancing steps
            enhance_steps: Whether to use LLM to enhance brief steps
            user_requested: Whether user specifically asked for this recipe
            
        Returns:
            Formatted string ready for display
        """
        output = []

        name = str(recipe_details.get('name', 'this recipe')).strip() or "this recipe"
        country = str(recipe_details.get('country', '')).strip()
        meal_type_raw = recipe_details.get('meal_type', '')
        # Handle NaN values properly
        meal_type = str(meal_type_raw).strip() if pd.notna(meal_type_raw) and str(meal_type_raw).lower() not in ['nan', 'none', ''] else ''

        intro_parts = []
        if user_requested:
            # User specifically asked for this recipe
            if name and country:
                intro_parts.append(f"Great choice! Here's how to make {name} from {country}")
            elif name:
                intro_parts.append(f"Great choice! Here's how to make {name}")
        else:
            # System is suggesting this recipe
            if name and country:
                intro_parts.append(f"You could try {name} from {country}")
            elif name:
                intro_parts.append(f"You could try {name}")
        if meal_type:
            intro_parts.append(f"it's a {meal_type} dish" if intro_parts else f"It's a {meal_type} dish")
        if not intro_parts:
            intro_parts.append("Here's a cozy recipe to try")
        output.append(" - ".join(intro_parts))

        # Ingredients
        output.append("")
        output.append("Ingredients to grab:")
        output.append(RecipeFormatter.format_ingredients(recipe_details.get('ingredients', '')))
        
        # Steps
        if include_steps:
            recipe_text = recipe_details.get('recipe', '')
            if recipe_text and not pd.isna(recipe_text):
                steps = RecipeFormatter.parse_steps(recipe_text)
                
                # Enhance steps with LLM if requested and available
                if enhance_steps and llm_service and steps:
                    try:
                        language = llm_service.current_language
                        ingredients = recipe_details.get('ingredients', '')
                        recipe_name = recipe_details.get('name', 'this dish')
                        steps = llm_service.enhance_recipe_steps(recipe_name, steps, ingredients, language)
                    except Exception as e:
                        # If enhancement fails, use original steps
                        pass
                
                output.append("")
                output.append("Let's cook it:")
                output.append(RecipeFormatter.format_steps(steps))
            else:
                output.append("")
                output.append("Let's cook it:")
                output.append("  Instructions not available")
        
        # Variations
        variations = recipe_details.get('variations', '')
        if variations and not pd.isna(variations) and str(variations).strip():
            swap_text = RecipeFormatter._friendly_swap_text(variations, recipe_details.get('ingredients', ''))
            if swap_text:
                output.append("")
                output.append("Swap idea:")
                output.append(f"  {swap_text}")
        
        return "\n".join(output)
    
    @staticmethod
    def format_recipe_summary(match_info: dict) -> str:
        """
        Format a compact recipe summary for listing multiple recipes.
        
        Args:
            match_info: Match dictionary from RecipeEngine.match_recipes()
            
        Returns:
            Formatted summary string
        """
        name = match_info.get('name', 'Unknown')
        country = match_info.get('country', '')
        match_pct = int(match_info.get('match_percentage', 0) * 100)
        missing = match_info.get('missing_names', [])
        
        summary = f"{name}"
        if country:
            summary += f" ({country})"
        
        summary += f" - {match_pct}% match"
        
        if missing:
            missing_count = len(missing)
            if missing_count <= 2:
                summary += f"\n   Missing: {', '.join(missing)}"
            else:
                summary += f"\n   Missing: {', '.join(missing[:2])} and {missing_count - 2} more"
        
        return summary
