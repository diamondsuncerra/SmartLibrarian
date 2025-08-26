"use client"

import { useState } from "react"
import { recommend } from "./api"
import MicSearch from "./components/MicSearch"
import "./App.css"
// Poll a URL (HEAD) until it returns 200
async function waitUntil200(url, { tries = 30, delay = 400 } = {}) {
  for (let i = 0; i < tries; i++) {
    const r = await fetch(url + (url.includes("?") ? "&" : "?") + "v=" + Date.now(), {
      method: "HEAD",
      cache: "no-store",
    })
    if (r.ok) return true
    await new Promise((res) => setTimeout(res, delay))
  }
  return false
}
const withCacheBust = (url) => url + (url.includes("?") ? "&" : "?") + "v=" + Date.now()

export default function App() {
  const [q, setQ] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [data, setData] = useState(null)
  const [transcript, setTranscript] = useState("")
  const [mediaReady, setMediaReady] = useState({ audio: false, image: false })

  const onSubmit = async (e) => {
    e?.preventDefault?.()
    if (!q.trim()) return
    setLoading(true)
    setError("")
    setData(null)
    try {
      const resp = await recommend(q.trim())
      setData(resp)
      handleAfterSetData(resp)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  function handleMicResult({ transcript, data }) {
    setTranscript(transcript || "")
    setQ(transcript || "")
    setData(data || null)
    if (data) handleAfterSetData(data)
    setError("")
    setLoading(false)
  }

  async function handleAfterSetData(resp) {
  setMediaReady({ audio: false, image: false })
  if (resp?.audio_url) {
    waitUntil200(resp.audio_url).then((ok) => ok && setMediaReady((m) => ({ ...m, audio: true })))
  }
  if (resp?.image_url) {
    waitUntil200(resp.image_url).then((ok) => ok && setMediaReady((m) => ({ ...m, image: true })))
  }
}

  return (
    <div className="app-container">
      <div className="background-elements">
        <div className="floating-element-1"></div>
        <div className="floating-element-2"></div>
        <div className="floating-element-3"></div>
      </div>

      <div className="main-content">
        <div className="header-section">
          <div className="logo-container">
            <span>📚</span>
          </div>
          <h1 className="main-title">Smart Librarian</h1>
          <p className="main-subtitle">
            Your personal literary curator. Discover books that resonate with your soul through intelligent
            recommendations.
          </p>
        </div>

        <div className="search-container">
          <div className="search-card">
            <form onSubmit={onSubmit} className="search-form">
              <div className="input-container">
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Describe your perfect book..."
                  className="search-input"
                />
                <div className="input-indicator">
                  <div className="ping-dot"></div>
                </div>
              </div>

              <button disabled={loading || !q.trim()} className="search-button">
                {loading ? (
                  <div className="loading-content">
                    <div className="loading-spinner"></div>
                    Curating recommendations...
                  </div>
                ) : (
                  "Find My Perfect Book"
                )}
              </button>
            </form>
          </div>
        </div>

        <div className="voice-search-container">
          <div className="voice-search-card">
            <div className="voice-search-header">
              <div className="voice-icon-container">
                <span>🎙️</span>
              </div>
              <h3 className="voice-search-title">Voice Search</h3>
            </div>

            <MicSearch onResult={handleMicResult} />

            {transcript && (
              <div className="transcript-display">
                <p className="transcript-label">Your request:</p>
                <p className="transcript-text">"{transcript}"</p>
              </div>
            )}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="error-container">
            <div className="error-card">
              <p className="error-text">Unable to process request: {error}</p>
            </div>
          </div>
        )}

        {data && (
          <div className="results-container">
            <div className="results-grid">
              <div className="results-content">
                {data.title && <h2 className="results-title">{data.title}</h2>}

                <div className="results-answer">
                  <div className="answer-content">{data.answer}</div>
                </div>

                {Array.isArray(data.candidates) && data.candidates.length > 0 && (
                  <div className="recommendations-section">
                    <h3 className="recommendations-title">
                      <span>⭐</span>
                      Recommended Titles
                    </h3>
                    <div className="recommendations-list">
                      {data.candidates.map(([title, distance], i) => (
                        <div key={i} className="recommendation-item" style={{ animationDelay: `${i * 100}ms` }}>
                          <span className="recommendation-title">{title}</span>
                          <span className="recommendation-score">{distance?.toFixed?.(3) ?? distance}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="results-sidebar">
                {data.image_url && (
                  mediaReady.image ? (
                    <div className="book-cover">
                      <img
                        src={withCacheBust(data.image_url)}
                        alt={data.title ?? "Book Cover"}
                      />
                    </div>
                  ) : (
                    <div className="book-cover">
                      <div className="generating-placeholder">
                        Generating your book cover…
                      </div>
                    </div>
                  )
                )}

                 {data.audio_url && (
                      mediaReady.audio ? (
                        <div className="audio-preview">
                          <div className="audio-container">
                            <h4 className="audio-title">
                              <span>🎧</span>
                              Audio Preview
                            </h4>
                            <audio controls src={withCacheBust(data.audio_url)} className="audio-controls" />
                          </div>
                        </div>
                      ) : (
                        <div className="audio-preview">
                          <div className="audio-container">
                            <h4 className="audio-title">
                              <span>🎧</span>
                              Generating your audio description…
                            </h4>
                            <div className="audio-progress" />
                          </div>
                        </div>
                      )
                    )}


              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
