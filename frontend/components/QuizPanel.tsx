"use client";

import { useState } from "react";
import { api, fmtTime, QuizQuestion, Source } from "@/lib/api";

type Props = {
  courseId: string;
  currentTime: number;
  onSeek: (t: number) => void;
};

type Result = {
  score: number;
  total: number;
  detail: { id: string; correct: boolean; correct_index: number; explanation: string; question: string }[];
};

export default function QuizPanel({ courseId, currentTime, onSeek }: Props) {
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [picked, setPicked] = useState<Record<string, number>>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function generate() {
    setBusy(true);
    setError("");
    setResult(null);
    setPicked({});
    try {
      const res = await api<{ questions: QuizQuestion[] }>("/quiz/generate", {
        method: "POST",
        body: JSON.stringify({ course_id: courseId, video_time: currentTime, n_questions: 5 }),
      });
      setQuestions(res.questions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate quiz");
      setQuestions([]);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setBusy(true);
    try {
      const res = await api<Result>("/quiz/submit", {
        method: "POST",
        body: JSON.stringify({ course_id: courseId, answers: picked }),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  }

  function chip(s?: Source) {
    if (!s) return null;
    return (
      <button
        className={`source-chip ${s.type === "video" ? "video" : ""}`}
        onClick={() => s.type === "video" && s.start_time != null && onSeek(s.start_time)}
        title={s.label}
      >
        {s.type === "video" ? `▶ ${fmtTime(s.start_time)}` : s.type === "pdf" ? `📄 p.${s.page}` : `📊 s.${s.slide}`}{" "}
        <span style={{ fontWeight: 500, opacity: 0.75 }}>{s.type === "video" ? "video" : s.label.split(" ").pop()}</span>
      </button>
    );
  }

  const allPicked = questions.length > 0 && questions.every((q) => picked[q.id] !== undefined);

  return (
    <>
      <div className="panel-body">
        {error && <div className="error-box">{error}</div>}

        {questions.length === 0 ? (
          <div className="empty">
            <div className="big">📝</div>
            <strong>Quiz from what you&apos;ve watched</strong>
            <p style={{ marginTop: 6 }}>
              Questions are built only from material up to {fmtTime(currentTime)} — click a source to jump back to it.
            </p>
            <button className="btn" style={{ marginTop: 16 }} onClick={generate} disabled={busy}>
              {busy && <span className="spinner" />}
              {busy ? "Generating…" : `Generate quiz at ${fmtTime(currentTime)}`}
            </button>
          </div>
        ) : (
          <>
            {questions.map((q, i) => {
              const detail = result?.detail.find((d) => d.id === q.id);
              return (
                <div key={q.id} className="card quiz-q">
                  <div className="spread">
                    <span className="qtext">
                      {i + 1}. {q.question}
                    </span>
                    <span className="badge grey">#{i + 1}</span>
                  </div>
                  <div className="stack" style={{ gap: 8 }}>
                    {q.options.map((opt, oi) => {
                      let cls = "opt";
                      if (result) {
                        if (oi === q.correct_index) cls += " correct";
                        else if (picked[q.id] === oi) cls += " wrong";
                      }
                      return (
                        <button
                          key={oi}
                          className={cls}
                          disabled={!!result}
                          onClick={() => setPicked((p) => ({ ...p, [q.id]: oi }))}
                        >
                          <span className="badge grey" style={{ minWidth: 22, justifyContent: "center" }}>
                            {String.fromCharCode(65 + oi)}
                          </span>
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    {chip(q.source)}
                    {detail && (
                      <span className={`badge ${detail.correct ? "green" : "red"}`}>
                        {detail.correct ? "✓ Correct" : "✗ Incorrect"}
                      </span>
                    )}
                  </div>
                  {detail && detail.explanation && (
                    <p style={{ fontSize: 13.3, color: "var(--text-2)" }}>{detail.explanation}</p>
                  )}
                </div>
              );
            })}

            {result && (
              <div className="card score-pill">
                <div className="num">
                  {result.score}/{result.total}
                </div>
                <p style={{ color: "var(--text-2)", fontSize: 14 }}>
                  {result.score === result.total
                    ? "Perfect — you've mastered this stretch of the course."
                    : "Review the red ones, click their sources, and rewatch that moment."}
                </p>
              </div>
            )}
          </>
        )}
      </div>

      <div className="panel-foot">
        <div className="row">
          {questions.length > 0 && !result && (
            <button className="btn success" style={{ flex: 1 }} disabled={!allPicked || busy} onClick={submit}>
              {busy && <span className="spinner" />}
              {allPicked ? "Submit answers" : `Pick an option for every question (${Object.keys(picked).length}/${questions.length})`}
            </button>
          )}
          <button className={`btn ${questions.length ? "secondary" : ""}`} onClick={generate} disabled={busy}>
            {questions.length ? "New quiz" : "Generate"}
          </button>
          {result && (
            <button
              className="btn secondary"
              onClick={() => {
                setQuestions([]);
                setResult(null);
                setPicked({});
              }}
            >
              Done
            </button>
          )}
        </div>
      </div>
    </>
  );
}
