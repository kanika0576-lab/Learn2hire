"use client";

/** Cute, animated classroom characters used on the landing page and dashboard.
 *  Pure SVG, no assets: they bob, blink and react to hover. */

import { useEffect, useRef, useState } from "react";

export type TeacherMood = "teaching" | "thinking" | "proud";

export function TeacherFigure({ size = 150, mood = "teaching", animate = true }: {
  size?: number;
  mood?: TeacherMood;
  animate?: boolean;
}) {
  return (
    <svg width={size} height={size * 1.05} viewBox="0 0 160 168" role="img" aria-label="Teacher figure">
      <ellipse cx="80" cy="158" rx="42" ry="7" fill="rgba(59,91,219,.10)" />
      {/* board behind */}
      <rect x="18" y="14" width="124" height="76" rx="8" fill="#eaf0ff" stroke="#c9d6ff" strokeWidth="2" />
      <path d="M32 34h44M32 48h64M32 62h30" stroke="#9db4ff" strokeWidth="4" strokeLinecap="round" />
      {/* body */}
      <g className={animate ? "fig-bob" : undefined}>
        <path d="M80 92c-24 0-40 14-40 32v18h80v-18c0-18-16-32-40-32z" fill="#3b5bdb" />
        <path d="M66 118h28v24H66z" fill="#eef2ff" />
        {/* arms */}
        <path d="M42 112c-8 8-10 20-8 30" stroke="#3b5bdb" strokeWidth="11" strokeLinecap="round" fill="none" />
        <path d="M118 112c10 6 14 16 14 24" stroke="#3b5bdb" strokeWidth="11" strokeLinecap="round" fill="none" />
        {/* head */}
        <circle cx="80" cy="74" r="26" fill="#ffd9b8" />
        {/* hair */}
        <path d="M54 70c0-16 12-26 26-26s26 10 26 26c0-6-10-10-26-10S54 64 54 70z" fill="#3b2f2a" />
        {/* eyes */}
        <g className={animate ? "fig-blink" : undefined}>
          <circle cx="71" cy="76" r="3.4" fill="#22304a" />
          <circle cx="89" cy="76" r="3.4" fill="#22304a" />
        </g>
        {/* glasses */}
        <g stroke="#3b5bdb" strokeWidth="2" fill="none" opacity=".85">
          <circle cx="71" cy="76" r="8" />
          <circle cx="89" cy="76" r="8" />
          <path d="M79 76h2M63 74l-6-2M97 74l6-2" />
        </g>
        {/* mouth */}
        {mood === "thinking" ? (
          <path d="M74 90q6-4 12 0" stroke="#c2654a" strokeWidth="2.4" fill="none" strokeLinecap="round" />
        ) : mood === "proud" ? (
          <path d="M72 88q8 9 16 0" stroke="#c2654a" strokeWidth="2.6" fill="none" strokeLinecap="round" />
        ) : (
          <path d="M73 88q7 6 14 0" stroke="#c2654a" strokeWidth="2.6" fill="none" strokeLinecap="round" />
        )}
        {/* cheeks */}
        <circle cx="63" cy="85" r="4" fill="#ffb3a0" opacity=".55" />
        <circle cx="97" cy="85" r="4" fill="#ffb3a0" opacity=".55" />
      </g>
      {/* pointer stick */}
      <g className={animate ? "fig-wave" : undefined}>
        <path d="M132 136 L150 118" stroke="#f08c00" strokeWidth="4" strokeLinecap="round" />
        <circle cx="132" cy="136" r="4" fill="#f08c00" />
      </g>
    </svg>
  );
}

export function StudentFigure({ size = 120, mood = "happy", animate = true, hat = true }: {
  size?: number;
  mood?: "happy" | "thinking" | "cheer";
  animate?: boolean;
  hat?: boolean;
}) {
  return (
    <svg width={size} height={size * 1.05} viewBox="0 0 140 150" role="img" aria-label="Student figure">
      <ellipse cx="70" cy="142" rx="34" ry="6" fill="rgba(12,166,120,.12)" />
      <g className={animate ? "fig-bob" : undefined}>
        {/* backpack strap */}
        <path d="M52 84c-10 10-14 26-14 42" stroke="#0ca678" strokeWidth="8" strokeLinecap="round" fill="none" />
        {/* body */}
        <path d="M70 84c-20 0-34 12-34 28v16h68v-16c0-16-14-28-34-28z" fill="#0ca678" />
        {/* arms */}
        {mood === "cheer" ? (
          <>
            <path d="M36 100c-10-4-16-12-18-22" stroke="#0ca678" strokeWidth="10" strokeLinecap="round" fill="none" />
            <path d="M104 100c10-4 16-12 18-22" stroke="#0ca678" strokeWidth="10" strokeLinecap="round" fill="none" />
          </>
        ) : (
          <>
            <path d="M36 104c-6 8-8 16-8 24" stroke="#0ca678" strokeWidth="10" strokeLinecap="round" fill="none" />
            <path d="M104 104c6 8 8 16 8 24" stroke="#0ca678" strokeWidth="10" strokeLinecap="round" fill="none" />
          </>
        )}
        {/* head */}
        <circle cx="70" cy="62" r="24" fill="#ffd9b8" />
        <path d="M46 58c0-15 11-24 24-24s24 9 24 24c0-6-9-9-24-9s-24 3-24 9z" fill="#2f2a26" />
        {/* graduation cap */}
        {hat && (
          <g>
            <path d="M70 16 42 27l28 11 28-11z" fill="#3b5bdb" />
            <path d="M52 32v9c0 4 8 7 18 7s18-3 18-7v-9l-18 7z" fill="#2f4bc4" />
            <path d="M98 27v13" stroke="#f08c00" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="98" cy="41" r="3.4" fill="#f08c00" />
          </g>
        )}
        <g className={animate ? "fig-blink" : undefined}>
          <circle cx="61" cy="64" r="3.2" fill="#22304a" />
          <circle cx="79" cy="64" r="3.2" fill="#22304a" />
        </g>
        {mood === "thinking" ? (
          <path d="M64 78q6-4 12 0" stroke="#c2654a" strokeWidth="2.3" fill="none" strokeLinecap="round" />
        ) : (
          <path d="M63 76q7 7 14 0" stroke="#c2654a" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        )}
        <circle cx="54" cy="72" r="3.6" fill="#ffb3a0" opacity=".55" />
        <circle cx="86" cy="72" r="3.6" fill="#ffb3a0" opacity=".55" />
      </g>
    </svg>
  );
}

