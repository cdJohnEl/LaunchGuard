"use client";

import { useState } from "react";
import { signInWithGoogle } from "@/lib/auth";

export function SignInPrompt({ context }: { context: string }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      await signInWithGoogle();
    } catch (signError) {
      console.error(signError);
      setError("Google sign-in didn't complete. Check that popups aren't blocked, then try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-10 border border-rule-strong px-6 py-8 md:px-8" aria-label="Sign in">
      <p className="kicker">Sign in</p>
      <h2 className="mt-2 max-w-lg font-display text-2xl tracking-tight md:text-[26px]">
        {context}
      </h2>
      <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-soft">
        Groups are private to the founder who claimed them. Sign in with
        Google to continue.
      </p>
      <button type="button" onClick={signIn} disabled={busy} className="btn-primary mt-6">
        {busy ? "Opening Google…" : "Continue with Google"}
      </button>
      {error !== null && (
        <p role="alert" className="err mt-3 max-w-md">
          {error}
        </p>
      )}
    </section>
  );
}
