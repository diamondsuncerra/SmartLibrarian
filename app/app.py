# --- path shim (works for `python -m app.app` and `streamlit run app/app.py`) ---
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]   # project root
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

# Chroma (persistent, telemetry off)
from chromadb import PersistentClient
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# local tool
from app.tools import get_summary_by_title

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

# ---------- Tiny safety filter ----------
BAD_WORDS = {"idiot", "stupid", "hate"}
def is_clean(text: str) -> bool:
    t = text.lower()
    return not any(b in t for b in BAD_WORDS)

# ---------- Dataset helpers ----------
def load_books() -> List[Dict]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")
    books = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(books, list):
        raise ValueError("book_summaries.json must be a JSON array")
    return books

def validate_dataset(strict: bool = True) -> List[str]:
    books = load_books()
    warnings = []
    if len(books) < 10:
        msg = f"Dataset has {len(books)} entries; assignment requires at least 10."
        if strict:
            raise ValueError(msg)
        warnings.append(msg)

    for i, b in enumerate(books):
        missing = [k for k in ("title", "short", "full") if not b.get(k)]
        if missing:
            w = f"Book #{i} missing {missing}: {b.get('title', '(no title)')}"
            if strict:
                raise ValueError(w)
            warnings.append(w)
    return warnings

# ---------- Vector DB (Chroma) ----------
def init_chroma() -> PersistentClient:
    CHROMA_DIR.mkdir(exist_ok=True)
    return PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False)
    )

def _build_docs(books: List[Dict]) -> Tuple[List[str], List[str], List[Dict]]:
    ids = [f"book-{i}" for i, _ in enumerate(books)]
    docs = [
        f"Title: {b['title']}\nShort: {b['short']}\nTags: {', '.join(b.get('tags', []))}"
        for b in books
    ]
    metas = [{"title": b["title"]} for b in books]
    return ids, docs, metas

def get_or_bootstrap_collection(client: PersistentClient, name: str = "books"):
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY in your .env")

    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBED_MODEL,
    )
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
        # reindex to keep the vector DB consistent with your dataset
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
    """Return [(title, distance), ...]. Lower distance = closer match."""
    res = col.query(query_texts=[query], n_results=k)
    if not res or not res.get("metadatas") or not res["metadatas"][0]:
        return []
    titles = [m["title"] for m in res["metadatas"][0]]
    distances = res.get("distances", [[0.0] * len(titles)])[0]
    return list(zip(titles, distances))

# ---------- OpenAI chat + function calling ----------
oai = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_summary_by_title",
            "description": "Return the full summary of an exact book title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Exact book title"}
                },
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    }
]

SYSTEM_PROMPT = (
    "You are Smart Librarian. You will be given a user query and a small list of candidate titles "
    "with similarity scores from a vector search.\n"
    "1) Pick EXACTLY ONE title that best matches the user's themes.\n"
    "2) Call the tool `get_summary_by_title` with that exact title.\n"
    "3) Compose a helpful final answer that includes: a one-sentence recommendation, why it matches, "
    "and the full summary returned by the tool.\n"
    "Be concise but friendly. If candidates are empty, ask the user to rephrase."
)

def recommend_with_toolcall(user_query: str, candidates: List[Tuple[str, float]]) -> str:
    cand = [{"title": t, "distance": float(d)} for (t, d) in candidates]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"user_query": user_query, "candidates": cand})},
    ]

    # small guard to avoid infinite loops
    for _ in range(6):
        resp = oai.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.4,
        )
        msg = resp.choices[0].message

        # --- IMPORTANT: append the assistant message that contains tool_calls ---
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],  # keep the tool_calls in history
                }
            )
            # Then execute each tool and append tool results
            for tc in msg.tool_calls:
                if tc.function.name == "get_summary_by_title":
                    args = json.loads(tc.function.arguments or "{}")
                    title = (args.get("title") or "").strip()
                    full_summary = get_summary_by_title(title)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": "get_summary_by_title",
                            "content": full_summary,
                        }
                    )
            # loop again so the model can produce a final answer using the tool output(s)
            continue

        # No tool calls => final answer
        return msg.content or "Sorry, I couldn't generate a response."

    return "Sorry, I couldn't complete the tool interaction."

# ---------- CLI runner ----------
def run_cli():
    # validate dataset before building index
    warns = validate_dataset(strict=True)
    for w in warns:
        log.warning(w)

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

        if not is_clean(q):
            print("Bot: Let’s keep it respectful. Please rephrase 🙏")
            continue

        hits = rag_search(col, q, k=3)
        if not hits:
            print("Bot: I couldn't find matches. Can you add more detail?")
            continue

        answer = recommend_with_toolcall(q, hits)
        print(f"\n{answer}\n")

# ---------- Streamlit UI ----------
def run_ui():
    import streamlit as st

    # warn, but don't crash the UI
    try:
        warns = validate_dataset(strict=False)
    except Exception as e:
        st.error(str(e))
        st.stop()

    for w in warns:
        st.warning(w)

    st.set_page_config(page_title="Smart Librarian", page_icon="📚")
    st.title("📚 Smart Librarian")
    st.caption("RAG with ChromaDB + Tool Calling")

    if "col" not in st.session_state:
        db = init_chroma()
        st.session_state.col = get_or_bootstrap_collection(db)

    q = st.text_input("Describe what you’re in the mood for (themes, vibes, genre):", "")
    if st.button("Recommend"):
        if not q.strip():
            st.warning("Please type something first.")
            st.stop()
        if not is_clean(q):
            st.warning("Please keep it respectful.")
            st.stop()

        with st.spinner("Finding the best match..."):
            hits = rag_search(st.session_state.col, q, k=3)
            if not hits:
                st.info("No good matches. Try adding more detail.")
                st.stop()

            try:
                answer = recommend_with_toolcall(q, hits)
                st.markdown("---")
                st.markdown(answer)
            except Exception as e:
                st.error(f"Something went wrong: {e}")

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
