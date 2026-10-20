"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Course, fmtTime, getToken } from "@/lib/api";

export type PlayerHandle = { seek: (t: number) => void; duration: () => number };

type Props = {
  course: Course;
  currentTime: number;
  onTimeChange: (t: number) => void;
  onEnded?: () => void;
  overlay?: React.ReactNode;
};

const VideoPlayer = forwardRef<PlayerHandle, Props>(function VideoPlayer(
  { course, currentTime, onTimeChange, onEnded, overlay },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [mediaError, setMediaError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const video = course.materials.find((m) => m.kind === "video");

  useImperativeHandle(ref, () => ({
    seek(t: number) {
      const el = videoRef.current;
      if (el) {
        el.currentTime = t;
        onTimeChange(t);
        el.play().catch(() => undefined);
      } else {
        onTimeChange(t);
      }
    },
    duration() {
      return videoRef.current?.duration ?? duration ?? 0;
    },
  }));

  function toggle() {
    const el = videoRef.current;
    if (!el) return;
    if (el.paused) {
      el.play().catch(() => undefined);
    } else {
      el.pause();
    }
  }

  function onSlide(v: number) {
    const el = videoRef.current;
    if (el) el.currentTime = v;
    onTimeChange(v);
  }

  /** Skip forward/back. Uses the live duration so "+10s" always moves the video on. */
  function skip(delta: number) {
    const el = videoRef.current;
    const dur = el?.duration ?? duration ?? 0;
    if (!el) return;
    const max = dur > 0 ? dur : Infinity;
    const target = Math.max(0, Math.min(el.currentTime + delta, max - 0.25));
    el.currentTime = target;
    onTimeChange(target);
    el.play().catch(() => undefined);
  }

  const token = getToken();
  // cache-bust so a previously cached 401 (old auth-less URL) can never stick around
  const src = video
    ? `/api/courses/${course.id}/materials/${video.id}/file?token=${encodeURIComponent(token ?? "")}&v=${reloadKey}`
    : null;

  function reload() {
    setMediaError("");
    setReloadKey((k) => k + 1);
    const el = videoRef.current;
    if (el) {
      el.load();
      el.play().catch(() => undefined);
    }
  }

  return (
    <section className="player-shell">
      <div className="player-stage">
        {src && !mediaError ? (
          <video
            key={reloadKey}
            ref={videoRef}
            src={src}
            playsInline
            preload="auto"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onTimeUpdate={(e) => onTimeChange(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
            onEnded={onEnded}
            onClick={toggle}
            onError={() =>
              setMediaError(
                video?.filename?.toLowerCase().endsWith(".mp4")
                  ? "This video could not be played in your browser."
                  : "This video file could not be decoded. Re-uploading it will convert it to MP4 automatically."
              )
            }
          />
        ) : src ? (
          <div className="player-placeholder">
            <div className="big">⚠️</div>
            <strong>{mediaError}</strong>
            <span style={{ fontSize: 13.5, maxWidth: 460 }}>
              The lecture file is stored correctly — try loading it again, or re-upload the video and we will convert
              it to a browser-friendly MP4 automatically.
            </span>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn sm" onClick={reload}>
                Retry playback
              </button>
              <a className="btn sm secondary" href={src} target="_blank" rel="noreferrer">
                Open file directly
              </a>
            </div>
          </div>
        ) : (
          <div className="player-placeholder">
            <div className="big">🎞️</div>
            <strong>No video uploaded for this course</strong>
            <span style={{ fontSize: 13.5, maxWidth: 460 }}>
              Use the timeline to set the moment you&apos;ve “watched up to” — the tutor gates its answers to that
              time. Upload a video to make it a real player.
            </span>
          </div>
        )}
        {overlay}
      </div>

      <div className="player-controls">
        <input
          className="seek"
          type="range"
          min={0}
          max={Math.max(duration, 1)}
          step={0.1}
          value={Math.min(currentTime, duration || 0)}
          onChange={(e) => onSlide(parseFloat(e.target.value))}
          aria-label="Seek"
        />
        <div className="spread">
          <div className="row">
            <button className="play-btn" onClick={toggle} disabled={!src} title={playing ? "Pause" : "Play"}>
              {playing ? "❚❚" : "▶"}
            </button>
            <button
              className="skip-btn"
              onClick={() => skip(-10)}
              disabled={!src}
              title="Back 10 seconds"
              aria-label="Back 10 seconds"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M11 19 2 12l9-7v7h1a8 8 0 1 1-5 13h2a6 6 0 1 0 3-11h-1z" />
              </svg>
              <span>10</span>
            </button>
            <button
              className="skip-btn"
              onClick={() => skip(10)}
              disabled={!src}
              title="Forward 10 seconds"
              aria-label="Forward 10 seconds"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M13 19 22 12 13 5v7h-1a8 8 0 1 0 5 13h-2a6 6 0 1 1-3-11h1z" />
              </svg>
              <span>10</span>
            </button>
            <span className="time">
              {fmtTime(currentTime)} / {fmtTime(duration)}
            </span>
            {src && (
              <select
                className="input sm"
                style={{ width: 74, padding: "5px 7px", fontSize: 13 }}
                value={rate}
                onChange={(e) => {
                  const r = parseFloat(e.target.value);
                  setRate(r);
                  if (videoRef.current) videoRef.current.playbackRate = r;
                }}
                aria-label="Playback speed"
              >
                {[0.75, 1, 1.25, 1.5, 2].map((r) => (
                  <option key={r} value={r}>
                    {r}×
                  </option>
                ))}
              </select>
            )}
          </div>
          <span className="now-asking" title="Questions are gated to content at or before this time">
            🕒 Asking at {fmtTime(currentTime)}
          </span>
        </div>
      </div>
    </section>
  );
});

export default VideoPlayer;
