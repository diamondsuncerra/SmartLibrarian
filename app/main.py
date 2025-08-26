# --- path shim (works for `python -m app.app` and `streamlit run app/app.py`) ---
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -------------------------------------------------------------------------------

# hard-silence Chroma telemetry + keep logs tidy
import os, logging
os.environ["ANONYMIZED_TELEMETRY"] = "False"
logging.getLogger("chromadb").setLevel(logging.CRITICAL)

import argparse
import json
from typing import Dict, List, Tuple
from dotenv import load_dotenv
from openai import OpenAI

# Chroma (persistent)
from chromadb import PersistentClient
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# —— our tools (helpers) ——
from app.tools.dataset import load_books, validate_dataset, get_book_meta_by_title
from app.tools.summary import get_summary_by_title
from app.tools.recommend import recommend_with_toolcall
from app.tools.filters import contains_profanity
from app.tools.media_tts import synthesize_tts
from app.tools.media_images import generate_cover_image
from app.tools.media_stt import transcribe_audio

# ---------- Constants / paths ----------
DATA_PATH = ROOT / "data" / "book_summaries.json"
CHROMA_DIR = ROOT / ".chroma"

# Models via .env (with safe defaults)
load_dotenv()
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("smart-librarian")

# ---------- Vector DB (Chroma) ----------
def init_chroma() -> PersistentClient:
    CHROMA_DIR.mkdir(exist_ok=True)
    return PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))

def _build_docs(books: List[Dict]) -> Tuple[List[str], List[str], List[Dict]]:
    ids = [f"book-{i}" for i, _ in enumerate(books)]
    docs = [f"Title: {b['title']}\nShort: {b['short']}\nTags: {', '.join(b.get('tags', []))}" for b in books]
    metas = [{"title": b["title"]} for b in books]
    return ids, docs, metas

def get_or_bootstrap_collection(client: PersistentClient, name: str = "books"):
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY in your .env")

    ef = embedding_functions.OpenAIEmbeddingFunction(api_key=OPENAI_API_KEY, model_name=EMBED_MODEL)
    col = client.get_or_create_collection(name=name, embedding_function=ef)

    books = load_books()
    expected = len(books)
    current = col.count()

    if current == 0:
        log.info("Bootstrapping Chroma collection from dataset...")
        ids, docs, metas = _build_docs(books)
        col.add(ids=ids, documents=docs, metadatas=metas)
        log.info("Bootstrap completed.")
    elif current != expected:
        log.info("Rebuilding collection (dataset changed: %d -> %d)...", current, expected)
        client.delete_collection(name)
        col = client.get_or_create_collection(name=name, embedding_function=ef)
        ids, docs, metas = _build_docs(books)
        col.add(ids=ids, documents=docs, metadatas=metas)
        log.info("Rebuild completed.")
    else:
        log.info("Chroma collection found with %d items.", current)
    return col

def rag_search(col, query: str, k: int = 3) -> List[Tuple[str, float]]:
    res = col.query(query_texts=[query], n_results=k)
    if not res or not res.get("metadatas") or not res["metadatas"][0]:
        return []
    titles = [m["title"] for m in res["metadatas"][0]]
    distances = res.get("distances", [[0.0] * len(titles)])[0]
    return list(zip(titles, distances))

# ---------- CLI ----------
def run_cli():
    validate_dataset(strict=True)  # will raise on issues

    db = init_chroma()
    col = get_or_bootstrap_collection(db)

    print("Smart Librarian ready. Ask for themes (e.g., 'friendship and magic'). Type 'quit' to exit.")
    while True:
        try:
            q = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if q.lower() in {"quit", "exit"}:
            print("Bye!")
            break

        # ✅ profanity gate — do NOT send to LLM if offensive
        if contains_profanity(q):
            print("Bot: Let’s keep it respectful 🙏 Please rephrase your request.")
            continue

        hits = rag_search(col, q, k=3)
        if not hits:
            print("Bot: I couldn't find matches. Can you add a bit more detail?")
            continue

        # model picks a title + calls tool internally
        answer, picked_title, picked_full = recommend_with_toolcall(q, hits, model=CHAT_MODEL)

        print("\n" + answer + "\n")

        # TTS + auto image (optional in CLI)
        try:
            audio_path = synthesize_tts(answer, voice="alloy")
            print(f"[TTS] Saved to: {audio_path}")
            try:
                os.startfile(audio_path)  # Windows best-effort
            except Exception:
                pass
        except Exception as e:
            print(f"[TTS] Failed: {e}")

        if picked_title:
            try:
                short, tags = get_book_meta_by_title(picked_title)
                img_path = generate_cover_image(picked_title, short=short, tags=tags, size="1024x1024")
                print(f"[IMG] Saved cover to: {img_path}")
            except Exception as e:
                print(f"[IMG] Failed: {e}")

