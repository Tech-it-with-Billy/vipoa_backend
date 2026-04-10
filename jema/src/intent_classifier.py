"""
Intent Classification and Context Detection
Classifies user intent and detects constraints/preferences
"""

from typing import Dict, List, Tuple, Optional
from enum import Enum


class Intent(Enum):
    """User intent types"""
    GREETING = "greeting"
    INGREDIENT_BASED = "ingredient_based"  # "I have rice and beans, what can I make?"
    RECIPE_REQUEST = "recipe_request"       # "Make me a ugali recipe"
    HOW_TO_COOK = "how_to_cook"            # "How do I cook rice?"
    MEAL_IDEA = "meal_idea"                # "What should I make for breakfast?"
    ACCOMPANIMENT = "accompaniment"         # "What goes with rice?"
    INFORMATION = "information"             # "Tell me about East African food"
    CHAT_SOCIAL = "chat_social"            # General conversation
    REJECTION = "rejection"                 # "I don't like that"
    FOLLOW_UP = "follow_up"                # Follow-up to previous response


class Constraint(Enum):
    """User constraints/preferences"""
    QUICK = "quick"          # "fast", "quick", "in a hurry"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    BUDGET = "budget"        # "cheap", "affordable", "budget"
    FILLING = "filling"      # "hearty", "filling", "substantial"
    LIGHT = "light"          # "light", "simple"
    NO_OVEN = "no_oven"
    ONE_POT = "one_pot"
    TRADITIONAL = "traditional"  # "traditional", "authentic"


