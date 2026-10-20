"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import Nav from "@/components/Nav";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api<{ access_token: string; user_id: string; name: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setSession(res.access_token, { id: res.user_id, name: res.name });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setBusy(false);
    }
  }

  return (
    <>
      <Nav />
      <div className="auth-wrap">
        <form className="card auth-card stack" onSubmit={submit}>
          <div>
            <h1>Welcome back</h1>
            <p className="hint">Log in to continue learning — watch, ask, practice, interview.</p>
          </div>
          {error && <div className="error-box">{error}</div>}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              required
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button className="btn block" disabled={busy} type="submit">
            {busy && <span className="spinner" />}
            {busy ? "Logging in…" : "Log in"}
          </button>
          <p style={{ fontSize: 13.5, color: "var(--text-2)", textAlign: "center" }}>
            New here? <Link href="/register">Create an account</Link>
          </p>
        </form>
      </div>
    </>
  );
}
