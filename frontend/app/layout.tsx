import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Learn2Hire — Timestamp-aware AI Tutor + AI Mock Interview",
  description:
    "Pause any course video, ask a question, and get an answer sourced only from what you have watched — plus practice interviews built from the same material. AHGV BuildVerse 2026, Team codeflux.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.variable}>{children}</body>
    </html>
  );
}
