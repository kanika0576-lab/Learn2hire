"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Mascot from "@/components/Mascot";
import Nav from "@/components/Nav";
import OnboardingGuide from "@/components/OnboardingGuide";
import { api, Course, getToken, getUser } from "@/lib/api";

const KIND_ICON: Record<string, string> = {
  video: "🎬",
  pdf: "📄",
  slides: "📊",
  transcript: "📝",
};

// The study buddy walks the learner through the whole loop; it changes tone with progress.
const GUIDE_LINES = [
  "Welcome! I'm Bolt — your study buddy. Let's set up your first course together.",
  "Nice, the course exists! Now drop your lecture video and any notes, PDF or slides into the card below.",
  "Everything's uploaded. Hit “Build knowledge base” and I'll index every sentence with its timestamp.",
  "Knowledge base ready! Open the course, pause anywhere and ask me a question — no spoilers.",
  "You're all set. When the lecture ends, I'll pop up as a robot interviewer for the live session. Good luck!",
];

function guideLineFor(courses: Course[]): number {
  if (courses.length === 0) return 0;
  const hasMaterials = courses.some((c) => c.materials.length > 0);
  if (!hasMaterials) return 1;
  const building = courses.some((c) => c.status === "ingesting");
  const anyReady = courses.some((c) => c.status === "ready");
  if (building) return 2;
  if (anyReady) return 3;
  return 2;
}

