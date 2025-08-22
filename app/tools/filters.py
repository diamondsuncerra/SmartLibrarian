from __future__ import annotations
from better_profanity import profanity
from pathlib import Path

# load default English list
profanity.load_censor_words()

# extend with optional local lists (one word per line)
ROOT = Path(__file__).resolve().parents[2]
for fname in ["profanity_en.txt", "profanity_ro.txt"]:
    path = ROOT / "data" / fname
    if path.exists():
        extra = [w.strip() for w in path.read_text(encoding="utf-8").splitlines() if w.strip()]
        if extra:
            profanity.add_censor_words(extra)

def contains_profanity(text: str) -> bool:
    return profanity.contains_profanity(text or "")

def clean_profanity(text: str) -> str:
    return profanity.censor(text or "")
