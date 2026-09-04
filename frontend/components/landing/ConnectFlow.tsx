"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { doc, getDoc } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import {
  TELEGRAM_DEEP_LINK,
  chatIdInputError,
  normalizeChatId,
} from "@/lib/onboarding";
import { SetupRequired } from "@/components/landing/SetupRequired";

const STORAGE_KEY = "launchguard:chat";

type FlowState =
  | { s: "form" }
  | { s: "checking" }
  | { s: "error" }
  | { s: "missing"; chatId: string }
  | {
      s: "found";
      chatId: string;
      name: string | null;
      active: boolean;
      blocked: number;
      subscription: string | null;
    };

/**
 * Step 3 of the setup: paste a chat id, verify it against
 * groups/{chatId}, then hand off to /dashboard?chat=<id>.
 * No window access during render; async work happens in handlers.
 */
export function ConnectFlow() {
  const [draft, setDraft] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [state, setState] = useState<FlowState>({ s: "form" });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.s === "checking") return;
    const message = chatIdInputError(draft);
    if (message !== null) {
      setFieldError(message);
      return;
    }
    const chatId = normalizeChatId(draft);
    if (chatId === null) return;
    setFieldError(null);
    setState({ s: "checking" });
    try {
      const snapshot = await getDoc(doc(db, "groups", chatId));
      if (!snapshot.exists()) {
        setState({ s: "missing", chatId });
        return;
      }
      const data = snapshot.data();
      setState({
        s: "found",
        chatId,
        name: typeof data.group_name === "string" ? data.group_name : null,
        active: data.active === true,
        blocked:
          typeof data.scams_blocked === "number" &&
          Number.isFinite(data.scams_blocked)
            ? Math.max(0, Math.trunc(data.scams_blocked))
            : 0,
        subscription:
          typeof data.subscription_status === "string"
            ? data.subscription_status
            : null,
      });
    } catch (error) {
      console.error(error);
      setState({ s: "error" });
    }
  }

  function openDashboard(chatId: string) {
    try {
      window.localStorage.setItem(STORAGE_KEY, chatId);
    } catch {
      // Private browsing: the URL parameter still carries the id.
    }
  }

  const showForm =
    state.s === "form" || state.s === "checking" || state.s === "error";

  return (
    <section className="mt-12 md:mt-16">
      <p className="kicker">Setup · step 3 of 3</p>
      <h1 className="mt-3 max-w-[20ch] font-display text-[clamp(2rem,4.6vw,2.75rem)] font-medium leading-[1.1] tracking-[-0.02em]">
        Connect your group.
      </h1>
      <p className="mt-4 max-w-[58ch] text-[15px] leading-relaxed text-ink-soft">
        Paste the group&apos;s chat id and Launch Guard opens its dashboard for
        that group. Easiest source: the bot&apos;s welcome message in your
        group posts the id. You can also read it in Telegram Web — the number
        after the{" "}
        <span className="font-mono text-[13px] text-ink">#</span> in the
        address bar, and a supergroup&apos;s starts with{" "}
        <span className="font-mono text-[13px] text-ink">-100</span>.
      </p>

      <p aria-live="polite" className="sr-only">
        {state.s === "found" && `Found ${state.name ?? "your group"}.`}
        {state.s === "missing" &&
          "The bot hasn't registered that chat id yet."}
        {state.s === "error" && "Couldn't reach the record."}
      </p>

      {!firebaseConfigured ? (
        <div className="mt-8">
          <SetupRequired heading="Lookups aren't wired up yet" />
        </div>
      ) : (
        <>
          {showForm && (
            <form onSubmit={submit} noValidate className="mt-8 max-w-md">
              <label htmlFor="connect-chat-id" className="kicker block text-ink">
                Chat id
              </label>
              <input
                id="connect-chat-id"
                type="text"
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  if (fieldError !== null) setFieldError(null);
                }}
                placeholder="-1001234567890"
                autoComplete="off"
                spellCheck={false}
                aria-invalid={fieldError !== null ? true : undefined}
                aria-describedby={
                  fieldError !== null ? "connect-chat-error" : undefined
                }
                className="input-line mt-1"
              />
              {fieldError !== null && (
                <p id="connect-chat-error" className="err">
                  {fieldError}
                </p>
              )}
              <button
                type="submit"
                disabled={state.s === "checking"}
                className="btn-primary mt-5"
              >
                {state.s === "checking" ? "Checking…" : "Find my group"}
              </button>
              {state.s === "error" && (
                <p role="alert" className="err">
                  Couldn&apos;t reach the record. Check your connection and
                  try again.
                </p>
              )}
            </form>
          )}

          {state.s === "found" && (
            <section className="mt-8 border border-rule-strong" aria-label="Group found">
              <div className="border-b border-rule px-6 py-6 md:px-8">
                <p className="kicker">Found</p>
                <h2 className="mt-2 font-display text-2xl tracking-tight">
                  {state.name ?? "This group"}
                </h2>
                <p className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-ink-soft">
                  <span
                    className={`inline-block h-1.5 w-1.5 self-center rounded-full ${
                      state.active ? "bg-ink" : "bg-signal"
                    }`}
                    aria-hidden="true"
                  />
                  {state.active
                    ? "Bot active in the group"
                    : "Bot not active — check its admin rights in the group"}
                  {state.subscription !== null && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span className="font-mono text-[11px] uppercase tracking-[0.14em]">
                        {state.subscription}
                      </span>
                    </>
                  )}
                </p>
                <p className="mt-2 font-mono text-[13px] text-ink-soft">
                  Blocked so far: {state.blocked.toLocaleString("en-US")} · id{" "}
                  {state.chatId}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3 px-6 py-5 md:px-8">
                <Link
                  href={`/dashboard?chat=${encodeURIComponent(state.chatId)}`}
                  className="btn-primary"
                  onClick={() => openDashboard(state.chatId)}
                >
                  Open the dashboard
                </Link>
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => setState({ s: "form" })}
                >
                  Check another id
                </button>
              </div>
            </section>
          )}

          {state.s === "missing" && (
            <section
              className="mt-8 border border-rule-strong"
              aria-label="Group not registered yet"
            >
              <div className="border-b border-rule px-6 py-6 md:px-8">
                <p className="kicker">Not registered yet</p>
                <h2 className="mt-2 max-w-md font-display text-2xl leading-snug tracking-tight">
                  The bot hasn&apos;t seen that group yet.
                </h2>
                <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-soft">
                  A group appears here the moment the bot joins it with the
                  Delete messages right. If you haven&apos;t added it yet,
                  start with step 1 — then come back and paste the id again.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-6 py-5 md:px-8">
                <a
                  className="btn-primary"
                  href={TELEGRAM_DEEP_LINK}
                  target="_blank"
                  rel="noreferrer"
                >
                  Add the bot to your group
                  <span aria-hidden="true" className="font-mono">
                    ↗
                  </span>
                </a>
                <button
                  type="button"
                  className="btn-quiet"
                  onClick={() => setState({ s: "form" })}
                >
                  Edit the id
                </button>
                <Link href="/#setup" className="landing-link text-sm">
                  Review the three steps
                </Link>
              </div>
            </section>
          )}
        </>
      )}
    </section>
  );
}
