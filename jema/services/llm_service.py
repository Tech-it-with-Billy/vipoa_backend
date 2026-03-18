import os
import re
import json
from pathlib import Path
from typing import List, Dict, Optional
try:
    from groq import Groq
except ImportError:
    Groq = None
from jema.utils.language_detector import LanguageDetector

class LLMService:
    """Service to interact with LLM and manage conversation context for Jema."""

    def __init__(self):
        # Load .env manually from jema/.env
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()

        self.conversation_history: List[Dict[str, str]] = []
        self.current_language: str = 'english'
        self.client = None
        if Groq is None:
            print("Warning: Groq not installed; LLM features will use defaults.")
            return

        api_key = os.environ.get("GROQ_API_KEY", "api key")
        if not api_key:
            print("Warning: GROQ_API_KEY not found. LLM features disabled.")
            return

        try:
            self.client = Groq(api_key=api_key)
        except Exception as e:
            print(f"Warning: Failed to initialize Groq: {e}")
            self.client = None

        self.system_prompt_template = """You are Jema, a friendly East African cooking assistant. 
Help users discover meals and prepare dishes from Kenya, Uganda, Tanzania, Ethiopia, Rwanda, Burundi, South Sudan, and Swahili cuisine.

Style: short, simple, friendly, to the point. Plain text only.

{language_instruction}"""

        self.system_prompt = self.system_prompt_template.format(language_instruction="Respond in English.")

    def add_to_history(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

    def clear_history(self) -> None:
        self.conversation_history = []

    def update_language(self, text: str) -> None:
        detected_language = LanguageDetector.detect_language(text)
        if detected_language != self.current_language:
            self.current_language = detected_language
            instruction = LanguageDetector.get_language_instruction(detected_language)
            self.system_prompt = self.system_prompt_template.format(language_instruction=instruction)

    def get_conversation_context(self) -> List[Dict[str, str]]:
        return [{"role": "system", "content": self.system_prompt}] + self.conversation_history

    def general_response(self, user_input: str, use_history: bool = True, include_cta: bool = True) -> str:
        if use_history:
            self.add_to_history("user", user_input)
            messages = self.get_conversation_context()
        else:
            messages = [{"role": "user", "content": user_input}]
        if self.client is None:
            default = "I'm here to help you cook! Tell me a meal name or the ingredients you have."
            if use_history:
                self.add_to_history("assistant", default)
            return default
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                max_tokens=2000,
                temperature=0.7
            )
            assistant_msg = response.choices[0].message.content.strip()
            if use_history:
                self.add_to_history("assistant", assistant_msg)
            return assistant_msg
        except Exception as e:
            print(f"LLM Error: {e}")
            return "I'm here to help you cook! Tell me a meal name or the ingredients you have."

    def enhance_recipe_steps(self, recipe_name: str, steps: List[str], ingredients: str, language: str = 'english') -> List[str]:
        if not steps:
            return []
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
        prompt = f"""You are Jema, an East African cooking assistant.
Ingredients: {ingredients}
Recipe: {recipe_name}

Brief steps:
{steps_text}

Expand each step with clear instructions, timing, and tips."""
        if self.client is None:
            return steps
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Expand brief cooking steps into detailed instructions."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=1500,
                temperature=0.7
            )
            enhanced_text = response.choices[0].message.content.strip()
            enhanced_steps = []
            for line in enhanced_text.split('\n'):
                line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if line and len(line) > 10:
                    enhanced_steps.append(line)
            return enhanced_steps if enhanced_steps else steps
        except Exception as e:
            print(f"LLM Error during step enhancement: {e}")
            return steps

    def generate_east_african_recipe_from_ingredients(
        self,
        user_ingredients: List[str],
        exclude_names: List[str],
        count: int,
        language: str = "en"
    ) -> List[Dict]:
        """
        Generate East African recipe suggestions from ingredients.
        
        Generates recipes using Groq LLM constrained to East African cuisine.
        Excludes recipes already found in the database to prevent duplicates.
        
        Args:
            user_ingredients: List of normalized ingredient names (e.g., ["rice", "beef", "onion"])
            exclude_names: List of recipe names already found to exclude (e.g., ["Biriani"])
            count: Number of recipes to generate (typically 1, 2, or 3)
            language: "en" for English, "sw" for Swahili
        
        Returns:
            List of recipe dicts with keys: meal_name, cuisine_region, ingredients (list), steps (list)
            Returns empty list if generation fails or LLM is unavailable.
        
        Example:
            recipes = llm.generate_east_african_recipe_from_ingredients(
                user_ingredients=["rice", "beef", "onion"],
                exclude_names=["Biriani"],
                count=2,
                language="en"
            )
        """
        if self.client is None:
            return []
        
        # Prepare ingredients string
        ingredients_str = ", ".join(user_ingredients)
        
        # Prepare exclude string
        exclude_str = ", ".join(exclude_names) if exclude_names else "none"
        
        # Build the prompt with strict rules
        prompt = f"""You are Jema, an expert African cooking assistant with deep knowledge of East African, West African, and Southern African cuisine.

THE USER HAS EXACTLY THESE INGREDIENTS: {ingredients_str}

YOUR ONLY JOB: Suggest exactly {count} African dish(es) where ALL of these ingredients are used: {ingredients_str}

BEFORE YOU SUGGEST ANYTHING — run this check for each dish you are considering:
1. Does this dish use {ingredients_str} as its MAIN components?
2. If ANY of {ingredients_str} is missing from the dish — REJECT that dish and think of another
3. Only suggest the dish if ALL of {ingredients_str} appear as primary components

STRICT RULES:
1. Every dish MUST have a real recognized African name — do NOT invent names like "Ugandan Lentil Curry" or "Kenyan Beef Dish"
2. The dish MUST use ALL of {ingredients_str} as primary components
3. Do NOT suggest any of these already found recipes: {exclude_str}
4. Do NOT suggest two dishes that are the same recipe with different spellings
5. Cuisine region MUST be a specific African country
6. FIRST priority is East African dishes — only suggest broader African dishes if no East African dish fits
7. Steps must be exactly 4 to 7 practical home cooking steps each with a title

BANNED DISHES:
Ndizi Nyama, Sekela, Tibs, Doro Wot, Injera, Kitfo, Shakshuka, Mchuzi wa Pweza

Return EXACTLY this plain text format repeated {count} time(s).
No JSON. No markdown. Nothing before the first RECIPE_START:

RECIPE_START
Meal: <Real African Dish Name>
Cuisine: <Specific African Country>
Uses ingredients: <comma separated list of user ingredients this dish uses>

Introduction
<2 to 3 sentences describing the dish, its origin, and what makes it authentic>

Essential Ingredients

* Rice: <quantity> <ingredient> (<preparation note>)
* Protein: <quantity> <ingredient> (<preparation note>)
* Aromatics: <quantity> <ingredient> (<prep note>), <quantity> <ingredient> (<prep note>)
* Spices: <quantity> <spice mix> (<individual spices if relevant>)
* Liquid: <quantity> <liquid> (<alternative if any>)
* Fat: <quantity> <oil or fat>
* Optional: <ingredient> (<note>)

Use ONLY these category labels: Rice, Starch, Grain, Protein, Aromatics, Vegetables, Spices, Liquid, Fat, Optional
Every ingredient line MUST start with * and follow: * Category: quantity ingredient (note)
ALL of these ingredients MUST appear in the list: {ingredients_str}

Step-by-Step Cooking Instructions

1. <Step Title>: <Detailed instruction with technique and timing.>
2. <Step Title>: <Detailed instruction with technique and timing.>
3. <Step Title>: <Detailed instruction with technique and timing.>
4. <Step Title>: <Detailed instruction with technique and timing.>

Tips for Perfect <Meal Name>

* <Tip Label>: <Practical explanation>
* <Tip Label>: <Practical explanation>
* Serve with: <Serving suggestion>
RECIPE_END"""
        
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert at generating authentic East African recipes in plain text format only."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=3000,
                temperature=0.7
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse plain text format with RECIPE_START and RECIPE_END markers
            recipes = self._parse_plain_text_recipes(response_text, count)
            return recipes
        
        except Exception as e:
            print(f"LLM Error during recipe generation: {e}")
            return []
    
    def _parse_plain_text_recipes(self, text: str, expected_count: int) -> List[Dict]:
        """Parse plain text recipes in RECIPE_START...RECIPE_END format."""
        recipes = []
        
        # Split by RECIPE_START and RECIPE_END markers
        recipe_blocks = []
        current_pos = 0
        while True:
            start_idx = text.find("RECIPE_START", current_pos)
            if start_idx == -1:
                break
            end_idx = text.find("RECIPE_END", start_idx)
            if end_idx == -1:
                break
            
            recipe_text = text[start_idx + len("RECIPE_START"):end_idx].strip()
            recipe_blocks.append(recipe_text)
            current_pos = end_idx + len("RECIPE_END")
        
        # Parse each recipe block
        for block in recipe_blocks[:expected_count]:
            recipe = self._parse_single_recipe_block(block)
            if recipe:
                recipes.append(recipe)
        
        return recipes
    
    def _parse_single_recipe_block(self, block: str) -> Optional[Dict]:
        """Parse a single recipe block into a dict with meal_name, cuisine_region, introduction, ingredients, steps, tips."""
        lines = block.strip().split('\n')
        
        meal_name = ""
        cuisine_region = ""
        introduction = ""
        ingredients = []
        steps = []
        tips = []
        
        intro_text = []
        mode = None  # Tracks current parsing section: None, "intro", "ingredients", "steps", "tips"
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Parse meal name
            if line_stripped.startswith("Meal:"):
                meal_name = line_stripped.replace("Meal:", "").strip()
            
            # Parse cuisine/region
            elif line_stripped.startswith("Cuisine:"):
                cuisine_region = line_stripped.replace("Cuisine:", "").strip()
            
            # Parse "Uses ingredients:" line (from generate_east_african_recipe_from_ingredients prompt)
            elif line_stripped.startswith("Uses ingredients:"):
                continue  # Skip this line, we don't need it for storing
            
            # Detect "Introduction" section header
            elif line_stripped.lower() == "introduction":
                # Finish previous intro text collection if any
                if intro_text:
                    introduction = " ".join(intro_text).strip()
                    intro_text = []
                mode = "intro"
                continue
            
            # Detect "Essential Ingredients" section header
            elif "essential ingredients" in line_stripped.lower():
                # Finish intro if still collecting
                if intro_text:
                    introduction = " ".join(intro_text).strip()
                    intro_text = []
                mode = "ingredients"
                continue
            
            # Detect "Step-by-Step" section header
            elif "step" in line_stripped.lower() and ("cooking" in line_stripped.lower() or "instruction" in line_stripped.lower()):
                mode = "steps"
                continue
            
            # Detect "Tips" section header
            elif "tips for perfect" in line_stripped.lower():
                mode = "tips"
                continue
            
            # Collect introduction text
            elif mode == "intro":
                # Introduction lines are just descriptive text without special formatting
                if line_stripped and not line_stripped.startswith("*"):
                    intro_text.append(line_stripped)
            
            # Parse ingredients (lines starting with *)
            elif mode == "ingredients":
                if line_stripped.startswith("*"):
                    ing = line_stripped.lstrip("*").strip()
                    if ing:
                        ingredients.append(ing)
            
            # Parse steps (lines starting with numbers)
            elif mode == "steps":
                if line_stripped and line_stripped[0].isdigit():
                    # Extract step title and instruction
                    # Format: N. Title: instruction
                    if "." in line_stripped:
                        parts = line_stripped.split(".", 1)
                        if len(parts) > 1:
                            rest = parts[1].strip()
                            if ":" in rest:
                                title, instruction = rest.split(":", 1)
                                step_line = f"{title.strip()}: {instruction.strip()}"
                            else:
                                step_line = rest
                            if step_line:
                                steps.append(step_line)
            
            # Parse tips (lines starting with *)
            elif mode == "tips":
                if line_stripped.startswith("*"):
                    tip = line_stripped.lstrip("*").strip()
                    if tip:
                        tips.append(tip)
        
        # Finish intro collection if still collecting
        if intro_text:
            introduction = " ".join(intro_text).strip()
        
        # Return recipe if we have at least meal_name and basic content
        if meal_name and cuisine_region and ingredients and steps:
            return {
                "meal_name": meal_name,
                "cuisine_region": cuisine_region,
                "introduction": introduction,
                "ingredients": ingredients,
                "steps": steps,
                "tips": tips
            }
        
        return None

    def generate_recipe(self, recipe_name: str, cuisine_region: str = "") -> Dict:
        """
        Generate a detailed East African recipe using Groq.
        
        Returns a dict with keys: cuisine, introduction, ingredients, steps, tips
        """
        if self.client is None:
            return {}
        
        prompt = f"""You are Jema, an expert East African cooking assistant.

Generate a detailed authentic African recipe for: {recipe_name}
{"Cuisine region: " + cuisine_region if cuisine_region else ""}

Return the recipe in EXACTLY this format. Follow every section precisely.
Do not add extra sections. Do not skip any section. Do not use markdown:

Introduction
Write exactly 2 to 3 sentences describing this dish, its cultural significance,
and the key technique or ingredient that defines it. Be specific to the country
or region this dish comes from.

Cuisine: [Specific country name e.g. Kenya, Tanzania, Uganda]

Essential Ingredients

* [Category]: [quantity] [ingredient name] ([preparation note])
* [Category]: [quantity] [ingredient name] ([preparation note])
* [Category]: [quantity] [ingredient name] ([preparation note])
* [Category]: [quantity] [ingredient name] ([preparation note])
* [Category]: [quantity] [ingredient name] ([preparation note])
* [Category]: [quantity] [ingredient name] ([preparation note])
* Optional: [ingredient] ([preparation note])

Use ONLY these category labels:
Rice, Starch, Grain, Protein, Aromatics, Vegetables, Spices, Liquid, Fat, Optional

Each ingredient line MUST follow this pattern exactly:
* Category: quantity ingredient-name (preparation note)

Examples:
* Rice: 2 cups Basmati rice (soaked for 20–30 mins)
* Protein: 500g beef (cut into chunks)
* Aromatics: 2 large onions (finely sliced), 3 cloves garlic (minced), 1 tbsp ginger (grated)
* Spices (Pilau Masala): 2 tbsp pilau masala (or whole seeds: cumin, cardamom, cinnamon)
* Liquid: 4 cups beef broth (or water)
* Fat: 3 tbsp vegetable oil or ghee
* Optional: 2 potatoes (halved), fresh cilantro (for garnish)

Step-by-Step Cooking Instructions

1. [Step Title]: [Detailed instruction with technique, timing, and what to look for.]
2. [Step Title]: [Detailed instruction with technique, timing, and what to look for.]
3. [Step Title]: [Detailed instruction with technique, timing, and what to look for.]
4. [Step Title]: [Detailed instruction with technique, timing, and what to look for.]
5. [Step Title]: [Detailed instruction with technique, timing, and what to look for.]
6. [Step Title]: [Detailed instruction with technique, timing, and what to look for.]

Rules for steps:
- Provide exactly 4 to 7 steps
- Every step MUST have a title followed by a colon then the instruction
- Title must describe what the step does e.g. "Brown the Onions", "Add Spices", "Simmer and Steam"
- Include cooking times, heat levels, and visual cues in every step

Tips for Perfect [Recipe Name]

* [Tip label]: [Practical explanation]
* [Tip label]: [Practical explanation]
* [Tip label]: [Serving suggestion]

Rules for tips:
- Provide exactly 3 to 4 tips
- Every tip MUST have a label followed by a colon then the explanation
- Last tip must be a serving suggestion starting with "Serve with:"
"""
        
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert East African cooking assistant generating detailed recipes."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=3000,
                temperature=0.7
            )
            
            response_text = response.choices[0].message.content.strip()
            return self._parse_recipe(response_text)
        
        except Exception as e:
            print(f"LLM Error during recipe generation: {e}")
            return {}
    
    def _parse_recipe(self, text: str, cuisine_region: str = None) -> dict:
        """
        Parse the structured recipe text returned by Groq.

        Handles these sections in order:
        - Introduction (2-3 sentences before Cuisine line)
        - Cuisine: Country
        - Essential Ingredients (* Category: quantity ingredient (note))
        - Step-by-Step Cooking Instructions (N. Title: instruction)
        - Tips for Perfect [Name] (* Label: explanation)
        """

        cuisine = cuisine_region or "East Africa"
        introduction = ""
        ingredients = []
        steps = []
        tips = []
        mode = None

        lines = text.split("\n")

        for line in lines:
            line = line.strip()

            if not line:
                continue

            # ── Cuisine line ─────────────────────────────────────────────────────
            if line.lower().startswith("cuisine:"):
                cuisine = line.split(":", 1)[1].strip()
                mode = None
                continue

            # ── Section headers ───────────────────────────────────────────────────
            if line.lower().startswith("introduction"):
                mode = "introduction"
                continue

            if line.lower().startswith("essential ingredients"):
                mode = "ingredients"
                continue

            if line.lower().startswith("step-by-step") or line.lower().startswith("steps"):
                mode = "steps"
                continue

            if line.lower().startswith("tips for") or line.lower() == "tips":
                mode = "tips"
                continue

            # ── Content parsing by mode ───────────────────────────────────────────

            if mode == "introduction":
                # Collect introduction lines until we hit a section header
                if not line.lower().startswith(("cuisine:", "essential", "step", "tips")):
                    introduction += line + " "
                continue

            if mode == "ingredients":
                # Each ingredient line starts with * Category: ...
                if line.startswith("*"):
                    ingredient = line.lstrip("*").strip()
                    if ingredient:
                        ingredients.append(ingredient)
                continue

            if mode == "steps":
                # Each step starts with a number: "1. Title: instruction"
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                # Remove markdown bold markers
                cleaned = re.sub(r'\*\*', '', cleaned).strip()
                if cleaned:
                    steps.append(cleaned)
                continue

            if mode == "tips":
                # Each tip starts with * Label: explanation
                if line.startswith("*"):
                    tip = line.lstrip("*").strip()
                    if tip:
                        tips.append(tip)
                continue

        return {
            "cuisine": cuisine,
            "introduction": introduction.strip(),
            "ingredients": ingredients,
            "steps": steps[:7],
            "tips": tips
        }
        
