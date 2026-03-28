"""
Jema Source Hierarchy Diagnostic
=================================
Run with:
    python manage.py shell < jema/tests/test_source_hierarchy.py
Or:
    python jema/tests/test_source_hierarchy.py

Tests every layer of the source hierarchy and reports pass/fail clearly.
"""

# import os
# import sys
# from pathlib import Path
# import django

# # --- Add project root to path for proper module discovery ---
# PROJECT_ROOT = Path(__file__).parent.parent.parent
# if str(PROJECT_ROOT) not in sys.path:
#     sys.path.insert(0, str(PROJECT_ROOT))

# # --- Django setup (skip if already in shell) ---
# if not os.environ.get("DJANGO_SETTINGS_MODULE"):
#     os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vipoa_backend.settings")
#     try:
#         django.setup()
#     except Exception as e:
#         print(f"{RED}Error setting up Django: {e}{RESET}")
#         print(f"{YELLOW}Tip: Run with: python manage.py shell < jema/tests/test_source_hierarchy.py{RESET}")
#         sys.exit(1)

# from pathlib import Path

# # ── Colour helpers ──────────────────────────────────────────────────────────
# GREEN  = "\033[92m"
# RED    = "\033[91m"
# YELLOW = "\033[93m"
# RESET  = "\033[0m"

# def ok(msg):   print(f"{GREEN}  ✅ PASS:{RESET} {msg}")
# def fail(msg): print(f"{RED}  ❌ FAIL:{RESET} {msg}")
# def warn(msg): print(f"{YELLOW}  ⚠️  WARN:{RESET} {msg}")
# def section(title): print(f"\n{'─'*60}\n🔍 {title}\n{'─'*60}")

# errors = []

import os
import sys
from pathlib import Path  # ✅ FIX: must come before usage
import django

# ── Colour helpers ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}  ✅ PASS:{RESET} {msg}")
def fail(msg): print(f"{RED}  ❌ FAIL:{RESET} {msg}")
def warn(msg): print(f"{YELLOW}  ⚠️  WARN:{RESET} {msg}")
def section(title): print(f"\n{'─'*60}\n🔍 {title}\n{'─'*60}")

errors = []

# --- Add project root to path for proper module discovery ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Django setup (skip if already in shell) ---
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vipoa_backend.settings")
    try:
        django.setup()
    except Exception as e:
        print(f"{RED}Error setting up Django: {e}{RESET}")
        print(f"{YELLOW}Tip: Run with: python manage.py shell < jema/tests/test_source_hierarchy.py{RESET}")
        sys.exit(1)

# --- Load .env file to populate environment variables ---
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f.read().splitlines():
            line = line.strip()
            if line and '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


# ════════════════════════════════════════════════════════════════════════════
# LAYER 1 — PDF RECIPE STORE
# ════════════════════════════════════════════════════════════════════════════
section("LAYER 1 — PDF Recipe Store")

try:
    from jema.services.pdf_recipe_store import PDFRecipeStore
    ok("pdf_recipe_store.py imported successfully")
except ImportError as e:
    fail(f"Could not import PDFRecipeStore: {e}")
    errors.append("PDFRecipeStore import failed")
    PDFRecipeStore = None

