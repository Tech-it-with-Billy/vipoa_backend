import os
import re
from pathlib import Path
from groq import Groq
from typing import List, Dict
from jema.src.language_detector import LanguageDetector

class LLMService:
    def __init__(self):
        # Load .env manually from project root
        env_path = Path(__file__).parent.parent / '.env'
        
        # Read the file directly with UTF-8 encoding
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
                for line in content.split('\n'):
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        os.environ[key] = value
        
        api_key = os.environ.get("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in .env file")
        
        self.client = Groq(api_key=api_key)
        self.conversation_history: List[Dict[str, str]] = []
        self.current_language: str = 'english'  # Track the current conversation language
        self.system_prompt_template = """You are Jema, a friendly and knowledgeable East African cooking assistant. You help users discover and prepare meals from Kenya, Uganda, Tanzania, Ethiopia, South Sudan, Rwanda, Burundi, and Swahili cuisine.

You can help with:
- Specific meal recipes (e.g., "I want to make ugali", "Ninataka kutengeneza ugali")
- Suggesting recipes based on available ingredients
- Providing cooking instructions and tips
- Answering questions about East African cuisine

Style: keep replies short (1-2 sentences), simple, friendly, and to the point. Remember the context of the conversation.

IMPORTANT: Do not use markdown formatting like **bold** or *italic* in your responses. Write in plain text only.

When providing suggestions or answering questions, end your response with a clear call-to-action that guides the user toward the next step (e.g., "Would you like the recipe?", "Which one would you like to try?", "Can you tell me more?").

{language_instruction}"""
        
        self.system_prompt = self.system_prompt_template.format(language_instruction="Respond in English.")
    
    def add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})
        
        # Keep only last 10 messages to avoid token limits
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
    
    def update_language(self, text: str) -> None:
        """
        Update the current conversation language based on user input.
        
        Args:
            text: User input text
        """
        detected_language = LanguageDetector.detect_language(text)
        if detected_language != self.current_language:
            self.current_language = detected_language
            language_instruction = LanguageDetector.get_language_instruction(detected_language)
            self.system_prompt = self.system_prompt_template.format(language_instruction=language_instruction)
    
    def get_conversation_context(self) -> List[Dict[str, str]]:
        """Get the full conversation context including system prompt."""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.conversation_history)
        return messages
    
    def explain_recommendation(self, context):
        """
        Generate a natural language explanation for a recipe recommendation
        
        Args:
            context: dict with recipe_name, match_percent, have, missing
        """
        recipe = context["recipe_name"]
        percent = context["match_percent"]
        matched = context["have"]
        missing = context["missing"]
        country = context.get("country", "")
        
        if percent == 100:
            prompt = f"""You are Jema, a friendly East African cooking assistant. The user has the ingredients to make {recipe}.
Write a short message (1-2 sentences) that says: "With the ingredients you have, you could make {recipe}" and mention it's quick/easy to prepare. Be warm and encouraging."""
        else:
            missing_list = ", ".join(missing)
            prompt = f"""You are Jema, a friendly East African cooking assistant. The user has {matched} out of {matched + len(missing)} ingredients for {recipe}.
They are missing: {missing_list}

Write a short, helpful message (1-2 sentences) that:
1. Says "You're almost there! With the ingredients you have, you're {percent}% of the way to making {recipe}"
2. Suggests they get the missing items OR look for another recipe

Be warm and supportive."""
        
        try:
            message = self.client.chat.completions.create(
                messages=[
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=500,
            )
            return message.choices[0].message.content.strip()
        except Exception as e:
            print(f" LLM Error: {e}")
            return f"Match: {percent}% - Missing: {', '.join(missing) if missing else 'Nothing!'}"
    
    def general_response(self, user_input: str, use_history: bool = True, include_cta: bool = True) -> str:
        """
        Generate a response to general questions/greetings with conversation context.
        
        Args:
            user_input: The user's message
            use_history: Whether to use conversation history for context
            include_cta: Whether to include a call-to-action in the response
        """
        if use_history:
            # Add user message to history
            self.add_to_history("user", user_input)
            
            # Get conversation context
            messages = self.get_conversation_context()
        else:
            # Single-turn interaction
            cta_instruction = "End your response with a clear call-to-action, like 'Would you like the recipe?' or 'Which one would you like?'" if include_cta else ""
            prompt = f"""You are Jema, a friendly East African cooking assistant. A user just said: "{user_input}"

Respond warmly and helpfully in plain text. If they're greeting you or asking general questions, briefly remind them you can help with specific meal names or the ingredients they have.

{cta_instruction}

Keep it simple, friendly, and to the point (ideally one sentence)."""
            
            messages = [{"role": "user", "content": prompt}]
        
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                max_tokens=2000,
                temperature=0.7,
            )
            assistant_message = response.choices[0].message.content.strip()
            
            # Add assistant response to history if using history
            if use_history:
                self.add_to_history("assistant", assistant_message)
            
            return assistant_message
        except Exception as e:
            print(f" LLM Error: {e}")
            return "I'm here to help you cook! Tell me a meal name or the ingredients you have."    
    def enhance_recipe_steps(self, recipe_name: str, steps: List[str], ingredients: str, language: str = 'english') -> List[str]:
        """
        Enhance brief recipe steps with detailed cooking instructions.
        
        Args:
            recipe_name: Name of the recipe
            steps: List of brief step descriptions
            ingredients: Ingredient list for context
            language: 'english' or 'swahili'
            
        Returns:
            List of enhanced, detailed step descriptions
        """
        if not steps:
            return []
        
        # Create prompt for enhancement
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
        
        # Note: Using English for step enhancement regardless of detected language
        # Swahili translation is limited to greetings only for now
        prompt = f"""You are Jema, an East African cooking assistant. You are helping someone make {recipe_name}.

Ingredients: {ingredients}

Brief steps:
{steps_text}

Please expand these brief steps into detailed cooking instructions. For each step, include:
- Specific actions and techniques
- Approximate timing
- Important tips or warnings

Return the expanded steps as a numbered list, one step per line."""
        
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful cooking assistant. Expand brief cooking steps into detailed instructions."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=1500,
                temperature=0.7,
            )
            
            enhanced_text = response.choices[0].message.content.strip()
            
            # Parse the enhanced steps back into a list
            enhanced_steps = []
            for line in enhanced_text.split('\n'):
                line = line.strip()
                # Remove numbering if present
                line = re.sub(r'^\d+[\.\)]\s*', '', line)
                if line and len(line) > 10:  # Filter out empty or very short lines
                    enhanced_steps.append(line)
            
            return enhanced_steps if enhanced_steps else steps
            
        except Exception as e:
            print(f" LLM Error during step enhancement: {e}")
            return steps  # Return original steps if enhancement fails