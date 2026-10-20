"use client";

import { RobotInterviewer } from "@/components/Classroom";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import ChatPanel from "@/components/ChatPanel";
import InterviewPanel from "@/components/InterviewPanel";
import Mascot from "@/components/Mascot";
import Nav from "@/components/Nav";
import NotesPanel from "@/components/NotesPanel";
import QuizPanel from "@/components/QuizPanel";
import VideoPlayer, { PlayerHandle } from "@/components/VideoPlayer";
import { api, Course, fmtTime, getToken } from "@/lib/api";

type Tab = "ask" | "quiz" | "interview" | "notes";

export default function CoursePage() {
  const params = useParams<{ id: string }>();
  const courseId = params.id;
  const router = useRouter();
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("ask");
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [askBusy, setAskBusy] = useState(false);
  const [lectureEnded, setLectureEnded] = useState(false);
  const [interviewLaunch, setInterviewLaunch] = useState<{ mode: "live" | "text"; n: number } | null>(null);
  const [building, setBuilding] = useState(false);
  const playerRef = useRef<PlayerHandle>(null);

  const load = useCallback(async () => {
    try {
      const c = await api<Course>(`/courses/${courseId}`);
      setCourse(c);
      if (c.status === "ingesting") setTimeout(load, 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load course");
    }
  }, [courseId]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    const wanted = new URLSearchParams(window.location.search).get("tab");
    if (wanted === "notes" || wanted === "quiz" || wanted === "interview" || wanted === "ask") {
      setTab(wanted as Tab);
    }
    load();
  }, [load, router]);

  async function build() {
    setBuilding(true);
    try {
      await api(`/courses/${courseId}/ingest`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start build");
    } finally {
      setBuilding(false);
    }
  }

  function seek(t: number) {
    playerRef.current?.seek(t);
  }

  // Only offer the interview once the learner has genuinely watched the lecture:
  // a video that was never played (or never really played) must not pop the CTA.
  const watchedRef = useRef(0);
  const [interviewUnlocked, setInterviewUnlocked] = useState(false);

  function handleTimeChange(t: number) {
    setCurrentTime(t);
    if (t > watchedRef.current) watchedRef.current = t;
    if (watchedRef.current >= 5) setInterviewUnlocked(true);
  }

  function handleEnded() {
    const dur = playerRef.current?.duration?.() ?? 0;
    const watchedRatio = dur > 0 ? watchedRef.current / dur : 0;
    if (watchedRatio >= 0.9 || watchedRef.current >= 5) setLectureEnded(true);
  }

  function launchInterview(mode: "live" | "text") {
    setLectureEnded(false);
    setInterviewLaunch((prev) => ({ mode, n: (prev?.n ?? 0) + 1 }));
    setTab("interview");
  }

  const showMascot = tab !== "interview";
  const mascotMood = askBusy ? "thinking" : playing ? "studying" : "idle";
  const mascotMsg = askBusy
    ? "Hmm, thinking about your question…"
    : playing
    ? `Studying at ${fmtTime(currentTime)} — you've got this!`
    : "Paused? Ask me anything from here.";

  return (
    <>
      <Nav />
      <main className="container">
        <div className="page-head spread" style={{ flexWrap: "wrap", paddingBottom: 12 }}>
          <div>
            <div className="row" style={{ gap: 8 }}>
              <Link href="/dashboard" className="btn ghost sm">
                ← Courses
              </Link>
              <span className="badge grey">{course?.status === "ready" ? "Knowledge base ready" : course?.status}</span>
            </div>
            <h1 style={{ marginTop: 6 }}>{course?.title ?? "Loading…"}</h1>
          </div>
          <div className="row">
            <span className="meta">
              {course?.materials?.length ?? 0} material(s)
              {course?.chunks !== undefined ? ` · ${course.chunks} chunks` : ""}
            </span>
          </div>
        </div>

        {error && <div className="error-box" style={{ marginBottom: 14 }}>{error}</div>}

        {course && course.status === "ingesting" ? (
          <div className="card" style={{ padding: 34, textAlign: "center", marginBottom: 50 }}>
            <div style={{ fontSize: 44, marginBottom: 10 }}>⚙️</div>
            <h3 style={{ marginBottom: 6 }}>Building the knowledge base…</h3>
            <p style={{ color: "var(--text-2)", maxWidth: 560, margin: "0 auto" }}>
              Transcribing video, chunking documents with time/page tags, embedding and indexing. This page refreshes
              automatically.
            </p>
            <div className="progressbar" style={{ maxWidth: 420, margin: "18px auto 0" }}>
              <div style={{ width: "60%" }} />
            </div>
          </div>
        ) : course ? (
          <>
            {course.status !== "ready" && (
              <div className={`build-banner ${course.status === "error" ? "error" : ""}`}>
                <div className="bb-ico">{course.status === "error" ? "⚠️" : "📦"}</div>
                <div className="bb-text">
                  <strong>
                    {course.status === "error"
                      ? "Knowledge base couldn't be built"
                      : "Knowledge base not built yet"}
                  </strong>
                  <p>
                    {course.status === "error"
                      ? course.error ||
                        "Upload a transcript (.vtt/.srt/.txt) with the video, or a PDF/slides, then rebuild."
                      : "Build it to unlock the AI tutor, quiz and interviewer. You can still watch the video below."}
                  </p>
                </div>
                <div className="row" style={{ flexShrink: 0 }}>
                  <Link href="/dashboard" className="btn ghost sm">
                    Add files
                  </Link>
                  {course.materials.length > 0 && (
                    <button className="btn sm" onClick={build} disabled={building}>
                      {building && <span className="spinner" />}
                      Build knowledge base
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="workspace">
              <div className="stack" style={{ gap: 16 }}>
                <VideoPlayer
                  ref={playerRef}
                  course={course}
                  currentTime={currentTime}
                  onTimeChange={handleTimeChange}
                  onEnded={handleEnded}
                  overlay={
                    lectureEnded && interviewUnlocked && course.status === "ready" ? (
                      <div className="lecture-cta">
                        <div className="cta-card">
                          <RobotInterviewer state="idle" size={110} />
                          <h3>Lecture complete — nice work!</h3>
                          <p>Ready to prove what you learned? Your AI interviewer is standing by.</p>
                          <div className="mode-pick">
                            <button className="mode-card" onClick={() => launchInterview("live")}>
                              <span className="m-ico">🎥</span>
                              <strong>Live interview</strong>
                              <span>Camera + voice — the robot asks, you answer out loud.</span>
                            </button>
                            <button className="mode-card" onClick={() => launchInterview("text")}>
                              <span className="m-ico">⌨️</span>
                              <strong>Type answers</strong>
                              <span>Interview questions — think, then type your reply.</span>
                            </button>
                          </div>
                          <button className="btn ghost sm" onClick={() => setLectureEnded(false)}>
                            Not now — keep studying
                          </button>
                        </div>
                      </div>
                    ) : null
                  }
                />

                <div className="card" style={{ padding: "14px 18px" }}>
                  <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
                    <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                      <span className="meta" style={{ marginRight: 4 }}>
                        Sources in play:
                      </span>
                      {(course?.materials ?? [])
                        .filter((m) => m.kind !== "transcript")
                        .map((m) => (
                          <span key={m.id} className="badge grey">
                            {m.kind === "video" ? "🎬" : m.kind === "pdf" ? "📄" : "📊"} {m.filename}
                          </span>
                        ))}
                    </div>
                    {course.status === "ready" ? (
                      <span className="badge green">● Time-gated RAG active</span>
                    ) : (
                      <span className="badge amber">Build to activate the tutor</span>
                    )}
                  </div>
                </div>
              </div>

              <section className="panel">
                <div className="panel-head">
                  <div className="tabs">
                    <button className={`tab ${tab === "ask" ? "active" : ""}`} onClick={() => setTab("ask")}>
                      💬 Ask
                    </button>
                    <button className={`tab ${tab === "quiz" ? "active" : ""}`} onClick={() => setTab("quiz")}>
                      📝 Quiz
                    </button>
                    <button className={`tab ${tab === "interview" ? "active" : ""}`} onClick={() => setTab("interview")}>
                      🎤 Interview
                    </button>
                    <button className={`tab ${tab === "notes" ? "active" : ""}`} onClick={() => setTab("notes")}>
                      🗒️ Notes
                    </button>
                  </div>
                  <span className="badge purple">AI Tutor</span>
                </div>

                {course.status !== "ready" ? (
                  <div className="empty" style={{ padding: "38px 20px" }}>
                    <div style={{ fontSize: 38, marginBottom: 8 }}>🔒</div>
                    <strong>The AI tutor wakes up after the build</strong>
                    <p className="meta" style={{ marginTop: 6, maxWidth: 340 }}>
                      Watch the lecture below, or add a caption/transcript file from the dashboard and rebuild — then
                      ask, quiz and interview all light up.
                    </p>
                  </div>
                ) : (
                  <>
                    {tab === "ask" && (
                      <ChatPanel courseId={courseId} currentTime={currentTime} onSeek={seek} onBusyChange={setAskBusy} />
                    )}
                    {tab === "quiz" && <QuizPanel courseId={courseId} currentTime={currentTime} onSeek={seek} />}
                    {tab === "notes" && <NotesPanel courseId={courseId} />}
                    {tab === "interview" && (
                      <InterviewPanel
                        key={interviewLaunch?.n ?? 0}
                        courseId={courseId}
                        initialMode={interviewLaunch?.mode ?? null}
                      />
                    )}
                  </>
                )}
              </section>
            </div>
          </>
        ) : (
          <div className="empty" style={{ padding: 60 }}>
            <span className="spinner dark" />
          </div>
        )}
      </main>
      {showMascot && <Mascot mood={mascotMood} message={mascotMsg} />}
    </>
  );
}
