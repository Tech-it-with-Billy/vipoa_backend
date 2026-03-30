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


def _build_personalisation_block(user_profile: dict) -> str:
    """
    Builds a personalisation instruction block injected into
    every Groq system prompt. Tells Groq exactly how to tailor
    the recipe for this specific user.
    Returns empty string if no meaningful profile data exists.
    """
    if not user_profile:
        return ""

    lines = [
        "═" * 50,
        "USER PROFILE — tailor this recipe to fit this user:",
        "═" * 50,
    ]

    # Goal
    goal = user_profile.get("goal")
    if goal:
        lines.append(f"Goal: {goal}")

    # Calorie target
    tdee = user_profile.get("tdee")
    if tdee:
        lines.append(
            f"Daily calorie target: ~{tdee} kcal "
            f"(adjust portions accordingly)"
        )

    # BMI
    bmi_category = user_profile.get("bmi_category")
    bmi = user_profile.get("bmi")
    if bmi_category and bmi:
        lines.append(f"BMI: {bmi} ({bmi_category})")

    # Diet
    diet = user_profile.get("diet")
    if diet:
        lines.append(f"Diet type: {diet}")

    # Cooking skills — adjust recipe complexity
    cooking_skills = user_profile.get("cooking_skills")
    if cooking_skills:
        skill_instructions = {
            "novice": (
                "Use simple techniques only. "
                "Explain every step in plain language. "
                "Avoid complex methods like braising or reduction."
            ),
            "basic": (
                "Keep steps clear and straightforward. "
                "Brief explanations are fine."
            ),
            "intermediate": (
                "You can include moderate techniques. "
                "Assume the user knows basic cooking terms."
            ),
            "advanced": (
                "Full complexity is fine. "
                "You may include advanced techniques and chef tips."
            ),
        }
        instruction = skill_instructions.get(
            cooking_skills.lower(), ""
        )
        if instruction:
            lines.append(f"Cooking skill: {cooking_skills}. {instruction}")

    # Eating reality
    eating_realities = user_profile.get("eating_realities")
    if eating_realities:
        reality_map = {
            "affordable": (
                "Prioritise low-cost, accessible ingredients. "
                "Suggest budget-friendly substitutes where possible."
            ),
            "fast": (
                "Prioritise recipes under 30 minutes. "
                "Suggest shortcuts where appropriate."
            ),
            "variety": (
                "Feel free to suggest interesting variations "
                "and creative serving ideas."
            ),
            "familiar": (
                "Stick to traditional, well-known cooking methods. "
                "Avoid unusual or unfamiliar ingredients."
            ),
        }
        for reality_key, reality_instruction in reality_map.items():
            if reality_key in eating_realities.lower():
                lines.append(f"Eating reality: {reality_instruction}")
                break

    # Halal
    if user_profile.get("is_halal"):
        lines.append(
            "STRICT HALAL: This recipe must be fully halal. "
            "No pork, no alcohol, no lard, no wine in cooking. "
            "Do not suggest any of these even as alternatives."
        )

    # Vegetarian
    if user_profile.get("is_vegan"):
        lines.append(
            "STRICT VEGAN: No meat, no fish, no dairy, "
            "no eggs, no honey, no animal products of any kind."
        )
    elif user_profile.get("is_vegetarian"):
        if user_profile.get("is_pescatarian"):
            lines.append(
                "PESCATARIAN: No meat or poultry. "
                "Fish and seafood are allowed."
            )
        else:
            lines.append(
                "VEGETARIAN: No meat, no poultry, no fish. "
                "Eggs and dairy are allowed."
            )

    # Medical conditions
    if user_profile.get("has_diabetes"):
        lines.append(
            "MEDICAL — DIABETES: Avoid high-GI ingredients "
            "(white rice, white bread, refined sugar, honey). "
            "Prefer high-fibre, low-GI alternatives. "
            "Mention this in your tips section."
        )

    if user_profile.get("has_hypertension"):
        lines.append(
            "MEDICAL — HYPERTENSION: Minimise sodium. "
            "Avoid salty sauces, stock cubes, and canned goods. "
            "Suggest low-sodium alternatives in your tips section."
        )

    other_conditions = [
        c for c in user_profile.get("medical_restrictions", [])
        if c not in ("diabetes", "hypertension", "none",
                     "no medical restrictions")
    ]
    if other_conditions:
        lines.append(
            f"Other medical conditions: {', '.join(other_conditions)}. "
            f"Be mindful of these when suggesting ingredients."
        )

    # Allergies
    allergies = [
        a for a in user_profile.get("allergies", [])
        if a not in ("no allergies", "none", "")
    ]
    if allergies:
        lines.append(
            f"ALLERGIES — strictly avoid: {', '.join(allergies)}. "
            f"Do not suggest these even as optional ingredients."
        )

    # Dislikes
    dislikes = [
        d for d in user_profile.get("dislikes", [])
        if d not in ("none", "no", "")
    ]
    if dislikes:
        lines.append(
            f"Dislikes — try to avoid: {', '.join(dislikes)}."
        )

    # Name personalisation
    name = user_profile.get("name")
    if name and name != "User":
        lines.append(f"Address the user as {name}.")

    lines.append("═" * 50)

    # If only the header and footer lines were added, no real
    # profile data exists — return empty to skip injection
    if len(lines) <= 3:
        return ""

    lines.append(
        "Always respect every restriction above. "
        "Never suggest an ingredient that conflicts with the "
        "user's allergies, religion, medical conditions, or diet. "
        "Adjust tips and serving suggestions to match their goal."
    )

    return "\n".join(lines)


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
ng Help users discover meals and prepare dishes from across the African continent — all African cuisines are welcome.

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

    def generate_african_recipe_from_ingredients(
        self,
        user_ingredients: List[str],
        exclude_names: List[str],
        count: int,
        language: str = "en"
    ) -> List[Dict]:
        """
        Generate authentic African recipe suggestions from ingredients across all African regions.
        
        Generates diverse recipes using Groq LLM from all African cuisines (not just East African).
        Excludes recipes already found in the database to prevent duplicates.
        Emphasizes variety — if multiple recipes fit, randomly select from different regions.
        
        Args:
            user_ingredients: List of normalized ingredient names (e.g., ["rice", "beef", "onion"])
            exclude_names: List of recipe names already found to exclude (e.g., ["Biriani"])
            count: Number of recipes to generate (typically 1, 2, or 3)
            language: "en" for English, "sw" for Swahili
        
        Returns:
            List of recipe dicts with keys: meal_name, cuisine_region, ingredients (list), steps (list)
            Returns empty list if generation fails or LLM is unavailable.
        
        Example:
            recipes = llm.generate_african_recipe_from_ingredients(
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
        
        # Build the prompt with strict rules for continental diversity
        prompt = f"""You are Jema, an expert African cooking assistant celebrating all African cuisines equally.

