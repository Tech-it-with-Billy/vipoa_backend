"""FastAPI app for Jema AI (modern refactor)."""

import json
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from services.jema_engine import JemaEngine

logger = logging.getLogger("jema")

app = FastAPI(
    title="Jema AI Cooking Assistant",
    version="1.0.0",
    description="Modernized Jema AI API backend with recipe and chat endpoints.",
)

_engine: Optional[JemaEngine] = None
_session_engines: Dict[int, JemaEngine] = {}
_sessions: Dict[int, Dict] = {}
_next_session_id = 1


def get_engine() -> JemaEngine:
    global _engine
    if _engine is None:
        _engine = JemaEngine()
    return _engine


def get_session_engine(session_id: int) -> JemaEngine:
    if session_id not in _session_engines:
        _session_engines[session_id] = JemaEngine()
    return _session_engines[session_id]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[int] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    recipes: List[Dict]
    language: str
    cta: str
    state: Dict


class RecipeSearchRequest(BaseModel):
    search: str = Field(..., min_length=1)


class SuggestRequest(BaseModel):
    ingredients: List[str] = Field(..., min_items=1)
    constraints: Optional[List[str]] = []


class SuggestResponse(BaseModel):
    suggestions: List[Dict]
    count: int


class SessionCreateRequest(BaseModel):
    user_id: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: int
    user_id: Optional[str]
    created_at: str


@app.get("/", tags=["System"])
def root():
    return {
        "service": "Jema AI Cooking Assistant",
        "version": "1.0.0",
        "status": "ready",
        "endpoints": {
            "health": "GET /health",
            "chat": "POST /chat",
            "recipes": "GET /recipes",
            "recipes_search": "POST /recipes/search",
            "suggest": "POST /suggest",
            "sessions": "POST /sessions",
        },
    }


@app.get("/health", tags=["System"])
def health_check():
    try:
        engine = get_engine()
        recipe_count = len(engine.recipes_df) if engine.recipes_df is not None else 0
        return {"status": "healthy", "recipes_loaded": recipe_count}
    except Exception as e:
        logger.exception("Health check failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    try:
        if request.session_id is not None:
            engine = get_session_engine(int(request.session_id))
        else:
            engine = get_engine()

        resp = engine.process_message(request.message)

        if request.session_id is not None:
            session = _sessions.get(request.session_id)
            if session is not None:
                session.setdefault("history", []).append({"user": request.message, "assistant": resp.get("message")})

        return ChatResponse(**resp)
    except Exception as e:
        logger.exception("chat processing failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recipes", tags=["Recipes"])
def list_recipes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None),
):
    engine = get_engine()
    df = engine.recipes_df.copy()
    if search:
        low = search.lower()
        if "meal_name" in df.columns:
            df = df[df["meal_name"].astype(str).str.lower().str.contains(low, na=False)]
        if "country" in df.columns:
            df = df[df["country"].astype(str).str.lower().str.contains(low, na=False)]

    total = len(df)
    start = (page - 1) * limit
    end = start + limit
    slice_df = df.iloc[start:end]
    records = json.loads(slice_df.to_json(orient="records"))

    return {
        "recipes": records,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit,
    }


@app.post("/recipes/search", tags=["Recipes"])
def search_recipes(req: RecipeSearchRequest):
    engine = get_engine()
    df = engine.recipes_df.copy()
    low = req.search.lower()
    matches = df[
        df["meal_name"].astype(str).str.lower().str.contains(low, na=False)
        | df["country"].astype(str).str.lower().str.contains(low, na=False)
    ]
    return {"results": json.loads(matches.to_json(orient="records")), "count": len(matches)}


@app.post("/suggest", response_model=SuggestResponse, tags=["Recipes"])
def suggest(req: SuggestRequest):
    if not req.ingredients:
        raise HTTPException(status_code=400, detail="ingredients field is required")

    engine = get_engine()
    normalized = engine.matcher
    ingredient_list = [str(i).strip() for i in req.ingredients if str(i).strip()]
    matches = engine.matcher.match(
        user_ingredients=ingredient_list,
        user_constraints={"quick": any(c.lower() == "quick" for c in req.constraints or [])},
        min_match_percentage=0.3,
    )

    suggestions = []
    for match in matches[:10]:
        row = engine.recipes_df[engine.recipes_df["meal_name"] == match.name]
        if not row.empty:
            recipe_data = row.iloc[0].to_dict()
            suggestions.append({
                "meal_name": match.name,
                "country": recipe_data.get("country", ""),
                "cook_time": recipe_data.get("cook_time", ""),
                "match_percentage": round(match.match_percentage, 2),
                "missing_ingredients": match.missing_ingredients[:3],
            })

    return SuggestResponse(suggestions=suggestions, count=len(suggestions))


@app.post("/sessions", tags=["Sessions"])
def create_session(req: SessionCreateRequest):
    global _next_session_id
    session_id = _next_session_id
    _next_session_id += 1
    _sessions[session_id] = {
        "session_id": session_id,
        "user_id": req.user_id,
        "created_at": "now",
        "history": [],
    }
    return {"session_id": session_id, "user_id": req.user_id, "created_at": "now"}


@app.get("/sessions/{session_id}", tags=["Sessions"])
def read_session(session_id: int):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@app.get("/info", tags=["System"])
def info():
    return {"service": "jema", "status": "ready"}
