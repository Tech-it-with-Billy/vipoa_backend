import os
import re
from pathlib import Path
from typing import List, Dict
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

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            # Silently disable LLM features if key is not configured
            # Warning will only be shown when LLM features are actually used
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

    def generate_recipe(self, recipe_name: str, cuisine_region: str = 'East Africa') -> Dict:
        """
        Generate a complete traditional recipe using Groq.
        Returns a dict with: introduction, ingredients (list), steps (list), tips (list), cuisine
        """
        if self.client is None:
            return {
                "cuisine": cuisine_region,
                "introduction": "",
                "ingredients": [],
                "steps": [],
                "tips": [],
            }

        prompt = f"""Generate a complete traditional {recipe_name} recipe from {cuisine_region}.

Provide EXACTLY:
1. Introduction: 1-2 sentence description of the dish
2. Essential Ingredients: list with quantities
3. Step-by-Step Cooking Instructions: numbered steps
4. Tips for Perfect {recipe_name}: 2-3 practical tips

Format as plain text. Be specific with measurements and timing.
DO NOT use markdown formatting."""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=2500,
                temperature=0.7
            )
            
            full_response = response.choices[0].message.content.strip()
            return self._parse_recipe(full_response, recipe_name, cuisine_region)
        except Exception as e:
            print(f"LLM Error during recipe generation: {e}")
            return {
                "cuisine": cuisine_region,
                "introduction": "",
                "ingredients": [],
                "steps": [],
                "tips": [],
            }

    def generate_east_african_recipe_from_ingredients(self, ingredients: List[str], cuisine_region: str = 'East Africa') -> List[Dict]:
        """
        Generate 3 recipe suggestions based on user ingredients.
        Returns list of dicts with: meal_name, introduction, ingredients, steps, tips, cuisine
        
        Uses strict validation to ensure ALL user ingredients appear in suggested dishes.
        """
        if self.client is None:
            return []

        ingredients_str = ', '.join(ingredients)

        prompt = f"""
BEFORE YOU SUGGEST ANYTHING — for each dish run this exact check:

Ingredients the user has: {ingredients_str}

For EACH dish you are considering:
1. List every ingredient from [{ingredients_str}] and check if it appears in this dish
2. If ANY ingredient from [{ingredients_str}] is absent — REJECT this dish immediately
3. Only proceed if ALL of [{ingredients_str}] appear as PRIMARY components

REJECTION EXAMPLES using ingredients [{ingredients_str}]:
- If user has [beans, onion, bell pepper]:
  * Ful Medames — check: has beans ✅ has onion ✅ has bell pepper ❌ → REJECT
  * Beans Stew — check: has beans ✅ has onion ✅ has bell pepper ✅ → ACCEPT
- If user has [beef, rice, onion, garlic, tomato]:
  * Tibs — check: has beef ✅ has rice ❌ → REJECT
  * Pilau — check: has beef ✅ has rice ✅ has onion ✅ has garlic ✅ has tomato ✅ → ACCEPT
  * Meat Stew — check: has beef ✅ has rice ❌ → REJECT

DEDUPLICATION CHECK — before returning verify:
- Are any two suggested dishes the same recipe with different names?
- Biryani and Biriani are the SAME dish — suggest only one
- Meat Stew appearing twice is a duplicate — each suggestion must be unique
- If you find a duplicate replace it with a different real dish

---

Now suggest up to 3 traditional East African recipes using ONLY ingredients from [{ingredients_str}].

For EACH recipe provide:
1. Recipe Name: [name]
2. Introduction: [1-2 sentences]
3. Ingredients: [with quantities from user's list]
4. Steps: [numbered cooking instructions]
5. Tips: [2-3 practical tips]

Use plain text. Be specific. No markdown."""

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=3000,
                temperature=0.7
            )
            
            full_response = response.choices[0].message.content.strip()
            return self._parse_plain_text_recipes(full_response, cuisine_region)
        except Exception as e:
            print(f"LLM Error during ingredient-based recipe generation: {e}")
            return []

    def _parse_recipe(self, response_text: str, recipe_name: str, cuisine_region: str) -> Dict:
        """Parse a single recipe from LLM response."""
        lines = response_text.split('\n')
        
        introduction = ""
        ingredients = []
        steps = []
        tips = []
        
        current_section = None
        section_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            line_lower = line.lower()
            
            # Detect section headers
            if any(word in line_lower for word in ['introduction', 'description', 'about', 'overview']):
                if section_content and current_section:
                    if current_section == 'introduction':
                        introduction = ' '.join(section_content)
                    elif current_section == 'ingredients':
                        ingredients = section_content
                    elif current_section == 'steps':
                        steps = section_content
                    elif current_section == 'tips':
                        tips = section_content
                current_section = 'introduction'
                section_content = []
            elif any(word in line_lower for word in ['ingredient', 'essential']):
                if section_content and current_section:
                    if current_section == 'introduction':
                        introduction = ' '.join(section_content)
                    elif current_section == 'steps':
                        steps = section_content
                    elif current_section == 'tips':
                        tips = section_content
                current_section = 'ingredients'
                section_content = []
            elif any(word in line_lower for word in ['step', 'instruction', 'preparation', 'cooking', 'method']):
                if section_content and current_section:
                    if current_section == 'introduction':
                        introduction = ' '.join(section_content)
                    elif current_section == 'ingredients':
                        ingredients = section_content
                    elif current_section == 'tips':
                        tips = section_content
                current_section = 'steps'
                section_content = []
            elif any(word in line_lower for word in ['tip', 'advice', 'perfect', 'note']):
                if section_content and current_section:
                    if current_section == 'introduction':
                        introduction = ' '.join(section_content)
                    elif current_section == 'ingredients':
                        ingredients = section_content
                    elif current_section == 'steps':
                        steps = section_content
                current_section = 'tips'
                section_content = []
            elif current_section:
                # Clean and add content
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                cleaned = re.sub(r'^\*+\s*', '', cleaned).strip()
                cleaned = re.sub(r'^\-\s*', '', cleaned).strip()
                if cleaned:
                    section_content.append(cleaned)
        
        # Don't forget last section
        if section_content and current_section:
            if current_section == 'introduction':
                introduction = ' '.join(section_content)
            elif current_section == 'ingredients':
                ingredients = section_content
            elif current_section == 'steps':
                steps = section_content
            elif current_section == 'tips':
                tips = section_content
        
        return {
            "meal_name": recipe_name,
            "cuisine": cuisine_region,
            "cuisine_region": cuisine_region,
            "introduction": introduction,
            "ingredients": ingredients[:10],  # Limit to 10 ingredients
            "steps": steps[:6],  # Limit to 6 steps
            "tips": tips[:3],  # Limit to 3 tips
        }

    def _parse_plain_text_recipes(self, response_text: str, cuisine_region: str) -> List[Dict]:
        """Parse multiple recipes from plain text LLM response."""
        recipes = []
        current_recipe = None
        current_section = None
        section_content = []
        
        lines = response_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_recipe and section_content:
                    self._add_section_to_recipe(current_recipe, current_section, section_content)
                    section_content = []
                continue
            
            line_lower = line.lower()
            
            # Detect recipe name (e.g., "Recipe Name: Pilau" or just "Pilau")
            if 'recipe name:' in line_lower or (current_recipe is None and len(line) < 50 and ':' in line):
                if current_recipe and section_content:
                    self._add_section_to_recipe(current_recipe, current_section, section_content)
                    section_content = []
                
                recipe_name = re.sub(r'recipe name:\s*', '', line, flags=re.IGNORECASE).strip()
                current_recipe = {
                    "meal_name": recipe_name,
                    "cuisine": cuisine_region,
                    "cuisine_region": cuisine_region,
                    "introduction": "",
                    "ingredients": [],
                    "steps": [],
                    "tips": [],
                }
                recipes.append(current_recipe)
                current_section = None
            elif current_recipe is None:
                continue
            
            # Detect section headers
            elif any(word in line_lower for word in ['introduction:', 'description:', 'about:']):
                if section_content:
                    self._add_section_to_recipe(current_recipe, current_section, section_content)
                current_section = 'introduction'
                section_content = []
            elif any(word in line_lower for word in ['ingredient:', 'essential']):
                if section_content:
                    self._add_section_to_recipe(current_recipe, current_section, section_content)
                current_section = 'ingredients'
                section_content = []
            elif any(word in line_lower for word in ['step:', 'cooking instruction', 'preparation', 'method:']):
                if section_content:
                    self._add_section_to_recipe(current_recipe, current_section, section_content)
                current_section = 'steps'
                section_content = []
            elif any(word in line_lower for word in ['tip:', 'advice:', 'note:']):
                if section_content:
                    self._add_section_to_recipe(current_recipe, current_section, section_content)
                current_section = 'tips'
                section_content = []
            elif current_section:
                # Clean and add content
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                cleaned = re.sub(r'^\*+\s*', '', cleaned).strip()
                cleaned = re.sub(r'^\-\s*', '', cleaned).strip()
                if cleaned:
                    section_content.append(cleaned)
        
        # Don't forget last section
        if current_recipe and section_content:
            self._add_section_to_recipe(current_recipe, current_section, section_content)
        
        return recipes[:3]  # Return max 3 recipes

    def _add_section_to_recipe(self, recipe: Dict, section: str, content: List[str]) -> None:
        """Add parsed section content to recipe dict."""
        if not section or not content:
            return
        
        if section == 'introduction':
            recipe['introduction'] = ' '.join(content)
        elif section == 'ingredients':
            recipe['ingredients'] = content[:10]
        elif section == 'steps':
            recipe['steps'] = content[:6]
        elif section == 'tips':
            recipe['tips'] = content[:3]