THE USER HAS EXACTLY THESE INGREDIENTS: {ingredients_str}

YOUR ONLY JOB: Suggest exactly {count} authentic African dish(es) where ALL of these ingredients are the PRIMARY components.

CRITICAL DIVERSITY REQUIREMENT: 
- You MUST suggest recipes from DIFFERENT African regions/countries
- If you suggest {count} recipes, try to represent {count} different countries/regions when possible
- DO NOT favor East Africa — give equal consideration to West Africa, Southern Africa, North Africa, Central Africa
- When multiple valid options exist, RANDOMLY select from different regions
- Example for {count}=2: one from West Africa AND one from East Africa, OR one from North Africa AND one from Southern Africa

BEFORE SUGGESTING ANYTHING run this check for each dish:
1. Does this dish use ALL of {ingredients_str} as main components?
2. Is this dish known by this exact name in its country without a country prefix?
3. If removing the country name leaves a meaningless description — REJECT it and find a real dish
4. Is this dish from a different region than other suggestions? (If yes, prioritize it)

REAL DISH NAME TEST — apply this test to every suggestion:
PASS examples — these are real recognized dish names from across Africa:
- Rolex ✅ recognized Ugandan name on its own
- Ugali Mayai ✅ recognized Kenyan name on its own
- Chapati Mayai ✅ recognized name on its own
- Pilau ✅ recognized East African name on its own
- Ndengu ✅ recognized Kenyan name on its own
- Biriani ✅ recognized Tanzanian name on its own
- Jollof Rice ✅ recognized West African name on its own
- Fufu ✅ recognized West African name on its own
- Peanut Butter Stew ✅ recognized name on its own
- Tagine ✅ recognized North African name on its own
- Pap ✅ recognized Southern African name on its own
- Couscous ✅ recognized North African name on its own
- Matoke ✅ recognized Ugandan name on its own

