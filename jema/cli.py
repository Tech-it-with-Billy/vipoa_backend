#!/usr/bin/env python3
"""
Jema CLI Debug Tool - Test the Jema pipeline end-to-end from the terminal

This script allows developers to test the Jema cooking assistant locally without
needing to run the full Django API. It provides an interactive CLI interface and
optional debugging output to help diagnose issues.

Usage:
    python cli.py                    # Normal mode
    python cli.py --debug            # Debug mode with verbose output
    python cli.py --excel <path>     # Use custom recipe Excel file

Commands in the CLI:
    - Type any message to interact with Jema
    - Type 'exit' or 'quit' to end the session
    - Type 'reset' or 'clear' to start a new conversation
    - Type 'debug' to toggle debug output
    - Type 'help' to see available commands
"""

import sys
import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional, List

# Add parent directory to path for imports
JEMA_DIR = Path(__file__).parent
sys.path.insert(0, str(JEMA_DIR.parent))

# Setup logging — check for debug mode
DEBUG_PIPELINE = os.getenv("JEMA_DEBUG", "0") == "1"
if DEBUG_PIPELINE:
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")
    print("🔍 Pipeline debug mode ON — full data flow trace enabled\n")
else:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

# Import the main engine
try:
    from jema.services.jema_engine import JemaEngine
    from jema.services.profile_context import ProfileContext, ProfileMissingError
except ImportError as e:
    print(f"❌ Error importing JemaEngine or ProfileContext: {e}")
    print(f"   Make sure you're running from the correct directory.")
    print(f"   Current directory: {os.getcwd()}")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# PERSONALISATION PROFILES FOR CLI TESTING
# ──────────────────────────────────────────────────────────────────────────────

