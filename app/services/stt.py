# app/services/stt.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from openai import OpenAI

def transcribe_audio(
    audio_path: Path,
    *,
    model: str = "whisper-1",
    language: Optional[str] = None,
    client: Optional[OpenAI] = None,
) -> str:
    """
    Transcribe an audio file with OpenAI STT (Whisper).
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    client = client or OpenAI()
    with open(audio_path, "rb") as f:
        tr = client.audio.transcriptions.create(
            model=model,
            file=f,
            temperature=0.2,
            **({"language": language} if language else {}),
        )
    return getattr(tr, "text", "") or ""
