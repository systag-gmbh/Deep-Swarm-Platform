import { useState, useRef, useEffect } from "react";

// ── Config ──────────────────────────────────────────────────────────────────
const ANALYZER_BASE = "";

const TYPE_COLORS = {
  EMAIL_ADDRESS: "#e74c3c",
  PHONE_NUMBER: "#3498db",
  CREDIT_CARD: "#e67e22",
  SSN: "#c0392b",
  PERSON: "#e84393",
  LOCATION: "#06b6d4",
  DATE_TIME: "#f59e0b",
  IP_ADDRESS: "#1abc9c",
  IBAN: "#9b59b6",
  ID_NUMBER: "#8b5cf6",
  DRIVER_LICENSE: "#f97316",
  PASSPORT: "#14b8a6",
  ADDRESS: "#6366f1",
  AGE: "#a855f7",
  GENDER: "#ec4899",
  TAX_ID: "#84cc16",
  ZIP_CODE: "#0ea5e9",
  TITLE: "#78716c",
  URL: "#2ecc71",
};
const getColor = (type) => TYPE_COLORS[type] || "#64748b";

// ── Shared card style ───────────────────────────────────────────────────────
const CARD = {
  background: "rgba(255, 255, 255, 0.05)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  borderRadius: "16px",
  backdropFilter: "blur(10px)",
};

const INNER_ROW = {
  background: "rgba(255, 255, 255, 0.03)",
  border: "1px solid rgba(255, 255, 255, 0.06)",
  borderRadius: "10px",
};

