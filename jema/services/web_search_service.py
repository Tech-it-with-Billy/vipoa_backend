"""
Web Search Service using Tavily API
Searches for verified African recipe steps from trusted cooking websites using progressive queries.
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, List

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


# Trusted African cooking websites by region
TRUSTED_DOMAINS_BY_REGION = {
    "east_africa": [
        "instapilau.com",
        "karibu.sasakonnect.net",
        "youtube.com",
    ],
    "west_africa": [
        "yummymedley.com",
        "cheflolaskitchen.com",
        "linsfood.com",
        "eatwellabi.com",
    ],
    "north_africa": [
        "saveur.com",
        "allrecipes.com",
        "carolinescooking.com",
    ],
}

# Fallback trusted domains (used when region is unknown)
TRUSTED_DOMAINS_ALL = [
    "instapilau.com",
    "karibu.sasakonnect.net",
    "yummymedley.com",
    "cheflolaskitchen.com",
    "linsfood.com",
    "eatwellabi.com",
    "saveur.com",
    "allrecipes.com",
    "carolinescooking.com",
    "immaculatebites.com",
    "tasteatlas.com",
    "kenyanfoodie.com",
    "mydiasporakitchen.com",
    "thespruceeats.com",
    "recipetineats.com",
    "africafromedit.com",
]


class WebSearchService:
    """Search for verified recipe steps using Tavily API with progressive queries."""
    
    def __init__(self):
        self.client = None
        
        # Load .env manually from jema/.env
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
        
        api_key = os.environ.get("TAVILY_API_KEY")
        
        if not api_key:
            print(
                "[WebSearchService] TAVILY_API_KEY not found in environment. "
                "Web search will be skipped. Add TAVILY_API_KEY=tvly-xxxx to your .env file."
            )
            return
        
        if TavilyClient is None:
            print("[WebSearchService] tavily package not installed. Web search will be skipped.")
            return
        
        try:
            self.client = TavilyClient(api_key=api_key)
        except Exception as e:
            print(f"[WebSearchService] Failed to initialize Tavily client: {e}")

    def _count_ingredients(self, text: str) -> int:
        """
        Count potential ingredients in text by looking for lines with common ingredient patterns:
        - Lines with amounts (e.g., "2 cups flour", "1 tablespoon oil")
        - Lines with ingredient keywords
        """
        lines = text.lower().split('\n')
        ingredient_count = 0
        
        # Amount patterns like "1 cup", "2 tbsp", "3-4", "1/2", etc.
        amount_pattern = r'^\s*[\d\-\/\.\s]+\s*(cup|tbsp|tsp|tablespoon|teaspoon|gram|g|ml|l|kg|oz|pound)?s?\s+'
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Check for amount pattern at start of line
            if re.match(amount_pattern, line):
                ingredient_count += 1
            # Check for ingredient keywords on their own lines
            elif any(keyword in line for keyword in ['flour', 'oil', 'salt', 'pepper', 'water', 'onion', 
                                                      'garlic', 'tomato', 'rice', 'beans', 'meat', 'chicken',
                                                      'fish', 'egg', 'milk', 'butter', 'spice', 'herb']):
                ingredient_count += 1
        
        return ingredient_count

    def _count_steps(self, text: str) -> int:
        """
        Count potential cooking steps by looking for:
        - Numbered lines (1., 2., etc.)
        - Bulleted lines (-, *, •)
        - Lines with cooking verbs
        """
        lines = text.lower().split('\n')
        step_count = 0
        
        cooking_verbs = [
            'heat', 'cook', 'fry', 'bake', 'boil', 'simmer', 'stir', 'mix', 'add',
            'peel', 'chop', 'slice', 'dice', 'grate', 'blend', 'knead', 'combine',
            'season', 'drain', 'pour', 'serve', 'prepare', 'wash', 'cut', 'remove',
            'place', 'set', 'let', 'measure', 'sauté', 'roast', 'steam', 'broil'
        ]
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            # Check for numbered format (1., 2., 1), 2), etc.)
            if re.match(r'^\d+[\.\)]\s+', line):
                step_count += 1
            # Check for bullet points
            elif line.startswith(('-', '*', '•')):
                step_count += 1
            # Check for cooking verbs at start of line
            elif any(line.startswith(verb) for verb in cooking_verbs):
                step_count += 1
        
        return step_count

    def _validate_result(self, text: str) -> bool:
        """
        Validate that a search result is a real recipe with:
        - At least 3 ingredients
        - At least 3 preparation steps
        - At least 300 characters of content (after basic cleanup)
        """
        if not text:
            return False
        
        # Check minimum length
        text_clean = text.strip()
        if len(text_clean) < 300:
            return False
        
        # Check ingredient count
        ingredient_count = self._count_ingredients(text_clean)
        if ingredient_count < 3:
            return False
        
        # Check step count
        step_count = self._count_steps(text_clean)
        if step_count < 3:
            return False
        
        return True

    def _build_progressive_queries(self, recipe_name: str, region: str = None) -> List[str]:
        """
        Build progressive queries from most specific to most general.
        
        Query progression:
        1. Exact dish name
        2. Dish name + country/region
        3. Dish name + "recipe"
        4. Dish name + cultural group (if available)
        5. Broad descriptive fallback
        """
        queries = []
        
        # Query 1: Exact dish name
        queries.append(f'"{recipe_name}"')
        
        # Query 2: Dish name + region/country
        if region:
            region_clean = region.strip().lower()
            queries.append(f'"{recipe_name}" {region_clean}')
        
        # Query 3: Dish name + "recipe"
        queries.append(f'"{recipe_name}" recipe')
        
        # Query 4: Dish name + common cultural groups (East Africa focus)
        cultural_groups = [
            'Kamba', 'Kikuyu', 'Maasai', 'Samburu', 'Turkana', 'Swahili',  # East Africa
            'Yoruba', 'Igbo', 'Hausa',  # West Africa
            'Berber', 'Maghrebi',  # North Africa
        ]
        for group in cultural_groups:
            if group.lower() not in recipe_name.lower():
                queries.append(f'"{recipe_name}" {group}')
                break  # Only try one cultural group query
        
        # Query 5: Broad descriptive fallback
        if region:
            queries.append(f'traditional {region.lower()} {recipe_name} recipe')
        else:
            queries.append(f'traditional African {recipe_name} recipe')
        
        return queries

    def search_recipe(self, recipe_name: str, region: str = "East Africa") -> Optional[str]:
        """
        Search for verified recipe steps from trusted African cooking sites using progressive queries.
        
        Args:
            recipe_name: Name of the recipe to search for
            region: Geographic region (e.g., "East Africa", "Kenya", "Nigeria") - used for query construction
        
        Returns:
            Formatted recipe content if valid result found, None if all queries fail
        """
        if not self.client:
            return None
        
        if not recipe_name or not recipe_name.strip():
            return None
        
        recipe_name = recipe_name.strip()
        queries = self._build_progressive_queries(recipe_name, region)
        
        # Try each query in order until we get a valid result
        for query in queries:
            try:
                result = self._search_single_query(query)
                if result:
                    return result
            except Exception as e:
                print(f"[WebSearchService] Query '{query}' failed: {e}")
                continue
        
        # All queries failed
        return None

    def _search_single_query(self, query: str) -> Optional[str]:
        """
        Execute a single search query and validate the result.
        
        Returns formatted content if valid, None otherwise.
        """
        try:
            response = self.client.search(
                query=query,
                search_depth="advanced",
                include_domains=TRUSTED_DOMAINS_ALL,
                max_results=5
            )
            
            results = response.get("results", [])
            if not results:
                return None

            # Try each result until we find one that validates
            for result in results:
                content = result.get("content", "")
                url = result.get("url", "")
                
                if not content:
                    continue
                
                # Validate this result
                if self._validate_result(content):
                    # Format the result with source attribution
                    formatted = f"Source: {url}\n\n{content}"
                    return formatted.strip()
            
            # No results from this query passed validation
            return None

        except Exception as e:
            print(f"[WebSearchService] Search error for query '{query}': {e}")
            return None

    def is_available(self) -> bool:
        """Check if the web search service is properly initialized and available."""
        return self.client is not None

