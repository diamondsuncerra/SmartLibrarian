from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from typing import Literal, Optional
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TTS_DIR = ROOT / ".chroma" / "tts"

def synthesize_tts(
    text: str,
    *,
    voice: Literal["alloy", "aria", "verse"] = "alloy",
    out_dir: Optional[Path] = None,
    client: Optional[OpenAI] = None,
) -> Path:
    text = (text or "").strip()
    if not text:
        raise ValueError("synthesize_tts: empty text")

    out_dir = out_dir or DEFAULT_TTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid4()}.mp3"

    client = client or OpenAI()
    speech = client.audio.speech.create(model="gpt-4o-mini-tts", voice=voice, input=text)
    with open(out_path, "wb") as f:
        f.write(speech.content)
    return out_path
