# Deploying Learn2Hire

Two ways. **Pick the Docker way** — it uploads zero project files, so hidden-file
and file-count limits can never bite you.

---

## Option A — Docker (recommended, one command)

You only need `docker` installed. From the project root:

```bash
docker compose up -d --build
```

That builds both images, starts Postgres + OpenSearch + backend + frontend, seeds the
demo account, and leaves the app on **http://localhost:3000**.

```bash
docker compose down          # stop
docker compose logs -f       # watch logs
```

No `.env` to upload, no `node_modules`, no file picker. Everything is in the images.

---

## Option B — manual / platform build

If your host runs commands instead of Docker:

**1. Never upload `node_modules` or `.next`.** Those are thousands of files — that is
what "too many files" means. They are re-created on the server.

**2. Never rely on dotfile pickers.** Most upload UIs hide files starting with `.`,
which silently drops `.env` and `.dockerignore`. Always create `.env` **on the server**
instead of uploading it.

```bash
# --- backend ---
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cat > .env <<'EOF'
DEMO_MODE=true
JWT_SECRET=change-me-to-a-long-random-string
UPLOAD_DIR=./data/uploads
DATABASE_URL=sqlite:///./data/learn2hire.db
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.8-flash
EOF

uvicorn app.main:app --port 8000
python seed.py        # creates demo@learn2hire.dev / demo1234

# --- frontend ---
npm install
npm run build
npm start             # serves on :3000, proxies /api/* to the backend
```

**3. Which files actually matter** — everything else is generated:

| Needed | Ignore |
|---|---|
| `backend/app/`, `backend/requirements.txt`, `backend/seed.py`, `backend/Dockerfile` | `__pycache__/`, `*.pyc`, `*.db`, `data/` |
| `frontend/app/`, `frontend/components/`, `frontend/lib/`, `frontend/package.json`, `frontend/next.config.js` | `node_modules/`, `.next/`, `*.tsbuildinfo` |
| `docker-compose.yml` (if using Docker) | `.env` (create on server) |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| 500 on every request | `.env` missing (hidden-file upload) | `cat > .env` on the server |
| "too many files" | uploading `node_modules`/`.next` | delete them; use `.dockerignore` |
| npm install fails | `package-lock.json` out of sync | `npm install` regenerates it |
| demo login fails | seed not run / wrong DB path | run `python seed.py` after `cat > .env` |
| no AI answers | Gemini quota / bad key | check `/api/health` → `provider_error` |

---

## Uploading your lectures

Drop files **anywhere** on the dashboard — the whole page is a drop target.

- Multiple files at once work.
- **A `.zip` works too**: put your video + captions + notes in one zip, drop it, and
  everything is unpacked and indexed. This is the easiest option if your host limits
  how many files you can upload.

`.avif` is an image format, not a video — a still `.avif` converts to a 1-second clip
and is rejected with a clear message. Use the `.mp4` / `.mkv` / `.webm` download.