# ---------- Streamlit UI ----------
def run_ui():
    import streamlit as st

    # validate (warn, don't crash)
    try:
        validate_dataset(strict=True)
    except Exception as e:
        st.error(str(e))
        st.stop()

    st.set_page_config(page_title="Smart Librarian", page_icon="📚")
    st.title("📚 Smart Librarian")
    st.caption("RAG + Tool Calling + TTS + Auto Cover")

    # keep the query text in session state (so STT can fill it)
    if "q_text" not in st.session_state:
        st.session_state.q_text = ""

    # voice selector (for TTS)
    st.sidebar.header("🔊 TTS")
    st.session_state.voice = st.sidebar.selectbox("Voice", ["alloy", "aria", "verse"], index=0)

    # 🎤 STT sidebar
    st.sidebar.header("🎤 Speech-to-Text")
    audio_file = st.sidebar.file_uploader(
        "Upload audio (mp3, m4a, wav, webm)", type=["mp3", "m4a", "wav", "webm"]
    )
    stt_go = st.sidebar.button("📝 Transcribe to query")

    if stt_go:
        if not audio_file:
            st.sidebar.warning("Please upload an audio file first.")
        else:
            stt_dir = (ROOT / ".chroma" / "stt")
            stt_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(audio_file.name).suffix or ".mp3"
            tmp_path = stt_dir / f"upload{suffix}"
            with open(tmp_path, "wb") as f:
                f.write(audio_file.read())
            try:
                with st.spinner("Transcribing audio…"):
                    text = transcribe_audio(tmp_path)
                if text:
                    st.session_state.q_text = text   # 👈 fill the input box
                    st.sidebar.success("Transcribed! Inserted into the query field.")
                else:
                    st.sidebar.warning("No text could be extracted from audio.")
            except Exception as e:
                st.sidebar.error(f"STT failed: {e}")


    if "col" not in st.session_state:
        db = init_chroma()
        st.session_state.col = get_or_bootstrap_collection(db)
    if "history" not in st.session_state:
        st.session_state.history = []

    q = st.text_input(
        "Describe what you’re in the mood for (themes, vibes, genre):",
        value=st.session_state.q_text,
        key="q_text"
    )

    if st.button("Recommend"):
        if not q.strip():
            st.warning("Please type something first.")
            st.stop()

        # ✅ profanity gate — do NOT send to LLM if offensive
        if contains_profanity(q):
            st.warning("🤖 Let’s keep it respectful 🙏 Please rephrase your request.")
            st.stop()

        with st.spinner("Finding the best match..."):
            hits = rag_search(st.session_state.col, q, k=3)
            if not hits:
                st.info("No good matches. Try adding more detail.")
                st.stop()

            # 1) recommendation (answer, title, full summary)
            answer, picked_title, picked_full = recommend_with_toolcall(q, hits, model=CHAT_MODEL)

            # 2) auto-generate cover
            img_path = None
            if picked_title:
                short, tags = get_book_meta_by_title(picked_title)
                with st.spinner("Generating cover..."):
                    try:
                        img_path = generate_cover_image(
                            picked_title, short=short, tags=tags, size="1024x1024",
                            style="rich, detailed, book cover, cinematic lighting"
                        )
                    except Exception as e:
                        st.warning(f"Image generation failed: {e}")

            # 3) layout: text + image side-by-side + TTS
            st.markdown("---")
            col_text, col_img = st.columns([1.25, 1])
            with col_text:
                st.markdown(answer)
                try:
                    audio_path = synthesize_tts(answer, voice=st.session_state.voice)
                    st.audio(str(audio_path), format="audio/mp3")
                except Exception as e:
                    st.warning(f"TTS failed: {e}")
            with col_img:
                if img_path:
                    st.image(str(img_path), caption=f"Cover: {picked_title}")

            # 4) history
            st.session_state.history.insert(0, {
                "q": q,
                "hits": hits,
                "answer": answer,
                "title": picked_title,
                "image": str(img_path) if img_path else None,
                "audio": str(audio_path) if 'audio_path' in locals() else None
            })

# ---------- Entrypoint ----------
def main():
    parser = argparse.ArgumentParser(description="Smart Librarian — RAG + Chroma + Tool Calling")
    parser.add_argument("--ui", action="store_true", help="Start the Streamlit UI")
    args = parser.parse_args()
    if args.ui:
        run_ui()
    else:
        run_cli()

if __name__ == "__main__":
    main()
