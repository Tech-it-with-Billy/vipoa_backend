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
