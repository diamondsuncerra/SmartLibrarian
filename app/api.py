# app/api.py
from __future__ import annotations

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Tuple, Dict
from pathlib import Path
import os, uuid, shutil, hashlib, json

from openai import OpenAI

from app.tools.dataset import get_book_meta_by_title
from app.tools.filters import contains_profanity
from app.tools.recommend import recommend_with_toolcall
from app.tools.media_tts import synthesize_tts
from app.tools.media_images import generate_cover_image
from app.tools.media_stt import transcribe_audio, DEFAULT_STT_DIR
from app.main import init_chroma, get_or_bootstrap_collection, rag_search

# -------- STT transcript cache on disk --------
STT_CACHE_PATH = DEFAULT_STT_DIR / "transcripts.json"
try:
    _cache_data = json.loads(STT_CACHE_PATH.read_text(encoding="utf-8"))
except Exception:
    _cache_data = {}
STT_CACHE: Dict[str, str] = dict(_cache_data)

def _sha1_file(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _stt_cache_get(p: Path) -> str | None:
    return STT_CACHE.get(_sha1_file(p))

def _stt_cache_put(p: Path, text: str) -> None:
    STT_CACHE[_sha1_file(p)] = text
    try:
        STT_CACHE_PATH.write_text(json.dumps(STT_CACHE, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def _hash_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

# -------- one FastAPI app --------
app = FastAPI(title="SmartLibrarian API")

# CORS for Vite dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts (once)
DEFAULT_STT_DIR.mkdir(parents=True, exist_ok=True)        # .chroma/stt for TTS + uploads
STATIC_IMG = Path(".chroma/img"); STATIC_IMG.mkdir(parents=True, exist_ok=True)

app.mount("/static/stt", StaticFiles(directory=DEFAULT_STT_DIR), name="stt")
app.mount("/static/img", StaticFiles(directory=STATIC_IMG), name="img")

# Init heavy stuff once
@app.on_event("startup")
def _startup():
    app.state.db = init_chroma()
    app.state.col = get_or_bootstrap_collection(app.state.db)
    app.state.oai = OpenAI()  # reuse this client everywhere

# -------- Schemas --------
class RecommendRequest(BaseModel):
    query: str

class RecommendResponse(BaseModel):
    answer: str
    title: str | None
    audio_url: str | None
    image_url: str | None
    candidates: list[Tuple[str, float]]

# -------- Recommend (returns immediately; TTS/cover in background) --------
@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest, request: Request, background: BackgroundTasks):
    q = req.query.strip()
    if not q:
        return RecommendResponse(answer="Empty query.", title=None, audio_url=None, image_url=None, candidates=[])
    if contains_profanity(q):
        return RecommendResponse(
            answer="🤖 Să păstrăm un ton respectuos, te rog reformulează 🙏",
            title=None, audio_url=None, image_url=None, candidates=[]
        )

    col = request.app.state.col
    hits = rag_search(col, q, k=3)
    if not hits:
        return RecommendResponse(
            answer="Nu am găsit potriviri. Adaugă câteva detalii.",
            title=None, audio_url=None, image_url=None, candidates=[]
        )

    answer, picked_title, _ = recommend_with_toolcall(q, hits, model=os.getenv("CHAT_MODEL", "gpt-4o-mini"))

    # Pre-compute deterministic output paths so we can return URLs immediately
    audio_name = f"{_hash_text(answer)}.mp3"
    audio_url  = f"/static/stt/{audio_name}"
    img_name   = None
    image_url  = None
    if picked_title:
        img_name = f"{_hash_text('cover:'+picked_title)}.png"
        image_url = f"/static/img/{img_name}"

    # Defer heavy work so response is instant
    def _bg_generate():
        try:
            # TTS (skip if already exists)
            apath = DEFAULT_STT_DIR / audio_name
            if not apath.exists():
                out = synthesize_tts(answer, voice="alloy")
                if out and out.exists() and out.name != audio_name:
                    out.rename(apath)
        except Exception:
            pass
        try:
            if picked_title and img_name:
                ipath = STATIC_IMG / img_name
                if not ipath.exists():
                    short, tags = get_book_meta_by_title(picked_title)
                    out = generate_cover_image(picked_title, short=short, tags=tags, size="1024x1024")
                    if out and out.exists() and out.name != img_name:
                        out.rename(ipath)
        except Exception:
            pass

    background.add_task(_bg_generate)

    return RecommendResponse(
        answer=answer,
        title=picked_title or None,
        audio_url=audio_url,
        image_url=image_url,
        candidates=hits,
    )

# -------- STT upload + transcribe (with cache + shared client) --------
@app.post("/api/stt/transcribe")
async def stt_transcribe(file: UploadFile = File(...)):
    ext = (Path(file.filename).suffix or "").lower()
    if ext not in {".mp3", ".wav", ".m4a", ".webm", ".ogg"}:
        raise HTTPException(400, "Unsupported audio type")

    fname = f"{uuid.uuid4().hex}{ext}"
    dest = DEFAULT_STT_DIR / fname
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # cache hit? return instantly
    cached = _stt_cache_get(dest)
    if cached is not None:
        return {"text": cached, "url": f"/static/stt/{fname}", "cached": True}

    try:
        text = transcribe_audio(dest, client=app.state.oai)  # reuse client
    except Exception as e:
        raise HTTPException(500, f"STT failed: {e!s}")

    _stt_cache_put(dest, text or "")
    return {"text": text or "", "url": f"/static/stt/{fname}", "cached": False}