FAIL examples — these are invented names, never use them:
- Ugandan Rolex ❌ real name is just Rolex
- Kenyan Egg Stew ❌ invented description
- Ethiopian Scrambled Eggs ❌ not a real dish name
- West African Rice Bowl ❌ invented description
- Nigerian Beef Stew ❌ use real name if one exists
- Tanzanian Rice Dish ❌ invented description
- Ugandan Lentil Curry ❌ invented, use real dish names

INGREDIENT EXAMPLES FROM ACROSS AFRICA — use these as reference:
EAST AFRICAN options:
- eggs + onion + bell pepper → Ugali Mayai (Kenya), Rolex (Uganda), Chapati Mayai (Kenya)
- rice + beef + onion → Pilau (Kenya), Biriani (Tanzania/Kenya)
- beans + onion + tomato → Beans Stew (Kenya), Githeri (Kenya)
- chicken + onion + tomato → Kuku Mchuzi (Kenya), Kuku wa Kupaka (Tanzania)
- lentils + onion → Ndengu (Kenya), Misir Wot (Ethiopia)
- fish + coconut milk → Samaki wa Kupaka (Kenya/Tanzania)
- banana + meat → Matoke (Uganda), Katogo (Uganda)

WEST AFRICAN options:
- rice + tomato + onion + chicken → Jollof Rice (Nigeria/Ghana), Benachin (Senegal)
- groundnuts + chicken + onion → Peanut Butter Stew (West Africa), Groundnut Soup (Ghana)
- plantain + cassava → Fufu (Ghana/Nigeria), Cassava and Plantain (multiple West African countries)
- rice + black-eyed peas + onion → Hoppin' John variant (West Africa)

NORTH AFRICAN options:
- lamb + apricot + onion → Tagine (Morocco), Tajine (Algeria)
- chickpeas + couscous + onion → Couscous (Morocco/Algeria/Tunisia)
- chicken + preserved lemon → Chicken Tagine (Morocco)

SOUTHERN AFRICAN options:
- maize meal + water → Sadza (Zimbabwe/Botswana), Pap (South Africa)
- beef + onion + tomato → Potjiekos (South Africa), Beef Stew (Zimbabwe)

CONTINENTAL SELECTION RULE:
1. If you have East African + West African + Central/North/South African options, suggest one from EACH region
2. If you only have East African options, suggest East African
3. NEVER suggest multiple dishes from the same country unless absolutely necessary
4. Maximum 1 recipe per country — prefer diversity across countries

STRICT RULES:
1. NEVER invent a dish name by combining a country name with a generic food description
2. Every dish MUST use ALL of {ingredients_str} as primary components
3. Do NOT suggest any of these already found recipes: {exclude_str}
4. Do NOT suggest two dishes that are the same recipe with different spellings
5. Cuisine MUST be the specific country where this dish is genuinely known by locals
6. WHEN IN DOUBT about which of multiple valid recipes to suggest, RANDOMLY CHOOSE to ensure variety

FINAL CHECK before returning your answer:
- Are all dish names real recognized African names that exist without a country prefix?
- Do all dishes use ALL of {ingredients_str} as primary components?
- Are there any duplicates or invented names?
- Do the suggested recipes represent different African regions/countries when possible?

Return EXACTLY this plain text format repeated {count} time(s).
No JSON. No markdown. No preamble. Nothing before the first RECIPE_START:

