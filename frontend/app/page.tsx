"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ClassroomScene } from "@/components/Classroom";
import { getUser } from "@/lib/api";

const STEPS = [
  {
    n: "1",
    title: "Create your course",
    body: "Name it, then drop the lecture video (mp4/webm/mkv/avif) together with your notes, PDF or slides. We auto-convert any download into a browser-friendly MP4.",
  },
  {
    n: "2",
    title: "We index everything",
    body: "Speech-to-text turns the audio into timestamped segments (or use your own captions). Every line is chunked, embedded and tagged with its video time or PDF page.",
  },
  {
    n: "3",
    title: "Watch, pause, ask",
    body: "Ask a question at any moment. Answers are built only from what you've already reached, with clickable sources that seek the player to that exact second.",
  },
  {
    n: "4",
    title: "Practise, then interview",
    body: "Generate a quiz from the material, then finish with a proctored mock interview — camera on, robot voice in, spoken answers out, with an explainable scorecard.",
  },
];

const FEATURES = [
  {
    emoji: "🕒",
    title: "Time-gated tutor",
    body: "No spoilers. Ask at 0:30 about a topic taught at 5:00 and it says 'covered later' instead of leaking the answer.",
  },
  {
    emoji: "🎧",
    title: "Speech-to-text built in",
    body: "Uploaded a video without captions? We transcribe the audio into timestamped segments automatically.",
  },
  {
    emoji: "📝",
    title: "Revision notes",
    body: "After building, get a summary, key points with timestamps, exam-style questions and terms to memorise.",
  },
  {
    emoji: "🎥",
    title: "Live mock interview",
    body: "A robot interviewer speaks the questions and listens to your spoken answers. Camera stays on the whole time.",
  },
  {
    emoji: "🛡️",
    title: "Proctored session",
    body: "Fullscreen is locked and tab-switching, copy/paste and right-click are disabled — and logged — while you answer.",
  },
  {
    emoji: "📚",
    title: "Honest answers",
    body: "If it isn't in your material, it says so. Every claim carries a source you can click to verify.",
  },
];

const FAQ = [
  {
    q: "Do I need captions for my video?",
    a: "No. Drop the video alone and we transcribe the audio. If you'd rather be precise, upload the .vtt/.srt that comes with a YouTube download and we'll use that instead.",
  },
  {
    q: "Which video formats work?",
    a: "MP4 and WebM play directly. MKV, AVI, MOV and AVIF downloads are converted to MP4 automatically while the knowledge base is built.",
  },
  {
    q: "Does the interview use my camera and mic?",
    a: "Yes — in live mode your camera stays on, the interviewer speaks each question out loud, and it transcribes what you say. No typing is possible in that mode.",
  },
  {
    q: "What happens if I switch tabs?",
    a: "The proctoring layer records it as an integrity flag and shows the count in the session banner.",
  },
];

