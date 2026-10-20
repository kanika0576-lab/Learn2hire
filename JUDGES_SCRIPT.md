# Hackathon Judge Script — Learn2Hire

**Team codeflux** · Kanika (frontend/UI) · Rakshit Thareja (backend/AI)
~90 seconds · AHGV BuildVerse 2026 · Industry PS 1

---

## 30s — Hook + Problem

> "Sabse bada problem lecture ke baad hota hai: recording ek folder me pada rehti hai, aur koi
> nahi poochta — *kya aapko is cheez ka doubt hai jo 4:30 pe aa raha hai?*
> Learn2Hire ek lecture ko **timestamp-aware AI tutor** aur **proctored AI mock interviewer**
> me badal deta hai."

---

## 30s — Technologies (core stack)

> "Frontend: **Next.js 15 + React 19 + TypeScript** — hand-rolled CSS, custom video player
> jo HTTP Range support ke saath seek karta hai.
>
> Backend: **FastAPI + Python 3.12** — JWT auth, role-based endpoints.
>
> AI: **Gemini 3.8 Flash** primary, **Claude on Amazon Bedrock** fallback — same code path.
>
> Speech-to-text: video ke audio ko **Gemini understanding se timestamp segments** me
> convert karte hain — captions na hon tab bhi kaam karta hai. Hostile video formats ko
> **ffmpeg** se browser-playable MP4 me remux karte hain.
>
> Storage/index: **SQLite + in-memory vector index** demo mode me, aur **OpenSearch +
> PostgreSQL** production path pe."

---

## 20s — The hard part (this is what judges remember)

> "Sabse interesting piece **time-gated retrieval** hai. Video ka current time jo hai, uske
> **pehle ke chunks hi** retrievable hain. Toh agar learner 0:30 pe rukkar 5:00 ka topic
> poochhe, toh system answer nahi churata — wo bolta hai *covered later*.
>
> Quiz aur interviewer usi index se bante hain, aur answers hamesha clickable source
> cite karte hain — video second ya PDF page — jo player ko wapas seek kar deta hai."

---

## 10s — Live + deployment

> "Interview mode camera aur mic use karta hai, robot questions bolta hai, aapki awaaz
> sunta hai — aur **proctoring** ke saath: fullscreen lock, tab-switch, copy/paste block.
>
> Poora system **Docker Compose** me ek command se deploy hota hai.
>
> Ab main live demo dikhata hoon."

---

## Judge questions to be ready for

| Question | Short answer |
|---|---|
| Why not just use ChatGPT? | Time-gating — sirf wahi material jo aapne dekha. No spoilers, answers cited. |
| What if no captions? | We transcribe audio ourselves via Gemini. |
| Cost / scaling? | RAG over your own material = no per-question cost beyond one embed + one LLM call. |
| Database? | SQLite for the demo; Postgres + OpenSearch behind the same interfaces. |
| Anti-cheat strength? | Best-effort signals (focus loss, clipboard, fullscreen). Clearly shown, logged. |

---

**Demo path (4 min):** login → play lecture → ask at 2:00 → rewind & ask "red-black trees"
(covered later) → quiz → watch to end → live interview → scorecard.
