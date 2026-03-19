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
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to path for imports
JEMA_DIR = Path(__file__).parent
sys.path.insert(0, str(JEMA_DIR.parent))

# Import the main engine
try:
    from jema.services.jema_engine import JemaEngine
except ImportError as e:
    print(f"❌ Error importing JemaEngine: {e}")
    print(f"   Make sure you're running from the correct directory.")
    print(f"   Current directory: {os.getcwd()}")
    sys.exit(1)


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
  • "exit" or "quit"     → End the session
  • "reset" or "clear"   → Start a new conversation

DEBUG COMMANDS:
  • "debug"              → Toggle debug output
  • "help"               → Show this help message
  • "state"              → Print current conversation state

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
                if user_input.lower() in ["exit", "quit"]:
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
                elif user_input.lower() in ["reset", "clear", "new conversation"]:
                    print("🔄 Starting new conversation...\n")
                    self._initialize_engine()
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
            response = self.engine.process_message(user_input)
            self._print_response(response)
        
        except Exception as e:
            print(f"\n❌ Error processing message: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            print()
    
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