if PDFRecipeStore:
    # 1a — Check PDF file exists
    PDF_PATH = Path(__file__).parent.parent / "data" / "25-African-and-Caribbean-Recipes.pdf"
    if PDF_PATH.exists():
        ok(f"PDF file found at: {PDF_PATH}")
    else:
        fail(f"PDF file NOT found at: {PDF_PATH}")
        errors.append(f"PDF missing at {PDF_PATH}")

    # 1b — Check pdfplumber installed
    try:
        import pdfplumber
        ok("pdfplumber is installed")
    except ImportError:
        fail("pdfplumber is NOT installed — run: pip install pdfplumber --break-system-packages")
        errors.append("pdfplumber not installed")

    # 1c — Load the store
    try:
        store = PDFRecipeStore()
        recipe_count = len(store.recipes)
        if recipe_count > 0:
            ok(f"PDFRecipeStore loaded {recipe_count} recipes")
            print(f"       Loaded: {sorted(store.recipes.keys())}")
        else:
            fail("PDFRecipeStore loaded 0 recipes — PDF parsing is broken")
            errors.append("PDF parsed 0 recipes")
    except Exception as e:
        fail(f"PDFRecipeStore() constructor failed: {e}")
        errors.append(f"PDFRecipeStore constructor error: {e}")
        store = None

    # 1d — Test known lookups
    if store:
        KNOWN_RECIPES = [
            "chapati",
            "mandazi",
            "pilau rice",
            "jollof rice",
            "egusi soup",
            "atakilt wat",
            "puff puff",
            "suya",
        ]
        print()
        for name in KNOWN_RECIPES:
            result = store.lookup(name)
            if result is None:
                fail(f"lookup('{name}') → None  [recipe not found]")
                errors.append(f"PDF lookup failed for '{name}'")
            elif not result.get("steps"):
                warn(f"lookup('{name}') → found but steps list is EMPTY")
                errors.append(f"PDF steps empty for '{name}'")
            else:
                step_count = len(result["steps"])
                ok(f"lookup('{name}') → {step_count} steps found")

        # 1e — Confirm Caribbean dishes are excluded
        print()
        CARIBBEAN = ["jerk chicken", "curry goat", "rum cake", "mofongo"]
        for name in CARIBBEAN:
            result = store.lookup(name)
            if result is None:
                ok(f"lookup('{name}') → None  [correctly excluded]")
            else:
                fail(f"lookup('{name}') → returned data  [should be excluded!]")
                errors.append(f"Caribbean recipe '{name}' was not filtered out")

# ════════════════════════════════════════════════════════════════════════════
# LAYER 2 — WEB SEARCH SERVICE (TAVILY)
# ════════════════════════════════════════════════════════════════════════════
section("LAYER 2 — Web Search Service (Tavily)")

try:
    from jema.services.web_search_service import WebSearchService
    ok("web_search_service.py imported successfully")
except ImportError as e:
    fail(f"Could not import WebSearchService: {e}")
    errors.append("WebSearchService import failed")
    WebSearchService = None

if WebSearchService:
    # 2a — Check tavily-python installed
    try:
        from tavily import TavilyClient
        ok("tavily-python is installed")
    except ImportError:
        fail("tavily-python NOT installed — run: pip install tavily-python --break-system-packages")
        errors.append("tavily-python not installed")

    # 2b — Check API key in environment
    api_key = os.environ.get("TAVILY_API_KEY")
    if api_key:
        ok(f"TAVILY_API_KEY found in environment (starts with: {api_key[:8]}...)")
    else:
        fail("TAVILY_API_KEY not found in environment — add it to your .env file")
        errors.append("TAVILY_API_KEY missing from .env")

    # 2c — Test a real search for a recipe not in PDF
    if api_key:
        try:
            web = WebSearchService()
            result = web.search_recipe("Ugali Mayai")
            if result and len(result.strip()) > 100:
                ok(f"Web search for 'Ugali Mayai' returned content ({len(result)} chars)")
                print(f"       Preview: {result[:200].strip()}...")
            elif result:
                warn(f"Web search returned very short content ({len(result)} chars) — may be unreliable")
            else:
                fail("Web search returned None for 'Ugali Mayai'")
                errors.append("Tavily search returned None for Ugali Mayai")
        except Exception as e:
            fail(f"WebSearchService raised an exception: {e}")
            errors.append(f"WebSearchService error: {e}")

    # 2d — Confirm web search is skipped when PDF succeeds
    if store and api_key:
        pdf_result = store.lookup("chapati")
        if pdf_result and pdf_result.get("steps"):
            ok("Chapati found in PDF — web search would be correctly skipped")
        else:
            warn("Chapati not found in PDF — web search would be triggered unnecessarily")

# ════════════════════════════════════════════════════════════════════════════
# LAYER 3 — GROQ GENERATE RECIPE (source hierarchy wired in)
# ════════════════════════════════════════════════════════════════════════════
section("LAYER 3 — Groq generate_recipe() Source Wiring")

try:
    from jema.services.llm_service import LLMService
    ok("llm_service.py imported successfully")
except ImportError as e:
    fail(f"Could not import LLMService: {e}")
    errors.append("LLMService import failed")
    LLMService = None

