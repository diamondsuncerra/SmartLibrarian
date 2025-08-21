# app/services/tts.py
from __future__ import annotations
from pathlib import Path
from uuid import uuid4
from typing import Literal, Optional

from openai import OpenAI

# Default cache dir: <project>/.chroma/tts
DEFAULT_TTS_DIR = Path(__file__).resolve().parents[2] / ".chroma" / "tts"

def synthesize_tts(
    text: str,
    *,
    voice: Literal["alloy", "aria", "verse"] = "alloy",
    out_dir: Optional[Path] = None,
    client: Optional[OpenAI] = None,
) -> Path:
    """
    Generate speech audio (MP3) from text using OpenAI TTS.
    Returns the output file path.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("synthesize_tts: empty text")

    out_dir = out_dir or DEFAULT_TTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{uuid4()}.mp3"   # SDK returns MP3 bytes by default

    client = client or OpenAI()
    speech = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voice,          # use the parameter you pass in
        input=text            # synthesize your actual text
    )

    with open(out_path, "wb") as f:
        f.write(speech.content)

    return out_path
