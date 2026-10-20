# Learn2Hire — Project Report

AHGV BuildVerse 2026 · Industry PS 1 · Team codeflux
Kanika (Team leader — Frontend, UI/UX) · Rakshit Thareja (Backend, AI)
Date: 18 October 2026

---

## 1. Summary

Learn2Hire is a timestamp-aware AI tutor and AI mock interviewer in one learning flow:
Watch → Pause → Ask → Understand → Practice → Interview. The learner pauses a course
video, asks a question, and gets an answer built only from content they have already
reached (video time, PDF pages, uploaded slides), with clickable sources — or an honest
"not in the material" / "covered later" reply. The same knowledge base powers a quiz
generator and a mock interviewer that asks follow-up questions and produces an
explainable scorecard.

This report deliberately separates what is **completed and demonstrable today** from
what is **implemented but not verified here** and what remains **planned**, so it can be
trusted as-is during judging.

---

## 2. What is completed (working prototype, verified on this machine)

Everything below runs locally with no AWS account and was verified by automated tests
(see §7) plus a manual click-through.

**Authentication**
- Register / login with JWT sessions (bcrypt password hashing, 12 h token expiry).

**Course ingestion**
- Upload a course: video (mp4/mkv/webm/mov), transcript (vtt/srt/txt), PDF, PPTX.
- Background ingestion pipeline: parse or generate a timestamped transcript → split into
  small chunks tagged with video time / PDF page / slide number → embed → index.
- Progress and status per course (`processing` → `ready` / `failed`) shown in the UI.

**Timestamp-aware tutor (/ask)**
- The frontend sends the question together with the current video time.
- Retrieval keeps only video chunks at or before that time (PDF/page chunks are always
  available — they are documents the learner was given, not future video content).
- Answers cite sources inline; every source is clickable and seeks the player to that
  exact timestamp (or opens the PDF page).
- No-spoiler guarantee: asking about a later lesson at an early timestamp returns
  "covered later" or "not in the material" — verified by tests.
- Chat history is stored per course and reloaded on revisit.

**Quiz**
- Generates MCQs from the material (optionally time-gated), each with the source
  sentence it was built from; grades submissions and returns per-question explanations.

**Mock interviewer — two modes**
- **Live interview experience**: when the lecture video ends, a robot interviewer appears
  with an offer to start. Camera and microphone turn on; the robot *speaks* each question
  (browser speech synthesis), listens to the spoken answer (speech recognition), evaluates
  it, and speaks the next one — no typing anywhere in this mode. Self-view is shown; the
  scorecard appears when the six turns finish and the camera is released.
- **Typed answers**: the same adaptive interviewer with a text box — works in any browser.
- Both modes share the agent memory (topics covered, strong/weak answers) that picks each
  next question, and finish with an explainable scorecard (per-dimension scores, grade,
  strengths, improvements, sample answer).

**Knowledge base build — video alone is enough**
- Build works from a video upload with no transcript: the course title/description seed a
  single overview chunk so the demo flow (ask/quiz/interview) runs immediately.
- Add a `.vtt`/`.srt` transcript (or PDF/slides) to get time-gated, source-cited answers;
  without one, the tutor answers from the course overview and marks sources as
  non-time-gated.

**Video player integration**
- Custom player streams the uploaded lecture with HTTP Range support (seeking works);
  timeline chips show where cited sources come from.
- YouTube-friendly ingestion: mkv/avi/mov/avif downloads (typical yt-dlp output) are
  automatically remuxed to browser-playable mp4 with ffmpeg during ingestion; webm/mp4
  play as-is. Drop the video and its .vtt caption file together and it just works.

**Chat tutor panel**
- Every message carries a clickable timestamp chip ("asked at 2:14 · jump") that seeks
  the player; answers show source chips (video time / PDF page / slide) that also jump.

**Demo seed**
- `backend/seed.py` creates `demo@learn2hire.dev / demo1234` with a ready course
  (sample lecture video + transcript + PDF notes, 13 indexed chunks) so the demo starts
  in seconds.

**User experience**
- Light, clean theme throughout (no dark theme), Inter typography, consistent design
  system, responsive layout, error and empty states.
- A cute study-buddy student mascot sits in the corner of the dashboard and course page,
  reacting to what you're doing (watching, thinking, happy); the interviewer is a robot
  character with animated listening/speaking/thinking states. Courses list features a
  polished delete button with inline confirmation.