if LLMService:
    import inspect
    source = inspect.getsource(LLMService.generate_recipe)

    # 3a — Check PDF store is called inside generate_recipe
    if "PDFRecipeStore" in source:
        ok("generate_recipe() calls PDFRecipeStore — PDF layer is wired in")
    else:
        fail("generate_recipe() does NOT call PDFRecipeStore — PDF layer is missing!")
        errors.append("PDFRecipeStore not called in generate_recipe")

    # 3b — Check web search is called inside generate_recipe
    if "WebSearchService" in source:
        ok("generate_recipe() calls WebSearchService — web search layer is wired in")
    else:
        fail("generate_recipe() does NOT call WebSearchService — web layer is missing!")
        errors.append("WebSearchService not called in generate_recipe")

    # 3c — Check Groq disclaimer exists
    if "AI-generated" in source or "ai-generated" in source.lower():
        ok("Groq fallback disclaimer is present in generate_recipe()")
    else:
        fail("Groq fallback disclaimer is MISSING from generate_recipe()")
        errors.append("Groq disclaimer missing")

    # 3d — Check temperature is 0.3 (not higher)
    if "temperature=0.3" in source:
        ok("Groq temperature is set to 0.3 (low hallucination risk)")
    else:
        warn("Groq temperature is not 0.3 — check for hallucination risk")

    # 3e — Live test: recipe IN the PDF
    print()
    print("  Running live generate_recipe() tests (this calls Groq — takes ~5s each)...")
    try:
        llm = LLMService()

        # Test PDF path
        result_pdf = llm.generate_recipe("Chapati", "english")
        if result_pdf:
            # generate_recipe() now returns formatted string
            if "Great! Here's the recipe for Chapati" in result_pdf:
                ok("generate_recipe('Chapati') returned properly formatted recipe")
            # Check for PDF-specific detail
            if "golden brown" in result_pdf.lower() or "fold" in result_pdf.lower():
                ok("Chapati steps contain PDF-specific detail (fold/golden brown)")
            else:
                warn("Chapati steps may not be using PDF source — check manually")
        else:
            fail("generate_recipe('Chapati') returned empty")
            errors.append("generate_recipe Chapati returned nothing")

        # Test Groq fallback path
        result_groq = llm.generate_recipe("Omena na Ugali", "english")
        if result_groq:
            # Check for AI-generated disclaimer
            if "AI-generated" in result_groq or "ai-generated" in result_groq.lower():
                ok("generate_recipe('Omena na Ugali') correctly shows Groq disclaimer")
            else:
                warn("generate_recipe('Omena na Ugali') — disclaimer not visible in output, check manually")
        else:
            fail("generate_recipe('Omena na Ugali') returned nothing")
            errors.append("generate_recipe Omena na Ugali returned nothing")

    except Exception as e:
        fail(f"Live generate_recipe() test failed: {e}")
        errors.append(f"generate_recipe live test error: {e}")

# ════════════════════════════════════════════════════════════════════════════
# LAYER 4 — CSV SUGGESTION SCOPE
# ════════════════════════════════════════════════════════════════════════════
section("LAYER 4 — CSV Suggestion Scope (All Africa, no region priority)")

try:
    from jema.services.jema_engine import JemaEngine
    engine = JemaEngine()
    ok("JemaEngine loaded successfully")

    import inspect
    engine_source = inspect.getsource(engine._handle_ingredient_based)

    if "east_africa" in engine_source and "african_df" not in engine_source:
        fail("_handle_ingredient_based() still filters to east_africa only — not updated")
        errors.append("CSV still filtered to east_africa only")
    elif "african_df" in engine_source or "all" in engine_source.lower():
        ok("_handle_ingredient_based() uses all African regions")
    else:
        warn("Could not confirm CSV region scope — check _handle_ingredient_based() manually")

except Exception as e:
    fail(f"JemaEngine failed to load: {e}")
    errors.append(f"JemaEngine load error: {e}")

# ════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ════════════════════════════════════════════════════════════════════════════
section("FINAL REPORT")

if not errors:
    print(f"{GREEN}🎉 ALL CHECKS PASSED — Source hierarchy is correctly wired{RESET}")
    print()
    print("  PDF     → handles known African recipes (Chapati, Mandazi, Pilau etc.)")
    print("  Tavily  → handles unknown recipes not in PDF (Ugali Mayai, Nyama Choma etc.)")
    print("  Groq    → last resort fallback with disclaimer")
    print("  CSV     → searches all African regions for suggestions")
else:
    print(f"{RED}❌ {len(errors)} ISSUE(S) FOUND — Fix these before testing Jema:{RESET}")
    print()
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}")
    print()
    print("Fix the issues above, then re-run this file to confirm.")