export default function Dashboard() {
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [uploadFor, setUploadFor] = useState<string | null>(null);
  const [dropIntoId, setDropIntoId] = useState<string>("");
const [drag, setDrag] = useState(false);
const [dragOver, setDragOver] = useState(false);
const [busyCourse, setBusyCourse] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState(true);
  const [typedGuide, setTypedGuide] = useState("");
  const [seenBefore, setSeenBefore] = useState(false);
  // Bolt always starts from the beginning of the story, then follows what you actually do.
  const guideIdx = seenBefore ? guideLineFor(courses) : 0;
  const guideText = GUIDE_LINES[guideIdx] ?? GUIDE_LINES[0];

  useEffect(() => {
    const t = setTimeout(() => setSeenBefore(true), 1500);
    return () => clearTimeout(t);
  }, []);

  // auto-type the buddy's message like a chat bubble
  useEffect(() => {
    setTypedGuide("");
    let i = 0;
    const t = setInterval(() => {
      i += 2;
      setTypedGuide(guideText.slice(0, i));
      if (i >= guideText.length) clearInterval(t);
    }, 20);
    return () => clearInterval(t);
  }, [guideText]);
  const fileRef = useRef<HTMLInputElement>(null);
  const quRef = useRef<HTMLInputElement>(null);
  const coursesRef = useRef<Course[]>([]);
  const dropIntoRef = useRef("");
  coursesRef.current = courses;
  dropIntoRef.current = dropIntoId;
  // Drag depth counter: dragLeave fires when moving over children, so a boolean
// flickers and the drop silently never registers. A counter tracks "are we still
// inside this drop target?" and only clears when it truly exits.
const dragDepth = useRef<Record<string, number>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await api<Course[]>("/courses");
      setCourses(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load courses");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    load();
  }, [load, router]);

  useEffect(() => {
    const anyIngesting = courses.some((c) => c.status === "ingesting");
    if (anyIngesting && !pollRef.current) {
      pollRef.current = setInterval(load, 2500);
    } else if (!anyIngesting && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current && !anyIngesting) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [courses, load]);

  async function createCourse(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      const course = await api<Course>("/courses", { method: "POST", body: JSON.stringify({ title, description }) });
      setTitle("");
      setDescription("");
      setDropIntoId(course.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create course");
    } finally {
      setCreating(false);
    }
  }

  const enterDrag = (id: string) => {
    dragDepth.current[id] = (dragDepth.current[id] ?? 0) + 1;
    if (id === "quick") setDragOver(true);
    else setDrag(true);
  };

  const leaveDrag = (id: string) => {
    dragDepth.current[id] = Math.max(0, (dragDepth.current[id] ?? 1) - 1);
    if (dragDepth.current[id] === 0) {
      if (id === "quick") setDragOver(false);
      else setDrag(false);
    }
  };

  function resolveDropCourse(): string | "new" {
    const list = coursesRef.current;
    const chosen = dropIntoRef.current;
    if (chosen === "new") return "new";
    if (chosen && list.some((c) => c.id === chosen)) return chosen;
    const empty = list.filter((c) => c.status === "created" || c.materials.length === 0);
    if (empty.length) return empty[0].id;
    if (list.length === 1) return list[0].id;
    return "new";
  }

  // Drop files anywhere on this dashboard — one helper covers every target.
  const receive = (id: string, files: FileList | File[], courseId?: string) => {
    dragDepth.current[id] = 0;
    if (id === "quick") setDragOver(false);
    else setDrag(false);
    if (courseId && files.length) {
      uploadFiles(courseId, files);
    } else if (files.length) {
      attachOrCreate(files);
    }
  };

  async function uploadFiles(courseId: string, files: FileList | File[]) {
    setBusyCourse(courseId);
    setError("");
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await api<Course>(`/courses/${courseId}/materials`, { method: "POST", body: form });
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusyCourse(null);
      setUploadFor(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  useEffect(() => {
    const onDragOver = (e: DragEvent) => {
      e.preventDefault();
      setDragOver(true);
    };
    const onDrop = (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const files = e.dataTransfer?.files;
      if (!files?.length) return;
      const card = (e.target as HTMLElement | null)?.closest?.("[data-course-id]");
      const cardId = card?.getAttribute("data-course-id");
      if (cardId) {
        uploadFiles(cardId, files);
        return;
      }
      attachOrCreate(files);
    };
    const onDragLeave = (e: DragEvent) => {
      if (!e.relatedTarget) setDragOver(false);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    window.addEventListener("dragleave", onDragLeave);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("dragleave", onDragLeave);
    };
  }, []);

  // ---------------- upload actions ----------------

  /** Put files on the course you named, or only create a new one when none exists. */
  async function attachOrCreate(files: FileList | File[]) {
    const target = resolveDropCourse();
    if (target !== "new") {
      await uploadFiles(target, files);
      return;
    }
    await quickUpload(files);
  }

  /** One-shot flow: create a course named after the file, upload everything, build it. */
  async function quickUpload(files: FileList | File[]) {
    const list = Array.from(files);
    if (!list.length) return;
    setBusyCourse("quick");
    setError("");
    try {
      const video = list.find((f) => /\.(mp4|mov|mkv|webm|m4v|avi|avif|flv|ts|gif|webp|3gp)$/i.test(f.name));
      const name = (video ?? list[0]).name.replace(/\.[^.]+$/, "").slice(0, 70);
      const course = await api<Course>("/courses", {
        method: "POST",
        body: JSON.stringify({ title: name || "My lecture", description: "" }),
      });
      for (const file of list) {
        const form = new FormData();
        form.append("file", file);
        await api<Course>(`/courses/${course.id}/materials`, { method: "POST", body: form });
      }
      await api(`/courses/${course.id}/ingest`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusyCourse(null);
      if (quRef.current) quRef.current.value = "";
    }
  }

  async function ingest(courseId: string) {
    setBusyCourse(courseId);
    setError("");
    try {
      await api(`/courses/${courseId}/ingest`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start ingestion");
    } finally {
      setBusyCourse(null);
    }
  }

  async function remove(courseId: string) {
    setConfirmDelete(null);
    try {
      await api(`/courses/${courseId}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const user = getUser();

  return (
    <>
      <Nav />
      <main className="container">
        <div className="page-head spread" style={{ flexWrap: "wrap" }}>
          <div>
            <h1>Hello, {user?.name?.split(" ")[0] ?? "learner"} 👋</h1>
            <p>Upload course material, build the knowledge base, then learn and practice.</p>
          </div>
        </div>

        {error && <div className="error-box" style={{ marginBottom: 16 }}>{error}</div>}

{/* dropping ANYWHERE on this page uploads — files or a whole zip */}
      {dragOver && (
        <div className="drop-veil">
          <div className="drop-veil-box">
            <div className="big">📦</div>
            <strong>Drop it here</strong>
            <p>
              Videos, captions, notes, PDF — or one ZIP with everything inside.
            </p>
            <div className="fmt-chips">
              <span>MP4</span>
              <span>WEBM</span>
              <span>MKV</span>
              <span>VTT / SRT</span>
              <span>PDF</span>
              <span>ZIP</span>
            </div>
          </div>
        </div>
      )}

      {guideOpen && (
        <OnboardingGuide
            hasCourse={courses.length > 0}
            hasMaterials={courses.some((c) => c.materials.length > 0)}
            isReady={courses.some((c) => c.status === "ready")}
            onDismiss={() => setGuideOpen(false)}
          />
        )}

        {/* buddy speech bubble — the corner mascot talks through the same steps */}
        <div className="buddy-bar">
          <span className="buddy-label">Bolt</span>
          <p className="buddy-msg">
            {typedGuide}
            <span className="caret" />
          </p>
          {guideIdx === 3 && (
            <Link href={`/course/${courses.find((c) => c.status === "ready")?.id}`} className="btn xs">
              Open course →
            </Link>
          )}
        </div>

        <div className="card" style={{ padding: 22, marginBottom: 26 }}>
          <h3 style={{ marginBottom: 14, fontSize: 16.5 }}>New course</h3>
          <form className="stack" onSubmit={createCourse}>
            <div className="row" style={{ gap: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
              <div className="field" style={{ flex: 1, minWidth: 220 }}>
                <label htmlFor="ctitle">Title</label>
                <input
                  id="ctitle"
                  className="input"
                  required
                  minLength={2}
                  placeholder="Intro to DSA — Lecture 1"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div className="field" style={{ flex: 2, minWidth: 260 }}>
                <label htmlFor="cdesc">Description (optional)</label>
                <input
                  id="cdesc"
                  className="input"
                  placeholder="What is this course about?"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              <button className="btn" disabled={creating} type="submit">
                {creating && <span className="spinner" />}
                Create course
              </button>
            </div>
            {courses.length > 0 && (
              <p className="meta" style={{ marginTop: 10 }}>
                Drops go into{" "}
                <select
                  className="input sm"
                  style={{ width: "auto", display: "inline-block", padding: "4px 8px" }}
                  value={dropIntoId}
                  onChange={(e) => setDropIntoId(e.target.value)}
                  aria-label="Course that receives dropped files"
                >
                  <option value="">the last course you created (or a new one)</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                  <option value="new">a brand-new course named after the file</option>
                </select>
              </p>
            )}
          </form>
        </div>

        <div
          className={`quick-upload card ${dragOver ? "drag" : ""}`}
          onDragOver={(e) => { e.preventDefault(); enterDrag("quick"); }}
          onDragLeave={() => leaveDrag("quick")}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            receive("quick", e.dataTransfer.files);
          }}
        >
          <div className="qu-copy">
            <strong>🎬 Add your own lecture</strong>
            <p>
              Drag a recording here. If you already created a course, files go into that course — we convert
              odd YouTube downloads (mkv/webm/avif) to MP4 and generate captions if you have none.
            </p>
            <div className="fmt-chips">
              <span>MP4</span>
              <span>WEBM</span>
              <span>MKV</span>
              <span>MOV</span>
              <span>GIF</span>
              <span>VTT / SRT</span>
              <span>PDF</span>
            </div>
          </div>
          <button className="btn" onClick={() => quRef.current?.click()} disabled={busyCourse === "quick"}>
            {busyCourse === "quick" ? "Uploading…" : "Choose files"}
          </button>
          <input
            ref={quRef}
            type="file"
            multiple
            hidden
            accept=".mp4,.mov,.mkv,.webm,.m4v,.avi,.avif,.flv,.ts,.mts,.m2ts,.3gp,.gif,.webp,.zip,.pdf,.pptx,.ppt,.vtt,.srt,.txt"
            onChange={(e) => e.target.files && attachOrCreate(e.target.files)}
          />
        </div>

        {!loaded ? (
          <div className="empty">
            <span className="spinner dark" />
          </div>
        ) : courses.length === 0 ? (
          <div className="card empty" style={{ marginBottom: 50 }}>
            <div className="big">📚</div>
            <strong>No courses yet</strong>
            <p style={{ marginTop: 4 }}>Create a course above, then upload a video, its transcript, PDF or slides.</p>
          </div>
        ) : (
          <div className="course-grid">
            {courses.map((c) => (
              <article key={c.id} className="card course-card" data-course-id={c.id}>
                <div className="spread">
                  <h3>{c.title}</h3>
                  <StatusBadge status={c.status} />
                </div>
                {c.description && <p style={{ fontSize: 13.8, color: "var(--text-2)" }}>{c.description}</p>}

                <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                  {c.materials.map((m) => (
                    <span key={m.id} className="badge grey" title={`${m.filename} — ${m.status}`}>
                      {KIND_ICON[m.kind] ?? "📎"} {m.filename.length > 22 ? m.filename.slice(0, 20) + "…" : m.filename}
                    </span>
                  ))}
                  {c.materials.length === 0 && <span className="meta">No materials yet</span>}
                </div>

                {c.status === "ingesting" && (
                  <div>
                    <div className="progressbar"><div style={{ width: "55%" }} /></div>
                    <p className="meta" style={{ marginTop: 5 }}>
                      Transcribing, chunking &amp; indexing…
                    </p>
                  </div>
                )}
                {c.status === "error" && c.error && (
                  <div className="course-error">
                    <span className="ce-ico">⚠️</span>
                    <span className="ce-text">{c.error}</span>
                    <button
                      className="btn xs"
                      disabled={busyCourse === c.id}
                      onClick={() => ingest(c.id)}
                    >
                      {busyCourse === c.id ? "Retrying…" : "Retry build"}
                    </button>
                  </div>
                )}
                {c.status === "ready" && (
                  <p className="meta">
                    ✅ Knowledge base ready — {c.chunks ?? "—"} chunks indexed
                  </p>
                )}

                <div className="spread" style={{ marginTop: "auto" }}>
                  <div className="row">
                    <button className="btn secondary sm" onClick={() => setUploadFor(uploadFor === c.id ? null : c.id)}>
                      ＋ Upload
                    </button>
                    <button
                      className="btn sm"
                      disabled={!c.materials.length || c.status === "ingesting" || busyCourse === c.id}
                      onClick={() => ingest(c.id)}
                    >
                      {c.status === "ingesting" ? "Building…" : "Build knowledge base"}
                    </button>
                  </div>
                  <div className="row" style={{ justifyContent: "space-between", width: "100%" }}>
                    <div className="row" style={{ gap: 8 }}>
                      <Link href={`/course/${c.id}`} className="btn success sm">
                        Open →
                      </Link>
                      {c.status === "ready" && (
                        <Link href={`/course/${c.id}?tab=notes`} className="btn sm secondary" title="Revision notes">
                          🗒️ Notes
                        </Link>
                      )}
                    </div>
                    {confirmDelete === c.id ? (
                      <span className="inline-confirm danger">
                        Sure?
                        <button className="btn xs danger" onClick={() => remove(c.id)}>
                          Yes, delete
                        </button>
                        <button className="btn xs ghost" onClick={() => setConfirmDelete(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        className="btn sm danger-ghost"
                        title="Delete course"
                        aria-label={`Delete ${c.title}`}
                        onClick={() => setConfirmDelete(c.id)}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M3 6h18" />
                          <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                          <path d="M10 11v6" />
                          <path d="M14 11v6" />
                        </svg>
                        Delete
                      </button>
                    )}
                  </div>
                </div>

                {uploadFor === c.id && (
                  <div
                    className={`dropzone ${drag ? "drag" : ""}`}
                    onClick={() => fileRef.current?.click()}
                    onDragOver={(e) => { e.preventDefault(); enterDrag(c.id); }}
                    onDragLeave={() => leaveDrag(c.id)}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      receive(c.id, e.dataTransfer.files, c.id);
                    }}
                  >
                    <strong>Drop files here</strong> or click to browse
                    <div className="fmt-chips">
                      <span>MP4</span>
                      <span>WEBM</span>
                      <span>MKV (auto-converted)</span>
                      <span>AVIF (auto-converted)</span>
                      <span>VTT / SRT captions</span>
                      <span>PDF</span>
                      <span>PPTX</span>
                    </div>
                    <div className="yt-tip">
                      YouTube download? Drop the <strong>video + its .vtt caption file</strong> together (yt-dlp saves
                      one next to the video, e.g. <code>video.en.vtt</code>) — mp4, webm, mkv and avif all work.
                      {busyCourse === c.id && " — uploading…"}
                    </div>
                    <input
                      ref={fileRef}
                      type="file"
                      multiple
                      hidden
                      accept=".mp4,.mov,.mkv,.webm,.m4v,.avi,.avif,.flv,.ts,.mts,.m2ts,.3gp,.gif,.webp,.zip,.pdf,.pptx,.ppt,.vtt,.srt,.txt"
                      onChange={(e) => e.target.files && uploadFiles(c.id, e.target.files)}
                    />
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </main>
      <Mascot mood="idle" message={`Ready when you are${user?.name ? ", " + user.name.split(" ")[0] : ""}! Drop a lecture to get started.`} />
      <div style={{ height: 40 }} />
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ready") return <span className="badge green">Ready</span>;
  if (status === "ingesting") return <span className="badge amber">Building…</span>;
  if (status === "error") return <span className="badge red">Error</span>;
  return <span className="badge grey">Draft</span>;
}