---

## 3. What is implemented but not verified on this machine (honest caveats)

The PPT's target stack is AWS (Bedrock, Transcribe, S3, OpenSearch, PostgreSQL, Docker).
Every one of these real paths is **implemented in code behind the same interfaces** the
demo uses, but this machine has no AWS credentials and no Docker, so they run in a
local fallback ("DEMO_MODE=true") for the live demo:

| PPT claim | Code status | Demo status |
|---|---|---|
| AI answers from a frontier model | **Gemini** (`google-generativeai`) integrated as the primary answer + interview engine when `GEMINI_API_KEY` is set; Claude on Amazon Bedrock path also implemented | Deterministic extractive fallback (clearly labelled "demo-offline" in `/api/health`) until a Gemini key is added to `backend/.env` |
| AWS Transcribe turns video into timestamped text | Real job-submit/poll path in `transcription.py` | Transcript parsed from uploaded vtt/srt, or extractive fallback |
| S3 file storage | Real presigned-upload path in `storage.py` | Local filesystem storage |
| OpenSearch hybrid retrieval (keyword + meaning) | Real `OpenSearchIndex` (BM25 + kNN) in `index.py` | `LocalIndex` (BM25 + hashed-vector cosine) with the same ranking contract, `MIN_RELEVANCE` honesty filter |
| PostgreSQL for users, chats, scores | SQLAlchemy models run unchanged on Postgres | SQLite file (same schema) |
| Docker containers | `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` (Postgres + OpenSearch + both apps) written | Not started here — Docker is not installed on this machine; compose is for teammates/judges who have it |
| Interviewer agent with memory | Memory object (topics, strong/weak answers) drives next-question selection | Same flow; scoring is extractive in demo mode instead of Claude |

The switch is a single environment flag (`DEMO_MODE=false` + AWS credentials); no code
changes are needed. The demo mode is not a mock-up: the full pipeline (upload →
transcribe/parse → chunk → embed → index → time-gated retrieve → cite → answer, and the
interview loop) genuinely executes end to end.

---

## 4. What is planned (not yet built)

Marked clearly so nothing in the PPT is mistaken for finished work:

- Live verification against real AWS services (needs credentials/budget) and a recorded
  cost-per-query measurement — the PPT's "we'll report cost per query" item.
- Formal quantitative evaluation with the 5-case test set (accuracy, citations,
  hallucination rate, speed, cost). Functional equivalents exist (see §7); the scored
  benchmark study does not.
- CI/CD pipeline ("automatic updates from GitHub") — not set up.
- Multilingual content, deeper LMS integration, caching of repeated questions — future
  expansion as stated in the PPT. (Voice interviews, initially listed as future work in
  the PPT, are now implemented as the live camera/voice interview mode.)
- Slide (PPTX) extraction uses python-pptx text frames only; images/diagrams inside
  slides are not OCR'd.

---

## 5. Architecture (as implemented)

```
Frontend  Next.js 15 / React 19 / TypeScript, hand-rolled light CSS design system
          /login /register /dashboard /course/[id]
          VideoPlayer · ChatPanel · QuizPanel · InterviewPanel
              │  /api/* rewritten to the backend
Backend   FastAPI (Python 3.12) — JWT auth, /api/courses, /api/ask, /api/quiz,
          /api/interview, /api/files (Range-capable streaming), /api/health
          Services: ingestion · transcription · chunking · embeddings · index
                    retrieval · llm · quiz · interview · storage
Data      DEMO_MODE: SQLite + local files + LocalIndex (BM25 + vector cosine)
          Real path:  PostgreSQL + S3 + OpenSearch (BM25 + kNN) + Bedrock + Transcribe
```

Time gate (the core innovation): every video chunk carries `start_time`; retrieval
filters `start_time <= paused_time` before ranking, so later lessons can never be
retrieved. Non-video chunks (PDF pages, slides) are exempt — they are the documents the
learner was given, and every source is labelled with its origin. A `MIN_RELEVANCE`
threshold plus the `NOT_IN_MATERIAL` protocol prevent made-up answers.

---

## 6. How to run

**Local (what we demo):**

```
cd learn2hire/backend
pip install -r requirements.txt
copy .env.example .env          # defaults: DEMO_MODE=true, SQLite
uvicorn app.main:app --port 8000
python seed.py                  # demo account + ready course (idempotent)

cd ../frontend
npm install
npm run dev                     # http://localhost:3000
```