RECIPE_START
Meal: <Real African Dish Name — no country prefix>
Cuisine: <Specific African Country>
Uses ingredients: <comma separated list of user ingredients this dish uses>

Introduction
<2 to 3 sentences describing the dish, its origin, and what makes it authentic>

Essential Ingredients

Starch: <quantity> <ingredient> (<preparation note>)
Protein: <quantity> <ingredient> (<preparation note>)
Aromatics: <quantity> <ingredient> (<prep note>)
Vegetables: <quantity> <ingredient> (<prep note>)
Spices: <quantity> <spice> (<note>)
Fat: <quantity> <oil or fat>
Optional: <ingredient> (<note>)

(Only include categories that have ingredients.)

Step-by-Step Cooking Instructions

1. <Step Title>: <Detailed instruction>
2. <Step Title>: <Detailed instruction>
3. <Step Title>: <Detailed instruction>
4. <Step Title>: <Detailed instruction>
5. <Step Title>: <Detailed instruction>
6. <Step Title>: <Detailed instruction>

Tips for Perfect <Meal Name>

<Tip 1>
<Tip 2>
Serve with: <Serving suggestion>
RECIPE_END"""
        
        try:
            self._wait_for_rate_limit()
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an expert at generating authentic African recipes in plain text format only. Prioritize continental diversity and avoid East African bias. When multiple options exist from different African regions, randomly select to ensure variety."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=1800,  # Reduced from 3000 (significant savings!)
                temperature=0.5  # Increased to 0.5 to encourage more randomization and diversity
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse plain text format with RECIPE_START and RECIPE_END markers
            recipes = self._parse_plain_text_recipes(response_text, count)
            return recipes
        
        except Exception as e:
            error_msg = str(e)
            print(f"LLM Error during recipe generation: {e}")
            
            # Handle rate limit errors gracefully
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print("Rate limit reached. Using fallback recipes.")
                return []  # Return empty list; caller will use database fallback
            
            return []
    
    def generate_east_african_recipe_from_ingredients(
        self,
        user_ingredients: List[str],
        exclude_names: List[str],
        count: int,
        language: str = "en"
    ) -> List[Dict]:
        """
        DEPRECATED: Use generate_african_recipe_from_ingredients instead.
        This method is kept for backwards compatibility.
        
        Now calls the continental diversity version that covers all African cuisines equally.
        """
        return self.generate_african_recipe_from_ingredients(
            user_ingredients=user_ingredients,
            exclude_names=exclude_names,
            count=count,
            language=language
        )
    
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
            
            # Parse ingredients (lines with category labels)
            elif mode == "ingredients":
                # Accept lines that start with a category label (followed by colon)
                if ":" in line_stripped:
                    # Remove leading asterisks and dashes, then parse
                    ing = line_stripped.lstrip("*-").strip()
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
            
            # Parse tips (remove asterisks and dashes)
            elif mode == "tips":
                if line_stripped and not line_stripped.startswith(("Serve", "serve")):
                    # Remove leading asterisks and dashes
                    tip = line_stripped.lstrip("*-").strip()
                    if tip and len(tip) > 5:
                        tips.append(tip)
                elif line_stripped.lower().startswith("serve"):
                    # Keep serve suggestion
                    tip = line_stripped.lstrip("*-").strip()
                    tips.append(tip)
        
        # Finish intro collection if still collecting
        if intro_text:
            introduction = " ".join(intro_text).strip()
        
        # Limit tips to 2-3 items max (keep first 3 items to ensure variety but controlled)
        tips = tips[:3]
        
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

    def generate_recipe(
        self,
        recipe_name: str,
        cuisine_region: str = "",
        language: str = "english",
        user_profile: dict = None,
        csv_row=None,
    ) -> str:
        """
        Generate a fully formatted recipe using grounded source hierarchy.
        Always uses Groq for consistent formatting of all recipes.
        
        1. PDF recipe store (verified African cookbook)
        2. Web search (Tavily - trusted African cooking sites)
        3. Groq standalone (flagged as AI-generated)
        
        Returns the formatted recipe as a string with exact structure:
        - "Great! Here's the recipe for [Name]"
        - Introduction paragraph
        - Cuisine: [Region]
        - Essential Ingredients (categorized)
        - Step-by-Step Cooking Instructions (numbered)
        - Tips for Perfect [Name]
        """
        if self.client is None:
            print("[generate_recipe] Groq client not initialized. Check GROQ_API_KEY.")
            return ""

        grounded_context = None
        source_label = None
        pdf_recipe = None

        # --- SOURCE 1: PDF COOKBOOK ---
        try:
            from jema.services.pdf_recipe_store import get_pdf_store
            pdf_store = get_pdf_store()

            # Check for compound meal first (e.g. Ugali Mayai = Ugali + Egg Stew)
            pdf_recipe = pdf_store.lookup_compound(recipe_name)

            # If not compound, check single recipe lookup
            if not pdf_recipe:
                pdf_recipe = pdf_store.lookup(recipe_name)

            if pdf_recipe and pdf_recipe.get("steps"):
                is_compound = pdf_recipe.get("is_compound", False)
                steps_text = "\n".join(pdf_recipe.get("steps", []))
                ingredients_text = pdf_recipe.get("ingredients_raw", "")
                
                grounded_context = (
                    f"VERIFIED SOURCE: African Recipes PDF Cookbook\n\n"
                    f"Ingredients:\n{ingredients_text}\n\n"
                    f"Steps:\n{steps_text}"
                )
                source_label = "PDF"
        except Exception as e:
            pass  # Silent fail, will try other sources

        # --- SOURCE 2: WEB SEARCH ---
        if not grounded_context:
            try:
                from jema.services.web_search_service import WebSearchService
                web_service = WebSearchService()
                if web_service.is_available():
                    web_result = web_service.search_recipe(recipe_name)
                    if web_result:
                        grounded_context = f"VERIFIED SOURCE: Web Search (Trusted African Cooking Sites)\n\n{web_result}"
                        source_label = "TAVILY"
            except Exception as e:
                pass  # Silent fail, will try Groq

        # --- SOURCE 3: GROQ STANDALONE (flagged) ---
        if not grounded_context:
            source_label = "GROQ"

        # --- BUILD SYSTEM PROMPT ---
        system_prompt = f"""You are Jema, a friendly African cooking assistant. Format every recipe EXACTLY like this:

