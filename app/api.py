from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Tuple
from pathlib import Path
import os

from app.tools.dataset import load_books, get_book_meta_by_title, validate_dataset
from app.tools.filters import contains_profanity
from app.tools.recommend import recommend_with_toolcall
from app.tools.media_tts import synthesize_tts
from app.tools.media_images import generate_cover_image
from app.app import init_chroma, get_or_bootstrap_collection, rag_search  # reuse existing

app = FastAPI(title="SmartLibrarian API")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# init on startup
db = init_chroma()
col = get_or_bootstrap_collection(db)

class RecommendRequest(BaseModel):
    query: str

class RecommendResponse(BaseModel):
    answer: str
    title: str | None
    audio_url: str | None
    image_url: str | None
    candidates: list[tuple[str, float]]

@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    q = req.query.strip()
    if not q:
        return RecommendResponse(answer="Empty query.", title=None, audio_url=None, image_url=None, candidates=[])

    if contains_profanity(q):
        return RecommendResponse(answer="🤖 Să păstrăm un ton respectuos, te rog reformulează 🙏", title=None, audio_url=None, image_url=None, candidates=[])

    hits = rag_search(col, q, k=3)
    if not hits:
        return RecommendResponse(answer="Nu am găsit potriviri. Adaugă câteva detalii.", title=None, audio_url=None, image_url=None, candidates=[])

    answer, picked_title, _ = recommend_with_toolcall(q, hits, model=os.getenv("CHAT_MODEL", "gpt-4o-mini"))

    # TTS
    audio_url = None
    try:
        audio_path = synthesize_tts(answer, voice="alloy")
        audio_url = f"/static/tts/{audio_path.name}"
    except Exception:
        pass

    # Cover
    image_url = None
    if picked_title:
        short, tags = get_book_meta_by_title(picked_title)
        try:
            img_path = generate_cover_image(picked_title, short=short, tags=tags, size="1024x1024")
            image_url = f"/static/img/{img_path.name}"
        except Exception:
            pass

    return RecommendResponse(answer=answer, title=picked_title or None, audio_url=audio_url, image_url=image_url, candidates=hits)

# Simple static serving (dev): map .chroma files
from fastapi.staticfiles import StaticFiles
STATIC_TTS = Path(".chroma/tts")
STATIC_IMG = Path(".chroma/img")
STATIC_TTS.mkdir(parents=True, exist_ok=True)
STATIC_IMG.mkdir(parents=True, exist_ok=True)
app.mount("/static/tts", StaticFiles(directory=STATIC_TTS), name="tts")
app.mount("/static/img", StaticFiles(directory=STATIC_IMG), name="img")
