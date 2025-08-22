# app/tools/images.py
from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from typing import Optional
import base64

from openai import OpenAI

DEFAULT_IMG_DIR = Path(__file__).resolve().parents[2] / ".chroma" / "img"

def _build_prompt(title: str, *, short: str = "", tags: list[str] | None = None, style: str = "") -> str:
    """
    Creează un prompt bun pentru o copertă/ilustrație: titlu + 3–5 concepte cheie + stil.
    """
    tags = tags or []
    tag_line = ", ".join(tags[:5])
    style_line = style or "rich, detailed, book cover, cinematic lighting, cohesive typography, high-contrast focal point"
    # evitează text mare de copertă; nu cerem să scrie exact titlul pe imagine
    return (
        f"Create a representative cover-style illustration inspired by the book.\n"
        f"Title (for inspiration): {title}\n"
        f"Key ideas: {tag_line}\n"
        f"One-line theme: {short}\n"
        f"Style: {style_line}\n"
        f"Rules: No large text blocks; no logos. Clean composition with one strong focal element."
    )

def generate_cover_image(
    title: str,
    *,
    short: str = "",
    tags: list[str] | None = None,
    size: str = "1024x1024",
    style: str = "",
    out_dir: Optional[Path] = None,
    client: Optional[OpenAI] = None,
) -> Path:
    """
    Generează o imagine (PNG) cu OpenAI Images și o salvează pe disc. Returnează calea.
    """
    if not title or not title.strip():
        raise ValueError("generate_cover_image: missing title")

    out_dir = out_dir or DEFAULT_IMG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid4()}.png"

    client = client or OpenAI()
    prompt = _build_prompt(title, short=short, tags=tags, style=style)

    # Images API (SDK v1+): rezultatul vine ca b64
    resp = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality="high",
        n=1,
    )
    b64 = resp.data[0].b64_json
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))

    return out_path
