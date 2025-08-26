"use client"

import { useEffect, useRef, useState } from "react"
import "./MicSearch.css"

export default function MicSearch({ onResult }) {
  const [supported, setSupported] = useState(true)
  const [recState, setRecState] = useState("idle") // idle | recording | processing
  const [error, setError] = useState("")
  const [audioURL, setAudioURL] = useState("")
  const mediaRef = useRef(null) // MediaStream
  const recorderRef = useRef(null) // MediaRecorder
  const chunksRef = useRef([])

  useEffect(() => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setSupported(false)
    }
    return () => {
      try {
        mediaRef.current && mediaRef.current.getTracks().forEach((t) => t.stop())
      } catch {}
    }
  }, [])

  async function start() {
    setError("")
    if (!supported) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRef.current = stream
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
          ? "audio/ogg;codecs=opus"
          : ""

      recorderRef.current = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunksRef.current = []
      recorderRef.current.ondataavailable = (e) => {
        if (e.data?.size) chunksRef.current.push(e.data)
      }
      recorderRef.current.onstop = handleStop
      recorderRef.current.start()
      setRecState("recording")
    } catch (e) {
      setError("Microphone permission denied or unavailable.")
    }
  }

  async function stop() {
    try {
      recorderRef.current?.stop()
      mediaRef.current?.getTracks().forEach((t) => t.stop())
      setRecState("processing")
    } catch (e) {
      setError("Failed to stop recording.")
      setRecState("idle")
    }
  }

  async function handleStop() {
    try {
      const blob = new Blob(chunksRef.current, { type: recorderRef.current?.mimeType || "audio/webm" })
      const localURL = URL.createObjectURL(blob)
      setAudioURL(localURL)

      // 1) send to STT
      const form = new FormData()
      const filename = blob.type.includes("ogg") ? "speech.ogg" : "speech.webm"
      form.append("file", blob, filename)

      const sttRes = await fetch("/api/stt/transcribe", { method: "POST", body: form })
      if (!sttRes.ok) throw new Error(`STT HTTP ${sttRes.status}`)
      const { text } = await sttRes.json()
      if (!text) throw new Error("Empty transcript.")

      // 2) call your recommend endpoint with the transcript
      const recRes = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text }),
      })
      if (!recRes.ok) throw new Error(`Search HTTP ${recRes.status}`)
      const data = await recRes.json()

      // bubble up to parent (show answer, title, etc.)
      onResult?.({ transcript: text, data })
      setRecState("idle")
    } catch (e) {
      setError(e.message || String(e))
      setRecState("idle")
    }
  }

  return (
    <div className="mic-search-container">
      <div className="mic-search-content">
        {/* Main Recording Button */}
        <button
          onClick={recState === "recording" ? stop : start}
          disabled={!supported || recState === "processing"}
          className={`mic-button ${
            recState === "recording"
              ? "mic-button-recording"
              : recState === "processing"
                ? "mic-button-processing"
                : "mic-button-idle"
          }`}
        >
          {recState === "recording" ? (
            <div className="button-content">
              <div className="recording-indicator"></div>
              <span>■ Stop Recording</span>
            </div>
          ) : recState === "processing" ? (
            <div className="button-content">
              <div className="processing-spinner"></div>
              <span>Processing...</span>
            </div>
          ) : (
            <div className="button-content">
              <span>🎙️</span>
              <span>Start Voice Search</span>
            </div>
          )}
        </button>

        {/* Status Text */}
        <div className="status-text">
          {recState === "recording" && (
            <p className="status-recording">🔴 Recording... speak clearly about the books you're looking for</p>
          )}
          {recState === "processing" && <p className="status-processing">⚡ Processing your request...</p>}
          {!supported && <p className="status-error">⚠️ Voice search is not supported in this browser</p>}
        </div>

        {/* Audio Playback */}
        {audioURL && (
          <div className="audio-container">
            <p className="audio-label">Your recording:</p>
            <audio controls src={audioURL} className="audio-player" />
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="error-container">
            <div className="error-content">
              <span>❌</span>
              <span className="error-text">{error}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
