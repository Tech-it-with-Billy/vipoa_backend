"""
Response Formatter with Call-to-Action
Adds contextual CTAs to make responses more actionable
"""

from typing import Optional, List
from enum import Enum


class ResponseType(Enum):
    """Types of responses that might need CTAs"""
    RECIPE_SUGGESTION = "recipe_suggestion"      # "You can make..."
    RECIPE_DISPLAY = "recipe_display"            # Full recipe shown
    MULTIPLE_OPTIONS = "multiple_options"        # Multiple recipes
    QUESTION_ANSWER = "question_answer"          # Answering a question
    GREETING = "greeting"                        # Greeting response
    FOLLOW_UP = "follow_up"                      # Follow-up to previous
    CLARIFICATION_NEEDED = "clarification_needed" # Need more info


class CTAFormatter:
    """Add contextual calls-to-action to responses"""
    
    # Default CTAs for different contexts
    CTA_TEMPLATES = {
        ResponseType.RECIPE_SUGGESTION: [
            "Would you like the recipe?",
            "Would you like me to show you how to make it?",
            "Would you like the full recipe and steps?"
        ],
        ResponseType.MULTIPLE_OPTIONS: [
            "Which one would you like?",
            "Which of these interests you?",
            "Which would you prefer?"
        ],
        ResponseType.QUESTION_ANSWER: [
            "Would you like to try making this?",
            "Does that help? Would you like a recipe?",
            "Can I help you with a recipe for this?"
        ],
        ResponseType.CLARIFICATION_NEEDED: [
            "Can you tell me more?",
            "What other ingredients do you have?",
            "Do you have any other ingredients?"
        ],
        ResponseType.FOLLOW_UP: [
            "Would you like to try it?",
            "Does that sound good?",
            "Shall we get started?"
        ]
    }
    
    @staticmethod
    def add_cta(response: str, response_type: ResponseType = ResponseType.RECIPE_SUGGESTION,
                language: str = 'english') -> str:
        """
        Add a contextual call-to-action to a response.
        
        Args:
            response: The response text
            response_type: Type of response for CTA selection
            language: 'english' or 'swahili'
            
        Returns:
            Response with CTA appended
        """
        if not response or not response.strip():
            return response
        
        # Get appropriate CTA
        cta = CTAFormatter._get_cta(response_type, language)
        
        # Check if response already ends with a question
        if response.strip().endswith(('?', '!')):
            # Already has punctuation, might have implicit CTA
            return response
        
        # Add CTA with proper spacing
        if response.strip().endswith('.'):
            response = response.strip()[:-1]  # Remove period
        
        return f"{response.strip()} {cta}"
    
    @staticmethod
    def _get_cta(response_type: ResponseType, language: str) -> str:
        """Get CTA for the response type and language"""
        
        # Note: Swahili translation limited to greetings only for now
        # CTAs are in English for all languages
        english_ctas = CTAFormatter.CTA_TEMPLATES.get(
            response_type,
            ["Would you like more help?"]
        )
        # Return first CTA (could randomize for variety)
        return english_ctas[0]
    
    @staticmethod
    def format_suggestion_with_cta(suggestion: str, items: List[str] = None,
                                   language: str = 'english') -> str:
        """
        Format a recipe suggestion with call-to-action.
        
        Args:
            suggestion: The base suggestion text
            items: List of suggested items (for determining CTA type)
            language: Response language
            
        Returns:
            Formatted suggestion with CTA
        """
        # Determine response type based on number of items
        if items and len(items) > 1:
            response_type = ResponseType.MULTIPLE_OPTIONS
        else:
            response_type = ResponseType.RECIPE_SUGGESTION
        
        return CTAFormatter.add_cta(suggestion, response_type, language)
    
    @staticmethod
    def format_question_response_with_cta(response: str, language: str = 'english',
                                         can_suggest_recipe: bool = True) -> str:
        """
        Format a question answer with CTA.
        
        Args:
            response: The answer text
            language: Response language
            can_suggest_recipe: Whether we can suggest a recipe
            
        Returns:
            Response with CTA
        """
        if can_suggest_recipe:
            return CTAFormatter.add_cta(response, ResponseType.QUESTION_ANSWER, language)
        return response
    
    @staticmethod
    def format_multiple_options_with_cta(intro: str, options: List[str],
                                        language: str = 'english') -> str:
        """
        Format multiple recipe options with CTA.
        
        Args:
            intro: Introduction text
            options: List of recipe options
            language: Response language
            
        Returns:
            Formatted options list with CTA
        """
        output = [intro]
        output.extend(options)
        
        # Add CTA for multiple options
        cta = CTAFormatter._get_cta(ResponseType.MULTIPLE_OPTIONS, language)
        output.append(f"\n{cta}")
        
        return "\n".join(output)
