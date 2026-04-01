"""
PDF Recipe Store Service
Extracts and stores African recipes from the PDF cookbook.
Filters out Caribbean/non-African dishes.
"""

import re
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
        Parse recipe blocks from extracted PDF text.
        Strategy: collect ALL numbered lines per recipe name match.
        """
        lines = text.split("\n")
        current_recipe = None
        buffer = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            lower = stripped.lower()

            # Skip Caribbean recipes immediately
            if any(c in lower for c in CARIBBEAN_RECIPES):
                current_recipe = None
                buffer = []
                continue

            # Detect recipe title
            matched = self._match_recipe_name(lower)
            if matched:
                # Save previous recipe before starting new one
                if current_recipe and buffer:
                    self._save_recipe(current_recipe, buffer)
                current_recipe = matched
                buffer = []
                continue

            # Accumulate lines for current recipe
            if current_recipe:
                buffer.append(stripped)

        # Save the final recipe
        if current_recipe and buffer:
            self._save_recipe(current_recipe, buffer)

    def _match_recipe_name(self, line: str) -> Optional[str]:
        """Check if line contains a known African recipe name."""
        # Check African recipes
        for name in AFRICAN_RECIPES:
            if name in line and len(line) < 80:  # Recipe titles are typically short
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

        Returns None if not a compound meal.
        """
        name_lower = recipe_name.lower().strip()
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
        Look up a recipe by name.
        
        Returns dict with meal_name, ingredients_raw, steps, tips.
        Returns None ONLY if recipe not found (not based on step count).
        Even recipes with few steps are returned to enable Tavily fallback.
        
        Args:
            recipe_name: Recipe name to look up
        
        Returns:
            Recipe dict if found, None if not found
        """
        if not recipe_name:
            return None
            
        key = recipe_name.lower().strip()
        
        # Direct match
        if key in self.recipes:
            return self.recipes[key]
        
        # Partial match — check if recipe name contains or is contained in search term
        for stored_name, data in self.recipes.items():
            if stored_name in key or key in stored_name:
                return data
        
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
