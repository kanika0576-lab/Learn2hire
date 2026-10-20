"use client";

/** Guided onboarding: a friendly study buddy that walks the learner through
 *  creating a course, uploading material, building it, and starting to learn. */

import { useEffect, useRef, useState } from "react";
import { StudentFigure, TeacherFigure } from "./Classroom";

export type StepId = "welcome" | "course" | "upload" | "build" | "learn" | "done";

const SCRIPT: Record<Exclude<StepId, "done">, { who: "student" | "teacher"; label: string; text: string; mood: "happy" | "thinking" | "cheer" }> = {
  welcome: {
    who: "student",
    label: "Say hello",
    text: "Hey! I'm Bolt, your study buddy. Ready to turn a lecture into a real learning session?",
    mood: "cheer",
  },
  course: {
    who: "teacher",
    label: "Create your course",
    text: "First, give your course a name — something like “DSA — Lecture 3, Trees”.",
    mood: "happy",
  },
  upload: {
    who: "student",
    label: "Upload lecture + notes",
    text: "Now drop your lecture video and notes. MP4, WebM, MKV or AVIF all work — I'll convert anything the browser can't play. Captions are optional: I'll transcribe the audio myself.",
    mood: "happy",
  },
  build: {
    who: "teacher",
    label: "Build knowledge base",
    text: "Press “Build knowledge base”. I index every sentence with its timestamp and generate your revision notes.",
    mood: "happy",
  },
  learn: {
    who: "student",
    label: "Start learning",
    text: "Now open the course, pause anywhere and ask me a question. I'll only use what you've watched so far — no spoilers!",
    mood: "happy",
  },
};

const ORDER: Exclude<StepId, "done">[] = ["welcome", "course", "upload", "build", "learn"];

export default function OnboardingGuide({
  hasCourse,
  hasMaterials,
  isReady,
  onDismiss,
}: {
  hasCourse: boolean;
  hasMaterials: boolean;
  isReady: boolean;
  onDismiss: () => void;
}) {
  const [idx, setIdx] = useState(0);
  const [typing, setTyping] = useState("");
  const [touched, setTouched] = useState(false);
  const stepKey = ORDER[idx];
  const step = SCRIPT[stepKey];

  // The guide must always START at step 1, even when the account already has a built
  // course, and must only move forward when the learner actually performs that action
  // during this visit — never jump straight to the last step because data already exists.
  const prev = useRef({ hasCourse, hasMaterials, isReady });
  useEffect(() => {
    const was = prev.current;
    prev.current = { hasCourse, hasMaterials, isReady };
    if (touched) return;

    let next = idx;
    if (idx === 0 && hasCourse && !was.hasCourse) next = 1; // they just created a course
    else if (idx === 1 && hasMaterials && !was.hasMaterials) next = 2; // they just uploaded
    else if (idx === 2 && isReady && !was.isReady) next = 3; // build just finished
    if (next !== idx) setIdx(next);
  }, [hasCourse, hasMaterials, isReady, idx, touched]);

  // type out the current line for a chat-like feel
  useEffect(() => {
    setTyping("");
    if (!step) return;
    let i = 0;
    const text = step.text;
    const t = setInterval(() => {
      i += 3;
      setTyping(text.slice(0, i));
      if (i >= text.length) clearInterval(t);
    }, 18);
    return () => clearInterval(t);
  }, [step]);

  if (!step) return null;
  const isStudent = step.who === "student";

  return (
    <section className="onboard card">
      <div className="ob-fig">
        {isStudent ? (
          <StudentFigure size={86} mood={step.mood} />
        ) : (
          <TeacherFigure size={92} mood={step.mood === "cheer" ? "proud" : "teaching"} />
        )}
      </div>
      <div className="ob-body">
        <div className="ob-top">
          <span className="ob-name">{isStudent ? "Bolt (study buddy)" : "Prof. Lumi (tutor)"}</span>
          <span className="ob-step">
            Step {idx + 1} of {ORDER.length}
          </span>
        </div>
        <p className="ob-text">{typing}</p>

        {/* full checklist so every step is visible, not just the current one */}
        <ol className="ob-list">
          {ORDER.map((s, i) => {
            const state = i < idx ? "done" : i === idx ? "now" : "todo";
            return (
              <li key={s} className={`ob-item ${state}`} onClick={() => { setTouched(true); setIdx(i); }}>
                <span className="ob-mark">{state === "done" ? "✓" : i + 1}</span>
                <span className="ob-label">{SCRIPT[s].who === "student" ? "Bolt" : "Prof. Lumi"}: {SCRIPT[s].label}</span>
              </li>
            );
          })}
        </ol>

        <div className="ob-actions">
          {idx > 0 && (
            <button className="btn xs secondary" onClick={() => { setTouched(true); setIdx((i) => Math.max(0, i - 1)); }}>
              ← Back
            </button>
          )}
          {idx < ORDER.length - 1 && (
            <button className="btn xs" onClick={() => { setTouched(true); setIdx((i) => Math.min(ORDER.length - 1, i + 1)); }}>
              Next →
            </button>
          )}
          <button className="btn xs ghost" onClick={onDismiss}>
            Got it, hide guide
          </button>
        </div>
      </div>
    </section>
  );
}