/** A rotating set of speech bubbles that rotate on a timer — makes the page feel alive. */
export function RotatingSpeech({ lines, interval = 3600 }: { lines: string[]; interval?: number }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (lines.length < 2) return;
    const t = setInterval(() => setI((v) => (v + 1) % lines.length), interval);
    return () => clearInterval(t);
  }, [lines.length, interval]);
  return (
    <div className="hero-bubble" key={i}>
      {lines[i]}
    </div>
  );
}

export function ClassroomScene() {
  const lines = [
    "Welcome! Upload your lecture and notes — I'll index them in seconds.",
    "Ask me anything at any timestamp. I only answer from what you've watched.",
    "Finished the lecture? Let's run a live mock interview. Camera on!",
  ];
  return (
    <div className="hero-scene">
      <div className="stage-floor" />
      <RotatingSpeech lines={lines} />
      <div className="hero-cast">
        <figure>
          <TeacherFigure size={128} mood="teaching" />
          <figcaption>Prof. Lumi — your AI tutor</figcaption>
        </figure>
        <figure>
          <StudentFigure size={104} mood="happy" />
          <figcaption>You — the learner</figcaption>
        </figure>
        <figure>
          <StudentFigure size={92} mood="cheer" hat={false} />
          <figcaption>Classmate bot</figcaption>
        </figure>
      </div>
    </div>
  );
}


/* ---------------- robot interviewer ---------------- */

export type RobotState = "idle" | "listening" | "thinking" | "speaking";


/**
 * The mock-interviewer robot. Pure inline SVG + CSS animations.
 */
export function RobotInterviewer({
  state = "idle",
  size = 150,
}: {
  state?: RobotState;
  size?: number;
}) {
  return (
    <div className={`robot robot-${state}`} style={{ width: size, height: size * 1.15 }} aria-hidden>
      <svg viewBox="0 0 140 160" width="100%" height="100%" role="img">
        {/* antenna */}
        <line x1="70" y1="18" x2="70" y2="34" stroke="#8b9bb8" strokeWidth="4" strokeLinecap="round" />
        <circle className="antenna-ball" cx="70" cy="13" r="7" fill="#4da3ff" />
        {(state === "listening" || state === "speaking") && (
          <circle className="antenna-pulse" cx="70" cy="13" r="7" fill="none" stroke="#4da3ff" strokeWidth="2" />
        )}
        {/* head */}
        <rect x="24" y="34" width="92" height="64" rx="20" fill="#dbe6f5" stroke="#b7c6de" strokeWidth="2.5" />
        {/* face screen */}
        <rect x="34" y="44" width="72" height="44" rx="13" fill="#16233a" />
        {/* eyes */}
        {state === "thinking" ? (
          <g fill="#7dd3fc">
            <rect x="48" y="58" width="14" height="4" rx="2" />
            <rect x="78" y="58" width="14" height="4" rx="2" />
          </g>
        ) : (
          <g className="robot-eyes" fill="#7dd3fc">
            <rect x="49" y="55" width="12" height="14" rx="5" />
            <rect x="79" y="55" width="12" height="14" rx="5" />
          </g>
        )}
        {/* mouth */}
        {state === "speaking" ? (
          <rect className="robot-mouth" x="57" y="76" width="26" height="6" rx="3" fill="#7dd3fc" />
        ) : (
          <rect x="60" y="77" width="20" height="5" rx="2.5" fill="#4b6284" />
        )}
        {/* ears */}
        <rect x="14" y="52" width="10" height="24" rx="5" fill="#b7c6de" />
        <rect x="116" y="52" width="10" height="24" rx="5" fill="#b7c6de" />
        {/* body */}
        <rect x="34" y="102" width="72" height="46" rx="16" fill="#eef3fa" stroke="#b7c6de" strokeWidth="2.5" />
        {/* chest screen */}
        <rect x="48" y="112" width="44" height="22" rx="8" fill="#16233a" />
        {state === "thinking" ? (
          <g className="chest-dots">
            <circle cx="60" cy="123" r="3" fill="#7dd3fc" />
            <circle cx="70" cy="123" r="3" fill="#7dd3fc" />
            <circle cx="80" cy="123" r="3" fill="#7dd3fc" />
          </g>
        ) : (
          <text x="70" y="127" textAnchor="middle" fontSize="11" fontWeight="700" fill="#7dd3fc">
            L2H
          </text>
        )}
        {/* arms */}
        <rect x="12" y="106" width="14" height="34" rx="7" fill="#b7c6de" className={state === "speaking" ? "arm-wave" : ""} />
        <rect x="114" y="106" width="14" height="34" rx="7" fill="#b7c6de" />
      </svg>
    </div>
  );
}
