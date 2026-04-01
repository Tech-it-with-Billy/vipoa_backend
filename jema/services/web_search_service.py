"""
Web Search Service using Tavily API
Searches for verified African recipe steps from trusted cooking websites.
"""

import os
from pathlib import Path
from typing import Optional

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


# Trusted African cooking websites
TRUSTED_DOMAINS = [
    "africanbites.com",
    "immaculatebites.com",
    "tasteatlas.com",
    "kenyanfoodie.com",
    "cheflolaskitchen.com",
    "mydiasporakitchen.com",
    "thespruceeats.com",
    "recipetineats.com",
    "africafromedit.com",
]


class WebSearchService:
    """Search for verified recipe steps using Tavily API."""
    
    def __init__(self):
        self.client = None
        
        # Load .env manually from jema/.env (same as LLMService)
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

    def search_recipe(self, recipe_name: str) -> Optional[str]:
        """
        Search for verified recipe steps from trusted African cooking sites.
        Returns content string only if it is relevant to the requested recipe.
        Returns None if no relevant result found — triggers Groq fallback.
        """
        query = f"{recipe_name} authentic African recipe steps ingredients"
        try:
            response = self.client.search(
                query=query,
                search_depth="advanced",        # more content per result
                include_domains=TRUSTED_DOMAINS,
                max_results=3
            )
            results = response.get("results", [])
            if not results:
                return None

            context = ""
            recipe_keywords = recipe_name.lower().split()

            for result in results:
                content = result.get("content", "")
                url = result.get("url", "")

                # Relevance check — content must mention at least one
                # word from the recipe name to be considered valid
                content_lower = content.lower()
                is_relevant = any(
                    keyword in content_lower
                    for keyword in recipe_keywords
                    if len(keyword) > 3  # skip short words like "na"
                )

                if is_relevant:
                    context += f"Source: {url}\n{content}\n\n"

            # Minimum content threshold — 300 chars means real steps exist
            if len(context.strip()) < 300:
                print(
                    f"[WebSearchService] Rejected results for '{recipe_name}' "
                    f"— content too short or not relevant ({len(context)} chars)"
                )
                return None

            return context.strip()

        except Exception as e:
            print(f"[WebSearchService] Search failed for '{recipe_name}': {e}")
            return None

    def is_available(self) -> bool:
        """Check if the web search service is properly initialized and available."""
        return self.client is not None
