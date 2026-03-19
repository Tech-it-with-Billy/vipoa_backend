import os
import re
import json
import time
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
        self.response_cache: Dict[str, str] = {}  # Simple cache to avoid duplicate requests
        self.last_request_time = 0  # Rate limiting
        
        if Groq is None:
            print("Warning: Groq not installed; LLM features will use defaults.")
            return

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("Warning: GROQ_API_KEY environment variable not set. LLM features disabled.")
            print("Set GROQ_API_KEY in your .env file or environment variables.")
            return

        try:
            self.client = Groq(api_key=api_key)
        except Exception as e:
            print(f"Warning: Failed to initialize Groq: {e}")
            self.client = None

        self.system_prompt_template = """You are Jema, a friendly African cooking assistant. 
Help users discover meals and prepare dishes from Kenya, Uganda, Tanzania, Ethiopia, Rwanda, Burundi, South Sudan, and Swahili cuisine.

Style: short, simple, friendly, to the point. Plain text only.

{language_instruction}"""

        self.system_prompt = self.system_prompt_template.format(language_instruction="Respond in English.")

    def _wait_for_rate_limit(self):
        """Rate limiting helper to respect API limits."""
        min_interval = 0.2  # Minimum 0.2 seconds between requests
        elapsed = time.time() - self.last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_request_time = time.time()

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
            self._wait_for_rate_limit()
            response = self.client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                max_tokens=600,  # Reduced from 2000
                temperature=0.7
            )
            assistant_msg = response.choices[0].message.content.strip()
            if use_history:
                self.add_to_history("assistant", assistant_msg)
            return assistant_msg
        except Exception as e:
            error_msg = str(e)
            print(f"LLM Error: {error_msg}")
            
            # Handle rate limit errors gracefully
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                return "I'm temporarily at capacity. Please try again in a few minutes."
            
            return "I'm here to help you cook! Tell me a meal name or the ingredients you have."

    def enhance_recipe_steps(self, recipe_name: str, steps: List[str], ingredients: str, language: str = 'english') -> List[str]:
        if not steps:
            return []
        
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
        cache_key = f"{recipe_name}|{steps_text}"
        
        # Check cache first
        if cache_key in self.response_cache:
            cached_text = self.response_cache[cache_key]
            enhanced_steps = []
            for line in cached_text.split('\n'):
                line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if line and len(line) > 10:
                    enhanced_steps.append(line)
            return enhanced_steps if enhanced_steps else steps
        
        prompt = f"""Enhance these cooking steps briefly:
Ingredients: {ingredients}
Recipe: {recipe_name}

Steps:
{steps_text}

Return just the enhanced step numbers and instructions. Keep each step under 50 words."""
        
        if self.client is None:
            return steps
        try:
            self._wait_for_rate_limit()
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Enhance cooking steps concisely."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=800,  # Reduced from 1500
                temperature=0.7
            )
            enhanced_text = response.choices[0].message.content.strip()
            self.response_cache[cache_key] = enhanced_text  # Cache the response
            
            enhanced_steps = []
            for line in enhanced_text.split('\n'):
                line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if line and len(line) > 10:
                    enhanced_steps.append(line)
            return enhanced_steps if enhanced_steps else steps
        except Exception as e:
            error_msg = str(e)
            print(f"LLM Error during step enhancement: {error_msg}")
            
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                return steps  # Return original steps on rate limit
            
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
        prompt = f"""You are Jema, an expert African cooking assistant specializing in East African cuisine.

THE USER HAS EXACTLY THESE INGREDIENTS: {ingredients_str}

YOUR ONLY JOB: Suggest exactly {count} African dish(es) where ALL of these ingredients are the PRIMARY components.

BEFORE SUGGESTING ANYTHING run this check for each dish:
1. Does this dish use ALL of {ingredients_str} as main components?
2. Is this dish known by this exact name in its country without a country prefix?
3. If removing the country name leaves a meaningless description — REJECT it and find a real dish

REAL DISH NAME TEST — apply this test to every suggestion:
PASS examples — these are real recognized dish names:
- Rolex ✅ recognized Ugandan name on its own
- Ugali Mayai ✅ recognized Kenyan name on its own
- Chapati Mayai ✅ recognized name on its own
- Pilau ✅ recognized name on its own
- Ndengu ✅ recognized Kenyan name on its own
- Biriani ✅ recognized Tanzanian name on its own
- Kuku Mchuzi ✅ recognized Kenyan name on its own
- Matoke ✅ recognized Ugandan name on its own

FAIL examples — these are invented names, never use them:
- Ugandan Rolex ❌ real name is just Rolex
- Kenyan Egg Stew ❌ invented description
- Ethiopian Scrambled Eggs ❌ not a real dish name
- Eritrean Frittered Eggs ❌ completely invented
- Scotch Eggs with Sukuma Wiki ❌ invented fusion
- Egg and Vegetable Tagine ❌ Tagine is Moroccan not East African
- Kuku wa Nyama ❌ means chicken of meat which is nonsense
- Tanzanian Rice Dish ❌ invented description
- Ugandan Lentil Curry ❌ invented, use Ndengu instead

MANDATORY INGREDIENT MATCHING — use this to select the correct dish:
- eggs + onion + bell pepper → Ugali Mayai (Kenya), Rolex (Uganda), Chapati Mayai (Kenya)
- eggs + onion + tomato → Ugali Mayai (Kenya), Rolex (Uganda), Chapati Mayai (Kenya)
- eggs + onion → Ugali Mayai (Kenya), Rolex (Uganda), Chapati Mayai (Kenya)
- rice + beef + onion → Pilau (Kenya), Biriani (Tanzania), Rice and Beef Stew (Kenya)
- rice + chicken + onion → Pilau (Kenya), Kuku Mchuzi (Kenya), Biryani (Kenya)
- beans + onion + tomato → Beans Stew (Kenya), Githeri (Kenya), Maharagwe (Tanzania)
- chicken + onion + tomato → Kuku Mchuzi (Kenya), Kuku wa Kupaka (Kenya)
- lentils + onion → Ndengu (Kenya), Misir Wot (Ethiopia)
- potato + onion → Irio (Kenya), Mukimo (Kenya), Viazi Karai (Kenya)
- kale + onion → Sukuma Wiki (Kenya), Githeri (Kenya)
- fish + coconut milk → Samaki wa Kupaka (Kenya), Samaki wa Nazi (Tanzania)
- banana + meat → Matoke (Uganda), Katogo (Uganda)
- maize + beans → Githeri (Kenya), Muthokoi (Kenya)

PRIORITY ORDER:
1. FIRST — East African dishes from Kenya, Tanzania, Uganda, Rwanda, Burundi, Somalia
2. SECOND — broader African dishes only if no East African dish fits ALL of {ingredients_str}
3. NEVER suggest non-African dishes

STRICT RULES:
1. NEVER invent a dish name by combining a country name with a generic food description
2. Every dish MUST use ALL of {ingredients_str} as primary components
3. Do NOT suggest any of these already found recipes: {exclude_str}
4. Do NOT suggest two dishes that are the same recipe with different spellings
5. Cuisine MUST be the specific country where this dish is genuinely known by locals

FINAL CHECK before returning your answer:
- Are all dish names real recognized African names that exist without a country prefix?
- Do all dishes use ALL of {ingredients_str} as primary components?
- Are there any duplicates or invented names?

Return EXACTLY this plain text format repeated {count} time(s).
No JSON. No markdown. No preamble. Nothing before the first RECIPE_START:

RECIPE_START
Meal: <Real African Dish Name — no country prefix>
Cuisine: <Specific African Country>
Uses ingredients: <comma separated list of user ingredients this dish uses>

Introduction
<2 to 3 sentences describing the dish, its origin, and what makes it authentic>

Essential Ingredients

* Starch: <quantity> <ingredient> (<preparation note>)
* Protein: <quantity> <ingredient> (<preparation note>)
* Aromatics: <quantity> <ingredient> (<prep note>), <quantity> <ingredient> (<prep note>)
* Vegetables: <quantity> <ingredient> (<prep note>)
* Spices: <quantity> <spice> (<note>)
* Fat: <quantity> <oil or fat>
* Optional: <ingredient> (<note>)

Use ONLY these category labels: Starch, Grain, Protein, Aromatics, Vegetables, Spices, Liquid, Fat, Optional
Every ingredient line MUST start with * and follow: * Category: quantity ingredient (note)
ALL of these ingredients MUST appear in the list: {ingredients_str}

Step-by-Step Cooking Instructions

1. <Step Title>: <Detailed instruction with technique and timing.>
2. <Step Title>: <Detailed instruction with technique and timing.>
3. <Step Title>: <Detailed instruction with technique and timing.>
4. <Step Title>: <Detailed instruction with technique and timing.>
5. <Step Title>: <Detailed instruction with technique and timing.>
6. <Step Title>: <Detailed instruction with technique and timing.>

IMPORTANT: You MUST include exactly 4 to 6 steps. Never skip this section.
Every step MUST have a title followed by a colon then the instruction.

Tips for Perfect <Meal Name>

* <Tip Label>: <Practical explanation>
* <Tip Label>: <Practical explanation>
* Serve with: <Serving suggestion>
RECIPE_END"""
        
        try:
            self._wait_for_rate_limit()
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert at generating authentic East African recipes in plain text format only."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=1800,  # Reduced from 3000 (significant savings!)
                temperature=0.3
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse plain text format with RECIPE_START and RECIPE_END markers
            recipes = self._parse_plain_text_recipes(response_text, count)
            return recipes
        
        except Exception as e:
            error_msg = str(e)
            print(f"LLM Error during recipe generation: {error_msg}")
            
            # Handle rate limit errors gracefully
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print("Rate limit reached. Using fallback recipes.")
                return []  # Return empty list; caller will use database fallback
            
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
            
            # Detect "Step-by-Step" section header (multiple format variants)
            elif (line_stripped.lower().startswith("step-by-step") or
                  line_stripped.lower().startswith("steps") or
                  line_stripped.lower().startswith("cooking instructions") or
                  line_stripped.lower().startswith("instructions") or
                  "step-by-step" in line_stripped.lower()):
                mode = "steps"
                continue
            
            # Detect "Tips" section header
            elif ("tips for perfect" in line_stripped.lower() or
                  "tips for" in line_stripped.lower() or
                  line_stripped.lower().strip() == "tips" or
                  line_stripped.lower().startswith("tips")):
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
                if not line_stripped:
                    continue
                # Accept numbered lines: "1.", "1)", "Step 1:"
                is_numbered = bool(re.match(r'^\d+[\.\)]\s+', line_stripped))
                is_step_label = line_stripped.lower().startswith("step ")

                if is_numbered or is_step_label:
                    # Remove number prefix: "1. " or "1) "
                    cleaned = re.sub(r'^\d+[\.\)]\s*', '', line_stripped).strip()
                    # Remove "Step N:" prefix if present
                    cleaned = re.sub(r'^step\s*\d+[\.):]\*\s*', '', cleaned,
                                     flags=re.IGNORECASE).strip()
                    # Remove markdown bold markers
                    cleaned = re.sub(r'\*\*', '', cleaned).strip()
                    if cleaned and len(cleaned) > 5:
                        steps.append(cleaned)
                elif steps and line_stripped and not line_stripped.startswith(("*", "-", "Tips")):
                    # Continuation line — append to previous step
                    continuation = re.sub(r'\*\*', '', line_stripped).strip()
                    if continuation:
                        steps[-1] = steps[-1].rstrip(".") + " " + continuation
            
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
        
        prompt = f"""SYSTEM INSTRUCTION: You are Jema, an expert East African cooking assistant. You MUST return the recipe in the EXACT structured format shown below. Do NOT return prose paragraphs. Do NOT skip any section. Follow the format character by character.

Recipe: {recipe_name}
{"Cuisine: " + cuisine_region if cuisine_region else ""}

Return using EXACTLY this structure — all 4 sections are mandatory:

Introduction
[2 to 3 sentences about this dish — its country of origin, cultural significance, and the defining technique or ingredient.]

Cuisine: [Specific country e.g. Kenya, Tanzania, Uganda, Ethiopia]

Essential Ingredients

* Starch: [quantity] [ingredient] ([preparation note])
* Protein: [quantity] [ingredient] ([preparation note])
* Aromatics: [quantity] [ingredient] ([prep note]), [quantity] [ingredient] ([prep note])
* Spices: [quantity] [spice name] ([whole vs ground, alternatives])
* Liquid: [quantity] [liquid] ([alternative in brackets])
* Fat: [quantity] [oil or fat type]
* Optional: [ingredient] ([note])

INGREDIENT RULES:
- Category labels allowed: Starch, Grain, Protein, Aromatics, Vegetables, Spices, Liquid, Fat, Optional
- Every line starts with * then Category: quantity ingredient (note)
- Include ALL ingredients needed to cook this dish from scratch for 4 servings
- Be specific with quantities — never write "some" or "to taste" for main ingredients

Step-by-Step Cooking Instructions

1. [Step Title]: [2 sentences — what to do, how long, and what to look for when done.]
2. [Step Title]: [2 sentences — what to do, how long, and what to look for when done.]
3. [Step Title]: [2 sentences — what to do, how long, and what to look for when done.]
4. [Step Title]: [2 sentences — what to do, how long, and what to look for when done.]
5. [Step Title]: [2 sentences — what to do, how long, and what to look for when done.]
6. [Step Title]: [2 sentences — what to do, how long, and what to look for when done.]

Rules for steps:
- Include EXACTLY 4 to 6 steps — never fewer than 4
- Every step has a descriptive title followed by a colon
- Every step is exactly 2 sentences — one for what to do, one for timing or visual cue
- Steps must be in logical cooking order

Tips for Perfect {recipe_name}

* [Tip label]: [One practical sentence about technique or common mistake to avoid.]
* [Tip label]: [One practical sentence about ingredients or substitution.]
* Serve with: [Specific traditional accompaniment from this dish's country.]

TIP RULES:
- Include exactly 3 tips
- Every tip has a label followed by a colon
- Last tip MUST start with "Serve with:"

MANDATORY FINAL CHECK — verify before returning:
[ ] Introduction section present with 2-3 sentences
[ ] Essential Ingredients section present with * Category: format
[ ] Step-by-Step Cooking Instructions present with 4-6 numbered titled steps
[ ] Tips for Perfect {recipe_name} present with 3 tips
If any section is missing — write it before returning.
"""
        
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert African cooking assistant generating detailed recipes."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=3000,
                temperature=0.3
            )
            
            response_text = response.choices[0].message.content.strip()
            parsed = self._parse_recipe(response_text, cuisine_region)
            if not parsed.get("meal_name"):
                parsed["meal_name"] = recipe_name
            return parsed
        
        except Exception as e:
            print(f"LLM Error during recipe generation: {e}")
            return {}
    
    def _parse_recipe(self, text: str, cuisine_region: str = None) -> dict:
        """
        Parse structured recipe text returned by generate_recipe.
        Handles all section header variations Groq might return.
        """
        cuisine = cuisine_region or "East Africa"
        introduction = ""
        ingredients = []
        steps = []
        tips = []
        intro_lines = []
        mode = None

        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            line_lower = line.lower()

            # ── Cuisine ─────────────────────────────────────────────────────────────
            if line_lower.startswith("cuisine:"):
                cuisine = line.split(":", 1)[1].strip()
                mode = None
                continue

            # ── Section headers ─────────────────────────────────────────────────────
            if line_lower in ("introduction", "intro"):
                mode = "introduction"
                continue

            if ("essential ingredients" in line_lower or
                    line_lower.strip() == "ingredients"):
                if intro_lines:
                    introduction = " ".join(intro_lines).strip()
                    intro_lines = []
                mode = "ingredients"
                continue

            if (line_lower.startswith("step-by-step") or
                    "step-by-step" in line_lower or
                    line_lower.startswith("cooking instruction") or
                    line_lower.startswith("cooking steps") or
                    line_lower.strip() in ("steps", "instructions", "method",
                                           "cooking instructions",
                                           "step-by-step cooking instructions")):
                if intro_lines:
                    introduction = " ".join(intro_lines).strip()
                    intro_lines = []
                mode = "steps"
                continue

            if ("tips for" in line_lower or
                    line_lower.strip() == "tips" or
                    line_lower.startswith("tips")):
                mode = "tips"
                continue

            # Skip separator lines
            if line.strip() in ("---", "===", "***", ""):
                continue

            # ── Content by mode ─────────────────────────────────────────────────────

            if mode == "introduction":
                if not any(line_lower.startswith(h) for h in
                           ("cuisine:", "essential", "ingredient",
                            "step", "tips", "---")):
                    intro_lines.append(line)
                continue

            # If no mode yet and line looks like intro text — collect it
            # Only use continue if we actually added the line to intro_lines
            # Otherwise fall through to section header detection below
            if mode is None and line and not line.startswith("*"):
                if not any(line_lower.startswith(h) for h in
                           ("cuisine:", "essential", "ingredient",
                            "step", "tips", "---", "introduction")):
                    intro_lines.append(line)
                    continue
                # Line starts with a section keyword — fall through to section header detection

            if mode == "ingredients":
                if line.startswith(("*", "-")):
                    ing = line.lstrip("*-").strip()
                    ing = re.sub(r'\*\*', '', ing).strip()
                    if ing and len(ing) > 2:
                        ingredients.append(ing)
                continue

            if mode == "steps":
                is_numbered = bool(re.match(r'^\d+[\.\)]\s+', line))
                is_step_label = line_lower.startswith("step ")

                if is_numbered or is_step_label:
                    cleaned = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                    cleaned = re.sub(r'^step\s*\d+[\.\):]*\s*', '', cleaned,
                                     flags=re.IGNORECASE).strip()
                    cleaned = re.sub(r'\*\*', '', cleaned).strip()
                    if cleaned and len(cleaned) > 5:
                        steps.append(cleaned)
                elif steps and line and not line.startswith(("*", "-")):
                    if not any(line_lower.startswith(h) for h in
                               ("tips", "essential", "cuisine")):
                        continuation = re.sub(r'\*\*', '', line).strip()
                        if continuation:
                            steps[-1] = steps[-1].rstrip(".") + " " + continuation
                continue

            if mode == "tips":
                if line.startswith(("*", "-")):
                    tip = line.lstrip("*-").strip()
                    tip = re.sub(r'\*\*', '', tip).strip()
                    if tip and len(tip) > 2:
                        tips.append(tip)
                elif tips and line:
                    tips[-1] = tips[-1] + " " + line
                continue

        # Finalize introduction
        if intro_lines and not introduction:
            introduction = " ".join(intro_lines).strip()

        return {
            "meal_name":      "",
            "cuisine":        cuisine,
            "cuisine_region": cuisine,
            "introduction":   introduction,
            "ingredients":    ingredients,
            "steps":          steps[:6],
            "tips":           tips,
        }
        
