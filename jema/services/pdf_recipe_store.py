"""
PDF Recipe Store Service
Extracts and stores African recipes from the PDF cookbook.
Filters out Caribbean/non-African dishes.
"""

import re
import difflib
from pathlib import Path
from typing import Dict, List, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


PDF_PATH = Path(__file__).parent.parent / "data" / "25-African-and-Caribbean-Recipes.pdf"

# African recipes to extract from PDF
AFRICAN_RECIPES = [
    "egusi soup", "jollof rice", "pilau rice", "chapati",
    "curry potatoes", "atakilt wat", "lentil sambusa",
    "moin moin", "moroccan lentil salad", "lentil salad",
    "mafe", "mafé", "waakye", "suya", "peri peri chicken",
    "braised lamb shank", "key watt beef stew", "key wat",
    "chermoula fish", "kelewele", "puff puff", "mandazi"
]

# Caribbean/non-African dishes to exclude
CARIBBEAN_RECIPES = [
    "jerk shrimp", "jerk chicken", "curry goat",
    "rum cake", "festival dumplings", "mofongo"
]


class PDFRecipeStore:
    """Extract and store African recipes from PDF cookbook."""
    
    def __init__(self):
        self.recipes: Dict[str, Dict] = {}
        self._load_pdf()
        


    def _load_pdf(self):
        """Extract and store all African recipes from the PDF."""
        if pdfplumber is None:
            print("[PDFRecipeStore] pdfplumber not installed. PDF recipes will not be available.")
            return
            
        if not PDF_PATH.exists():
            print(f"[PDFRecipeStore] PDF not found at {PDF_PATH}. Skipping PDF recipe loading.")
            return
        
        try:
            with pdfplumber.open(PDF_PATH) as pdf:
                full_text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
            self._parse_recipes(full_text)
        except Exception as e:
            print(f"[PDFRecipeStore] Failed to load PDF: {e}")

    def _parse_recipes(self, text: str):
        """
        Parse recipe blocks from extracted PDF text using a strict buffer pattern.
        Each recipe name is paired only with the content that follows it, preventing offset bugs.
        """
        lines = text.split("\n")
        
        # Normalize recipe names for matching
        recipe_names_normalized = {name.lower().strip(): name for name in AFRICAN_RECIPES}
        exclude_names_normalized = {name.lower().strip() for name in CARIBBEAN_RECIPES}
        
        current_recipe_name = None
        current_recipe_buffer = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            line_lower = stripped.lower()
            
            # Check if this line contains a recipe name (exact match, not substring)
            matched_name = None
            for normalized_name, original_name in recipe_names_normalized.items():
                if line_lower == normalized_name or (line_lower.endswith(normalized_name) and len(line_lower) < 100):
                    # Further check: make sure the line is short (recipe titles are typically short)
                    if len(stripped.split()) <= 5:  # Most recipe titles are 1-4 words
                        matched_name = normalized_name
                        break
            
            # Check if line contains excluded names
            is_excluded = any(excl in line_lower for excl in exclude_names_normalized)
            
            if matched_name and not is_excluded:
                # Save the previous recipe before starting a new one
                if current_recipe_name and current_recipe_buffer:
                    self._save_recipe(current_recipe_name, current_recipe_buffer)
                
                # Start new recipe
                current_recipe_name = matched_name
                current_recipe_buffer = []
                continue
            
            # If we're in an excluded recipe, skip all lines until next recipe name
            if is_excluded:
                current_recipe_name = None
                current_recipe_buffer = []
                continue
            
            # Accumulate lines for current recipe
            if current_recipe_name is not None:
                current_recipe_buffer.append(stripped)
        
        # Save the final recipe
        if current_recipe_name and current_recipe_buffer:
            self._save_recipe(current_recipe_name, current_recipe_buffer)

    def _match_recipe_name(self, line: str) -> Optional[str]:
        """Check if line contains a known African recipe name (legacy - now handled in _parse_recipes)."""
        # This is kept for backward compatibility but is not used by the new buffer pattern
        line_lower = line.lower().strip()
        for name in AFRICAN_RECIPES:
            if name in line_lower and len(line_lower) < 80:
                return name
        return None

    # Compound meals — each key is the combined dish name
    # Each value lists the component recipes to look up and combine
    COMPOUND_MEALS = {
        "ugali mayai": ["ugali", "egg stew"],
        "ugali na mayai": ["ugali", "egg stew"],
        "chapati mayai": ["chapati", "egg filling"],
        "ugali na sukuma wiki": ["ugali", "sukuma wiki"],
        "ugali sukuma": ["ugali", "sukuma wiki"],
        "rice and beans": ["rice", "beans stew"],
        "wali na maharagwe": ["rice", "beans stew"],
        "rolex": ["chapati", "egg omelette"],
        "chapati na dengu": ["chapati", "ndengu"],
        "ugali na nyama choma": ["ugali", "nyama choma"],
        "ugali na samaki": ["ugali", "fish stew"],
        "ugali na dengu": ["ugali", "ndengu"],
        "rice and stew": ["rice", "beef stew"],
        "wali na mchuzi": ["rice", "beef stew"],
    }

    def lookup_compound(self, recipe_name: str) -> dict | None:
        """
        Check if recipe_name is a compound meal that requires
        combining two component recipes.

        Returns a combined recipe dict with:
        - All ingredients from both components
        - Steps from both components clearly separated
        - Tips from both components

        Returns None if not a compound meal or components cannot be found.
        """
        if not recipe_name:
            return None
            
        name_lower = recipe_name.lower().strip()

        # Guard: Reject invalid recipe name strings
        INVALID_LOOKUPS = {
            "for iftar", "for suhoor", "for eid", "for dinner",
            "for lunch", "for breakfast", "quickly", "dinner",
            "lunch", "breakfast", "meal", "dish", "recipe",
        }
        
        if name_lower in INVALID_LOOKUPS:
            return None
        
        components = self.COMPOUND_MEALS.get(name_lower)

        if not components:
            return None

        combined_ingredients = []
        combined_steps = []
        combined_tips = []
        found_components = []

        for component in components:
            component_recipe = self.lookup(component)
            if component_recipe:
                found_components.append(component.title())

                # Add section header for this component's ingredients
                combined_ingredients.append(
                    f"── {component.title()} ──"
                )
                combined_ingredients.extend(
                    component_recipe.get("ingredients_raw", "").split("\n")
                )

                # Add section header for this component's steps
                existing_step_count = len(combined_steps)
                combined_steps.append(
                    f"── {component.title()} Steps ──"
                )
                for step in component_recipe.get("steps", []):
                    # Renumber steps continuously
                    step_text = re.sub(r"^\d+[\.\)]\s*", "", step).strip()
                    step_num  = existing_step_count + len(combined_steps)
                    combined_steps.append(f"{step_num}. {step_text}")

                combined_tips.extend(component_recipe.get("tips", []))

        if not found_components:
            return None
        return {
            "meal_name":       recipe_name.title(),
            "is_compound":     True,
            "components":      found_components,
            "ingredients_raw": "\n".join(combined_ingredients),
            "steps":           combined_steps,
            "tips":            combined_tips,
        }

    def _save_recipe(self, name: str, lines: list):
        """
        Parse ingredients and steps from buffered lines.
        Only saves if this version has MORE steps than any previously
        saved version of the same recipe.

        This prevents page headers re-matching a recipe name and
        overwriting the full 11-step version with a 3-step partial.
        """
        ingredients = []
        steps = []
        tips = []
        found_steps = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if re.match(r"^\d+[\.\)]\s+.+", line):
                found_steps = True
                steps.append(line)
            elif found_steps and any(
                line.lower().startswith(t)
                for t in ("tip", "note", "serve", "hint")
            ):
                tips.append(line)
            elif not found_steps:
                ingredients.append(line)

        if not steps:
            return

        # Only overwrite if this version has MORE steps than existing
        existing = self.recipes.get(name)
        if existing and len(existing.get("steps", [])) >= len(steps):
            pass
            return

        self.recipes[name] = {
            "meal_name":        name.title(),
            "ingredients_raw":  "\n".join(ingredients),
            "steps":            steps,
            "tips":             tips,
        }

    def lookup(self, recipe_name: str) -> Optional[Dict]:
        """
        Look up a recipe by name with strict matching.
        
        Strategy:
        1. Guard against non-recipe strings (context words, meal timing phrases)
        2. Exact match (case-insensitive, whitespace trimmed)
        3. Close match with 0.75 cutoff and guards
        4. Return None if no match found
        
        Returns dict with meal_name, ingredients_raw, steps, tips.
        Returns None ONLY if recipe not found.
        """
        if not recipe_name:
            return None
        
        name_lower = (recipe_name or "").lower().strip()

        # Guard: Reject strings that are clearly NOT recipe names
        # These are context words that should never be looked up in the recipe database
        INVALID_LOOKUPS = {
            # Meal timing
            "for iftar", "for suhoor", "for eid", "for dinner",
            "for lunch", "for breakfast", "for brunch",
            "after the gym", "after work", "after school",
            # Generic meal words
            "quickly", "dinner", "lunch", "breakfast", "meal", "dish", "recipe",
            "tonight", "today", "something", "anything",
            # Question fragments
            "i can make", "in under 30 minutes", "a meat dish",
            "what do you recommend",
        }

        # Reject if name exactly matches an invalid lookup
        if name_lower in INVALID_LOOKUPS:
            return None

        # Reject if name starts with a preposition — recipe names never start with these
        first_word = name_lower.split()[0] if name_lower.split() else ""
        prepositions = {"for", "after", "before", "in", "at", "what", "how", "a", "an"}
        if first_word in prepositions:
            return None

        # Reject if name is 3 words or fewer and contains only common words
        words = name_lower.split()
        common = {"for", "the", "a", "an", "to", "in", "at", "on", "of",
                  "with", "and", "or", "dinner", "lunch", "breakfast",
                  "iftar", "suhoor", "quickly", "fast", "meal", "dish",
                  "meat", "chicken", "beef"}
        if len(words) <= 3 and all(w in common for w in words):
            return None
        
        query = name_lower
        
        # Step 1: Exact match
        for stored_name in self.recipes.keys():
            stored_name_lower = stored_name.strip().lower()
            if stored_name_lower == query:
                return self.recipes[stored_name]
        
        # Step 2: Close match with high threshold and guards
        stored_names = [str(name).strip().lower() for name in self.recipes.keys()]
        matches = difflib.get_close_matches(query, stored_names, n=1, cutoff=0.75)
        
        if matches:
            matched_lower = matches[0]
            
            # Guard 1: reject if length differs by more than 4 characters
            if abs(len(matched_lower) - len(query)) > 4:
                return None
            
            # Guard 2: reject if query has more words than matched name
            if len(query.split()) > len(matched_lower.split()) + 1:
                return None
            
            # Find the original recipe with matching name
            for original_name in self.recipes.keys():
                if original_name.strip().lower() == matched_lower:
                    return self.recipes[original_name]
        
        return None

    def get_all_recipes(self) -> List[str]:
        """Return list of all available African recipe names from PDF."""
        return list(self.recipes.keys())


# ── Module-level singleton ────────────────────────────────────────────────────
# PDF is parsed ONCE at startup, not on every recipe request.
# Use get_pdf_store() everywhere instead of PDFRecipeStore().
_pdf_store_instance = None


def get_pdf_store() -> "PDFRecipeStore":
    """
    Returns the shared PDFRecipeStore instance.
    Parses the PDF only once per process lifetime.
    """
    global _pdf_store_instance
    if _pdf_store_instance is None:
        _pdf_store_instance = PDFRecipeStore()
    return _pdf_store_instance
