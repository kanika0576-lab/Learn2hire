"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearSession, getUser } from "@/lib/api";

export default function Nav() {
  const router = useRouter();
  const user = typeof window !== "undefined" ? getUser() : null;

  return (
    <header className="nav">
      <div className="container nav-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">L2</span>
          Learn2Hire
        </Link>
        <div className="row">
          <span className="badge grey" title="Problem statement track">
            Industry PS 1
          </span>
          {user ? (
            <>
              <Link href="/dashboard" className="btn ghost sm">
                My Courses
              </Link>
              <span className="badge">{user.name.split(" ")[0]}</span>
              <button
                className="btn secondary sm"
                onClick={() => {
                  clearSession();
                  router.push("/login");
                }}
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn ghost sm">
                Log in
              </Link>
              <Link href="/register" className="btn sm">
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
