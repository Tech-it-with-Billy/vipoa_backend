"""

INTEGRATION CHECKLIST: New Excel-First Modules
-----

These are the key changes needed to integrate the new modules into chat.py
"""

INTEGRATION_STEPS = """

WHAT TO ADD TO chat.py MAIN LOOP
-----

1. IMPORTS (add these at the top)
   --
   from intent_classifier import IntentClassifier, Intent, Constraint
   from excel_recipe_matcher import ExcelRecipeMatcher
   from substitute_resolver import SubstituteResolver
   from simple_recipe_formatter import SimpleRecipeFormatter
   from ingredient_normalizer_v2 import IngredientNormalizer
   from conversation_state import ConversationState

2. INITIALIZATION (in main() function, after loading data)
   --
   # Create Excel-aware components
   excel_matcher = ExcelRecipeMatcher(data["recipes"])
   substitute_resolver = SubstituteResolver(data["recipes"])
   ingredient_normalizer = IngredientNormalizer()
   conversation_state = ConversationState()


3. LOGIC WITH NEW FLOW
   -----
   NEW (improved):
   
    1. Check greeting                        
    2. Classify intent + detect community    
    3. Extract & normalize ingredients       
    4. Update conversation state             
    5. Apply Excel filters (community, etc)  
    6. Score & match recipes                 
    7. Format response                       
    8. Handle follow-ups                     


4. MAIN LOOP PSEUDOCODE
   -----
   
   while True:
       user_input = input("\\nYou: ").strip()
       user_lower = user_input.lower()
       
       # 0. Greeting check (keep existing)
       if is_simple_greeting:
           # existing greeting logic
           continue
       
       # 1. CLASSIFY INTENT & DETECT COMMUNITY (NEW)
       intent, constraints, detected_community, confidence = IntentClassifier.classify(user_input)
       
       # 2. EXTRACT INGREDIENTS (keep but improve)
       user_ingredients = normalizer.normalize(user_input)
       
       # 3. UPDATE STATE
       conversation_state.last_intent = intent.value
       for constraint in constraints:
           conversation_state.add_constraint(constraint.value)
       if detected_community:
           conversation_state.preferred_community = detected_community
       
       # 4. ROUTE BY INTENT
       
       if intent == Intent.INGREDIENT_BASED:
           # User has ingredients: "I have rice, beans..."
           conversation_state.update_ingredients(user_ingredients)
           
           # Apply filters
           matcher = excel_matcher
           if detected_community:
               matcher = matcher.filter_by_community(detected_community)
           
           if Constraint.QUICK in constraints:
               matcher = matcher.filter_by_cook_time(30)
           
           # Score & match
           scores = matcher.match(user_ingredients, min_match_percentage=0.6)
           
           if not scores:
               print("\\nNo recipes found. Do you have salt or oil?")
           elif len(scores) == 1:
               score = scores[0]
               recipe_row = matcher.recipes_df.iloc[score.recipe_id]
               response = SimpleRecipeFormatter.format_recipe_response(
                   recipe_row, score.ingredient_matches, 
                   score.ingredient_matches + score.ingredient_misses,
                   score.missing_ingredients, score.substitutes
               )
               print(f"\\n{response}")
           else:
               summary = SimpleRecipeFormatter.format_match_summary(scores, max_shown=3)
               print(f"\\n{summary}")
       
       elif intent == Intent.RECIPE_REQUEST:
           # User asks for specific recipe: "I want a kikuyu meal"
           if detected_community:
               # Show all meals from that community
               matcher = excel_matcher.filter_by_community(detected_community)
               matcher = matcher.exclude_beverages()
               # Get first 5 meals...
           else:
               # Extract recipe name and look it up
               score = excel_matcher.match_by_name(user_input)
               if score:
                   recipe_row = excel_matcher.recipes_df.iloc[score.recipe_id]
                   response = SimpleRecipeFormatter.format_recipe_response(recipe_row, ...)
                   print(f"\\n{response}")
       
       elif intent == Intent.HOW_TO_COOK:
           # Use LLM (existing logic with history)
           response = llm.general_response(user_input, use_history=True)
           print(f"\\n{response}")
       
       # ... handle other intents ...
       
       # ADD TO HISTORY
       conversation_state.messages_count += 1
       llm.add_to_history("user", user_input)
       # (add assistant response too)


5. KEY FUNCTIONS TO ADD
   ---
   
   def extract_recipe_name_from_input(user_input: str) -> Optional[str]:
       \"\"\"Extract recipe name from request like 'make me ugali'\"\"\"
       # Remove common phrases
       cleaned = user_input.lower()
       for phrase in ['make me ', 'i want ', 'recipe for ', 'how to make ']:
           cleaned = cleaned.replace(phrase, '')
       return cleaned.strip()
   
   def format_meals_list(recipes_df: pd.DataFrame, community: str) -> str:
       \"\"\"Format list of meals from a community\"\"\"
       meals = recipes_df[recipes_df['community'] == community]
       output = f"Traditional {community.title()} meals:\\n\\n"
       for idx, meal in enumerate(meals.iterrows(), 1):
           output += f"{idx}. {meal['meal_name']} ({meal['meal_type ']})\\n"
       return output


6. TESTING SCENARIOS
   -----
   
    "I want a traditional kikuyu meal, do you have one?"
      → Detect: intent=RECIPE_REQUEST, community=kikuyu, constraint=TRADITIONAL
      → Filter: Excel by community='Kikuyu', exclude beverages
      → Show: List of Kikuyu meals (Irio, Mukimo, Njahi, etc.)
   
    "I have rice, tomatoes, onions"
      → Detect: intent=INGREDIENT_BASED
      → Normalize: {rice, tomato, onion}
      → Score: Top match = Tomato Rice (90%)
      → Show: Full recipe
   
    "Something quick with chicken"
      → Detect: intent=MEAL_IDEA, constraint=QUICK
      → Filter: cook_time ≤ 30
      → Match against ingredients if provided
      → Show: Quick chicken recipes
   
    "I don't like that"
      → Detect: intent=REJECTION
      → Mark last_recipe as rejected
      → Show: Next best alternative
   
    "What's in it?" (after recipe shown)
      → Detect: intent=FOLLOW_UP
      → Use LLM with conversation history
      → Explain dish or ingredients


7. WHAT TO KEEP FROM OLD LOGIC
   -----
   
    Greeting detection (but improved)
    Language detection (llm.update_language)
    Conversation history (llm.add_to_history)
    LLM for explanations and follow-ups
    Error handling and fallbacks


8. WHAT TO REMOVE FROM OLD LOGIC
   -----
   
    Complex rule-based intent detection (replaced with IntentClassifier)
    Manual cuisine filtering (now automated by community detection)
    RecipeEngine.match_recipes() (replaced with ExcelRecipeMatcher)
    Manual recipe filtering logic (all in ExcelRecipeMatcher now)


FILES CREATED/MODIFIED:
-----

NEW:

  ✓ src/intent_classifier.py        - Intent & community detection
  ✓ src/excel_recipe_matcher.py     - Excel-aware recipe matching & scoring
  ✓ src/ingredient_normalizer_v2.py - Ingredient normalization
  ✓ src/substitute_resolver.py      - Substitute suggestions
  ✓ src/simple_recipe_formatter.py  - Simple Excel recipe formatting
  ✓ src/conversation_state.py       - Conversation state tracking
  ✓ src/community_example.py        - Example integration

MODIFIED:
  ✓ src/intent_classifier.py        - Added COMMUNITIES dict

TO MODIFY:
  → src/chat.py                     - Main integration (see pseudocode above)


TESTING BEFORE FULL INTEGRATION:
-----

# Test individually:
python -c "from intent_classifier import IntentClassifier; print(IntentClassifier.classify('i want a traditional kikuyu meal'))"

# Test matcher:
python -c "
from data_loader import DataLoader
from excel_recipe_matcher import ExcelRecipeMatcher
loader = DataLoader('../data/...')
data = loader.load_all()
matcher = ExcelRecipeMatcher(data['recipes'])
matcher = matcher.filter_by_community('Kikuyu')
print(matcher.recipes_df[['meal_name', 'community']].head())
"
"""

print(INTEGRATION_STEPS)
