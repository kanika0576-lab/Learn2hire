"use client";

import { RobotInterviewer, RobotState } from "@/components/Classroom";

import { useEffect, useRef, useState } from "react";
import { api, Evaluation, Scorecard } from "@/lib/api";

type Props = { courseId: string; initialMode?: "live" | "text" | null };

type Turn = { role: "interviewer" | "candidate"; content: string; evaluation?: Evaluation };

export default function InterviewPanel({ courseId, initialMode = null }: Props) {
  const [mode, setMode] = useState<"live" | "text" | null>(initialMode);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [status, setStatus] = useState<"idle" | "active" | "completed">("idle");
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // live-mode state
  const [robot, setRobot] = useState<RobotState>("idle");
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [micError, setMicError] = useState("");
  const [violations, setViolations] = useState<string[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const recRef = useRef<any>(null);
  const finalRef = useRef("");
  const sessionIdRef = useRef<string | null>(null);
  const turnsRef = useRef<Turn[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const proctoring = mode === "live" && status === "active";

  const srSupported =
    typeof window !== "undefined" &&
    !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  const ttsSupported = typeof window !== "undefined" && "speechSynthesis" in window;

  turnsRef.current = turns;
  sessionIdRef.current = sessionId;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy, interim]);

  useEffect(() => {
    return () => {
      cleanupLive();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Anti-cheat while the live interview runs: log integrity events, block copy/paste,
  // right-click, and screen-capture shortcuts so the candidate answers from their own head.
  useEffect(() => {
    if (!proctoring) return;

    const log = (reason: string) =>
      setViolations((prev) => (prev.includes(reason) ? prev : [...prev, reason]));

    const onVisibility = () => {
      if (document.hidden) log("Tab switched / window hidden");
    };
    const onBlur = () => log("Interview window lost focus");
    const onContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      log("Right-click blocked");
    };
    const onCopy = (e: ClipboardEvent) => {
      e.preventDefault();
      log("Copy blocked");
    };
    const onKeyDown = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      const ctrl = e.ctrlKey || e.metaKey;
      if (ctrl && ["c", "v", "x", "a", "p", "s"].includes(k)) {
        e.preventDefault();
        log(`Shortcut ${e.ctrlKey ? "Ctrl" : "Cmd"}+${k.toUpperCase()} blocked`);
      }
      if (e.key === "F11") {
        e.preventDefault();
        log("Fullscreen toggle blocked");
      }
    };
    const onFullscreenChange = () => {
      if (!document.fullscreenElement) log("Exited fullscreen");
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("contextmenu", onContextMenu);
    document.addEventListener("copy", onCopy);
    document.addEventListener("cut", onCopy);
    document.addEventListener("paste", onCopy);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("fullscreenchange", onFullscreenChange);

    document.documentElement.requestFullscreen?.().catch(() => {
      /* browser may refuse without a user gesture — not fatal */
    });

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("contextmenu", onContextMenu);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("cut", onCopy);
      document.removeEventListener("paste", onCopy);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
    };
  }, [proctoring]);

  function cleanupLive() {
    try {
      recRef.current?.abort?.();
      recRef.current = null;
    } catch {
      /* ignore */
    }
    try {
      window.speechSynthesis?.cancel();
    } catch {
      /* ignore */
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  async function start(modeChosen: "live" | "text") {
    setBusy(true);
    setError("");
    setMicError("");
    try {
      if (modeChosen === "live") {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
          streamRef.current = stream;
          const videoEl = document.getElementById("selfview") as HTMLVideoElement | null;
          if (videoEl) videoEl.srcObject = stream;
        } catch {
          setMicError(
            "Camera/microphone permission was denied or unavailable. Use typed answers instead, or allow access and retry.",
          );
          setMode("text");
          modeChosen = "text";
        }
      }
      setMode(modeChosen);
      const res = await api<{
        session_id: string;
        current_question: string;
        history: Turn[];
      }>("/interview/start", { method: "POST", body: JSON.stringify({ course_id: courseId }) });
      setSessionId(res.session_id);
      setTurns(res.history);
      setStatus("active");
      if (modeChosen === "live") speak(res.current_question);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start interview");
    } finally {
      setBusy(false);
    }
  }

  /* ---------- live mode: TTS + STT ---------- */

  function speak(text: string) {
    if (!text) return;
    if (!ttsSupported) {
      setMicError("This browser has no speech synthesis — reading is disabled, use the captions below.");
      setRobot("listening");
      return;
    }
    setRobot("speaking");
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = 1.02;
    const done = () => {
      if (streamRef.current) startListening();
      else setRobot("idle");
    };
    u.onend = done;
    u.onerror = done;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  function startListening() {
    if (!srSupported) {
      setRobot("idle");
      return;
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    finalRef.current = "";
    rec.onresult = (e: any) => {
      let interimText = "";
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t;
        else interimText += t;
      }
      setInterim(interimText);
      if (finalText) finalRef.current = (finalRef.current + " " + finalText).trim();
    };
    rec.onerror = (e: any) => {
      setListening(false);
      setInterim("");
      setRobot("idle");
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setMicError("Microphone access was blocked. Allow the mic, or switch to typed answers.");
      }
    };
    rec.onend = () => {
      setListening(false);
      setInterim("");
      const text = finalRef.current.trim();
      if (text) {
        submitLiveAnswer(text);
      } else {
        setRobot("idle");
      }
    };
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
      setRobot("listening");
    } catch {
      setRobot("idle");
    }
  }

  function stopListening() {
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
  }

  async function submitLiveAnswer(text: string) {
    if (!sessionIdRef.current) return;
    setBusy(true);
    setRobot("thinking");
    setTurns((t) => [...t, { role: "candidate", content: text }]);
    try {
      const res = await api<{
        status: string;
        current_question: string;
        evaluation: Evaluation;
        scorecard: Scorecard;
      }>("/interview/answer", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionIdRef.current, answer: text }),
      });
      setTurns((t) => [
        ...t,
        { role: "interviewer", content: res.current_question || "Thank you — that concludes the interview.", evaluation: res.evaluation },
      ]);
      if (res.status === "completed") {
        setStatus("completed");
        setScorecard(res.scorecard);
        setRobot("idle");
        cleanupLive();
      } else {
        speak(res.current_question);
      }
    } catch {
      setTurns((t) => [...t, { role: "interviewer", content: "⚠️ Something went wrong — please try again." }]);
      setRobot("idle");
    } finally {
      setBusy(false);
    }
  }

  /* ---------- text mode ---------- */

  async function submitTyped() {
    const text = input.trim();
    if (!text || !sessionId || busy) return;
    setInput("");
    setBusy(true);
    setRobot("thinking");
    setTurns((t) => [...t, { role: "candidate", content: text }]);
    try {
      const res = await api<{
        status: string;
        current_question: string;
        evaluation: Evaluation;
        scorecard: Scorecard;
      }>("/interview/answer", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, answer: text }),
      });
      setTurns((t) => [
        ...t,
        { role: "interviewer", content: res.current_question || "Thank you — that concludes the interview.", evaluation: res.evaluation },
      ]);
      if (res.status === "completed") {
        setStatus("completed");
        setScorecard(res.scorecard);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Answer failed");
      setTurns((t) => [...t, { role: "interviewer", content: "⚠️ Something went wrong — please try again." }]);
    } finally {
      setBusy(false);
      setRobot("idle");
    }
  }

  function reset() {
    cleanupLive();
    setMode(initialMode);
    setSessionId(null);
    setTurns([]);
    setStatus("idle");
    setScorecard(null);
    setInput("");
    setError("");
    setMicError("");
    setRobot("idle");
    setListening(false);
    setInterim("");
    setViolations([]);
  }

  /* ---------- views ---------- */

  if (status === "idle" && !mode) {
    return (
      <>
        <div className="panel-body">
          <div className="empty" style={{ paddingBottom: 20 }}>
            <RobotInterviewer state="idle" size={120} />
            <strong style={{ display: "block", marginTop: 10 }}>How do you want to be interviewed?</strong>
            <p style={{ marginTop: 6, maxWidth: 400, marginInline: "auto" }}>
              Same adaptive interviewer either way — 6 questions from your course, per-answer feedback, explainable
              scorecard.
            </p>
            {error && <div className="error-box" style={{ marginTop: 14 }}>{error}</div>}
            {micError && <div className="notice" style={{ marginTop: 14 }}>{micError}</div>}
            <div className="mode-pick" style={{ marginTop: 18, maxWidth: 480, marginInline: "auto" }}>
              <button className="mode-card" onClick={() => start("live")} disabled={busy}>
                <span className="m-ico">🎥</span>
                <strong>Live interview experience</strong>
                <span>Camera on, answer out loud. The robot asks, listens and speaks — no typing allowed.</span>
              </button>
              <button className="mode-card" onClick={() => start("text")} disabled={busy}>
                <span className="m-ico">⌨️</span>
                <strong>Type your answers</strong>
                <span>Interview-style questions — read, think, and type your answer. Works in any browser.</span>
              </button>
            </div>
            {busy && <p className="meta" style={{ marginTop: 12 }}>Starting…</p>}
          </div>
        </div>
        <div className="panel-foot">
          <p style={{ fontSize: 12.5, color: "var(--muted)" }}>
            Live mode uses your browser&apos;s speech recognition (Chrome / Edge recommended). Audio never leaves your
            machine except for the answer text sent to the tutor.
          </p>
        </div>
      </>
    );
  }

  if (status === "completed" && scorecard) {
    return (
      <>
        <div className="panel-body">
          <div style={{ textAlign: "center" }}>
            <RobotInterviewer state="idle" size={92} />
          </div>
          <div className="card scorecard">
            <div className="big-score">
              <div className="n">{scorecard.overall.toFixed(1)}</div>
              <span className="badge purple" style={{ fontSize: 13 }}>
                {scorecard.grade} · overall / 10
              </span>
            </div>
            <div className="stack" style={{ gap: 11 }}>
              <Meter label="Technical accuracy" value={scorecard.technical_accuracy} />
              <Meter label="Communication" value={scorecard.communication} />
              <Meter label="Relevance" value={scorecard.relevance} />
            </div>
            <div className="two-col">
              <div>
                <strong style={{ fontSize: 13.5, color: "var(--accent)" }}>Strengths</strong>
                <ul className="list-plain" style={{ marginTop: 7 }}>
                  {scorecard.strengths.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <strong style={{ fontSize: 13.5, color: "var(--warn)" }}>To improve</strong>
                <ul className="list-plain" style={{ marginTop: 7 }}>
                  {scorecard.improvements.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="notice" style={{ background: "var(--primary-weak)", borderColor: "rgba(59,91,219,.2)", color: "var(--primary)" }}>
              <strong>How this was scored: </strong>
              {scorecard.explanation}
            </div>
            {violations.length > 0 && (
              <div className="notice" style={{ marginTop: 10 }}>
                <strong>Integrity flags ({violations.length}):</strong> {violations.join(" · ")}
                {violations.length >= 3 ? " — this session would not count as a clean interview." : ""}
              </div>
            )}
            {scorecard.topics_covered.length > 0 && (
              <div className="row" style={{ flexWrap: "wrap" }}>
                <span className="meta">Topics:</span>
                {scorecard.topics_covered.map((t, i) => (
                  <span key={i} className="badge grey">{t}</span>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="panel-foot">
          <button className="btn block secondary" onClick={reset}>
            Take another interview
          </button>
        </div>
      </>
    );
  }

  /* active interview — live or text */
  const isLive = mode === "live";
  return (
    <>
      <div className="panel-body">
        {isLive && (
          <div className="live-stage">
            <div className="live-video-wrap">
              <RobotInterviewer state={busy && robot === "idle" ? "thinking" : robot} size={150} />
              <div className="live-self">
                <video id="selfview" autoPlay playsInline muted ref={(el) => { if (el && streamRef.current && el.srcObject !== streamRef.current) el.srcObject = streamRef.current; }} />
              </div>
            </div>
            <div className="live-caption">
              {listening ? (
                <>
                  <strong style={{ color: "var(--danger)" }}>● Listening…</strong>{" "}
                  <span className="interim">{interim || "speak now"}</span>
                </>
              ) : busy || robot === "speaking" || robot === "thinking" ? (
                <span className="interim">
                  {robot === "speaking" ? "Interviewer is speaking…" : "Thinking about your answer…"}
                </span>
              ) : (
                <span>Press the mic and answer out loud — no typing needed.</span>
              )}
            </div>
            {micError && <div className="notice" style={{ marginTop: 10 }}>{micError}</div>}

            <div className={`proctor-bar ${violations.length ? "warn" : ""}`}>
              <span className="pb-dot" />
              <span className="pb-text">
                <strong>Proctored session</strong> — camera on, fullscreen locked. Switching tabs, copying text and
                right-click are disabled and logged.
              </span>
              {violations.length > 0 && (
                <span className="pb-count" title={violations.join("\n")}>
                  {violations.length} flag{violations.length > 1 ? "s" : ""}
                </span>
              )}
            </div>
            {violations.length > 0 && (
              <div className="notice" style={{ marginTop: 8, fontSize: 12.5 }}>
                <strong>Integrity flags:</strong> {violations.join(" · ")}
              </div>
            )}
          </div>
        )}

        {!isLive &&
          turns.map((t, i) => (
            <div key={i} style={{ display: "contents" }}>
              {t.role === "interviewer" ? (
                <div className="turn-row bot">
                  <span className="avatar"><RobotHead /></span>
                  <div className="turn-q">{t.content}</div>
                </div>
              ) : (
                <div className="turn-row user">
                  <div className="turn-a">{t.content}</div>
                </div>
              )}
              {t.evaluation && (
                <div className="turn-feedback">
                  <strong>Feedback:</strong> {t.evaluation.feedback}{" "}
                  <span className="badge grey" style={{ marginLeft: 4 }}>
                    tech {t.evaluation.technical_accuracy}/10
                  </span>{" "}
                  <span className="badge grey">comm {t.evaluation.communication}/10</span>{" "}
                  <span className="badge grey">rel {t.evaluation.relevance}/10</span>
                </div>
              )}
            </div>
          ))}

        {busy && !isLive && (
          <div className="turn-row bot">
            <span className="avatar"><RobotHead /></span>
            <div className="turn-q">
              <span className="typing">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}
        {error && <div className="error-box">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <div className="panel-foot">
        {isLive ? (
          <div className="live-controls">
            <button
              className={`mic-btn ${listening ? "listening" : ""}`}
              onClick={() => (listening ? stopListening() : startListening())}
              disabled={busy || robot === "speaking"}
              title={listening ? "Stop and submit" : "Start speaking"}
            >
              {listening ? "■" : "🎤"}
            </button>
            <div>
              <div className="live-hint">
                {listening ? "Tap ■ when finished — your answer is submitted automatically" : "Tap 🎤 to answer out loud"}
              </div>
              <button className="btn ghost sm" style={{ marginTop: 6 }} onClick={() => speak(turns.filter((t) => t.role === "interviewer").slice(-1)[0]?.content ?? "")}>
                🔁 Repeat the question
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="composer">
              <textarea
                className="input"
                placeholder="Type your interview answer…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submitTyped();
                  }
                }}
              />
              <button className="btn" onClick={submitTyped} disabled={busy || !input.trim()}>
                {busy ? <span className="spinner" /> : "Answer"}
              </button>
            </div>
            <div className="row" style={{ marginTop: 8, fontSize: 12, color: "var(--muted)" }}>
              <span>Answer out loud in your head — type the key points</span>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function RobotHead() {
  return (
    <svg viewBox="0 0 30 30" width="20" height="20">
      <rect x="5" y="8" width="20" height="15" rx="5" fill="#dbe6f5" stroke="#b7c6de" strokeWidth="1" />
      <rect x="8" y="11" width="14" height="9" rx="3" fill="#16233a" />
      <rect x="10.5" y="13.5" width="3" height="4" rx="1.4" fill="#7dd3fc" />
      <rect x="16.5" y="13.5" width="3" height="4" rx="1.4" fill="#7dd3fc" />
      <line x1="15" y1="4" x2="15" y2="8" stroke="#8b9bb8" strokeWidth="1.6" />
      <circle cx="15" cy="3.4" r="2" fill="#4da3ff" />
    </svg>
  );
}

function Meter({ label, value }: { label: string; value: number }) {
  return (
    <div className="meter">
      <div className="lbl">
        <span>{label}</span>
        <span>{value.toFixed(1)} / 10</span>
      </div>
      <div className="track">
        <div className="fill" style={{ width: `${Math.min(100, (value / 10) * 100)}%` }} />
      </div>
    </div>
  );
}
