"""
Jema Chat - Refactored with Intent-First, Excel-Driven Architecture
"""

from jema.src.data_loader import DataLoader
from jema.src.ingredient_normalizer_v2 import IngredientNormalizer
from jema.src.excel_recipe_matcher import ExcelRecipeMatcher
from jema.src.intent_classifier import IntentClassifier, Intent, Constraint
from jema.src.llm_service import LLMService
from jema.src.substitute_resolver import SubstituteResolver
from jema.src.language_detector import LanguageDetector
from jema.src.response_formatter import CTAFormatter, ResponseType
import pandas as pd


def main():
    # Load Excel data
    loader = DataLoader("../data/Jema_AI_East_Africa_Core_Meals_Phase1.xlsx")
    data = loader.load_all()

    # Initialize services with new architecture
    recipes_df = data["recipes"]
    matcher = ExcelRecipeMatcher(recipes_df)
    substitute_resolver = SubstituteResolver(recipes_df)
    llm = LLMService()

    # Track conversation state
    last_suggested_recipes = []
    rejected_recipes = []
    last_user_ingredients = set()
    
    # === RECIPE LOCK-IN STATE ===
    current_recipe = None  # Currently active recipe (locked in)
    recipe_confirmed = False  # Has user confirmed recipe selection?
    awaiting_recipe_choice = False  # Is bot waiting for user to pick from options?

    print("Hi! I'm Jema. Tell me what ingredients you have or what you'd like to cook!")

    while True:
        user_input = input("\nYou: ").strip()

        if user_input.lower() in ["quit", "exit"]:
            print("Goodbye!")
            break
        
        if user_input.lower() in ["clear", "reset", "new conversation"]:
            llm.clear_history()
            last_suggested_recipes = []
            rejected_recipes = []
            current_recipe = None
            recipe_confirmed = False
            awaiting_recipe_choice = False
            print("Conversation history cleared. Let's start fresh!")
            continue
        
        # Detect user language
        llm.update_language(user_input)

        # === INTENT-FIRST ARCHITECTURE ===
        # Step 1: Classify user intent and detect constraints
        intent, constraints, community, confidence = IntentClassifier.classify(user_input)
        
        # === COMMUNITY-BASED REQUEST (High Priority) ===
        # If user asks for recipes from a specific community, handle it specially
        if community and intent in [Intent.MEAL_IDEA, Intent.INFORMATION, Intent.CHAT_SOCIAL, Intent.RECIPE_REQUEST]:
            # Filter recipes by community
            community_matcher = matcher.filter_by_community(community).exclude_beverages()
            
            # Get all recipes from this community
            all_community_recipes = recipes_df[recipes_df['community'].str.lower() == community.lower()] if 'community' in recipes_df.columns else pd.DataFrame()
            
            if not all_community_recipes.empty:
                # Show top 3-5 recipes from this community
                top_recipes = all_community_recipes.head(5)
                
                print(f"\nHey there, you could try one of the following:\n")
                recipe_list = []
                for i, (idx, recipe) in enumerate(top_recipes.iterrows(), 1):
                    meal_type = recipe.get('meal_type ', 'dish')
                    cook_time = recipe.get('cook_time', '')
                    time_str = f" ({cook_time} min)" if pd.notna(cook_time) and cook_time else ""
                    print(f"{i}. {recipe['meal_name']}{time_str}")
                    recipe_list.append(recipe.to_dict())
                
                print(f"\nWhich one would you like?")
                
                # Set state for selection
                last_suggested_recipes = recipe_list
                awaiting_recipe_choice = True
                
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", f"Suggested {len(recipe_list)} {community.title()} recipes.")
                continue
            else:
                # No recipes found for this community
                print(f"\nI don't have specific recipes from the {community.title()} community in my database yet.")
                print("But I can help you with other East African dishes. What ingredients do you have?")
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", f"No {community.title()} recipes found.")
                continue
        
        # --- GREETING ---
        if intent == Intent.GREETING:
            # If user is in recipe mode, ignore greeting
            if recipe_confirmed and current_recipe:
                # Redirect to help with current recipe
                response = llm.general_response(
                    f"User said: '{user_input}' (they're working on {current_recipe.get('meal_name', 'a recipe')})",
                    use_history=False,
                    include_cta=False
                )
                print(f"\n{response}")
            elif len(llm.conversation_history) > 0:
                response = llm.general_response(user_input, use_history=True, include_cta=False)
                print(f"\n{response}")
            else:
                # Swahili greeting only (limited translation for now)
                if llm.current_language == 'swahili':
                    print("\nHabari! Mimi ni Jema. Niambie viungo unavyonazo au chakula unachotaka!")
                else:
                    print("\nHello! I'm Jema, your East African cooking assistant. Tell me what ingredients you have or what you'd like to cook!")
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", "Hello! I'm Jema.")
            continue
        
        # --- REJECTION (User doesn't like suggested recipe) ---
        if intent == Intent.REJECTION:
            # Clear recipe lock when user rejects
            current_recipe = None
            recipe_confirmed = False
            
            if last_suggested_recipes:
                # Add rejected recipe to list
                if last_suggested_recipes:
                    rejected_recipes.extend([r['meal_name'] for r in last_suggested_recipes[:1]])
                
                # Find alternatives (excluding rejected ones)
                alternatives = []
                for idx, recipe in recipes_df.iterrows():
                    if recipe['meal_name'] not in rejected_recipes:
                        alternatives.append(recipe)
                    if len(alternatives) >= 3:
                        break
                
                if alternatives:
                    print("\nNo problem! Here are some alternatives:\n")
                    for i, recipe in enumerate(alternatives, 1):
                        cook_time = recipe.get('cook_time', '')
                        meal_type = recipe.get('meal_type ', 'dish')
                        print(f"{i}. {recipe['meal_name']} - {meal_type} ({cook_time} min)")
                    
                    cta = CTAFormatter.format_multiple_options_with_cta(
                        "\nWhich one interests you?",
                        [r['meal_name'] for r in alternatives],
                        llm.current_language
                    )
                    print(cta)
                    last_suggested_recipes = alternatives
                    awaiting_recipe_choice = True
                else:
                    response = llm.general_response(user_input, use_history=True, include_cta=False)
                    print(f"\n{response}")
            else:
                response = llm.general_response(user_input, use_history=True, include_cta=False)
                print(f"\n{response}")
            
            llm.add_to_history("user", user_input)
            llm.add_to_history("assistant", "Suggested alternative recipes or provided general response.")
            continue
        
        # --- ACCOMPANIMENT (What goes with this dish?) ---
        if intent == Intent.ACCOMPANIMENT:
            # Extract the dish name from user input
            dish_name = None
            for pattern in ["with", "goes with"]:
                if pattern in user_input.lower():
                    parts = user_input.lower().split(pattern)
                    if len(parts) > 1:
                        dish_name = parts[-1].strip()
                        break
            
            if dish_name:
                # Search for recipes that pair well or complement the dish
                response = llm.general_response(
                    f"What are good side dishes or accompaniments to serve with {dish_name}? Suggest traditional East African options.",
                    use_history=False,
                    include_cta=False
                )
                print(f"\n{response}")
            else:
                response = llm.general_response(user_input, use_history=True, include_cta=False)
                print(f"\n{response}")
            
            llm.add_to_history("user", user_input)
            llm.add_to_history("assistant", "Suggested accompaniments.")
            continue
        
        # --- FOLLOW-UP QUESTION ---
        if intent == Intent.FOLLOW_UP and len(llm.conversation_history) > 0:
            # If recipe is locked in, focus on clarifying current recipe only
            if recipe_confirmed and current_recipe:
                response = llm.general_response(
                    f"{user_input} (Answer in context of {current_recipe.get('meal_name', 'this recipe')})",
                    use_history=False,
                    include_cta=False
                )
                print(f"\n{response}")
            else:
                response = llm.general_response(user_input, use_history=True, include_cta=False)
                print(f"\n{response}")
            
            llm.add_to_history("user", user_input)
            llm.add_to_history("assistant", response)
            continue

        # === RECIPE SELECTION FROM SUGGESTIONS ===
        # High priority: if user is choosing from the list, serve full recipe immediately
        if awaiting_recipe_choice and last_suggested_recipes:
            # Check if user input is a number (1, 2, 3...) or recipe name
            selected_recipe = None
            try:
                choice_num = int(user_input.strip()) - 1  # Convert 1-indexed to 0-indexed
                if 0 <= choice_num < len(last_suggested_recipes):
                    selected_recipe = last_suggested_recipes[choice_num]
            except ValueError:
                user_input_lower = user_input.lower()
                for recipe in last_suggested_recipes:
                    name_lower = recipe.get('meal_name', '').lower()
                    if name_lower and (name_lower in user_input_lower or user_input_lower in name_lower):
                        selected_recipe = recipe
                        break

            if selected_recipe:
                # Display full recipe for selected choice (NO MORE QUESTIONS)
                recipe_name = selected_recipe.get('meal_name', 'Unknown')
                country = selected_recipe.get('country', '')
                cook_time = selected_recipe.get('cook_time', '')
                ingredients = selected_recipe.get('core_ingredients', '')
                steps = selected_recipe.get('recipes', '')

                recipe_msg = []
                recipe_msg.append(f"Great! Here's the recipe for {recipe_name}:")
                recipe_msg.append(f"\n**{recipe_name}**")
                if pd.notna(country) and country:
                    recipe_msg.append(f"*From: {country}*")
                if pd.notna(cook_time) and cook_time:
                    recipe_msg.append(f"*Time: {cook_time} minutes*\n")

                if pd.notna(ingredients) and ingredients:
                    recipe_msg.append("\n**Ingredients**\n")
                    safe_ingredients = ingredients.replace('→', '->').replace('•', '-').replace('✓', '*')
                    ingredient_list = [ing.strip() for ing in safe_ingredients.split(',')]
                    for ing in ingredient_list:
                        if ing:
                            recipe_msg.append(f"  * {ing}")
                    recipe_msg.append("")

                if pd.notna(steps) and steps:
                    recipe_msg.append("\n**Steps**\n")
                    safe_steps = steps.replace('→', '->').replace('•', '-').replace('✓', '*')
                    safe_steps = safe_steps.replace('Method: Fry', '').replace('Method: Stew', '').replace('Steps: ', '')
                    safe_steps = safe_steps.replace('Time: ', '')
                    safe_steps = safe_steps.replace('30–40 min', '').replace('35–45 min', '').replace('45–60 min', '').replace('20–30 min', '')
                    safe_steps = safe_steps.strip()
                    step_list = [step.strip() for step in safe_steps.split('->')]
                    step_num = 1
                    for step in step_list:
                        if step and step.lower() not in ['', 'fry', 'stew'] and 'min' not in step.lower():
                            recipe_msg.append(f"  {step_num}. {step}")
                            step_num += 1
                    recipe_msg.append("")

                recipe_msg.append("\n**Cooking Tips**\n")
                tips_prompt = f"Give me 2-3 practical cooking tips for making {recipe_name} from East Africa. Include tips like timing, texture, common mistakes to avoid. Keep it brief (2-3 sentences each). No markdown, plain text."
                tips_response = llm.general_response(tips_prompt, use_history=False, include_cta=False)
                tip_lines = tips_response.strip().split('\n')
                for tip_line in tip_lines:
                    if tip_line.strip():
                        recipe_msg.append(f"  • {tip_line.strip()}")

                print("\n" + "\n".join(recipe_msg))
                current_recipe = selected_recipe
                recipe_confirmed = True
                awaiting_recipe_choice = False
                print("\nLet me know if you need clarification on any step!")

                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", "\n".join(recipe_msg))
                continue

            # If we couldn't match, clear the flag and fall through to normal logic
            awaiting_recipe_choice = False
        
        # --- MEAL IDEA (What can I have for breakfast/lunch/dinner?) ---
        if intent == Intent.MEAL_IDEA:
            # Extract meal time if mentioned
            meal_time = ""
            if "breakfast" in user_input.lower():
                meal_time = "breakfast"
            elif "lunch" in user_input.lower():
                meal_time = "lunch"
            elif "dinner" in user_input.lower():
                meal_time = "dinner"
            
            # Get suggestions from LLM
            time_context = f" for {meal_time}" if meal_time else ""
            prompt = f"Suggest 3-4 delicious traditional East African recipes{time_context}. Include the dish name and a brief description of why it's great. Keep it conversational and appetizing."
            response = llm.general_response(prompt, use_history=False, include_cta=False)
            print(f"\n{response}")
            
            llm.add_to_history("user", user_input)
            llm.add_to_history("assistant", "Suggested meal ideas.")
            continue
        
        # --- INFORMATION / CHAT ---
        if intent in [Intent.INFORMATION, Intent.CHAT_SOCIAL]:
            response = llm.general_response(user_input, use_history=True, include_cta=False)
            print(f"\n{response}")
            llm.add_to_history("user", user_input)
            llm.add_to_history("assistant", response)
            continue
        
        # --- RECIPE REQUEST (User wants specific recipe) ---
        if intent == Intent.RECIPE_REQUEST:
            # Extract recipe name from input
            recipe_query = user_input.lower()
            for phrase in ['i would like to make', 'i want to make', 'recipe for', 'how do i make', 'show me', 'ninataka', 'i would like', 'i want']:
                recipe_query = recipe_query.replace(phrase, '').strip()
            
            # Search for recipe by name
            found_recipes = []
            for idx, recipe in recipes_df.iterrows():
                meal_name = recipe.get('meal_name', '')
                # Skip if meal_name is NaN or not a string
                if pd.isna(meal_name):
                    continue
                meal_name_lower = str(meal_name).lower()
                if recipe_query in meal_name_lower:
                    found_recipes.append(recipe)
            
            if found_recipes:
                recipe = found_recipes[0]
                
                # === BUILD COMPLETE RECIPE MESSAGE ===
                recipe_name = recipe.get('meal_name', 'Unknown')
                country = recipe.get('country', '')
                cook_time = recipe.get('cook_time', '')
                ingredients = recipe.get('core_ingredients', '')
                steps = recipe.get('recipes', '')
                
                recipe_msg = []
                recipe_msg.append(f"**{recipe_name}**")
                if pd.notna(country) and country:
                    recipe_msg.append(f"*From: {country}*")
                if pd.notna(cook_time) and cook_time:
                    recipe_msg.append(f"*Time: {cook_time} minutes*\n")
                
                # INGREDIENTS
                if pd.notna(ingredients) and ingredients:
                    recipe_msg.append("\n**Ingredients**\n")
                    safe_ingredients = ingredients.replace('→', '->').replace('•', '-').replace('✓', '*')
                    ingredient_list = [ing.strip() for ing in safe_ingredients.split(',')]
                    for ing in ingredient_list:
                        if ing:
                            recipe_msg.append(f"  * {ing}")
                    recipe_msg.append("")
                
                # STEPS
                if pd.notna(steps) and steps:
                    recipe_msg.append("\n**Steps**\n")
                    safe_steps = steps.replace('→', '->').replace('•', '-').replace('✓', '*')
                    safe_steps = safe_steps.replace('Method: Boil', '').replace('Method: Fry', '').replace('Method: Stew', '').replace('Steps: ', '')
                    safe_steps = safe_steps.replace('Time: ', '')
                    safe_steps = safe_steps.replace('30–40 min', '').replace('35–45 min', '').replace('45–60 min', '').replace('20–30 min', '')
                    safe_steps = safe_steps.strip()
                    
                    step_list = [step.strip() for step in safe_steps.split('->')]
                    step_num = 1
                    for step in step_list:
                        if step and step.lower() not in ['', 'fry', 'stew', 'boil'] and 'min' not in step.lower():
                            recipe_msg.append(f"  {step_num}. {step}")
                            step_num += 1
                    recipe_msg.append("")
                
                # TIPS
                recipe_msg.append("\n**Cooking Tips**\n")
                tips_prompt = f"Give me 2-3 practical cooking tips for making {recipe_name} from East Africa. Include tips like timing, texture, common mistakes to avoid. Keep it brief (2-3 sentences each). No markdown, plain text."
                tips_response = llm.general_response(tips_prompt, use_history=False, include_cta=False)
                tip_lines = tips_response.strip().split('\n')
                for tip_line in tip_lines:
                    if tip_line.strip():
                        recipe_msg.append(f"  • {tip_line.strip()}")
                
                # Print complete recipe
                print("\n" + "\n".join(recipe_msg))
                
                # Set recipe lock-in state
                current_recipe = recipe.to_dict()
                recipe_confirmed = True
                
                # Only one helpful offer at the end
                print("\nLet me know if you need clarification on any step!")
                
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", "\n".join(recipe_msg))
                last_suggested_recipes = [recipe.to_dict()]
            else:
                print(f"\nI don't have a recipe for '{recipe_query}' in my database yet.")
                print("But I can help you make something with ingredients you have. What do you have available?")
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", f"Recipe for '{recipe_query}' not found.")
            continue
        
        
        # --- INGREDIENT-BASED MATCHING ---
        if intent == Intent.INGREDIENT_BASED or intent == Intent.MEAL_IDEA:
            # Extract ingredients from user input
            user_ingredients = IngredientNormalizer.extract_from_string(user_input)
            
            if not user_ingredients:
                response = llm.general_response(user_input, use_history=True, include_cta=False)
                print(f"\n{response}")
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", response)
                continue
            
            # Remember latest ingredients
            last_user_ingredients = set(user_ingredients)
            
            # Match recipes using Excel matcher
            # Build constraints dict
            user_constraints = {}
            if Constraint.QUICK in constraints:
                user_constraints['quick'] = True
            
            # Apply community filter to matcher if specified
            active_matcher = matcher
            if community:
                active_matcher = active_matcher.filter_by_community(community)
            
            # Exclude beverages unless user explicitly asks for drinks
            beverage_terms = ['drink', 'beverage', 'juice', 'tea', 'coffee', 'soda', 'chai']
            if not any(term in user_input.lower() for term in beverage_terms):
                active_matcher = active_matcher.exclude_beverages()
            
            matches = active_matcher.match(
                user_ingredients=user_ingredients,
                user_constraints=user_constraints,
                min_match_percentage=0.4
            )
            
            # Exclude rejected recipes
            if rejected_recipes:
                matches = [m for m in matches if m.name not in rejected_recipes]
            
            if not matches:
                # No strict matches - try lowering threshold for near-misses
                near_matches = active_matcher.match(
                    user_ingredients=user_ingredients,
                    user_constraints=user_constraints,
                    min_match_percentage=0.3
                )
                
                if rejected_recipes:
                    near_matches = [m for m in near_matches if m.name not in rejected_recipes]
                
                if near_matches:
                    # Show near-miss suggestions
                    print(f"\nYou're close! With a few more ingredients, you could make:\n")
                    for i, match in enumerate(near_matches[:3], 1):
                        missing_str = f" (add: {', '.join(match.missing_ingredients[:3])})" if match.missing_ingredients else ""
                        print(f"{i}. {match.name} - {int(match.match_percentage * 100)}% match{missing_str}")
                    
                    cta = CTAFormatter.format_multiple_options_with_cta(
                        "\nInterested in any of these?",
                        [m.name for m in near_matches[:3]],
                        llm.current_language
                    )
                    print(cta)
                    
                    llm.add_to_history("user", user_input)
                    llm.add_to_history("assistant", "Suggested near-match recipes.")
                    last_suggested_recipes = [recipes_df[recipes_df['meal_name'] == m.name].iloc[0].to_dict() for m in near_matches[:3]]
                    continue
                
                # No matches at all - suggest substitutes
                print(f"\nI don't have recipes that match those exact ingredients.")
                
                # Offer general substitutes from the default list
                substitutes_found = False
                ingredient_list = list(user_ingredients)
                for ingredient in ingredient_list[:2]:  # Check first 2 ingredients
                    # Check default substitutes
                    if ingredient in SubstituteResolver.DEFAULT_SUBSTITUTES:
                        subs = SubstituteResolver.DEFAULT_SUBSTITUTES[ingredient]
                        print(f"\nFor {ingredient}, you could try: {', '.join(subs[:3])}")
                        substitutes_found = True
                
                if substitutes_found:
                    cta = CTAFormatter.add_cta(
                        "Would you like recipes with these substitutes?",
                        ResponseType.CLARIFICATION_NEEDED,
                        llm.current_language
                    )
                    print(f"\n{cta}")
                
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", "No matches found, suggested substitutes.")
                continue
            
            # Filter high-confidence matches (≥60%)
            good_matches = [m for m in matches if m.match_percentage >= 0.6]
            
            if not good_matches:
                good_matches = matches[:3]  # Show top 3 even if low confidence
            
            # Show top matches
            if len(good_matches) == 1:
                # Single match - show FULL recipe in ONE message, no confirmation questions
                recipe_data = recipes_df[recipes_df['meal_name'] == good_matches[0].name].iloc[0]
                
                # Display recipe inline (using direct Excel columns)
                recipe_name = recipe_data.get('meal_name', 'Unknown')
                country = recipe_data.get('country', '')
                cook_time = recipe_data.get('cook_time', '')
                ingredients = recipe_data.get('core_ingredients', '')
                steps = recipe_data.get('recipes', '')
                
                # === BUILD COMPLETE RECIPE MESSAGE ===
                recipe_msg = []
                recipe_msg.append(f"Great! Here's the recipe for {recipe_name}:")
                
                # Relate user's ingredients to the recipe
                if last_user_ingredients and pd.notna(ingredients) and ingredients:
                    recipe_ing_list = [s.strip() for s in str(ingredients).split(',') if s.strip()]
                    recipe_ing_set = IngredientNormalizer.normalize_list(recipe_ing_list)
                    have = sorted(list(recipe_ing_set.intersection(last_user_ingredients)))
                    missing = [ing for ing in recipe_ing_set if ing not in last_user_ingredients and not IngredientNormalizer.is_assumed_ingredient(ing)]
                    if have:
                        recipe_msg.append(f"Great! Based on what you have ({', '.join(have)}), here's an easy recipe:")
                    if missing:
                        recipe_msg.append(f"(You may need: {', '.join(missing)})")

                recipe_msg.append(f"\n**{recipe_name}**")
                if pd.notna(country) and country:
                    recipe_msg.append(f"*From: {country}*")
                if pd.notna(cook_time) and cook_time:
                    recipe_msg.append(f"*Time: {cook_time} minutes*\n")
                
                # INGREDIENTS
                if pd.notna(ingredients) and ingredients:
                    recipe_msg.append("\n**Ingredients**\n")
                    safe_ingredients = ingredients.replace('→', '->').replace('•', '-').replace('✓', '*')
                    ingredient_list = [ing.strip() for ing in safe_ingredients.split(',')]
                    for ing in ingredient_list:
                        if ing:
                            recipe_msg.append(f"  * {ing}")
                    recipe_msg.append("")
                
                # STEPS
                if pd.notna(steps) and steps:
                    recipe_msg.append("\n**Steps**\n")
                    safe_steps = steps.replace('→', '->').replace('•', '-').replace('✓', '*')
                    safe_steps = safe_steps.replace('Method: Fry', '').replace('Method: Stew', '').replace('Steps: ', '')
                    safe_steps = safe_steps.replace('Time: ', '')
                    safe_steps = safe_steps.replace('30–40 min', '').replace('35–45 min', '').replace('45–60 min', '').replace('20–30 min', '')
                    safe_steps = safe_steps.strip()
                    
                    step_list = [step.strip() for step in safe_steps.split('->')]
                    step_num = 1
                    for step in step_list:
                        if step and step.lower() not in ['', 'fry', 'stew'] and 'min' not in step.lower():
                            recipe_msg.append(f"  {step_num}. {step}")
                            step_num += 1
                
                # Get LLM tips and add them
                recipe_msg.append("\n**Cooking Tips**\n")
                tips_prompt = f"Give me 2-3 practical cooking tips for making {recipe_name} from East Africa. Include tips like timing, texture, common mistakes to avoid. Keep it brief (2-3 sentences each). No markdown, plain text."
                tips_response = llm.general_response(tips_prompt, use_history=False, include_cta=False)
                tip_lines = tips_response.strip().split('\n')
                for tip_line in tip_lines:
                    if tip_line.strip():
                        recipe_msg.append(f"  • {tip_line.strip()}")
                
                # Print complete recipe
                print("\n" + "\n".join(recipe_msg))
                
                # === NO CONFIRMATION QUESTION - LOCK IN RECIPE ===
                # Only ask ONE helpful follow-up if needed
                recipe_msg_for_history = "\n".join(recipe_msg)
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", recipe_msg_for_history)
                
                # Set recipe lock-in state
                current_recipe = recipe_data.to_dict()
                recipe_confirmed = True
                
                # Ask ONE relevant follow-up question only if it blocks progress
                follow_up = "\nDo you have a deep pan or wok for this recipe, or should I suggest an alternative method?"
                if "fry" in str(steps).lower() or "deep" in str(ingredients).lower():
                    print(f"{follow_up}")
                else:
                    # No blocking questions - just offer optional help
                    print("\nLet me know if you need any clarification on any step, or if you'd like to try something else!")
                
                last_suggested_recipes = [recipe_data.to_dict()]
            
            else:
                # Multiple matches - show options (still no unnecessary questions)
                print(f"\nHey there, you could try one of the following:\n")
                for i, match in enumerate(good_matches[:5], 1):
                    missing_str = f" (add: {', '.join(match.missing_ingredients[:2])})" if match.missing_ingredients else ""
                    print(f"{i}. {match.name} - {int(match.match_percentage * 100)}% match{missing_str}")
                
                # ONE simple question about which to try
                cta = CTAFormatter.format_multiple_options_with_cta(
                    "\nWhich one would you like?",
                    [m.name for m in good_matches[:5]],
                    llm.current_language
                )
                print(cta)
                
                awaiting_recipe_choice = True
                llm.add_to_history("user", user_input)
                llm.add_to_history("assistant", f"Suggested {len(good_matches)} options.")
                last_suggested_recipes = [recipes_df[recipes_df['meal_name'] == m.name].iloc[0].to_dict() for m in good_matches[:5]]
            
            continue
        
        # --- ACCOMPANIMENT (What goes with X?) ---
        if intent == Intent.ACCOMPANIMENT:
            response = llm.general_response(user_input, use_history=True, include_cta=False)
            print(f"\n{response}")
            llm.add_to_history("user", user_input)
            llm.add_to_history("assistant", response)
            continue
        
        # --- FALLBACK (Unrecognized intent) ---
        response = llm.general_response(user_input, use_history=True, include_cta=False)
        print(f"\n{response}")
        llm.add_to_history("user", user_input)
        llm.add_to_history("assistant", response)


if __name__ == "__main__":
    main()