PROFILES = {
    "1": {
        "name": "Muslim User",
        "religion": "muslim",
        "dietary_preference": "balanced",
        "allergies": [],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": [],
        "fitness_goal": "weight_loss",
        "cooking_level": "intermediate",
        "eating_reality": "balanced",
        "income_level": "middle",
        "calorie_target": 1800,
    },
    "2": {
        "name": "Hindu Vegetarian",
        "religion": "hindu",
        "dietary_preference": "hindu_vegetarian",
        "allergies": [],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": [],
        "fitness_goal": "muscle_gain",
        "cooking_level": "intermediate",
        "eating_reality": "variety",
        "income_level": "middle",
        "calorie_target": 2500,
    },
    "3": {
        "name": "Vegan with Nut Allergy",
        "religion": "not religious",
        "dietary_preference": "vegan",
        "allergies": ["nuts", "groundnuts", "peanuts"],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": [],
        "fitness_goal": "weight_loss",
        "cooking_level": "novice",
        "eating_reality": "fast",
        "income_level": "low",
        "calorie_target": 1500,
    },
    "4": {
        "name": "Diabetic User",
        "religion": "christian",
        "dietary_preference": "balanced",
        "allergies": [],
        "medical_conditions": ["diabetes"],
        "health_conditions": ["diabetes"],
        "dislikes": ["lamb"],
        "fitness_goal": "blood_sugar_control",
        "cooking_level": "intermediate",
        "eating_reality": "balanced",
        "income_level": "middle",
        "calorie_target": 1800,
    },
    "5": {
        "name": "Keto User",
        "religion": "not religious",
        "dietary_preference": "keto",
        "allergies": [],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": ["fish"],
        "fitness_goal": "weight_loss",
        "cooking_level": "intermediate",
        "eating_reality": "fast",
        "income_level": "middle",
        "calorie_target": 1600,
    },
    "6": {
        "name": "Hypertensive User",
        "religion": "christian",
        "dietary_preference": "balanced",
        "allergies": [],
        "medical_conditions": ["hypertension"],
        "health_conditions": ["hypertension"],
        "dislikes": [],
        "fitness_goal": "general_health",
        "cooking_level": "beginner",
        "eating_reality": "affordable",
        "income_level": "low",
        "calorie_target": 2000,
    },
    "7": {
        "name": "Jewish User",
        "religion": "jewish",
        "dietary_preference": "balanced",
        "allergies": [],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": [],
        "fitness_goal": "maintain",
        "cooking_level": "advanced",
        "eating_reality": "variety",
        "income_level": "middle",
        "calorie_target": 2200,
    },
    "8": {
        "name": "Pescatarian",
        "religion": "not religious",
        "dietary_preference": "pescatarian",
        "allergies": [],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": [],
        "fitness_goal": "eat healthier",
        "cooking_level": "intermediate",
        "eating_reality": "variety",
        "income_level": "middle",
        "calorie_target": 2000,
    },
    "9": {
        "name": "Student / Budget",
        "religion": "not religious",
        "dietary_preference": "balanced",
        "allergies": [],
        "medical_conditions": [],
        "health_conditions": [],
        "dislikes": [],
        "fitness_goal": "eat healthier",
        "cooking_level": "novice",
        "eating_reality": "affordable",
        "income_level": "low",
        "calorie_target": 2000,
    },
    "10": {
        "name": "Anonymous User",
        # None profile — no personalisation applied
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# PROFILE SELECTION AND VALIDATION FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def build_custom_profile() -> Dict:
    """Interactively build a custom profile."""
    print("\nEnter custom profile values (press Enter to skip any field):\n")
    profile = {"name": "Custom Profile"}
    
    religion = input("Religion (muslim/hindu/jewish/christian/not religious): ").strip()
    if religion:
        profile["religion"] = religion.lower()
    
    dietary = input("Dietary (keto/vegan/vegetarian/pescatarian/balanced/low carb/mediterranean): ").strip()
    if dietary:
        profile["dietary_preference"] = dietary.lower()
    
    allergies = input("Allergies (comma separated, or Enter for none): ").strip()
    profile["allergies"] = [a.strip() for a in allergies.split(",")] if allergies else []
    
    medical = input("Medical conditions (comma separated, or Enter for none): ").strip()
    profile["medical_conditions"] = [m.strip() for m in medical.split(",")] if medical else []
    profile["health_conditions"] = profile["medical_conditions"]
    
    dislikes = input("Dislikes (comma separated, or Enter for none): ").strip()
    profile["dislikes"] = [d.strip() for d in dislikes.split(",")] if dislikes else []
    
    fitness = input("Fitness goal (lose weight/gain weight/maintain/muscle_gain/eat healthier): ").strip()
    if fitness:
        profile["fitness_goal"] = fitness.lower()
    
    cooking = input("Cooking level (novice/basic/intermediate/advanced): ").strip()
    if cooking:
        profile["cooking_level"] = cooking.lower()
    
    income = input("Income level (low/middle/high): ").strip()
    if income:
        profile["income_level"] = income.lower()
    
    calories = input("Daily calorie target (number, or Enter to skip): ").strip()
    if calories.isdigit():
        profile["calorie_target"] = int(calories)
    
    return profile


def select_profile() -> Optional[Dict]:
    """Display profile menu and return selected profile."""
    print(f"\n{'='*80}")
    print("JEMA CLI — PERSONALISATION VALIDATOR")
    print(f"{'='*80}")
    print("Select a user profile to chat as:\n")
    
    menu = [
        ("1", "Muslim user — halal only, no pork/alcohol, weight loss"),
        ("2", "Hindu vegetarian — no beef/pork, muscle gain, intermediate"),
        ("3", "Vegan + nut allergy — no animal products, no nuts, weight loss, novice"),
        ("4", "Diabetic user — no high-GI, blood sugar control, dislikes lamb"),
        ("5", "Keto user — no carbs, weight loss, dislikes fish"),
        ("6", "Hypertensive user — no stock cubes/Maggi, low sodium, beginner"),
        ("7", "Jewish user — kosher, no meat/dairy mix, advanced cook"),
        ("8", "Pescatarian — no red meat, Mediterranean diet, intermediate"),
        ("9", "Student / budget — low income, fast meals, novice cook"),
        ("10", "Anonymous user — no profile, no restrictions"),
        ("11", "Custom profile — enter your own values manually"),
    ]
    
    for num, desc in menu:
        print(f"  {num:2}. {desc}")
    
    while True:
        choice = input("\nEnter number (1-11): ").strip()
        if choice == "11":
            return build_custom_profile()
        elif choice == "10":
            return None  # Anonymous — no profile
        elif choice in PROFILES:
            profile = PROFILES[choice]
            # Ensure it's not just a marker
            if isinstance(profile, dict) and "name" in profile:
                return profile
        print("❌ Invalid choice. Please enter a number between 1 and 11.")


def print_active_profile(profile: Optional[Dict]) -> None:
    """Print active profile summary with restrictions."""
    if not profile or profile.get("name") == "Anonymous User":
        print("\n📋 Active Profile: Anonymous — no personalisation applied\n")
        return
    
    print(f"\n{'='*80}")
    print(f"📋 Active Profile: {profile.get('name', 'Custom')}")
    print(f"{'='*80}")
    
    checks = []
    
    religion = (profile.get("religion") or "").lower()
    if religion == "muslim":
        checks.append("🕌 Halal rules active — no pork, no alcohol")
    elif religion == "hindu":
        checks.append("🙏 Hindu rules active — no beef, no pork")
    elif religion == "jewish":
        checks.append("✡️  Kosher rules active — no meat/dairy mix")
    
    dietary = (profile.get("dietary_preference") or "").lower()
    if dietary == "keto":
        checks.append("🥩 Keto active — no rice, ugali, bread, cassava, starch")
    elif dietary == "vegan":
        checks.append("🌱 Vegan active — no meat, dairy, eggs, honey")
    elif dietary == "vegetarian":
        checks.append("🥗 Vegetarian active — no meat or fish")
    elif dietary == "pescatarian":
        checks.append("🐟 Pescatarian active — no red meat or poultry")
    elif dietary == "hindu_vegetarian":
        checks.append("🙏 Hindu vegetarian active — no meat, fish, eggs")
    
    allergies = profile.get("allergies") or []
    if allergies:
        checks.append(f"⚠️  Allergies: {', '.join(allergies)} — must never appear")
    
    medical = profile.get("medical_conditions") or profile.get("health_conditions") or []
    if "diabetes" in [m.lower() for m in medical]:
        checks.append("🩺 Diabetes active — no high-GI, tips section must mention blood sugar")
    if any(m.lower() in ["hypertension", "low sodium"] for m in medical):
        checks.append("❤️  Hypertension active — no Maggi/stock cubes, tips must mention sodium")
    
    dislikes = profile.get("dislikes") or []
    if dislikes:
        checks.append(f"🚫 Dislikes: {', '.join(dislikes)} — must not appear")
    
    fitness = (profile.get("fitness_goal") or "").lower()
    if fitness:
        checks.append(f"🎯 Fitness goal: {fitness}")
    
    calorie_tgt = profile.get("calorie_target")
    if calorie_tgt:
        checks.append(f"🔢 Calorie target: {calorie_tgt} kcal/day")
    
    cooking = (profile.get("cooking_level") or "").lower()
    if cooking in ["novice", "basic"]:
        checks.append("👨‍🍳 Novice cook — plain language, no technical terms")
    
    for check in checks:
        print(f"  {check}")
    
    print(f"\n💬 What to watch for in every response:")
    print(f"   ✅ Restrictions above must NEVER be violated")
    print(f"   ✅ Tips section must reflect medical conditions if any")
    print(f"   ✅ Language complexity must match cooking level")
    print(f"{'='*80}\n")


def print_validation_cheatsheet(profile: Optional[Dict]) -> None:
    """Print suggested test messages for the profile."""
    if not profile or profile.get("name") == "Anonymous User":
        return
    
    name = profile.get("name", "this profile")
    print(f"💡 Suggested test messages for {name}:\n")
    
    dietary = (profile.get("dietary_preference") or "").lower()
    religion = (profile.get("religion") or "").lower()
    medical = [m.lower() for m in (profile.get("medical_conditions") or
               profile.get("health_conditions") or [])]
    
    messages = ["Give me an African recipe for dinner"]
    
    if religion == "muslim":
        messages.append("Suggest a meat dish I can make for Eid")
    if religion == "hindu":
        messages.append("What is a high-protein meal I can make after the gym?")
    if dietary == "keto":
        messages.append("Give me a quick African meal I can make in under 30 minutes")
    if dietary == "vegan":
        messages.append("What is a good African breakfast I can make quickly?")
    if "diabetes" in medical:
        messages.append("I want to make a rice dish — what do you recommend?")
    if "hypertension" in medical:
        messages.append("Give me a hearty African stew recipe")
    
    messages.append("What can I cook with chicken and tomatoes?")
    messages.append("Give me a West African recipe")
    messages.append("What can I substitute for palm oil?")
    
    for i, msg in enumerate(messages, 1):
        print(f"  {i}. {msg}")
    print()


def validate_response(response: str, profile: Optional[Dict]) -> None:
    """Automatically validate response against profile restrictions."""
    if not profile or not response:
        return
    
    response_lower = response.lower()
    violations = []
    passes = []
    
    # Religion checks
    religion = (profile.get("religion") or "").lower()
    if religion == "muslim":
        forbidden = ["pork", "bacon", "ham", "lard", "alcohol", "wine", "beer"]
        for term in forbidden:
            if re.search(r'\b' + term + r'\b', response_lower):
                violations.append(f"🚨 VIOLATION: '{term}' found — halal rule broken")
        if not any(re.search(r'\b' + term + r'\b', response_lower) for term in forbidden):
            passes.append("✅ Halal rules respected")
    
    if religion == "hindu":
        forbidden = ["beef", "veal"]
        for term in forbidden:
            if re.search(r'\b' + term + r'\b', response_lower):
                violations.append(f"🚨 VIOLATION: '{term}' found — Hindu rule broken")
        if not any(re.search(r'\b' + term + r'\b', response_lower) for term in forbidden):
            passes.append("✅ Hindu rules respected")
    
    # Dietary checks
    dietary = (profile.get("dietary_preference") or "").lower()
    if dietary == "keto":
        forbidden = ["ugali", "rice", "bread", "pasta", "fufu", "cassava", "yam", "plantain"]
        for term in forbidden:
            if re.search(r'\b' + term + r'\b', response_lower):
                violations.append(f"🚨 VIOLATION: '{term}' found — keto rule broken")
        if not any(re.search(r'\b' + term + r'\b', response_lower) for term in forbidden):
            passes.append("✅ Keto rules respected")
    
    if dietary == "vegan":
        forbidden = ["meat", "beef", "chicken", "fish", "egg", "milk", "butter", "dairy"]
        for term in forbidden:
            if re.search(r'\b' + term + r'\b', response_lower):
                violations.append(f"🚨 VIOLATION: '{term}' found — vegan rule broken")
        if not any(re.search(r'\b' + term + r'\b', response_lower) for term in forbidden):
            passes.append("✅ Vegan rules respected")
    
    if dietary == "hindu_vegetarian":
        forbidden = ["meat", "beef", "chicken", "fish", "egg"]
        for term in forbidden:
            if re.search(r'\b' + term + r'\b', response_lower):
                violations.append(f"🚨 VIOLATION: '{term}' found — hindu vegetarian rule broken")
        if not any(re.search(r'\b' + term + r'\b', response_lower) for term in forbidden):
            passes.append("✅ Hindu vegetarian rules respected")
    
    # Allergy checks
    allergies = [a.lower() for a in (profile.get("allergies") or [])]
    for allergen in allergies:
        if re.search(r'\b' + allergen + r'\b', response_lower):
            violations.append(f"🚨 VIOLATION: Allergen '{allergen}' found in response")
        else:
            passes.append(f"✅ Allergen '{allergen}' correctly excluded")
    
    # Medical checks
    medical = [m.lower() for m in (
        profile.get("medical_conditions") or
        profile.get("health_conditions") or []
    )]
    
    if "diabetes" in medical:
        if any(t in response_lower for t in ["diabetes", "blood sugar", "glycemic", "low gi"]):
            passes.append("✅ Diabetes tip present in response")
        else:
            violations.append("⚠️  WARNING: No diabetes/blood sugar tip found in Tips section")
    
    if any(m in medical for m in ["hypertension", "low sodium"]):
        forbidden = ["maggi", "stock cube", "bouillon", "knorr"]
        for term in forbidden:
            if re.search(r'\b' + term + r'\b', response_lower):
                violations.append(f"🚨 VIOLATION: '{term}' found — hypertension rule broken")
        if not any(re.search(r'\b' + term + r'\b', response_lower) for term in forbidden):
            passes.append("✅ No high-sodium seasoning found")
        if any(t in response_lower for t in ["sodium", "blood pressure", "hypertension"]):
            passes.append("✅ Low-sodium tip present in response")
        else:
            violations.append("⚠️  WARNING: No sodium/blood pressure tip in Tips section")
    
    # Dislikes checks
    dislikes = [d.lower() for d in (profile.get("dislikes") or [])]
    for dislike in dislikes:
        if re.search(r'\b' + dislike + r'\b', response_lower):
            violations.append(f"🚨 VIOLATION: Disliked ingredient '{dislike}' found")
        else:
            passes.append(f"✅ Disliked ingredient '{dislike}' correctly excluded")
    
    # Print validation summary
    print(f"\n{'─'*80}")
    print("PERSONALISATION VALIDATION:")
    for p in passes:
        print(f"  {p}")
    for v in violations:
        print(f"  {v}")
    
    if violations:
        print(f"\n  ⚠️  {len(violations)} issue(s) detected")
    else:
        print(f"\n  🎯 All personalisation checks passed for this response")
    print(f"{'─'*80}\n")


class JemaCLI:
    """Interactive CLI for testing Jema engine."""

    def __init__(self, excel_path: Optional[str] = None, debug: bool = False):
        """
        Initialize Jema CLI.
        
        Args:
            excel_path: Optional path to custom Excel recipe file
            debug: Enable verbose debug output
        """
        self.debug = debug
        self.engine: Optional[JemaEngine] = None
        self.excel_path = excel_path
        self.active_profile: Optional[Dict] = None  # Store selected personalisation profile
        self.chat_history: List[Dict[str, str]] = []  # Store conversation history
        
        # Initialize engine
        self._initialize_engine()
    
    def _initialize_engine(self) -> None:
        """Initialize the JemaEngine."""
        try:
            print("⚙️  Initializing Jema Engine...")
            self.engine = JemaEngine(excel_path=self.excel_path)
            self.engine.debug_mode = self.debug
            print("✅ Jema Engine ready!\n")
        except FileNotFoundError as e:
            print(f"❌ File not found: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error initializing engine: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    
    def _print_debug_info(self, response: Dict) -> None:
        """Print debug information from response."""
        if not self.debug:
            return
        
        print("\n" + "=" * 60)
        print("DEBUG INFORMATION")
        print("=" * 60)
        
        # Language detected
        if "language" in response:
            lang = response["language"]
            print(f"🌍 Language Detected: {lang.upper()}")
        
        # State information
        if "state" in response:
            state = response["state"]
            print(f"\n📊 Conversation State:")
            for key, value in state.items():
                if isinstance(value, (list, set)):
                    print(f"   • {key}: {len(value)} items")
                    if len(value) <= 3:
                        print(f"     {value}")
                elif isinstance(value, dict):
                    print(f"   • {key}: {len(value)} items")
                else:
                    print(f"   • {key}: {value}")
        
        # Recipes information
        if "recipes" in response and response["recipes"]:
            print(f"\n🍳 Recipes in Response: {len(response['recipes'])} recipes")
            for i, recipe in enumerate(response["recipes"][:3], 1):
                meal_name = recipe.get("meal_name", "Unknown")
                print(f"   {i}. {meal_name}")
        
        print("=" * 60 + "\n")
    
    def _print_response(self, response: Dict) -> None:
        """
        Format and print a response from the engine.
        
        Args:
            response: Response dictionary from JemaEngine.process_message()
        """
        # Main message
        if "message" in response:
            print(f"\n🤖 Jema: {response['message']}")
        
        # CTA if provided
        if "cta" in response and response["cta"]:
            print(f"\n💡 {response['cta']}")
        
        print()
        
        # Debug info if enabled
        self._print_debug_info(response)
    
    def _print_help(self) -> None:
        """Print available commands."""
        help_text = """
╔════════════════════════════════════════════════════════════╗
║              JEMA CLI - Available Commands                 ║
╚════════════════════════════════════════════════════════════╝

CHAT COMMANDS:
  • Just type normally to chat with Jema
  • "exit" or "quit" or "/quit"  → End the session
  • "reset" or "clear" or "/clear" → Start a new conversation

PERSONALISATION COMMANDS (NEW):
  • "/profile"           → Show current profile restrictions
  • "/switch"            → Change to a different profile
  • "/history"           → View chat history
  
DEBUG COMMANDS:
  • "debug"              → Toggle debug output
  • "help"               → Show this help message
  • "state"              → Print current conversation state

PERSONALISATION VALIDATION:
  After each response, violations are automatically checked:
  ✅ Allergies never appear in response
  ✅ Forbidden ingredients excluded (keto, vegan, halal, etc.)
  ✅ Medical tips included when profile requires it
  ✅ Cooking level matches profile (novice/advanced)

EXAMPLE INPUTS:
  • "I have onions and eggs"
  • "What can I cook with tomatoes?"
  • "Give me a recipe for Ugali"
  • "What are the nutritional benefits?"
  • "Show me East African dishes"

════════════════════════════════════════════════════════════
"""
        print(help_text)

    
    def _print_state(self) -> None:
        """Print current conversation state."""
        if not self.engine:
            print("❌ Engine not initialized\n")
            return
        
        print("\n" + "=" * 60)
        print("CONVERSATION STATE")
        print("=" * 60)
        print(f"Language: {self.engine.llm.current_language.upper()}")
        print(f"Last Suggested Recipes: {len(self.engine.last_suggested_recipes)} recipes")
        print(f"Rejected Recipes: {len(self.engine.rejected_recipes)} items")
        print(f"Last User Ingredients: {self.engine.last_user_ingredients or 'None'}")
        print(f"Current Recipe: {self.engine.current_recipe.get('meal_name') if self.engine.current_recipe else 'None'}")
        print(f"Recipe Confirmed: {self.engine.recipe_confirmed}")
        print(f"Awaiting Recipe Choice: {self.engine.awaiting_recipe_choice}")
        print(f"Conversation History Length: {len(self.engine.llm.conversation_history) if self.engine.llm else 0}")
        print("=" * 60 + "\n")
    
    def run(self) -> None:
        """Start the interactive CLI loop."""
        print("\n" + "=" * 60)
        print("  JEMA - African Cooking Assistant")
        print("=" * 60)
        print(f"Debug Mode: {'ON ✓' if self.debug else 'OFF'}")
        print("Type 'help' for available commands\n")
        
        # PERSONALISATION: Show profile selector
        self.active_profile = select_profile()
        print_active_profile(self.active_profile)
        print_validation_cheatsheet(self.active_profile)
        
        greetings = [
            "Hello! I'm Jema. Tell me what ingredients you have or what you'd like to cook!",
            "Habari! Mimi ni Jema. Niambie viungo unavyonazo!",
        ]
        print(f"🤖 Jema: {greetings[0]}\n")
        
        try:
            while True:
                # Get user input
                try:
                    user_input = input("You: ").strip()
                except EOFError:
                    # Handle pipe/redirect input
                    break
                
                if not user_input:
                    continue
                
                # Handle special commands
                if user_input.lower() in ["exit", "quit", "/quit"]:
                    self._handle_exit()
                    break
                elif user_input.lower() == "help":
                    self._print_help()
                    continue
                elif user_input.lower() == "debug":
                    self.debug = not self.debug
                    self.engine.debug_mode = self.debug  # keep engine in sync
                    status = "ON ✓" if self.debug else "OFF"
                    print(f"🔧 Debug mode: {status}\n")
                    continue
                elif user_input.lower() == "state":
                    self._print_state()
                    continue
                elif user_input.lower() in ["reset", "clear", "/clear", "new conversation"]:
                    print("🔄 Starting new conversation...\n")
                    self.chat_history = []
                    self._initialize_engine()
                    continue
                elif user_input.lower() == "/profile":
                    print_active_profile(self.active_profile)
                    continue
                elif user_input.lower() == "/switch":
                    new_profile = select_profile()
                    self.active_profile = new_profile
                    print_active_profile(self.active_profile)
                    print_validation_cheatsheet(self.active_profile)
                    continue
                elif user_input.lower() == "/history":
                    self._print_chat_history()
                    continue
                
                # Process message through engine
                self._process_user_input(user_input)
        
        except KeyboardInterrupt:
            self._handle_exit()
    
    def _process_user_input(self, user_input: str) -> None:
        """
        Process a user message through the engine.
        
        Args:
            user_input: User's message
        """
        if not self.engine:
            print("❌ Engine not initialized\n")
            return
        
        try:
            # Build ProfileContext from active profile if available
            ctx = None
            if self.active_profile:
                try:
                    ctx = ProfileContext(self.active_profile)
                    print(f"[ProfileContext] Active — diet={ctx.diet}, religion={ctx.religion}, forbidden={len(ctx.forbidden)} tokens")
                except ProfileMissingError as e:
                    print(f"❌ Profile error: {e}")
                    return
            
            # Process message with ProfileContext
            response = self.engine.process_message(user_input, ctx=ctx)
            
            # Store in chat history
            self.chat_history.append({"user": user_input, "jema": response})
            
            # Print response
            self._print_response(response)
        
        except Exception as e:
            print(f"\n❌ Error processing message: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            print()
    
    def _print_chat_history(self) -> None:
        """Print chat history."""
        if not self.chat_history:
            print("\n📝 Chat history is empty\n")
            return
        
        print(f"\n{'='*80}")
        print(f"📝 Chat History ({len(self.chat_history)} exchanges)")
        print(f"{'='*80}\n")
        
        for i, exchange in enumerate(self.chat_history, 1):
            print(f"[Exchange {i}]")
            print(f"  You: {exchange['user']}")
            print(f"  Jema: {exchange['jema'].get('response', '')[:200]}...\n")
        
        print(f"{'='*80}\n")
    
    def _handle_exit(self) -> None:
        """Handle exit gracefully."""
        print("\n👋 Goodbye! Thank you for using Jema!\n")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Jema CLI - Test the cooking assistant pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py                  # Run in normal mode
  python cli.py --debug          # Run with debug output
  python cli.py --excel /path/to/recipes.xlsx  # Use custom recipe file
        """
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose output"
    )
    parser.add_argument(
        "--excel",
        type=str,
        default=None,
        help="Path to custom Excel recipe file"
    )
    
    args = parser.parse_args()
    
    # Create and run CLI
    cli = JemaCLI(excel_path=args.excel, debug=args.debug)
    cli.run()


if __name__ == "__main__":
    main()