// ── Score Bar ───────────────────────────────────────────────────────────────
function ScoreBar({ score, color }) {
  const pct = Math.round(score * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px", flex: 1 }}>
      <div style={{
        flex: 1, height: "4px", backgroundColor: "rgba(255,255,255,0.08)",
        borderRadius: "2px", overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`, height: "100%", backgroundColor: color,
          opacity: 0.3 + score * 0.7, borderRadius: "2px",
        }} />
      </div>
      <span style={{
        fontSize: "10px", fontWeight: 700, color,
        fontFamily: "var(--mono)", minWidth: "30px", textAlign: "right",
      }}>{pct}%</span>
    </div>
  );
}

// ── Highlighted Text ────────────────────────────────────────────────────────
function HighlightedText({ text, entities, activeType, setActiveType }) {
  if (!entities || !entities.length) return <span>{text}</span>;
  const sorted = [...entities].sort((a, b) => a.start - b.start);
  const parts = [];
  let cursor = 0;
  for (const e of sorted) {
    if (cursor < e.start) parts.push(<span key={`t${cursor}`}>{text.slice(cursor, e.start)}</span>);
    const color = getColor(e.entity_type);
    const value = text.slice(e.start, e.end);
    const isActive = activeType === e.entity_type;
    const isDimmed = activeType !== null && !isActive;
    parts.push(
      <span key={`e${e.start}`} className="pii-entity" style={{
        backgroundColor: isActive ? color + "50" : color + "25",
        color,
        borderBottom: `2px solid ${color}`,
        padding: "0 3px", borderRadius: "2px", fontWeight: 600,
        cursor: "default",
        position: "relative",
        opacity: isDimmed ? 0.35 : 1,
        transition: "all 0.15s ease",
      }}>
        {value}
        <span className="pii-tooltip" style={{
          position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
          transform: "translateX(-50%)", pointerEvents: "none",
          opacity: 0, transition: "opacity 0.15s ease",
          whiteSpace: "nowrap", fontSize: "11px", fontWeight: 600,
          fontFamily: "var(--mono)",
          background: "rgba(0,0,0,0.85)", color: "#fff",
          padding: "4px 10px", borderRadius: "6px",
          border: `1px solid ${color}44`,
          zIndex: 10,
        }}>
          <span style={{ color }}>{e.entity_type}</span>
          <span style={{ color: "#64748b", margin: "0 4px" }}>·</span>
          <span style={{ color }}>{Math.round(e.score * 100)}%</span>
        </span>
      </span>
    );
    cursor = e.end;
  }
  if (cursor < text.length) parts.push(<span key={`t${cursor}`}>{text.slice(cursor)}</span>);
  return <>{parts}</>;
}

// ── Analysis Result ─────────────────────────────────────────────────────────
function AnalysisResult({ text, analyzeResult, anonymizeResult }) {
  const [view, setView] = useState("original");
  const [activeType, setActiveType] = useState(null);

  const entities = analyzeResult.map((e) => {
    const value = text.slice(e.start, e.end);
    const mask = anonymizeResult?.entity_mapping
      ? Object.entries(anonymizeResult.entity_mapping).find(
          ([, v]) => v.toLowerCase() === value.toLowerCase()
        )?.[0] || "—"
      : "—";
    return { ...e, value, mask };
  });

  const grouped = {};
  for (const e of entities) {
    if (!grouped[e.entity_type]) grouped[e.entity_type] = [];
    grouped[e.entity_type].push(e);
  }

  const views = [
    { id: "original", label: "Original" },
    { id: "masked", label: "Masked" },
    { id: "entities", label: `${entities.length} found` },
  ];

  return (
    <div style={{ ...CARD, overflow: "hidden" }}>
      {/* Section header */}
      <div style={{
        padding: "1.25rem 1.5rem 0.75rem",
        borderBottom: "1px solid rgba(255,255,255,0.1)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <h2 style={{
          fontSize: "1.1rem", fontWeight: 500, textTransform: "uppercase",
          letterSpacing: "0.15em", color: "#94a3b8", margin: 0,
        }}>Results</h2>
        <div style={{
          display: "flex", gap: "2px",
          background: "rgba(0,0,0,0.3)", borderRadius: "8px",
          padding: "3px",
        }}>
          {views.map(v => (
            <button key={v.id} onClick={() => setView(v.id)} style={{
              padding: "4px 12px", borderRadius: "6px", border: "none",
              fontSize: "11px", fontWeight: 600, cursor: "pointer",
              fontFamily: "var(--mono)",
              backgroundColor: view === v.id ? "rgba(255,255,255,0.1)" : "transparent",
              color: view === v.id ? "#e4e4e4" : "#64748b",
              transition: "all 0.15s ease",
            }}>{v.label}</button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{
        padding: "1.25rem 1.5rem", fontFamily: "var(--mono)",
        fontSize: "13.5px", lineHeight: 1.8, color: "#e4e4e4",
        whiteSpace: "pre-wrap", wordBreak: "break-word",
      }}>
        {view === "original" && (
          <HighlightedText text={text} entities={analyzeResult} activeType={activeType} setActiveType={setActiveType} />
        )}
        {view === "masked" && (
          <span style={{ color: "#94a3b8" }}>
            {anonymizeResult?.text || text}
          </span>
        )}
        {view === "entities" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            {Object.entries(grouped).map(([type, items]) => {
              const color = getColor(type);
              return (
                <div key={type}>
                  <div style={{
                    fontSize: "0.7rem", fontWeight: 500, color,
                    letterSpacing: "0.15em", textTransform: "uppercase",
                    marginBottom: "8px", display: "flex", alignItems: "center", gap: "8px",
                  }}>
                    <span style={{
                      width: "6px", height: "6px", borderRadius: "50%",
                      backgroundColor: color, flexShrink: 0,
                    }} />
                    {type} ({items.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    {items.map((e, i) => (
                      <div key={i} style={{
                        ...INNER_ROW,
                        display: "grid",
                        gridTemplateColumns: "minmax(0, 1fr) 20px minmax(0, 1fr) 100px",
                        alignItems: "center", gap: "8px",
                        padding: "0.75rem 1rem",
                        fontSize: "12px",
                        transition: "all 0.2s ease",
                      }}>
                        <span style={{ color, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {e.value}
                        </span>
                        <span style={{ color: "#64748b", textAlign: "center" }}>&rarr;</span>
                        <span style={{ color: "#94a3b8", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.mask}</span>
                        <ScoreBar score={e.score} color={color} />
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Entity summary strip */}
      {entities.length > 0 && (
        <div style={{
          display: "flex", gap: "6px", flexWrap: "wrap",
          padding: "0.75rem 1.5rem",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          alignItems: "center",
        }}>
          {Object.entries(grouped).map(([type, items]) => {
            const color = getColor(type);
            const isActive = activeType === type;
            const isDimmed = activeType !== null && !isActive;
            return (
              <span key={type} style={{
                display: "inline-flex", alignItems: "center", gap: "4px",
                fontSize: "10px", fontFamily: "var(--mono)",
                color, backgroundColor: isActive ? color + "30" : color + "12",
                padding: "2px 8px", borderRadius: "4px",
                border: `1px solid ${isActive ? color + "50" : color + "25"}`,
                fontWeight: 600, cursor: "pointer",
                opacity: isDimmed ? 0.35 : 1,
                transition: "all 0.15s ease",
              }}
              onMouseEnter={() => setActiveType(type)}
              onMouseLeave={() => setActiveType(null)}
              >
                <span style={{
                  width: "5px", height: "5px", borderRadius: "50%",
                  backgroundColor: color, flexShrink: 0,
                }} />
                {type} &times;{items.length}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Suggestions ─────────────────────────────────────────────────────────────
const SUGGESTIONS = [
  "Hi, I'm Dr. Lena Bergström. My email is lena.bergstrom@example.com and my phone is +49 170 9876543.",
  "Please transfer €500 to IBAN DE89 3704 0044 0532 0130 00 for Mrs. Amara Okonkwo.",
  "Employee SSN: 321-54-9876, card: 4532-8765-4321-0987, born 22.07.1990, IP: 192.168.1.55",
  "Contact Prof. Tomáš Dvořák at t.dvorak@example.com or call (555) 234-8901",
];

// ── Settings Panel ──────────────────────────────────────────────────────────
function SettingsPanel({ config, setConfig, onClose }) {
  return (
    <div style={{
      position: "fixed", top: 0, right: 0, bottom: 0, width: "360px",
      background: "linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)",
      borderLeft: "1px solid rgba(255,255,255,0.1)",
      padding: "1.5rem", zIndex: 100, overflowY: "auto",
      boxShadow: "-8px 0 32px rgba(0,0,0,0.5)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <span style={{
          fontSize: "1.1rem", fontWeight: 500, color: "#94a3b8",
          textTransform: "uppercase", letterSpacing: "0.15em",
        }}>Settings</span>
        <button onClick={onClose} style={{
          background: "none", border: "none", color: "#64748b",
          fontSize: "18px", cursor: "pointer",
        }}>&times;</button>
      </div>
      <div style={{ marginBottom: "16px" }}>
        <label style={{
          display: "block", fontSize: "0.7rem", fontWeight: 500,
          color: "#64748b", fontFamily: "var(--mono)",
          letterSpacing: "0.1em", marginBottom: "8px",
          textTransform: "uppercase",
        }}>Analyzer Base URL</label>
        <input
          type="text"
          value={config.analyzerBase}
          onChange={(e) => setConfig(prev => ({ ...prev, analyzerBase: e.target.value }))}
          style={{
            width: "100%", padding: "0.875rem 1rem",
            ...INNER_ROW,
            color: "#e4e4e4",
            fontSize: "13px", fontFamily: "var(--mono)",
            outline: "none", boxSizing: "border-box",
          }}
        />
      </div>
    </div>
  );
}

// ── Main App ────────────────────────────────────────────────────────────────
export default function PIIAnalyzerTool() {
  const [input, setInput] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [responseTime, setResponseTime] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [config, setConfig] = useState({ analyzerBase: ANALYZER_BASE });
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleAnalyze = async (text) => {
    const trimmed = (text || input).trim();
    if (!trimmed || analyzing) return;
    setError(null);
    setResult(null);
    setResponseTime(null);
    setAnalyzing(true);

    const t0 = performance.now();
    try {
      const analyzeRes = await fetch(`${config.analyzerBase}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: trimmed, language: "en" }),
      });
      if (!analyzeRes.ok) throw new Error(`Analyze failed: ${analyzeRes.status}`);
      const analyzeResult = await analyzeRes.json();

      let anonymizeResult = null;
      if (analyzeResult.length > 0) {
        const anonRes = await fetch(`${config.analyzerBase}/anonymize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: trimmed, analyzer_results: analyzeResult }),
        });
        if (!anonRes.ok) throw new Error(`Anonymize failed: ${anonRes.status}`);
        anonymizeResult = await anonRes.json();
      }

      setResponseTime(performance.now() - t0);
      setResult({ text: trimmed, analyzeResult, anonymizeResult });
    } catch (err) {
      setError(err.message);
      setResult(null);
      setResponseTime(null);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleClear = () => {
    setInput("");
    setResult(null);
    setError(null);
    setResponseTime(null);
    inputRef.current?.focus();
  };

  const handleSuggestion = (text) => {
    setInput(text);
    handleAnalyze(text);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleAnalyze();
    }
  };

  const entityCount = result?.analyzeResult?.length || 0;

  return (
    <div style={{
      "--mono": "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
      minHeight: "100vh", display: "flex", flexDirection: "column",
      background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
      color: "#e4e4e4",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
      <style>{`.pii-entity:hover .pii-tooltip { opacity: 1 !important; }`}</style>

      {/* Header */}
      <div style={{
        padding: "1.25rem 2rem",
        borderBottom: "1px solid rgba(255,255,255,0.1)",
        background: "rgba(0,0,0,0.15)",
        backdropFilter: "blur(10px)",
        flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div onClick={handleClear} style={{ display: "flex", alignItems: "center", gap: "12px", cursor: "pointer" }}>
          <div style={{
            width: "32px", height: "32px", borderRadius: "8px",
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "14px", fontWeight: 700, color: "#fff",
            flexShrink: 0,
          }}>PII</div>
          <span style={{
            fontSize: "1.25rem", fontWeight: 300, color: "#fff",
            letterSpacing: "0.05em",
          }}>PII Analyzer</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {entityCount > 0 && (
            <span style={{
              fontSize: "11px", color: "#f59e0b", fontFamily: "var(--mono)", fontWeight: 600,
            }}>{entityCount} PII detected</span>
          )}

          {responseTime != null && (
            <span style={{
              fontSize: "10px", color: "#64748b", fontFamily: "var(--mono)", fontWeight: 600,
              padding: "4px 10px",
              ...INNER_ROW,
            }}>{responseTime < 1000 ? `${Math.round(responseTime)}ms` : `${(responseTime / 1000).toFixed(1)}s`}</span>
          )}

          {config.analyzerBase && (
            <span style={{
              fontSize: "10px", color: "#64748b", fontFamily: "var(--mono)",
              padding: "4px 10px",
              ...INNER_ROW,
            }}>{config.analyzerBase}</span>
          )}

          {result && (
            <button onClick={handleClear} style={{
              ...INNER_ROW,
              color: "#94a3b8", padding: "4px 12px",
              fontSize: "10px", cursor: "pointer", fontFamily: "var(--mono)", fontWeight: 500,
              transition: "all 0.2s ease",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(255,255,255,0.1)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = INNER_ROW.background; e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; }}
            >Clear</button>
          )}

          {ANALYZER_BASE && (
            <button onClick={() => setShowSettings(!showSettings)} style={{
              ...INNER_ROW,
              color: "#94a3b8", padding: "4px 12px",
              fontSize: "16px", cursor: "pointer", lineHeight: 1,
              transition: "all 0.2s ease",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(255,255,255,0.1)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = INNER_ROW.background; e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; }}
            >&#9881;</button>
          )}
        </div>
      </div>

      {showSettings && (
        <SettingsPanel config={config} setConfig={setConfig} onClose={() => setShowSettings(false)} />
      )}

      {/* Main content */}
      <div style={{
        flex: 1, overflowY: "auto", padding: "2rem",
        display: "flex", flexDirection: "column", alignItems: "center",
      }}>
        <div style={{ width: "100%", maxWidth: "800px", display: "flex", flexDirection: "column", gap: "1.5rem" }}>

          {/* Input card */}
          <div style={{ ...CARD, overflow: "hidden" }}>
            <div style={{
              padding: "1.25rem 1.5rem 0.75rem",
              borderBottom: "1px solid rgba(255,255,255,0.1)",
            }}>
              <h2 style={{
                fontSize: "1.1rem", fontWeight: 500, textTransform: "uppercase",
                letterSpacing: "0.15em", color: "#94a3b8", margin: 0,
              }}>Analyze Text</h2>
            </div>
            <div style={{ padding: "1.25rem 1.5rem" }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Paste or type text containing PII to analyze..."
                rows={4}
                style={{
                  width: "100%", padding: "0.875rem 1rem",
                  ...INNER_ROW,
                  color: "#e4e4e4",
                  outline: "none", resize: "vertical",
                  fontSize: "14px", fontFamily: "var(--mono)",
                  lineHeight: 1.6, minHeight: "100px",
                  boxSizing: "border-box",
                }}
              />
              <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                marginTop: "0.75rem",
              }}>
                <span style={{ fontSize: "11px", color: "#64748b", fontFamily: "var(--mono)" }}>
                  {input.length > 0 ? `${input.length} chars` : "Ctrl+Enter to analyze"}
                </span>
                <button
                  onClick={() => handleAnalyze()}
                  disabled={!input.trim() || analyzing}
                  style={{
                    padding: "0.625rem 1.5rem", borderRadius: "10px", border: "none",
                    fontSize: "0.85rem", fontWeight: 600,
                    cursor: !input.trim() || analyzing ? "not-allowed" : "pointer",
                    background: !input.trim() || analyzing
                      ? "rgba(255,255,255,0.05)"
                      : "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                    color: !input.trim() || analyzing ? "#64748b" : "#fff",
                    transition: "all 0.2s ease",
                    letterSpacing: "0.05em",
                  }}
                >{analyzing ? "Analyzing..." : "Analyze"}</button>
              </div>
            </div>
          </div>

          {/* Suggestion chips (show when no result) */}
          {!result && !error && !analyzing && (
            <div style={{ ...CARD, padding: "1.5rem" }}>
              <h2 style={{
                fontSize: "1.1rem", fontWeight: 500, textTransform: "uppercase",
                letterSpacing: "0.15em", color: "#94a3b8", margin: 0,
                paddingBottom: "0.75rem",
                borderBottom: "1px solid rgba(255,255,255,0.1)",
                marginBottom: "1.25rem",
              }}>Try an Example</h2>
              <div style={{
                display: "flex", flexDirection: "column", gap: "0.5rem",
              }}>
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} onClick={() => handleSuggestion(s)} style={{
                    ...INNER_ROW,
                    display: "flex", alignItems: "center", gap: "0.75rem",
                    textAlign: "left", padding: "0.875rem 1rem",
                    cursor: "pointer",
                    fontSize: "12px", color: "#e4e4e4",
                    fontFamily: "var(--mono)", lineHeight: 1.5,
                    transition: "all 0.2s ease",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = "rgba(255,255,255,0.1)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"; e.currentTarget.style.transform = "translateX(4px)"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = INNER_ROW.background; e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; e.currentTarget.style.transform = "none"; }}
                  >
                    <div style={{
                      width: "32px", height: "32px", borderRadius: "8px",
                      background: [
                        "linear-gradient(135deg, #f97316 0%, #ea580c 100%)",
                        "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                        "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
                        "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
                      ][i],
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: "12px", color: "#fff", flexShrink: 0,
                      fontWeight: 600,
                    }}>{i + 1}</div>
                    <span style={{ flex: 1 }}>{s}</span>
                    <span style={{ color: "#64748b", fontSize: "1.25rem", transition: "transform 0.2s ease" }}>&rarr;</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{
              ...CARD,
              padding: "1rem 1.5rem",
              borderColor: "rgba(239,68,68,0.3)",
              fontSize: "13px", color: "#fca5a5", fontFamily: "var(--mono)",
            }}>{error}</div>
          )}

          {/* Results */}
          {result && (
            <AnalysisResult
              text={result.text}
              analyzeResult={result.analyzeResult}
              anonymizeResult={result.anonymizeResult}
            />
          )}

          {/* No PII found */}
          {result && result.analyzeResult.length === 0 && (
            <div style={{
              ...CARD,
              padding: "1.25rem 1.5rem",
              borderColor: "rgba(34,197,94,0.2)",
              fontSize: "13px", color: "#86efac", fontFamily: "var(--mono)",
              textAlign: "center",
            }}>No PII detected in the input text.</div>
          )}
        </div>
      </div>
    </div>
  );
}
