"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Notes = {
  summary: string;
  key_points: string[];
  exam_questions: { q: string; a: string }[];
  terms: { term: string; definition: string }[];
  generated_by: string;
};

export default function NotesPanel({ courseId }: { courseId: string }) {
  const [notes, setNotes] = useState<Notes | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generate(regenerate = false) {
    setBusy(true);
    setError("");
    try {
      setNotes(await api<Notes>(`/courses/${courseId}/notes`, { method: regenerate ? "POST" : "GET" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build notes");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    generate(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  if (error) return <div className="error-box">{error}</div>;
  if (!notes && busy) return <div className="empty"><span className="spinner dark" /></div>;
  if (!notes) {
    return (
      <div className="empty">
        <strong>No notes yet</strong>
        <button className="btn sm" onClick={() => generate(true)} style={{ marginTop: 10 }}>
          Generate notes
        </button>
      </div>
    );
  }

  const current: Notes = notes;
  function downloadFile() {
    const notes = current;
    const lines = [
      "# Revision notes",
      "",
      notes.summary,
      "",
      "## Key points",
      ...notes.key_points.map((k) => `- ${k}`),
      "",
      "## Likely exam questions",
      ...notes.exam_questions.map((q) => `- **${q.q}** — ${q.a}`),
      "",
      "## Terms to memorise",
      ...notes.terms.map((t) => `- **${t.term}** — ${t.definition}`),
      "",
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "learn2hire-notes.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="notes-sheet">
      <div className="spread" style={{ marginBottom: 6 }}>
        <h4>Revision notes</h4>
        <div className="row" style={{ gap: 8 }}>
          <span className="badge grey">{notes.generated_by === "gemini" ? "AI written" : "from your material"}</span>
          <button className="btn xs secondary" onClick={downloadFile}>
            Download .md
          </button>
          <button className="btn xs secondary" onClick={() => generate(true)} disabled={busy}>
            {busy ? "Rebuilding…" : "Regenerate"}
          </button>
        </div>
      </div>

      <p style={{ fontSize: 14.2, lineHeight: 1.6, color: "var(--text)", marginBottom: 14 }}>{notes.summary}</p>

      {notes.key_points.length > 0 && (
        <>
          <h4>Key points</h4>
          <ul>
            {notes.key_points.map((k, i) => (
              <li key={i}>{k}</li>
            ))}
          </ul>
        </>
      )}

      {notes.exam_questions.length > 0 && (
        <>
          <h4 style={{ marginTop: 14 }}>Likely exam questions</h4>
          <ul>
            {notes.exam_questions.map((q, i) => (
              <li key={i}>
                <strong>{q.q}</strong> — {q.a}
              </li>
            ))}
          </ul>
        </>
      )}

      {notes.terms.length > 0 && (
        <>
          <h4 style={{ marginTop: 14 }}>Terms to memorise</h4>
          <ul>
            {notes.terms.map((t, i) => (
              <li key={i}>
                <strong>{t.term}</strong> — {t.definition}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}