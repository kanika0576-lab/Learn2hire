"use client";

import { useEffect, useRef, useState } from "react";
import { api, ChatMsg, fmtTime, Source } from "@/lib/api";

type Props = {
  courseId: string;
  currentTime: number;
  onSeek: (t: number) => void;
  onBusyChange?: (busy: boolean) => void;
};

export default function ChatPanel({ courseId, currentTime, onSeek, onBusyChange }: Props) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const timeRef = useRef(currentTime);
  timeRef.current = currentTime;

  useEffect(() => {
    api<ChatMsg[]>(`/courses/${courseId}/chat`)
      .then(setMessages)
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, [courseId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function setBusyBoth(v: boolean) {
    setBusy(v);
    onBusyChange?.(v);
  }

  async function send() {
    const question = input.trim();
    if (!question || busy) return;
    const askedAt = timeRef.current;
    setInput("");
    setBusyBoth(true);
    setMessages((m) => [...m, { role: "user", content: question, video_time: askedAt }]);
    try {
      const res = await api<{
        answer: string;
        sources: Source[];
        in_material: boolean;
        covered_later: boolean;
        retrieved_count: number;
      }>("/ask", {
        method: "POST",
        body: JSON.stringify({ course_id: courseId, question, video_time: askedAt }),
      });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          video_time: askedAt,
          sources: res.sources,
        },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠️ ${err instanceof Error ? err.message : "Ask failed"}`, video_time: askedAt },
      ]);
    } finally {
      setBusyBoth(false);
    }
  }

  return (
    <>
      <div className="panel-body">
        {!loaded ? (
          <div className="empty"><span className="spinner dark" /></div>
        ) : messages.length === 0 ? (
          <div className="empty">
            <div className="big">💬</div>
            <strong>Pause the video and ask anything</strong>
            <p style={{ marginTop: 6 }}>
              Answers come only from material you&apos;ve reached at {fmtTime(currentTime)} — with clickable sources.
            </p>
            <div className="row" style={{ justifyContent: "center", marginTop: 14, flexWrap: "wrap" }}>
              {["Explain the main concept so far", "Give me a quick example", "Summarize what I've watched"].map(
                (q) => (
                  <button key={q} className="btn secondary sm" onClick={() => setInput(q)}>
                    {q}
                  </button>
                ),
              )}
            </div>
          </div>
        ) : (
          messages.map((m, i) => {
            const honest =
              m.role === "assistant" &&
              (m.content.startsWith("NOT_IN_MATERIAL") || m.content.startsWith("COVERED_LATER"));
            return (
              <div key={i} className={`msg-row ${m.role === "user" ? "user" : "bot"}`}>
                {m.role === "assistant" && <StudentAvatar />}
                <div className={`msg ${m.role} ${honest ? "honest" : ""}`}>
                  <span>
                    {m.content.replace(/^NOT_IN_MATERIAL:\s*/, "🚫 Not in the material — ").replace(/^COVERED_LATER:\s*/, "⏳ Coming later — ")}
                  </span>
                  {m.video_time != null && (
                    <div className="msg-meta" style={m.role === "user" ? { justifyContent: "flex-end" } : undefined}>
                      <button
                        className="msg-time"
                        style={m.role === "user" ? { color: "rgba(255,255,255,.8)" } : undefined}
                        onClick={() => onSeek(m.video_time!)}
                        title="Jump the player to this moment"
                      >
                        ⏱ {m.role === "user" ? "asked at" : "answered at"} {fmtTime(m.video_time)} · jump
                      </button>
                    </div>
                  )}
                  {m.role === "assistant" && !!m.sources?.length && (
                    <div className="msg-meta">
                      {m.sources.map((s, j) => (
                        <button
                          key={j}
                          className={`source-chip ${s.type === "video" ? "video" : ""}`}
                          title={s.quote || s.label}
                          onClick={() => s.type === "video" && s.start_time != null && onSeek(s.start_time)}
                        >
                          {s.type === "video" ? `▶ ${fmtTime(s.start_time)}` : s.type === "pdf" ? `📄 p.${s.page}` : `📊 s.${s.slide}`}
                          <span style={{ fontWeight: 500, opacity: 0.75 }}>
                            {s.type === "video" ? "jump" : s.label.split(" ").pop()}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
        {busy && (
          <div className="msg-row bot">
            <StudentAvatar />
            <div className="msg assistant">
              <span className="typing">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="panel-foot">
        <div className="composer">
          <textarea
            className="input"
            placeholder={`Ask about the lesson at ${fmtTime(currentTime)}…`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button className="btn" onClick={send} disabled={busy || !input.trim()}>
            {busy ? <span className="spinner" /> : "Ask"}
          </button>
        </div>
        <div className="row" style={{ marginTop: 8, fontSize: 12, color: "var(--muted)" }}>
          <span>⏎ send · ⇧⏎ newline</span>
          <span style={{ marginLeft: "auto" }}>Gated to ⏱ {fmtTime(currentTime)}</span>
        </div>
      </div>
    </>
  );
}

function StudentAvatar() {
  return (
    <span className="avatar" title="Learn2Hire tutor">
      <svg viewBox="0 0 30 30" width="22" height="22">
        <circle cx="15" cy="16" r="9" fill="#ffe3c9" />
        <polygon points="15,3 27,8 15,13 3,8" fill="#2b3a67" />
        <circle cx="12" cy="16" r="1.3" fill="#3b2b1f" />
        <circle cx="18" cy="16" r="1.3" fill="#3b2b1f" />
        <path d="M12 19.5 Q15 22 18 19.5" stroke="#3b2b1f" strokeWidth="1.2" fill="none" strokeLinecap="round" />
      </svg>
    </span>
  );
}