class IntentClassifier:
    """Classify user intent and extract constraints"""
    
    # Intent detection patterns
    INTENT_PATTERNS = {
        Intent.INGREDIENT_BASED: [
            "i have", "with these", "have ingredients", "only have",
            "ingredients i have", "nina", "ninavyo", "nini ninaweza",
            # New ingredient-based triggers
            "i've got", "using", "with chicken", "with beef",
            "with fish", "with rice", "with tomatoes", "with onions",
            "what can i cook with", "what can i make with",
            "cook with", "make with", "recipes with", "dish with",
            "meal with", "something with"
        ],
        Intent.RECIPE_REQUEST: [
            "recipe for", "how do i make", "make me", "teach me",
            "show me how", "want to make", "would like to make",
            "tengeneza", "pika", "karibu", "do you have",
            # Suggestion and recommendation phrases
            "suggest", "recommend", "give me", "what can i make",
            "what should i cook", "what can i cook", "meal i can",
            "recipe do you", "i want to make", "how do i cook",
            "what do you recommend", "can you suggest", "ideas for",
            # Meal timing phrases — CRITICAL for meal occasion context
            "for dinner", "for lunch", "for breakfast", "for brunch",
            "for iftar", "for suhoor", "for eid", "for ramadan",
            "after the gym", "after work", "before bed",
            "in the morning", "in the evening", "at night",
            # Speed and constraint phrases
            "quick meal", "fast meal", "something quick", "something easy",
            "under 30", "in 30 minutes", "cook in", "make in",
            "in under", "less than 30", "quick african", "fast african",
            # Descriptor and protein phrases — capture meat/vegetarian/vegan requests
            "hearty", "filling", "light meal", "heavy meal",
            "high-protein", "low-calorie", "healthy meal",
            "meat dish", "chicken dish", "beef dish", "fish dish",
            "vegetarian dish", "vegan dish",
            # General recipe request phrases
            "something to eat", "to eat", "can i cook", "can i make",
            "a recipe", "a dish", "a meal", "i can have",
            # Additional meal suggestion patterns
            "i can make for", "i can cook for", "i can have for",
            "what meals", "what dishes", "what recipes"
        ],
        Intent.HOW_TO_COOK: [
            "how do i cook", "how to cook", "steps", "instructions",
            "how long", "how many minutes", "timing", "procedure"
        ],
        Intent.MEAL_IDEA: [
            "what should i make", "what can i cook", "give me idea",
            "suggest", "recommend", "what's good", "idea for",
            "what can i have", "what for breakfast", "what for lunch", "what for dinner",
            "breakfast ideas", "lunch ideas", "dinner ideas", "meal ideas"
        ],
        Intent.ACCOMPANIMENT: [
            "what goes with", "what side", "pair with", "serve with",
            "goes well with", "goes with", "add to", "what should i add",
            "what can i have with", "what can i eat with", "what can you suggest",
            "what would go", "what pairs", "what to serve"
        ],
        Intent.REJECTION: [
            "i don't like", "don't want", "not interested", "dislike",
            "something else", "prefer", "not a fan", "hate"
        ],
        Intent.FOLLOW_UP: [
            "what do you mean", "explain", "why", "tell me more",
            "more about", "additional", "another", "different"
        ],
        Intent.INFORMATION: [
            "tell me about", "what is", "what are", "information",
            "learn about", "explain", "cuisine", "history"
        ]
    }
    
    # Community/ethnic group keywords
    COMMUNITIES = {
        'kikuyu': ['kikuyu', 'gikuyu'],
        'maasai': ['maasai'],
        'samburu': ['samburu'],
        'luhya': ['luhya'],
        'luo': ['luo'],
        'kamba': ['kamba', 'akamba'],
        'embu': ['embu'],
        'meru': ['meru'],
        'swahili': ['swahili'],
        'somali': ['somali'],
        'ethiopian': ['ethiopian', 'habesha'],
        'ugandan': ['ugandan'],
        'tanzanian': ['tanzanian'],
        'rwandan': ['rwandan'],
    }
    
    # Constraint detection patterns
    CONSTRAINT_PATTERNS = {
        Constraint.QUICK: ["quick", "fast", "hurry", "soon", "30 min", "15 min", "rapid"],
        Constraint.VEGETARIAN: ["vegetarian", "no meat", "veg"],
        Constraint.VEGAN: ["vegan", "no dairy", "plant-based"],
        Constraint.BUDGET: ["cheap", "budget", "affordable", "low cost", "inexpensive"],
        Constraint.FILLING: ["filling", "hearty", "substantial", "heavy"],
        Constraint.LIGHT: ["light", "simple", "easy", "healthy"],
        Constraint.NO_OVEN: ["no oven", "without oven", "stovetop", "open fire"],
        Constraint.ONE_POT: ["one pot", "single pot", "easy cleanup"],
        Constraint.TRADITIONAL: ["traditional", "authentic", "native", "indigenous"],
    }
    
    @staticmethod
    def classify(user_input: str) -> Tuple[Intent, List[Constraint], Optional[str], float]:
        """
        Classify user intent and detect constraints.
        
        Args:
            user_input: User's message
            
        Returns:
            Tuple of (primary_intent, constraints, detected_community, confidence_score)
            confidence_score: 0.0-1.0 indicating classification confidence
        """
        user_lower = user_input.lower()
        intent_scores = {}
        
        # Score each intent
        for intent, patterns in IntentClassifier.INTENT_PATTERNS.items():
            matches = sum(1 for pattern in patterns if pattern in user_lower)
            if matches > 0:
                intent_scores[intent] = matches
        
        # Special priority rules: ACCOMPANIMENT takes precedence if it matches
        if Intent.ACCOMPANIMENT in intent_scores and Intent.INGREDIENT_BASED in intent_scores:
            if any(phrase in user_lower for phrase in ["with", "goes with", "serve with", "pair with"]):
                primary_intent = Intent.ACCOMPANIMENT
                confidence = 0.95
                return primary_intent, [], None, confidence
        
        # Special priority rule: MEAL_IDEA takes precedence for meal time queries
        if Intent.MEAL_IDEA in intent_scores and Intent.INGREDIENT_BASED in intent_scores:
            if any(phrase in user_lower for phrase in ["breakfast", "lunch", "dinner", "meal", "for today"]):
                primary_intent = Intent.MEAL_IDEA
                confidence = 0.95
                return primary_intent, [], None, confidence
        
        # Determine primary intent
        if intent_scores:
            primary_intent = max(intent_scores, key=intent_scores.get)
            confidence = min(1.0, intent_scores[primary_intent] / 3.0)  # Normalize
        else:
            primary_intent = Intent.CHAT_SOCIAL
            confidence = 0.3
        
        # Detect constraints
        detected_constraints = []
        for constraint, patterns in IntentClassifier.CONSTRAINT_PATTERNS.items():
            if any(pattern in user_lower for pattern in patterns):
                detected_constraints.append(constraint)
        
        # Detect community/ethnic group mention
        detected_community = None
        for community, keywords in IntentClassifier.COMMUNITIES.items():
            if any(keyword in user_lower for keyword in keywords):
                detected_community = community
                break
        
        return primary_intent, detected_constraints, detected_community, confidence
    
    @staticmethod
    def should_ask_clarification(ingredient_count: int, confidence: float) -> bool:
        """
        Determine if we should ask a clarifying question.
        
        Args:
            ingredient_count: Number of ingredients user mentioned
            confidence: Confidence score from classification
            
        Returns:
            True if we should ask for clarification
        """
        # Ask if: few ingredients mentioned AND low confidence
        return ingredient_count <= 2 and confidence < 0.6
    
    @staticmethod
    def get_clarification_question(intent: Intent, constraints: List[Constraint]) -> str:
        """
        Generate a single clarifying question based on intent.
        
        Args:
            intent: Detected intent
            constraints: Detected constraints
            
        Returns:
            A clarifying question string
        """
        if intent == Intent.INGREDIENT_BASED:
            return "Are you cooking for breakfast, lunch, or dinner?"
        elif intent == Intent.MEAL_IDEA:
            return "Do you want something quick or something filling?"
        else:
            return "Would you like a quick recipe or something more hearty?"
