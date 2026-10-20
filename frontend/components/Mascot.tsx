"use client";

export type MascotMood = "idle" | "studying" | "thinking" | "happy";

/**
 * Cute study-buddy student that sits in the corner of the screen.
 * Pure inline SVG + CSS animations (no image assets).
 */
export default function Mascot({
  mood = "idle",
  message,
  onDismiss,
}: {
  mood?: MascotMood;
  message?: string;
  onDismiss?: () => void;
}) {
  return (
    <div className={`mascot mood-${mood}`} aria-hidden>
      {onDismiss && (
        <button className="mascot-x" onClick={onDismiss} title="Hide study buddy" aria-label="Hide study buddy">
          ×
        </button>
      )}
      <div className="mascot-bubble">{message ?? defaultLine(mood)}</div>
      <div className="mascot-art">
        <MascotFigure mood={mood} />
      </div>
    </div>
  );
}

/** Inline (non-fixed) mascot art, for use inside pages/heroes. */
export function MascotFigure({ mood = "idle", size = 86 }: { mood?: MascotMood; size?: number }) {
  return (
    <svg viewBox="0 0 110 110" width={size} height={size} role="img">
      {/* body / hoodie */}
      <path d="M28 106 Q30 78 55 76 Q80 78 82 106 Z" fill="#5b7cfa" />
      <path d="M46 80 L55 92 L64 80" fill="#fff" opacity="0.9" />
      {/* head */}
      <circle cx="55" cy="52" r="27" fill="#ffe3c9" />
      {/* ears */}
      <circle cx="28.5" cy="53" r="4.5" fill="#ffd7b5" />
      <circle cx="81.5" cy="53" r="4.5" fill="#ffd7b5" />
      {/* hair fringe */}
      <path d="M30 46 Q34 30 55 28 Q76 30 80 46 Q72 38 55 38 Q38 38 30 46 Z" fill="#4a3728" />
      {/* grad cap */}
      <polygon points="55,14 96,28 55,42 14,28" fill="#2b3a67" />
      <rect x="49" y="10" width="12" height="8" rx="2" fill="#2b3a67" />
      <path d="M96 28 L96 46" stroke="#e8b339" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="96" cy="48" r="3" fill="#e8b339" />
      {/* blush */}
      <ellipse cx="40" cy="59" rx="5" ry="3" fill="#ffb3a0" opacity="0.75" />
      <ellipse cx="70" cy="59" rx="5" ry="3" fill="#ffb3a0" opacity="0.75" />
      {/* eyes */}
      {mood === "happy" ? (
        <g stroke="#3b2b1f" strokeWidth="2.4" strokeLinecap="round" fill="none">
          <path d="M40 51 Q44 47 48 51" />
          <path d="M62 51 Q66 47 70 51" />
        </g>
      ) : (
        <g>
          <circle cx="45" cy="51" r="3.4" fill="#3b2b1f" />
          <circle cx="66" cy="51" r="3.4" fill="#3b2b1f" />
          <circle cx="46.2" cy="49.8" r="1.1" fill="#fff" />
          <circle cx="67.2" cy="49.8" r="1.1" fill="#fff" />
        </g>
      )}
      {/* mouth */}
      {mood === "happy" ? (
        <path d="M46 63 Q55 71 64 63" stroke="#3b2b1f" strokeWidth="2.2" fill="none" strokeLinecap="round" />
      ) : (
        <path d="M48 63 Q55 68 62 63" stroke="#3b2b1f" strokeWidth="2.2" fill="none" strokeLinecap="round" />
      )}
      {/* open book */}
      {mood === "studying" && (
        <g>
          <path d="M18 96 L42 90 L42 106 L18 104 Z" fill="#fff" stroke="#c9d4ea" strokeWidth="1.5" />
          <path d="M92 96 L68 90 L68 106 L92 104 Z" fill="#fff" stroke="#c9d4ea" strokeWidth="1.5" />
          <path d="M42 90 L55 94 L68 90" fill="none" stroke="#c9d4ea" strokeWidth="1.5" />
        </g>
      )}
    </svg>
  );
}

function defaultLine(mood: MascotMood): string {
  if (mood === "thinking") return "Hmm, let me think…";
  if (mood === "happy") return "Nice one!";
  if (mood === "studying") return "You're studying — keep going!";
  return "I'm here if you get stuck!";
}
