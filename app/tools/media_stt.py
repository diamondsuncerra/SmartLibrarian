# app/tools/media_stt.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STT_DIR = ROOT / ".chroma" / "stt"

def transcribe_audio(audio_path: Path, *, model: str = "whisper-1", client: Optional[OpenAI] = None) -> str:
    """
    Transcribe an audio file using OpenAI STT.
    Supports mp3, m4a, wav, webm, etc.
    Returns the transcript text ('' if none).
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    client = client or OpenAI()
    with open(audio_path, "rb") as f:
        tr = client.audio.transcriptions.create(
            model=model,
            file=f,
            temperature=0.2,
            # language="ro",  # optionally hint "en"/"ro" if you want
        )
    return getattr(tr, "text", "") or ""
