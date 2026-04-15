import os
import re
import json
import time
import difflib
import logging
from pathlib import Path
from typing import List, Dict, Optional
try:
    from groq import Groq
except ImportError:
    Groq = None
from jema.utils.language_detector import LanguageDetector
from jema.services.profile_context import ProfileContext

logger = logging.getLogger(__name__)


def split_steps_paragraph(paragraph: str) -> list:
    """
    Split a paragraph of recipe steps into individual sentences or action blocks.
    Handles newline-separated, action-header-separated, and period-separated formats.
    """
    if not paragraph or not paragraph.strip():
        return []

    # Normalize all line endings first
    paragraph = paragraph.replace('\r\n', '\n').replace('\r', '\n')

    # Remove leading method/steps prefix e.g. "Method: Boil\nSteps:" or "Steps:"
    paragraph = re.sub(r'^(Method:[^\n]*\n)?Steps?:\s*', '', paragraph.strip(), flags=re.IGNORECASE)

    # Strategy 1: Newline-separated steps (Title: content\nTitle: content)
    lines = [line.strip() for line in paragraph.split('\n') if line.strip() and len(line.strip()) > 5]
    if len(lines) >= 3:
        return lines

    # Strategy 2: Paragraph with action-header pattern (Title: content. Title: content.)
    action_splits = re.split(r'(?<=\.)\s+(?=[A-Z][a-zA-Z\s\(\)]+:)', paragraph)
    action_steps = [s.strip() for s in action_splits if s.strip() and len(s.strip()) > 5]
    if len(action_steps) >= 3:
        return action_steps

    # Strategy 3: Plain sentence splitting (fallback)
    sentences = re.split(r'\.\s+', paragraph.strip())
    steps = []
    for s in sentences:
        s = s.strip()
        if s and len(s) > 5:
            if not s.endswith('.'):
                s = s + '.'
            steps.append(s)
    return steps



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
        
        # Initialize system prompt first (always needed)
        self.system_prompt_template = """You are Jema, a friendly African cooking assistant. 
Help users discover meals and prepare dishes from across the African continent — all African cuisines are welcome.

Style: short, simple, friendly, to the point. Plain text only.

{language_instruction}"""

        self.system_prompt = self.system_prompt_template.format(language_instruction="Respond in English.")
        
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

    def general_response(self, user_input: str, use_history: bool = True, include_cta: bool = True, user_profile: dict = None, ctx: ProfileContext = None) -> str:
        if use_history:
            self.add_to_history("user", user_input)
            messages = self.get_conversation_context()
        else:
            messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_input}]
        
        # Inject personalisation block from ProfileContext if available
        if ctx is not None:
            personalisation_block = ctx.build_personalisation_block()
            logger.debug(f"[JemaEngine] Personalisation block obtained — {len(personalisation_block)} chars")
            if personalisation_block:
                # Update the system prompt in the messages
                if messages and messages[0]["role"] == "system":
                    messages[0]["content"] = messages[0]["content"] + "\n\n" + personalisation_block
                else:
                    messages.insert(0, {"role": "system", "content": self.system_prompt + "\n\n" + personalisation_block})
        
        if self.client is None:
            default = "I'm here to help you cook! Tell me a meal name or the ingredients you have."
            if use_history:
                self.add_to_history("assistant", default)
            return default
        try:
            self._wait_for_rate_limit()
            logger.debug(f"[LLMService] LLM API call — model=llama-3.3-70b-versatile, system_prompt_length={len(messages[0]['content'] if messages else '')}, messages={len(messages)}")
            response = self.client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                max_tokens=600,  # Reduced from 2000
                temperature=0.7
            )
            assistant_msg = response.choices[0].message.content.strip()
            logger.debug(f"[LLMService] LLM response received — {len(assistant_msg)} chars")
            
            # Apply safety scan from ProfileContext if available
            if ctx is not None:
                assistant_msg = ctx.scan_response(assistant_msg)
            
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
            logger.debug(f"[LLMService] LLM API call — model=llama-3.3-70b-versatile, system_prompt_length=26, messages={len([{'role': 'system', 'content': 'Enhance cooking steps concisely.'}, {'role': 'user', 'content': prompt}])}")
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
            logger.debug(f"[LLMService] LLM response received — {len(enhanced_text)} chars")
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
            logger.debug(f"[LLMService] LLM API call — model=llama-3.3-70b-versatile, system_prompt_length=162, messages=2")
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
            logger.debug(f"[LLMService] LLM response received — {len(response_text)} chars")
            
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
                    # FIX 1: Additional cleanup for all asterisks before appending
                    cleaned = cleaned.replace("**", "").replace("*", "").strip()
                    if cleaned and len(cleaned) > 5:
                        steps.append(cleaned)
                elif steps and line_stripped and not line_stripped.startswith(("*", "-", "Tips")):
                    # Continuation line — append to previous step
                    continuation = re.sub(r'\*\*', '', line_stripped).strip()
                    if continuation:
                        steps[-1] = steps[-1].rstrip(".") + " " + continuation
            
            # Parse tips (remove asterisks and dashes, never include "Serve" suggestions)
            elif mode == "tips":
                # Skip "Serve with:" lines entirely — never collect them
                if line_stripped and not line_stripped.lower().startswith("serve"):
                    # Remove leading asterisks and dashes, then remove all remaining asterisks
                    tip = line_stripped.lstrip("*-").strip()
                    tip = tip.replace("*", "").strip()  # Remove all asterisks from the tip
                    if tip and len(tip) > 5:
                        tips.append(tip)
        
        # Finish intro collection if still collecting
        if intro_text:
            introduction = " ".join(intro_text).strip()
        
        # Limit tips to 2-3 items max (keep first 3 items to ensure variety but controlled)
        tips = tips[:3]
        
        # Filter ingredients to skip "none" values
        def clean_text_simple(text):
            """Remove all asterisks and clean content."""
            if not text:
                return text
            text = text.replace("*", "").strip()
            return text
        
        filtered_ingredients = []
        for ing in ingredients:
            cleaned = clean_text_simple(ing)
            if not cleaned:
                continue
            if cleaned.endswith(":"):
                continue
            # Skip lines where the value is none, n/a, dash, or empty
            if ":" in cleaned:
                value = cleaned.split(":", 1)[1].strip().lower()
                if value in ("none", "n/a", "-", "", "–"):
                    continue
            if len(cleaned) > 2:
                filtered_ingredients.append(cleaned)
        
        # Return recipe if we have at least meal_name and basic content
        if meal_name and cuisine_region and filtered_ingredients and steps:
            return {
                "meal_name": meal_name,
                "cuisine_region": cuisine_region,
                "introduction": introduction,
                "ingredients": filtered_ingredients,
                "steps": steps,
                "tips": tips
            }
        
        return None

    def generate_recipe(
        self,
        recipe_name: str,
        cuisine_region: str = "",
        language: str = "english",
        source: str = None,
        grounded_context: str = None,
        csv_steps: list = None,
        csv_ingredients: str = "",
        csv_row=None,
        user_profile: dict = None,
        compound_data: dict = None,
        variant_modifier: str = None,
    ) -> str:
        """
        Generate a fully formatted recipe using source-aware prompting.
        
        Args:
            recipe_name: The name of the recipe to generate/format
            cuisine_region: The region/country of the recipe
            language: Language for response ("english" or "swahili")
            source: One of "CSV", "PDF", "TAVILY", or "GROQ". If None, attempts source hierarchy.
            grounded_context: Raw ingredients and steps to format (used with CSV/PDF/TAVILY sources)
        
        Returns:
            Fully formatted recipe string in canonical format
        """
        if self.client is None:
            print("[generate_recipe] Groq client not initialized. Check GROQ_API_KEY.")
            return ""

        # Determine source if not explicitly provided
        if source is None:
            # Try PDF first
            try:
                from jema.services.pdf_recipe_store import get_pdf_store
                pdf_store = get_pdf_store()
                pdf_recipe = pdf_store.lookup_compound(recipe_name)
                if not pdf_recipe:
                    pdf_recipe = pdf_store.lookup(recipe_name)
                
                # Validate that the returned recipe actually matches the requested name
                if pdf_recipe:
                    returned_name = str(pdf_recipe.get("name", pdf_recipe.get('meal_name', ''))).strip().lower()
                    query_lower = recipe_name.strip().lower()
                    
                    # Calculate name similarity
                    name_similarity = difflib.SequenceMatcher(None, query_lower, returned_name).ratio()
                    
                    # Reject if too different (less than 50% similar)
                    if name_similarity < 0.5:
                        print(f"[PDF DEBUG] Rejected PDF result '{returned_name}' — too different from query '{query_lower}' (similarity: {name_similarity:.2f})")
                        pdf_recipe = None
                
                if pdf_recipe and pdf_recipe.get("steps"):
                    steps_text = "\n".join(pdf_recipe.get("steps", []))
                    ingredients_text = pdf_recipe.get("ingredients_raw", "")
                    grounded_context = f"Ingredients:\n{ingredients_text}\n\nSteps:\n{steps_text}"
                    source = "PDF"
            except Exception as e:
                pass
            
            # Try Tavily/Web search if PDF failed
            if source is None:
                try:
                    from jema.services.web_search_service import WebSearchService
                    web_service = WebSearchService()
                    if web_service.is_available():
                        web_result = web_service.search_recipe(recipe_name)
                        if web_result:
                            grounded_context = web_result
                            source = "TAVILY"
                except Exception as e:
                    pass

            # Fall back to Groq generation
            if source is None:
                source = "GROQ"

        # --- HANDLE CSV SOURCE WITH PASSED PARAMETERS ---
        if source == "CSV":
            if csv_steps and len(csv_steps) >= 1:
                # Build numbered steps text from the list
                steps_text = "\n".join(
                    f"{i+1}. {step}" for i, step in enumerate(csv_steps)
                )
                grounded_context = (
                    f"VERIFIED SOURCE: Jema CSV Database\n\n"
                    f"Ingredients:\n{csv_ingredients}\n\n"
                    f"Steps:\n{steps_text}"
                )
            else:
                print("[generate_recipe] WARNING: CSV source selected but csv_steps is empty. Falling through to GROQ.")
                source = "GROQ"

        # --- BUILD UNIFIED SYSTEM PROMPT ---
        system_prompt = """You are Jema, an African cooking assistant. Your only job is to format recipes.

ABSOLUTE RULES — no exceptions:
1. Never use asterisks anywhere in your response. Not in ingredients, not in tips, nowhere.
2. Never add bullet points. Tips are plain sentences on separate lines.
3. Never add a "Serve with:" line. It is culturally presumptuous. Remove it entirely.
4. Never add a disclaimer, footnote, or note saying the recipe is AI-generated or unverified.
5. Never invent ingredients. If a source provides the ingredients, use only those.
6. Never invent steps. If a source provides the steps, use only those.
7. Never invent cultural facts, origin stories, or translations you are not certain about.
8. If you do not know something, omit it rather than guessing.
9. Skip ingredient categories that have no value, no amount, or "none" — do not write "none", do not write the label.
10. Step titles must be descriptive actions: "Measure Flour", "Knead Dough", "Heat Pan" — never "Step 1" or generic labels."""

        # Helper function to build personalization instruction from user profile
        def build_personalization_instruction(user_profile: dict) -> str:
            """Build personalization rules based on user's dietary preferences from onboarding."""
            if not user_profile:
                return ""
            
            instructions = []
            
            # Allergies
            allergies = user_profile.get('allergies', '').strip()
            if allergies:
                allergies_list = [a.strip() for a in allergies.split(',') if a.strip()]
                instructions.append(f"ALLERGIES: User cannot eat: {', '.join(allergies_list)}. Do NOT include these ingredients. If they are in the base recipe, suggest appropriate substitutes.")
            
            # Medical restrictions
            restrictions = user_profile.get('medical_restrictions', '').strip()
            if restrictions:
                instructions.append(f"MEDICAL RESTRICTIONS: {restrictions}. Adapt the recipe accordingly.")
            
            # Dislikes
            dislikes = user_profile.get('dislikes', '').strip()
            if dislikes:
                dislikes_list = [d.strip() for d in dislikes.split(',') if d.strip()]
                instructions.append(f"DISLIKES: User dislikes: {', '.join(dislikes_list)}. Try to avoid or suggest alternatives.")
            
            # Diet type (vegan, vegetarian, etc.)
            diet = user_profile.get('diet', '').strip()
            if diet and diet.lower() not in ('none', 'no preference', 'omnivore'):
                diet_lower = diet.lower()
                if 'vegan' in diet_lower:
                    instructions.append("USER DIET: Vegan. Replace all animal products with plant-based alternatives.")
                elif 'vegetarian' in diet_lower:
                    instructions.append("USER DIET: Vegetarian. Remove or replace meat/fish with vegetarian alternatives.")
                elif 'halal' in diet_lower:
                    instructions.append("USER DIET: Halal. Use only halal-certified ingredients and preparation methods.")
                else:
                    instructions.append(f"USER DIET: {diet}. Adapt recipe accordingly.")
            
            # Cooking skill level (can affect complexity of instructions)
            cooking_skills = user_profile.get('cooking_skills', '').strip()
            if cooking_skills and cooking_skills.lower() not in ('none', 'intermediate'):
                if cooking_skills.lower() == 'beginner':
                    instructions.append("COOKING SKILL: Beginner. Use simple, clear instructions. Avoid advanced techniques.")
                elif cooking_skills.lower() == 'advanced':
                    instructions.append("COOKING SKILL: Advanced cook. You can assume familiarity with advanced techniques.")
            
            return "\n".join(instructions)
        
        personalization = build_personalization_instruction(user_profile)

        # --- BUILD SOURCE-SPECIFIC USER PROMPTS ---
        if source == "CSV":
            # Build variant instruction if modifier present
            variant_instruction = ""
            if variant_modifier:
                variant_instruction = f"\n\nIMPORTANT: The user has requested the {variant_modifier.upper()} version of this recipe. Replace the primary protein with {variant_modifier} throughout the ingredients and steps. Adjust cooking times and methods appropriately for {variant_modifier}. Do not use the original meat protein."
            
            # Build personalization instruction
            personalization_section = ""
            if personalization:
                personalization_section = f"\n\nPERSONALIZATION RULES:\n{personalization}"
            
            user_prompt = f"""You are formatting a recipe from the Jema CSV database into a specific structure.
The ingredients and steps below are the ONLY source of truth. Do not add, remove, or change any content.
Do not generate your own recipe. Do not guess. Use only what is provided below.{variant_instruction}{personalization_section}

CRITICAL: Do not use any markdown formatting anywhere in your response. Do not wrap step titles in double asterisks like **Title**. Write step titles in plain text followed by a colon only. Correct: "1. Prepare the Dough: Mix flour and water." Wrong: "1. **Prepare the Dough**: Mix flour and water." This rule applies to every single step without exception.

Recipe Name: {recipe_name}
Cuisine Region: {cuisine_region if cuisine_region else "East Africa"}
Language: {language}

{grounded_context}

FORMAT INSTRUCTIONS:
1. Write a 2-3 sentence introduction about the dish and its origin. No asterisks. Plain prose only.
2. Write: Cuisine: {cuisine_region if cuisine_region else "East Africa"}
3. Write: Essential Ingredients
4. List only ingredient categories that have actual values. Use these exact labels:
   Starch, Protein, Aromatics, Vegetables, Spices, Fat, Optional
   Skip any category with no ingredient. Do not write "none". No asterisks. Plain lines.
   Never list water as an ingredient — water is a cooking medium.
   Only include a category line if it has a real ingredient value after the colon.
5. Write: Step-by-Step Cooking Instructions
6. Take the numbered steps provided above and format each one with a descriptive title.
   Example: "1. Wash Ingredients: Wash the dehulled maize and pigeon peas until the water runs clear."
   Use titles like "Wash Ingredients", "Boil Maize and Peas", "Build the Sauce", "Simmer and Garnish".
   Do not merge steps. Do not drop steps. Do not add steps not in the source.
   No asterisks.
7. Write: Tips for Perfect {recipe_name}
8. Write exactly 2 practical tips as plain sentences. No asterisks. No dashes. No "Serve with:" line.
9. End with exactly this line:
   Let me know if you need any clarification on any step, or if you'd like to try something else!
"""

        elif source == "PDF":
            user_prompt = f"""You are formatting a recipe from a verified African cookbook. The steps and ingredients below are correct. Do not add or remove content. Format only.

Recipe Name: {recipe_name}
Cuisine Region: {cuisine_region if cuisine_region else "East Africa"}
Language: {language}

{grounded_context}

INGREDIENT FORMAT RULES:
- List only ingredient categories that have actual ingredients.
- Do not write "none", do not write the label at all if the category is empty.
- Never list water as an ingredient — water is a cooking medium.
- Only include a category line if it has a real ingredient value after the colon.
- Use these exact category labels: Starch, Protein, Aromatics, Vegetables, Spices, Fat, Optional
- No asterisks. No bullet points. Plain lines only.

FORMAT RULES:
- Write a 2-3 sentence introduction about the dish. No asterisks.
- Write "Cuisine: {cuisine_region if cuisine_region else "East Africa"}"
- Write "Essential Ingredients" as a section header
- Write "Step-by-Step Cooking Instructions" as a section header
- Number every step with a descriptive title. No asterisks.
- Write "Tips for Perfect {recipe_name}" as a section header
- Write 2 practical tips as plain sentences. No asterisks. No dashes. No "Serve with:" line.
- End with: Let me know if you need any clarification on any step, or if you'd like to try something else!"""

        elif source == "TAVILY":
            user_prompt = f"""You are formatting a recipe found on a trusted African cooking website. Use the ingredients and steps from the source. You may expand vague steps into clearer instructions but do not invent new ingredients.

Recipe Name: {recipe_name}
Cuisine Region: {cuisine_region if cuisine_region else "East Africa"}
Language: {language}

{grounded_context}

INGREDIENT FORMAT RULES:
- List only ingredient categories that have actual ingredients.
- Do not write "none", do not write the label at all if the category is empty.
- Never list water as an ingredient — water is a cooking medium.
- Only include a category line if it has a real ingredient value after the colon.
- Use these exact category labels: Starch, Protein, Aromatics, Vegetables, Spices, Fat, Optional
- No asterisks. No bullet points. Plain lines only.

FORMAT RULES:
- Write a 2-3 sentence introduction about the dish. No asterisks.
- Write "Cuisine: {cuisine_region if cuisine_region else "East Africa"}"
- Write "Essential Ingredients" as a section header
- Write "Step-by-Step Cooking Instructions" as a section header
- Number every step with a descriptive title. No asterisks.
- Write "Tips for Perfect {recipe_name}" as a section header
- Write 2 practical tips as plain sentences. No asterisks. No dashes. No "Serve with:" line.
- End with: Let me know if you need any clarification on any step, or if you'd like to try something else!"""

        elif source == "CSV_COMPOUND" and compound_data:
            c1_name = compound_data["component_1_name"]
            c1_ingredients = compound_data["component_1_ingredients"]
            c1_steps_raw = compound_data["component_1_steps"]
            c2_name = compound_data["component_2_name"]
            c2_ingredients = compound_data["component_2_ingredients"]
            c2_steps_raw = compound_data["component_2_steps"]

            c1_steps = split_steps_paragraph(c1_steps_raw)
            c2_steps = split_steps_paragraph(c2_steps_raw)

            c1_steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(c1_steps))
            c2_steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(c2_steps))

            grounded_context = (
                f"COMPOUND MEAL: {recipe_name}\n"
                f"This dish is made of two components prepared separately and served together.\n\n"
                f"COMPONENT 1: {c1_name}\n"
                f"Ingredients: {c1_ingredients}\n"
                f"Steps:\n{c1_steps_text}\n\n"
                f"COMPONENT 2: {c2_name}\n"
                f"Ingredients: {c2_ingredients}\n"
                f"Steps:\n{c2_steps_text}"
            )
            source_label = "CSV_COMPOUND"
            
            user_prompt = f"""You are formatting a compound African meal recipe. This dish consists of two components that are prepared separately and served together. Both components are from the Jema CSV database and their steps are correct and authoritative. Do not add, remove, or change any content. Format only.

Recipe Name: {recipe_name}
Language: {language}

{grounded_context}

FORMAT INSTRUCTIONS:
1. Write a 2-3 sentence introduction explaining that {recipe_name} is a complete meal made of two components: {compound_data['component_1_name']} and {compound_data['component_2_name']}. No asterisks.
2. Write: Cuisine: {cuisine_region or "East Africa"}
3. Write: Component 1: {compound_data['component_1_name']}
4. Write: Essential Ingredients
5. List only ingredient categories that have actual values for {compound_data['component_1_name']}. Use labels: Starch, Protein, Aromatics, Vegetables, Spices, Fat, Optional. Skip empty categories. No asterisks. Plain lines.
6. Write: Step-by-Step Cooking Instructions
7. Number every step of {compound_data['component_1_name']} with a descriptive title. No asterisks. No bold markdown.
8. Write: Component 2: {compound_data['component_2_name']}
9. Write: Essential Ingredients
10. List only ingredient categories that have actual values for {compound_data['component_2_name']}. Same rules as above.
11. Write: Step-by-Step Cooking Instructions
12. Number every step of {compound_data['component_2_name']} with a descriptive title. No asterisks. No bold markdown.
13. Write: Tips for Perfect {recipe_name}
14. Write exactly 2 practical tips covering both components as plain sentences. No asterisks. No dashes. No "Serve with:" line.
15. End with exactly: Let me know if you need any clarification on any step, or if you'd like to try something else!
"""

        else:  # source == "GROQ"
            user_prompt = f"""Generate a complete authentic African recipe for {recipe_name}. Only include information you are certain about. If you are not certain about an ingredient or step, omit it rather than guessing.

Recipe Name: {recipe_name}
Cuisine Region: {cuisine_region if cuisine_region else "East Africa"}
Language: {language}

INGREDIENT FORMAT RULES:
- List only ingredient categories that have actual ingredients.
- Do not write "none", do not write the label at all if the category is empty.
- Never list water as an ingredient — water is a cooking medium.
- Only include a category line if it has a real ingredient value after the colon.
- Use these exact category labels: Starch, Protein, Aromatics, Vegetables, Spices, Fat, Optional
- No asterisks. No bullet points. Plain lines only.
- Only real ingredients that belong to this dish.

FORMAT RULES:
- Write a 2-3 sentence factual introduction about the dish and its origin. Omit any cultural fact you are not certain about. No asterisks.
- Write "Cuisine: {cuisine_region if cuisine_region else "East Africa"}"
- Write "Essential Ingredients" as a section header
- Write "Step-by-Step Cooking Instructions" as a section header
- Number every step with a descriptive title. No asterisks. Only real steps for this dish.
- Write "Tips for Perfect {recipe_name}" as a section header
- Write 2 practical tips as plain sentences. No asterisks. No dashes. No "Serve with:" line.
- End with: Let me know if you need any clarification on any step, or if you'd like to try something else!
- If you genuinely do not know this dish, respond only with: "I don't have reliable information about this dish. Please search for {recipe_name} on a trusted African recipe site." """

        # --- CALL GROQ ---
        try:
            logger.debug(f"[LLMService] LLM API call — model=llama-3.3-70b-versatile, system_prompt_length={len(system_prompt)}, messages=2")
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
            logger.debug(f"[LLMService] LLM response received — {len(result)} chars")
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
                    # FIX 1: Additional cleanup for all asterisks before appending
                    cleaned = cleaned.replace("**", "").replace("*", "").strip()
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
            if not cleaned:
                continue
            if cleaned.endswith(":"):
                continue
            # Skip lines where the value is none, n/a, dash, or empty
            if ":" in cleaned:
                value = cleaned.split(":", 1)[1].strip().lower()
                # Check for empty or whitespace-only values
                if value in ("none", "n/a", "-", "", "–") or len(value) == 0 or not value.strip():
                    continue
            if len(cleaned) > 2:
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
        
