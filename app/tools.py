from pathlib import Path
import json
import unicodedata

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "book_summaries.json"

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "")).casefold().strip()

def get_summary_by_title(title: str) -> str:
    """Return the 'full' summary for an exact (normalized) title; fallback to other fields."""
    books = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    t = _norm(title)

    # exact match first
    for b in books:
        if _norm(b.get("title")) == t:
            full = b.get("full") or b.get("summary") or b.get("description") or b.get("short")
            return full or "I couldn't find a full summary for this title in the dataset."

    # partial match fallback
    for b in books:
        if t in _norm(b.get("title")):
            full = b.get("full") or b.get("summary") or b.get("description") or b.get("short")
            return full or "I couldn't find a full summary for this title in the dataset."

    return "Sorry, I couldn't find that title in the dataset. Please check your JSON."
