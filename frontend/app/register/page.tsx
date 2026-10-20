"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import Nav from "@/components/Nav";
import { api, setSession } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api<{ access_token: string; user_id: string; name: string }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      setSession(res.access_token, { id: res.user_id, name: res.name });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
      setBusy(false);
    }
  }

  return (
    <>
      <Nav />
      <div className="auth-wrap">
        <form className="card auth-card stack" onSubmit={submit}>
          <div>
            <h1>Create your account</h1>
            <p className="hint">Upload a course, learn with an AI tutor, practice interviews.</p>
          </div>
          {error && <div className="error-box">{error}</div>}
          <div className="field">
            <label htmlFor="name">Full name</label>
            <input
              id="name"
              className="input"
              required
              minLength={2}
              placeholder="Kanika"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
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
              minLength={6}
              autoComplete="new-password"
              placeholder="At least 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button className="btn block" disabled={busy} type="submit">
            {busy && <span className="spinner" />}
            {busy ? "Creating…" : "Create account"}
          </button>
          <p style={{ fontSize: 13.5, color: "var(--text-2)", textAlign: "center" }}>
            Already registered? <Link href="/login">Log in</Link>
          </p>
        </form>
      </div>
    </>
  );
}
