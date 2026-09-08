"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { doc, getDoc, onSnapshot } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import { useAuth } from "@/lib/auth";
import { claimState } from "@/lib/claim";
import {
  TELEGRAM_DEEP_LINK,
  chatIdInputError,
  normalizeChatId,
} from "@/lib/onboarding";
import { SetupRequired } from "@/components/landing/SetupRequired";
import { SignInPrompt } from "@/components/SignInPrompt";

const STORAGE_KEY = "launchguard:chat";

type FoundGroup = {
  chatId: string;
  name: string | null;
  active: boolean;
  blocked: number;
  subscription: string | null;
  ownerUid: string | null;
};

type FlowState =
  | { s: "form" }
  | { s: "checking" }
  | { s: "error" }
  | { s: "missing"; chatId: string }
  | { s: "found"; group: FoundGroup }
  | { s: "pending-claim"; group: FoundGroup };

/**
 * Step 3 of the setup: paste a chat id, verify groups/{chatId}, then claim it
 * by typing /claim <code> in the group — the bot checks the sender is a group
 * admin (Telegram is the authority) and binds owner_uid server-side. The page
 * watches the doc and unlocks the moment the claim lands.
 */
export function ConnectFlow() {
  const { user, loading } = useAuth();
  const [draft, setDraft] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [state, setState] = useState<FlowState>({ s: "form" });
  const [watchError, setWatchError] = useState(false);

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
        group: {
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
          ownerUid:
            typeof data.owner_uid === "string" && data.owner_uid !== ""
              ? data.owner_uid
              : null,
        },
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

      {!firebaseConfigured ? (
        <div className="mt-8">
          <SetupRequired heading="Lookups aren't wired up yet" />
        </div>
      ) : !loading && user === null ? (
        <SignInPrompt context="Sign in to connect and claim your group." />
      ) : (
        <>
          <p aria-live="polite" className="sr-only">
            {state.s === "found" &&
              `Found ${state.group.name ?? "your group"}.`}
            {state.s === "pending-claim" &&
              "Waiting for the claim command in your group."}
            {state.s === "missing" &&
              "The bot hasn't registered that chat id yet."}
            {state.s === "error" && "Couldn't reach the record."}
          </p>

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
            <FoundPanel
              group={state.group}
              userUid={user?.uid ?? null}
              onClaim={() => setState({ s: "pending-claim", group: state.group })}
              onReset={() => setState({ s: "form" })}
              onOpen={() => openDashboard(state.group.chatId)}
            />
          )}

          {state.s === "pending-claim" && user !== null && (
            <PendingClaim
              group={state.group}
              userUid={user.uid}
              watchError={watchError}
              onWatchError={() => setWatchError(true)}
              onResolved={(ownerUid) =>
                setState({
                  s: "found",
                  group: { ...state.group, ownerUid },
                })
              }
              onCancel={() => setState({ s: "form" })}
            />
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

function FoundPanel({
  group,
  userUid,
  onClaim,
  onReset,
  onOpen,
}: {
  group: FoundGroup;
  userUid: string | null;
  onClaim: () => void;
  onReset: () => void;
  onOpen: () => void;
}) {
  const ownership = claimState(group.ownerUid, userUid ?? "");
  const dashboardHref = `/dashboard?chat=${encodeURIComponent(group.chatId)}`;

  return (
    <section className="mt-8 border border-rule-strong" aria-label="Group found">
      <div className="border-b border-rule px-6 py-6 md:px-8">
        <p className="kicker">
          {ownership === "mine" ? "Your group" : "Found"}
        </p>
        <h2 className="mt-2 font-display text-2xl tracking-tight">
          {group.name ?? "This group"}
        </h2>
        <p className="mt-3 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm text-ink-soft">
          <span
            className={`inline-block h-1.5 w-1.5 self-center rounded-full ${
              group.active ? "bg-ink" : "bg-signal"
            }`}
            aria-hidden="true"
          />
          {group.active
            ? "Bot active in the group"
            : "Bot not active — check its admin rights in the group"}
          {group.subscription !== null && (
            <>
              <span aria-hidden="true">·</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.14em]">
                {group.subscription}
              </span>
            </>
          )}
        </p>
        <p className="mt-2 font-mono text-[13px] text-ink-soft">
          Blocked so far: {group.blocked.toLocaleString("en-US")} · id{" "}
          {group.chatId}
        </p>
        {ownership === "unowned" && (
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-soft">
            No founder has claimed this group yet. Claiming binds it to your
            account — only you will see and configure its dashboard.
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 px-6 py-5 md:px-8">
        {ownership === "mine" && (
          <Link href={dashboardHref} className="btn-primary" onClick={onOpen}>
            Open the dashboard
          </Link>
        )}
        {ownership === "unowned" && (
          <button type="button" className="btn-primary" onClick={onClaim}>
            Claim this group
          </button>
        )}
        <button type="button" className="btn-quiet" onClick={onReset}>
          Check another id
        </button>
        {ownership === "mine" && (
          <span className="font-mono text-[12px] text-ink-soft">
            claimed to your account
          </span>
        )}
      </div>
    </section>
  );
}

function PendingClaim({
  group,
  userUid,
  watchError,
  onWatchError,
  onResolved,
  onCancel,
}: {
  group: FoundGroup;
  userUid: string;
  watchError: boolean;
  onWatchError: () => void;
  onResolved: (ownerUid: string) => void;
  onCancel: () => void;
}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    onWatchError();
    const unsubscribe = onSnapshot(
      doc(db, "groups", group.chatId),
      (snapshot) => {
        if (!snapshot.exists()) {
          onCancel();
          return;
        }
        const owner = snapshot.data().owner_uid;
        if (typeof owner === "string" && owner !== "") {
          // Resolves to either your dashboard ("mine") or the taken state.
          onResolved(owner);
        }
      },
      (error) => {
        console.error(error);
        // A silent wait would hide a rules or connection problem.
        onWatchError();
      },
    );
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group.chatId, userUid]);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(userUid);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable: the code is selectable text anyway.
    }
  }

  return (
    <section className="mt-8 border border-rule-strong" aria-label="Claim your group">
      <div className="border-b border-rule px-6 py-6 md:px-8">
        <p className="kicker">Prove you control the group</p>
        <h2 className="mt-2 max-w-lg font-display text-2xl leading-snug tracking-tight">
          Type this command in {group.name ?? "your group"} as an admin.
        </h2>
        <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-soft">
          The bot answers only to group admins, so this one message is the
          proof. It binds the group to your account and this page unlocks the
          moment it lands.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <code className="border border-rule-strong bg-paper px-3 py-2 font-mono text-[14px] text-ink">
            /claim {userUid}
          </code>
          <button type="button" onClick={copyCode} className="btn-quiet">
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-6 py-5 md:px-8">
        {watchError ? (
          <p role="alert" className="err max-w-md">
            Lost the live watch on the group — the command may have landed
            anyway. Reload the page to check.
          </p>
        ) : (
          <p className="flex items-center gap-2 text-[15px] text-ink-soft">
            <span
              className="inline-block h-2 w-2 animate-pulse rounded-full bg-signal"
              aria-hidden="true"
            />
            Waiting for the command in {group.name ?? "your group"}… If someone
            claims it first, this page tells you instead of waiting.
          </p>
        )}
        <button type="button" className="btn-quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}
