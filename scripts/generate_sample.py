"""Generate the sample course assets into learn2hire/sample/:
  lecture1.vtt  — timestamped transcript (the source of truth for time-gating)
  notes.pdf     — companion course notes (multi-page)
  lecture1.mp4  — 1280x720 slideshow rendered with ffmpeg, synced to the VTT cues

Run from anywhere:  python scripts/generate_sample.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")
SAMPLE = os.path.join(ROOT, "sample")
sys.path.insert(0, BACKEND)

from tests.smoke import VTT, make_pdf  # noqa: E402
from app.services.transcription import parse_transcript_bytes  # noqa: E402

FONT_DIR = r"C:\Windows\Fonts"
RESOLUTION = "1280x720"
FG = "0x16233a"
MUTED = "0x5b6b85"
ACCENT = "0x3b5bdb"
SLIDE_BG = "0xf6f8fb"

NOTES_PAGES = [
    "Course Notes - Arrays and Linked Lists\n"
    "\n"
    "An array stores elements in contiguous memory.\n"
    "Index access is O(1): the address of element i is base + i * size.\n"
    "\n"
    "A linked list stores nodes with a value and a pointer to the next node.\n"
    "Insertion at the head is O(1), but there is no random access - reaching\n"
    "element i costs O(i).\n"
    "\n"
    "Choose arrays when you read by index often; choose linked lists when you\n"
    "insert or delete at known positions frequently.",
    "Course Notes - Stacks, Queues and Hash Maps\n"
    "\n"
    "A stack is LIFO: push adds to the top, pop removes from the top.\n"
    "Typical uses: undo history, expression evaluation, DFS.\n"
    "\n"
    "A queue is FIFO: enqueue adds at the rear, dequeue removes from the front.\n"
    "Typical uses: task scheduling, BFS, buffering.\n"
    "\n"
    "A hash map hashes each key into a bucket. Average lookup, insert and\n"
    "delete are O(1); worst case is O(n) on collisions. A good hash function\n"
    "and a sensible load factor keep buckets short.",
    "Course Notes - Trees, Heaps, Graphs and DP\n"
    "\n"
    "A binary search tree keeps keys sorted; a balanced BST (height ~ log n)\n"
    "supports search, insert and delete in O(log n).\n"
    "\n"
    "A heap is a complete tree satisfying the heap property. It powers priority\n"
    "queues: insert and extract-min are O(log n), peek is O(1).\n"
    "\n"
    "Graphs are vertices and edges. BFS explores level by level (shortest path\n"
    "in unweighted graphs); DFS explores deep first (cycle detection, topo sort).\n"
    "\n"
    "Dynamic programming caches subproblem results when a problem has optimal\n"
    "substructure and overlapping subproblems - turning exponential into\n"
    "polynomial time.",
]


def wrap(text: str, width: int = 46) -> str:
    lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        words = para.split()
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 <= width:
                cur = f"{cur} {w}".strip()
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return "\n".join(lines)


def fmt(t: float) -> str:
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def run(cmd: list[str], **kw) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])}...\n{proc.stderr[-1500:]}")


def probe_duration(path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return -1.0
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return -1.0


def build_video(cues: list[dict], out_path: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")

    # work OUTSIDE OneDrive (big writes get clobbered by the sync engine),
    # then copy the validated result into the project
    work = os.path.join(tempfile.gettempdir(), "l2h_clips")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    # fonts are copied next to the clips so the filtergraph can use relative
    # paths (Windows absolute paths would need multi-level filter escaping)
    for font in ("arial.ttf", "arialbd.ttf", "segoeuib.ttf", "seguisb.ttf"):
        src = os.path.join(FONT_DIR, font)
        if not os.path.exists(src):
            raise RuntimeError(f"required font not found: {src}")
        shutil.copy(src, os.path.join(work, font))

    for i, cue in enumerate(cues):
        dur = max(cue["end_time"] - cue["start_time"], 1.0)
        body = wrap(cue["text"])
        with open(os.path.join(work, f"text_{i:02d}.txt"), "w", encoding="utf-8") as fh:
            fh.write(body)
        with open(os.path.join(work, "title.txt"), "w", encoding="utf-8") as fh:
            fh.write("Intro to Data Structures  |  Lecture 1")
        with open(os.path.join(work, "stamp.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{fmt(cue['start_time'])} - {fmt(cue['end_time'])}   ·   slide {i + 1}/{len(cues)}")

        vf = ",".join(
            [
                f"drawtext=fontfile=seguisb.ttf:fontcolor={ACCENT}:fontsize=38:"
                "textfile=title.txt:x=70:y=64:line_spacing=6",
                f"drawbox=x=70:y=126:w=1140:h=4:color={ACCENT}@0.9:t=fill",
                f"drawtext=fontfile=segoeuib.ttf:fontcolor={FG}:fontsize=44:"
                f"textfile=text_{i:02d}.txt:x=70:y=190:line_spacing=16",
                f"drawtext=fontfile=arialbd.ttf:fontcolor={MUTED}:fontsize=26:"
                "textfile=stamp.txt:x=70:y=646",
                f"drawtext=fontfile=arialbd.ttf:fontcolor={ACCENT}:fontsize=26:"
                "text=Learn2Hire:x=w-tw-70:y=646",
            ]
        )
        clip = os.path.join(work, f"clip_{i:02d}.mp4")
        run(
            [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=c={SLIDE_BG}:s={RESOLUTION}:d={dur:.3f}:r=25",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
                "-pix_fmt", "yuv420p", "-r", "25",
                f"clip_{i:02d}.mp4",
            ],
            cwd=work,
        )

    concat_file = os.path.join(work, "list.txt")
    with open(concat_file, "w", encoding="utf-8") as fh:
        for i in range(len(cues)):
            fh.write(f"file 'clip_{i:02d}.mp4'\n")

    run(
        [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "out.mp4",
        ],
        cwd=work,
    )
    built = os.path.join(work, "out.mp4")
    dur = probe_duration(built)
    if dur < 0:
        raise RuntimeError("concatenated video failed validation")
    expected = cues[-1]["end_time"]
    if abs(dur - expected) > 2.0:
        raise RuntimeError(f"video duration {dur}s != expected {expected}s")

    # OneDrive may interfere while copying into the synced folder - verify and retry
    os.makedirs(SAMPLE, exist_ok=True)
    target = out_path
    for attempt in range(5):
        shutil.copy(built, target)
        got = probe_duration(target)
        if abs(got - expected) <= 2.0:
            print(f"  validated {target} ({os.path.getsize(target) / 1024 / 1024:.1f} MB, {got:.0f}s)")
            shutil.rmtree(work, ignore_errors=True)
            return
        time.sleep(1.5)
    raise RuntimeError(f"could not place a valid video at {target} (OneDrive interference?)")


def main() -> None:
    os.makedirs(SAMPLE, exist_ok=True)

    vtt_path = os.path.join(SAMPLE, "lecture1.vtt")
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(VTT)
    print(f"wrote {vtt_path}")

    pdf_path = os.path.join(SAMPLE, "notes.pdf")
    with open(pdf_path, "wb") as f:
        f.write(make_pdf(NOTES_PAGES))
    print(f"wrote {pdf_path}")

    cues = parse_transcript_bytes(VTT.encode(), "lecture1.vtt")
    if not cues:
        raise RuntimeError("no cues parsed from VTT")
    print(f"parsed {len(cues)} cues, total {cues[-1]['end_time']:.0f}s")

    mp4_path = os.path.join(SAMPLE, "lecture1.mp4")
    build_video(cues, mp4_path)
    size = os.path.getsize(mp4_path)
    print(f"wrote {mp4_path} ({size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