Log in as `demo@learn2hire.dev / demo1234`.

Optional but recommended: put a Google AI Studio key in `backend/.env`
(`GEMINI_API_KEY=...`) and restart the backend — answers, feedback and interview
questions switch from the extractive fallback to Gemini immediately
(`/api/health` shows `provider: gemini`). No code changes needed.

**Docker (for teammates/judges with Docker):**

```
cd learn2hire
docker compose up --build
docker compose exec backend python seed.py
```

Frontend on :3000, backend on :8000, Postgres and OpenSearch included.

---

## 7. Testing and verification

Three automated suites, all passing on this machine (56 checks total):

- `backend/tests/smoke.py` (35 checks) — auth; upload + full ingestion of video, PDF
  and transcript; `/ask` correctness including the no-spoiler case ("red-black trees"
  asked at t=30 s → "covered later", no future sources returned) and the
  not-in-material case ("capital of France" → `in_material=false`); quiz generation and
  grading; a complete interview run to an explainable scorecard.
- `backend/tests/smoke_files.py` (14 checks) — video streaming: full GET, byte-range
  GET (206, correct `Content-Range`), correct content type, auth required, PDF
  download, seeded-course ask/ask-no-spoiler.
- `backend/tests/smoke_proxy.py` (7 checks) — the same critical flows through the
  Next.js rewrite proxy, i.e. exactly the path the browser uses.

Plus YouTube/AVIF flows:
- `backend/tests/smoke_yt.py` (9 checks) — uploads a real .mkv (yt-dlp style) with its
  .vtt captions, verifies auto-remux to browser-playable mp4, Range streaming, and a
  correct tutor answer.
- `backend/tests/smoke_avif.py` (7 checks) — uploads an animated `.avif` (YouTube
  download style) with its `.vtt`, verifies auto-conversion to `.mp4`, Range streaming,
  and successful knowledge base build. Total 72 checks.

TypeScript typecheck (`tsc --noEmit`) and the production build (`next build`, 7 routes)
both pass. The generated sample lecture video was frame-checked for visual correctness.

Known limitations (also visible in testing):
- Demo-mode answers are extractive (verbatim source sentences) rather than Claude's
  fluent paraphrases; enabling Bedrock changes only the generation step.
- Hashed-vector embeddings are a local stand-in; semantic recall quality is lower than
  Titan/OpenSearch kNN (keyword+stemming carries most of the demo).
- Single-user SQLite demo storage; concurrent heavy load is out of scope for the
  prototype.

---

## 8. Live demo script (~5 minutes)

1. Log in as the seeded learner → dashboard shows the ready course and the study-buddy
   mascot greets you.
2. Open the course: the lecture plays; scrub the timeline (the mascot follows along).
3. Pause at 2:00, ask "What is a hash map?" → answer with a `[video @ 2:00]` source
   chip and an "answered at 2:00 · jump" timestamp; click either → player seeks back.
4. Rewind to 0:30, ask "Explain red-black trees" → "covered later" / no-spoiler reply
   (trees are taught after 5:00). Then ask something off-topic → "not in the material".
5. Quiz tab → 5 questions generated from watched material → submit → graded with
   explanations.
6. Drag the lecture to the end (or seek to the end) → the robot interviewer CTA appears
   over the player: choose **Live interview** (camera + voice, robot speaks and listens,
   no typing) or **Type answers** → 6 adaptive turns → explainable scorecard.
 7. (Optional) Upload flow: create a new course, drop `sample/lecture1.mp4` **and**
    `lecture1.vtt` together — or any YouTube .mkv download with its .vtt captions
    (auto-converted to mp4), or `.avif` downloads (auto-converted to mp4) — watch
    ingestion go to `ready`, repeat steps 3–4. The course card also has a sleek icon
    delete with inline confirmation.

---

## 9. Team and division of work

- **Kanika** — team leader, frontend and UI/UX: Next.js app, video player with seek
  integration, chat/quiz/interview panels, light design system, sample lecture design,
  this report.
- **Rakshit Thareja** — backend and AI: FastAPI services, ingestion pipeline,
  chunking/embedding/indexing, time-gated retrieval, honesty protocols, quiz and
  interviewer logic, AWS integration paths, test suites.

Both members contributed to end-to-end debugging, the sample content generator and the
Docker setup.
