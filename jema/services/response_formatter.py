from enum import Enum
from typing import List

class ResponseType(Enum):
    RECIPE_SUGGESTION = "recipe_suggestion"
    MULTIPLE_OPTIONS = "multiple_options"
    QUESTION_ANSWER = "question_answer"

class CTAFormatter:
    """Add contextual call-to-action (CTA) to responses."""

    CTA_TEMPLATES = {
        ResponseType.RECIPE_SUGGESTION: ["Would you like the full recipe?"],
        ResponseType.MULTIPLE_OPTIONS: ["Which one would you like?"],
        ResponseType.QUESTION_ANSWER: ["Can I help you with a recipe for this?"]
    }

    @staticmethod
    def add_cta(response: str, response_type: ResponseType) -> str:
        if not response or response.endswith(('?', '!')):
            return response
        cta = CTAFormatter.CTA_TEMPLATES.get(response_type, ["Would you like more help?"])[0]
        if response.endswith('.'):
            response = response[:-1]
        return f"{response} {cta}"

    @staticmethod
    def format_suggestion(suggestion: str, items: List[str] = None) -> str:
        response_type = ResponseType.MULTIPLE_OPTIONS if items and len(items) > 1 else ResponseType.RECIPE_SUGGESTION
        return CTAFormatter.add_cta(suggestion, response_type)