export default function Home() {
  const [user, setUser] = useState<{ name: string } | null>(null);

  // reflect the signed-in account in the nav (no "Log in" once you're in)
  useEffect(() => {
    setUser(getUser());
  }, []);

  return (
    <main>
      {/* ---------- nav ---------- */}
      <header className="lp-nav">
        <div className="container spread">
          <Link href="/" className="lp-brand">
            <span className="lp-logo">L2H</span>
            <span>Learn2Hire</span>
          </Link>
          <nav className="lp-links">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#upload">Upload</a>
            <a href="#faq">FAQ</a>
            {user ? (
              <>
                <span className="lp-user">Hi, {user.name?.split(" ")[0]}</span>
                <Link href="/dashboard" className="btn sm secondary">
                  My courses
                </Link>
                <Link href="/dashboard" className="btn sm">
                  Dashboard
                </Link>
              </>
            ) : (
              <>
                <Link href="/login" className="btn sm secondary">
                  Log in
                </Link>
                <Link href="/register" className="btn sm">
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* ---------- hero ---------- */}
      <section className="lp-hero">
        <div className="container lp-hero-grid">
          <div>
            <span className="badge green">AHGV BuildVerse 2026 · Industry PS 1</span>
            <h1 className="lp-h1">
              Your lecture, <span className="grad-text">explained at the right second</span>.
            </h1>
            <p className="lp-lede">
              Learn2Hire turns any recorded lecture into a timestamp-aware tutor and a proctored mock
              interviewer. Pause anywhere, ask a question, and get an answer built only from what you
              have already watched — then finish the lecture with a real interview, camera on.
            </p>
            <div className="row" style={{ flexWrap: "wrap", gap: 12, marginTop: 22 }}>
              <Link href={user ? "/dashboard" : "/register"} className="btn">
                {user ? "Upload your lecture →" : "Start learning free"}
              </Link>
              <Link href={user ? "/dashboard" : "/login"} className="btn secondary">
                {user ? "My courses" : "Try the demo course"}
              </Link>
            </div>
            <div className="lp-trust">
              <span>Works with MP4, WebM, MKV &amp; AVIF</span>
              <span>·</span>
              <span>Auto speech-to-text</span>
              <span>·</span>
              <span>No spoilers, ever</span>
            </div>
          </div>
          <div>
            <ClassroomScene />
          </div>
        </div>
      </section>

      {/* ---------- stats ---------- */}
      <section className="container">
        <div className="lp-stats">
          <div>
            <strong>100%</strong>
            <span>answers cited to a timestamp</span>
          </div>
          <div>
            <strong>&lt; 3s</strong>
            <span>to index a lecture</span>
          </div>
          <div>
            <strong>6 turns</strong>
            <span>adaptive interview questions</span>
          </div>
          <div>
            <strong>0</strong>
            <span>spoons before you watch</span>
          </div>
        </div>
      </section>

      {/* ---------- how it works ---------- */}
      <section id="how" className="lp-section">
        <div className="container">
          <h2 className="lp-h2">How it works</h2>
          <p className="lp-sub">Four steps from a raw video file to a job-ready interview loop.</p>
          <div className="lp-steps">
            {STEPS.map((s) => (
              <div key={s.n} className="step-card">
                <div className="step-num">{s.n}</div>
                <h3>{s.title}</h3>
                <p className="lp-body">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- features ---------- */}
      <section id="features" className="lp-section lp-alt">
        <div className="container">
          <h2 className="lp-h2">What you get</h2>
          <p className="lp-sub">
            Built for the moment after a lecture ends: consolidate, then prove it out loud.
          </p>
          <div className="lp-feature-grid">
            {FEATURES.map((f) => (
              <div key={f.title} className="step-card">
                <div className="feat-emoji">{f.emoji}</div>
                <h3>{f.title}</h3>
                <p className="lp-body">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- bring your own lecture ---------- */}
      <section id="upload" className="lp-section">
        <div className="container">
          <h2 className="lp-h2">Bring your own lecture</h2>
          <p className="lp-sub">
            Drop a recording straight from your downloads folder. We convert whatever the browser
            can&apos;t play, and transcribe the audio if you didn&apos;t grab captions.
          </p>
          <div className="byo">
            <div className="byo-box">
              <h3>Accepted files</h3>
              <div className="fmt-chips">
                <span>MP4</span>
                <span>WEBM</span>
                <span>MKV</span>
                <span>MOV</span>
                <span>GIF</span>
                <span>AVIF</span>
                <span>VTT / SRT</span>
                <span>PDF</span>
                <span>PPTX</span>
                <span>TXT</span>
              </div>
              <p className="lp-body" style={{ marginTop: 12 }}>
                MKV, MOV and AVIF downloads are converted to a browser-friendly MP4 automatically. Captions
                are <strong>optional</strong> — with no caption file we run speech-to-text on the audio and
                build the same timestamped index.
              </p>
            </div>
            <div className="byo-box">
              <h3>How to get a file you can use</h3>
              <ol className="byo-steps">
                <li>Open the lecture in YouTube and copy the video URL.</li>
                <li>
                  Run <code>yt-dlp -f best -o lecture.mp4 &lt;url&gt;</code> — you get a real{" "}
                  <code>.mp4</code> with audio.
                </li>
                <li>Optionally add <code>--write-auto-sub</code> to also save the caption file.</li>
                <li>Upload both files on the dashboard and press <strong>Build knowledge base</strong>.</li>
              </ol>
              <p className="lp-body" style={{ marginTop: 12 }}>
                Note: <code>.avif</code> files are still <em>images</em>, not videos. If a download is 1 second
                long it&apos;s a thumbnail — grab the actual <code>.mp4</code> instead.
              </p>
            </div>
          </div>
          <div className="row" style={{ justifyContent: "center", marginTop: 22 }}>
            <Link href={user ? "/dashboard" : "/register"} className="btn">
              {user ? "Go to dashboard and upload" : "Create an account to upload"}
            </Link>
          </div>
        </div>
      </section>

      {/* ---------- faq ---------- */}
      <section id="faq" className="lp-section lp-alt">
        <div className="container lp-faq">
          <h2 className="lp-h2">Questions people ask</h2>
          {FAQ.map((f) => (
            <details key={f.q} className="faq-item">
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ---------- cta ---------- */}
      <section className="container lp-cta-wrap">
        <div className="lp-cta">
          <h2>Ready to learn from your own lectures?</h2>
          <p>Create an account, upload one video, and ask your first question in under a minute.</p>
          <div className="row" style={{ justifyContent: "center", flexWrap: "wrap", gap: 12 }}>
            <Link href="/register" className="btn">
              Create free account
            </Link>
            <Link href="/login" className="btn secondary">
              Demo login
            </Link>
          </div>
        </div>
      </section>

      <footer className="lp-footer">
        <div className="container spread">
          <span>Learn2Hire — Team codeflux</span>
          <span>Kanika (frontend/UI) · Rakshit Thareja (backend/AI)</span>
        </div>
      </footer>
    </main>
  );
}