[Introduction paragraph - 2-3 sentences about the dish, its origin, and significance]

Cuisine: [Country or Region]

Essential Ingredients

* Starch: [ingredient with amount, or none]
* Protein: [ingredient with amount, or none]
* Aromatics: [ingredient with amount, or none]
* Vegetables: [ingredient with amount, or none]
* Spices: [ingredient with amount, or none]
* Fat: [ingredient with amount, or none]
* Optional: [ingredient with amount, or none]

Step-by-Step Cooking Instructions

1. [Specific descriptive title]: [Clear instruction]
2. [Specific descriptive title]: [Clear instruction]
3. [Specific descriptive title]: [Clear instruction]
(Continue for 4-6 steps. Use descriptive titles like "Toast Spices", "Simmer Sauce", never just "Step 1")

Tips for Perfect {recipe_name}

* [Practical tip]
* [Practical tip]
* Serve with: [specific serving suggestion]

Let me know if you need any clarification on any step, or if you'd like to try something else!"""

        # --- BUILD USER PROMPT ---
        if source_label == "PDF":
            # PDF: Use ONLY the verified steps, no invention or expansion
            user_prompt = f"""You are formatting a recipe from a verified African cookbook into this EXACT structure:

[Introduction paragraph]

Cuisine: [Country]

Essential Ingredients

* Starch: [ingredient with amount]
* Protein: [ingredient with amount]
* Aromatics: [ingredient with amount]
* Vegetables: [ingredient with amount]
* Spices: [ingredient with amount]
* Fat: [ingredient with amount]
* Optional: [ingredient with amount]

Step-by-Step Cooking Instructions

1. [Descriptive Title]: [Clear instruction]
2. [Descriptive Title]: [Clear instruction]
(Continue for all steps with descriptive titles like "Toast Spices", "Simmer Sauce", NOT "Step 1", "Step 2")

Tips for Perfect {recipe_name}

* [Practical tip]
* [Practical tip]
* Serve with: [serving suggestion]

Let me know if you need any clarification on any step, or if you'd like to try something else!

Recipe Name: {recipe_name}
Cuisine Region: {cuisine_region or "East Africa"}
Language: {language}

{grounded_context}

INSTRUCTIONS:
- Use ONLY the ingredients and steps from the source above
- DO NOT add, remove, or change any steps
- DO NOT invent ingredients not in the source
- Organize ingredients into the category structure
- Use descriptive step titles (Toast Spices, Simmer Sauce, etc.) not generic "Step 1"
- Keep the original instructions intact but format for clarity
- Follow the exact format shown above"""

        elif source_label == "TAVILY":
            # Web: Expand into clear, actionable instructions
            user_prompt = f"""You are formatting a recipe from a web search result into this EXACT structure:

[Introduction paragraph]

Cuisine: [Country]

Essential Ingredients

* Starch: [ingredient with amount]
* Protein: [ingredient with amount]
* Aromatics: [ingredient with amount]
* Vegetables: [ingredient with amount]
* Spices: [ingredient with amount]
* Fat: [ingredient with amount]
* Optional: [ingredient with amount]

Step-by-Step Cooking Instructions

1. [Descriptive Title]: [Clear instruction]
2. [Descriptive Title]: [Clear instruction]
(Continue for all steps with descriptive titles like "Toast Spices", "Simmer Sauce", NOT generic steps)

Tips for Perfect {recipe_name}

* [Practical tip]
* [Practical tip]
* Serve with: [serving suggestion]

Let me know if you need any clarification on any step, or if you'd like to try something else!

Recipe Name: {recipe_name}
Cuisine Region: {cuisine_region or "East Africa"}
Language: {language}

{grounded_context}

INSTRUCTIONS:
- Use the ingredients and steps from the source above
- You may expand vague steps into clearer, more detailed instructions
- Organize ingredients into the category structure
- Use descriptive step titles (Toast Spices, Simmer Sauce, etc.) not generic "Step 1"
- Keep all original ingredients and steps but make instructions more actionable
- Follow the exact format shown above"""

        else:  # source_label == "GROQ"
            # Generate: Create a complete authentic recipe from scratch
            user_prompt = f"""Generate a complete authentic African recipe from scratch using this EXACT format:

[Introduction paragraph - 2-3 sentences about the dish and its origin]

Cuisine: {cuisine_region or "East Africa"}

Essential Ingredients

* Starch: [ingredient with amount]
* Protein: [ingredient with amount]
* Aromatics: [ingredient with amount]
* Vegetables: [ingredient with amount]
* Spices: [ingredient with amount]
* Fat: [ingredient with amount]
* Optional: [ingredient with amount]

Step-by-Step Cooking Instructions

1. [Descriptive Title]: [Clear instruction]
2. [Descriptive Title]: [Clear instruction]
3. [Descriptive Title]: [Clear instruction]
(Continue for 4-6 steps with descriptive titles like "Toast Spices", "Simmer Sauce", "Add Vegetables" - NOT "Step 1", "Step 2")

Tips for Perfect {recipe_name}

* [Practical, authentic tip]
* [Practical, authentic tip]
* Serve with: [specific serving suggestion]

Let me know if you need any clarification on any step, or if you'd like to try something else!

Recipe: {recipe_name}
Language: {language}

Make it authentic, practical, and easy to follow. Use only real, chef-verified tips (no hallucinated tips). Include amounts for all ingredients."""

        # Build personalisation block from user profile
        personalisation = _build_personalisation_block(user_profile)

        # Inject into system prompt
        if personalisation:
            system_prompt = system_prompt + f"\n\n{personalisation}"

        # --- CALL GROQ ---
        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            result = response.choices[0].message.content.strip()

            return result

        except Exception as e:
            print(f"[generate_recipe] Groq call failed: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _get_compound_intro(self, recipe_name: str, compound_recipe: dict) -> str:
        """
        Generate a brief introduction for a compound meal explaining
        that it consists of multiple components.
        """
        components = compound_recipe.get("components", [])
        if not components:
            return ""

        if len(components) == 2:
            return (
                f"{recipe_name.title()} is a complete East African meal "
                f"consisting of two components: {components[0]} and {components[1]}. "
                f"Both parts are prepared separately and served together "
                f"for a satisfying and nutritious meal."
            )
        else:
            parts = ", ".join(components[:-1]) + f" and {components[-1]}"
            return (
                f"{recipe_name.title()} is a complete meal consisting of: {parts}. "
                f"Each component is prepared separately and served together."
            )
    
    def _parse_recipe(self, text: str, cuisine_region: str = None, recipe_name: str = None) -> dict:
        """
        Parse structured recipe text returned by generate_recipe.
        Handles all section header variations Groq might return.
        Filters out instruction text and removes all asterisks/dashes.
        """
        # Filter out instruction lines that shouldn't appear in recipe output
        filter_phrases = [
            "use only these category",
            "all of these ingredients",
            "important: you must",
            "every step must",
            "category labels must",
            "only include categories",
            "skip empty categories"
        ]
        
        lines_filtered = []
        for line in text.split("\n"):
            should_skip = any(phrase in line.lower() for phrase in filter_phrases)
            if not should_skip:
                lines_filtered.append(line)
        
        text = "\n".join(lines_filtered)
        
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
            # Handle "Introduction" or "Intro" as section header
            if line_lower in ("introduction", "intro"):
                if intro_lines:
                    introduction = " ".join(intro_lines).strip()
                    intro_lines = []
                mode = "introduction"
                continue
            
            # Handle "[Introduction: text...]" format (on same line)
            if line_lower.startswith("[introduction:") or line_lower.startswith("introduction:"):
                intro_text = line.split(":", 1)[1].strip().rstrip("]").strip()
                if intro_text:
                    introduction = intro_text
                mode = "introduction"
                continue

            if ("essential ingredients" in line_lower or
                    line_lower.strip() == "ingredients"):
                if intro_lines and not introduction:
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
                if intro_lines and not introduction:
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
                    # Remove asterisks completely
                    ing = ing.replace("*", "").strip()
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
                    # Remove markdown bold/asterisks
                    cleaned = re.sub(r'\*\*', '', cleaned).strip()
                    # Remove trailing instruction text in parentheses (IMPORTANT:, Note:, etc.)
                    cleaned = re.sub(r'\s*[\(\[]?(IMPORTANT|NOTE|Note|Important):[^\)]*[\)\]]?\s*$', '', cleaned, flags=re.IGNORECASE).strip()
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
                    tip = tip.replace("*", "").strip()
                    if tip and len(tip) > 2:
                        tips.append(tip)
                elif tips and line:
                    continuation = line.replace("*", "").strip()
                    if continuation:
                        tips[-1] = tips[-1] + " " + continuation
                continue

        # Finalize introduction
        if intro_lines and not introduction:
            introduction = " ".join(intro_lines).strip()
        
        # Final cleanup: remove all asterisks from all fields and filter empty ingredients
        def clean_text(text):
            """Remove all asterisks and clean content."""
            if not text:
                return text
            text = text.replace("*", "").strip()
            return text
        
        # Clean ingredients: remove asterisks and filter empty category-only lines
        cleaned_ingredients = []
        for ing in ingredients:
            cleaned = clean_text(ing)
            # Don't include lines that are just category labels with no content
            if cleaned and not cleaned.endswith(":") and len(cleaned) > 2:
                cleaned_ingredients.append(cleaned)
        
        cleaned_steps = [clean_text(step) for step in steps]
        cleaned_tips = [clean_text(tip) for tip in tips]
        cleaned_intro = clean_text(introduction)

        return {
            "meal_name":      recipe_name or "",
            "cuisine":        cuisine,
            "cuisine_region": cuisine,
            "introduction":   cleaned_intro,
            "ingredients":    cleaned_ingredients,
            "steps":          cleaned_steps[:6],
            "tips":           cleaned_tips,
        }
        


