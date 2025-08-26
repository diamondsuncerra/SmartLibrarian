# 📚 Smart Librarian

A sleek **FastAPI + React (Vite)** app that recommends books by text **or** voice.  
Speak your vibe → 🎙️ **STT** → 🤖 **RAG + LLM** → 📖 curated picks → (in background) 🔊 **TTS** + 🖼️ **cover image**.  
The UI shows “Generating…” placeholders and swaps in media automatically when ready.

---

## ✨ Features

- 🔎 **RAG** book recommendations (`/api/recommend`)
- 🎙️ **Voice search** (browser mic → `/api/stt/transcribe`)
- 🔊 **TTS narration** (background, deterministic filenames)
- 🖼️ **AI cover image** (background, deterministic filenames)
- ⚡ **Fast**: single OpenAI client, Chroma init once, STT disk cache
- 💸 **Cost controls**: disable TTS / Cover via env flags
- 🧱 **Clean DX**: Vite proxy, Swagger docs, simple project layout

---

## 🧰 Tech Stack

**Backend:** FastAPI, ChromaDB, OpenAI SDK  
**Frontend:** React (Vite)  
**Media:** Whisper (STT), TTS, Image Gen

---

## ✅ Requirements

- Python **3.11+**
- Node **18+**
- An **OpenAI API key**

---

## 🚀 Quick Start

### 1) Backend
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```
Create .env at the repo root (copy from .env.example if present):

OPENAI_API_KEY=sk-...
CHAT_MODEL=gpt-4o-mini
# Optional cost flags (1=on, 0=off)
ENABLE_TTS=1
ENABLE_COVER=1


Run the API (pick a free port, e.g. 8020):
```bash
uvicorn app.api:app --app-dir . --port 8020
```

📖 Docs: http://localhost:8020/docs

### 2) Frontend
```bash
cd frontend
npm install
```

Make sure frontend/vite.config.js proxies to your API port:
```bash
server: {
  port: 5173,
  proxy: {
    '/api': 'http://localhost:8020',
    '/static': 'http://localhost:8020'
  }
}
```

Run:
```bash
npm run dev
```

## 🖥️ App: http://localhost:5173

⚙️ Configuration

Environment variables (backend):

Key	Default	Notes
OPENAI_API_KEY	—	Required
CHAT_MODEL	gpt-4o-mini	LLM for recommendations
ENABLE_TTS	1	1/0 toggle audio generation
ENABLE_COVER	1	1/0 toggle cover generation

🗂️ Generated DB & media live under .chroma/ (gitignored).

📡 API (dev)
POST /api/recommend

Request

{ "query": "dark academia with friendship themes" }


Response

{
  "answer": "...",
  "title": "…",
  "audio_url": "/static/stt/<hash>.mp3",
  "image_url": "/static/img/<hash>.png",
  "candidates": [["Title A", 0.12], ["Title B", 0.18]]
}

POST /api/stt/transcribe

Multipart with file (webm/ogg/mp3/wav/m4a).
Response

{ "text": "…", "url": "/static/stt/<uploaded>" }

## 🧠 How Media Delivery Works (1-minute mental model)

The backend returns deterministic URLs for audio & image immediately.

Generation runs in a background task and saves to those exact paths.

The frontend shows “Generating…” and HEAD-polls those URLs until they return 200, then swaps in the real media.

Repeated requests for the same content reuse existing files (no extra API cost).

STT results are cached by file hash on disk.

## 🗃️ Project Structure
app/
  api.py          # FastAPI app (routes, static mounts, background tasks)
  main.py         # Chroma init & helpers (no FastAPI here)
  tools/          # STT, TTS, image, dataset, filters, recommend
frontend/
  src/            # App.jsx, MicSearch, styles
  vite.config.js  # dev proxy → backend
.chroma/          # DB + generated media (gitignored)

## 🛠️ Troubleshooting

404 on /api/* → Vite proxy points to the wrong API port. Update vite.config.js and restart both servers.

Port already in use → Stop the previous process or pick a new port (e.g. 8020) and update the proxy.

Media never appears → Check files land in:

Audio → .chroma/stt/<hash>.mp3 (served at /static/stt/...)

Image → .chroma/img/<hash>.png (served at /static/img/...)
Filenames must match the URLs returned by /api/recommend.

