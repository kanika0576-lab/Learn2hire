# Learn2Hire

A timestamp-aware AI tutor + AI mock interviewer in one learning flow.
Watch → Pause → Ask → Understand → Practice → Interview.

AHGV BuildVerse 2026 · Industry PS 1 · Team codeflux
(Kanika — frontend/UI · Rakshit Thareja — backend/AI)

Watch a lecture, pause, and ask — answers are built only from material you've
already reached (video time, PDF page, slide), with clickable sources or an honest
"not in the material" / "covered later" reply. Build the knowledge base from a video
alone (no transcript required — the course title/description seed the index); add a
`.vtt`/`.srt` transcript later to unlock time-gated answers. The same index powers a
quiz generator and a mock interviewer with an explainable scorecard — including a **live
camera-and-voice interview mode** where a robot interviewer speaks the questions and
listens to your answers (no typing).

## Quick start (local demo)

Prerequisites: Python 3.12, Node 20+.

```
cd backend
pip install -r requirements.txt
copy .env.example .env        # Windows; use cp on macOS/Linux
uvicorn app.main:app --port 8000
python seed.py                # in a second terminal — creates the demo account + course
```

```
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and log in with **demo@learn2hire.dev / demo1234**
(or register a new account and upload your own video + transcript — see
`learn2hire/sample/` for the format).

**YouTube downloads work out of the box**: drop the video (mp4/webm/mkv/avif — mkv and
avif are auto-converted to mp4) together with its `.vtt` caption file (yt-dlp saves one
next to the video). **Gemini answers**: put `GEMINI_API_KEY=your-key` in `backend/.env` and
restart the backend to switch from the offline extractive fallback to Gemini — no other
change needed (`/api/health` shows the active provider).

## Docker

```
docker compose up --build
docker compose exec backend python seed.py
```

Frontend :3000 · backend :8000 · PostgreSQL · OpenSearch.

## How it works

1. Upload course material (video, vtt/srt transcript, PDF, PPTX).
2. Ingestion: transcript with timestamps → small chunks tagged with video time / page /
   slide → embeddings → hybrid index (keyword + meaning).
3. Ask a question while paused: the backend gates retrieval to content at or before the
   current video time, then generates a cited answer — or refuses honestly.
4. Quiz and mock interviewer run on the same knowledge base; the interviewer adapts
   each next question to your last answer and scores you per dimension.

## Demo mode vs AWS

The prototype runs out of the box with `DEMO_MODE=true` (SQLite, local file storage,
local index, extractive answer fallback) — no AWS account needed. The full AWS path
(Bedrock for Claude, Transcribe, S3, OpenSearch, PostgreSQL) is implemented behind the
same interfaces; set `DEMO_MODE=false` and provide credentials to switch. See
`report/REPORT.md` §3 for exactly what is verified vs planned.

## Tests

```
cd backend
python tests/smoke.py          # 35 checks: auth, ingestion, ask, no-spoiler, quiz, interview
python tests/smoke_files.py    # 14 checks: video Range streaming, seeded-course ask
python tests/smoke_proxy.py    # 7 checks: the same flows through the Next.js proxy
python tests/smoke_yt.py       # 9 checks: YouTube .mkv + .vtt upload, auto-remux, answer
python tests/smoke_avif.py     # 7 checks: .avif upload, auto-convert to mp4, stream
```

## Repository layout

```
backend/    FastAPI app (auth, courses, ask, quiz, interview, file streaming) + tests
frontend/   Next.js app (player, chat, quiz, interview panels; light theme)
sample/     Generated demo lecture: lecture1.mp4, lecture1.vtt, notes.pdf
scripts/    Sample-content generator (video + transcript + PDF)
report/     PROJECT REPORT (completed vs planned, honest caveats, demo script)
```

## Report

Full write-up with the completed/planned breakdown, architecture, verification evidence
and the live-demo script: [`report/REPORT.md`](report/REPORT.md).
