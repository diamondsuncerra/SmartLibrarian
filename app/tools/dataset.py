from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "book_summaries.json"

def load_books() -> List[Dict]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")
    books = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(books, list):
        raise ValueError("book_summaries.json must be a JSON array")
    return books

def validate_dataset(strict: bool = True) -> List[str]:
    books = load_books()
    warnings: List[str] = []
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

def get_book_meta_by_title(title: str) -> tuple[str, list[str]]:
    """Return (short, tags) for a title or ('', [])."""
    try:
        books = load_books()
    except Exception:
        return "", []
    for b in books:
        if b.get("title", "").strip().lower() == (title or "").strip().lower():
            return b.get("short", ""), b.get("tags", []) or []
    return "", []
