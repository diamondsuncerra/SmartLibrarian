from __future__ import annotations
from pathlib import Path
import json
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "book_summaries.json"

def get_summary_by_title(title: str) -> str:
    books = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    t = (title or "").strip().lower()
    for b in books:
        if (b.get("title") or "").strip().lower() == t:
            return b.get("full") or b.get("summary") or b.get("description") or b.get("short") or ""
    return "Sorry, I couldn't find that title in the dataset. Please check your JSON."
