export type Source = {
  type: "video" | "pdf" | "slides";
  label: string;
  start_time?: number | null;
  page?: number | null;
  slide?: number | null;
  quote?: string;
};

export type Material = {
  id: string;
  filename: string;
  kind: "video" | "pdf" | "slides" | "transcript";
  status: string;
  duration?: number;
};

export type Course = {
  id: string;
  title: string;
  description: string;
  status: "created" | "ingesting" | "ready" | "error";
  error: string;
  materials: Material[];
  chunks?: number;
};

export type ChatMsg = {
  role: "user" | "assistant";
  content: string;
  video_time?: number | null;
  sources?: Source[];
};

export type QuizQuestion = {
  id: string;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  source: Source;
};

export type Evaluation = {
  technical_accuracy: number;
  communication: number;
  relevance: number;
  feedback: string;
  topic: string;
};

export type Scorecard = {
  technical_accuracy: number;
  communication: number;
  relevance: number;
  overall: number;
  grade: string;
  strengths: string[];
  improvements: string[];
  topics_covered: string[];
  explanation: string;
};

const TOKEN_KEY = "l2h_token";
const USER_KEY = "l2h_user";

// On Vercel the API is served from the same origin via rewrites; locally we
// fall back to the backend port. NEXT_PUBLIC_API_URL overrides both.
const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "https://learn2hire-390a.onrender.com").replace(/\/+$/, "");

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): { id: string; name: string } | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setSession(token: string, user: { id: string; name: string }) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}/api${path}`, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth")) {
    clearSession();
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function fmtTime(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || isNaN(sec)) return "0:00";
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}:${String(m % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}
