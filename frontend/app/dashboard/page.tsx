"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FirebaseError } from "firebase/app";
import { onSnapshot, doc } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import { signOutUser, useAuth } from "@/lib/auth";
import { extractFaqPairs } from "@/lib/faq";
import { BlockedCounter } from "@/components/BlockedCounter";
import { ChatPicker } from "@/components/ChatPicker";
import { FaqForm } from "@/components/FaqForm";
import { FaqList } from "@/components/FaqList";
import { GroupLine } from "@/components/GroupLine";
import { SetupNotice } from "@/components/SetupNotice";
import { SignInPrompt } from "@/components/SignInPrompt";

const STORAGE_KEY = "launchguard:chat";

type GroupData = {
  name: string | null;
  active: boolean;
  scams: number;
  subscription: string | null;
  pairs: [string, string][];
};

type DocState =
  | { s: "idle" }
  | { s: "loading" }
  | { s: "missing" }
  | { s: "error" }
  | { s: "denied" }
  | { s: "ready"; group: GroupData };

function persistChatId(chatId: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, chatId);
  } catch {
    // Private browsing: storage unavailable, session-only is fine.
  }
}

function updateUrl(chatId: string) {
  try {
    const url = new URL(window.location.href);
    url.searchParams.set("chat", chatId);
    window.history.replaceState(null, "", url);
  } catch {
    // History API unavailable: the dashboard still works from state.
  }
}

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const [mounted, setMounted] = useState(false);
  const [chatId, setChatId] = useState<string | null>(null);
  const [docState, setDocState] = useState<DocState>({ s: "idle" });
  const [dateline, setDateline] = useState<string | null>(null);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      stored = null;
    }
    const fromUrl = new URLSearchParams(window.location.search).get("chat");
    const envDefault = process.env.NEXT_PUBLIC_DEFAULT_CHAT_ID || null;
    const resolved =
      fromUrl?.trim() || envDefault?.trim() || stored?.trim() || null;
    if (resolved !== null) {
      setChatId(resolved);
      persistChatId(resolved);
      updateUrl(resolved);
    }
    setDateline(
      new Intl.DateTimeFormat("en-GB", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }).format(new Date()),
    );
    setMounted(true);
  }, []);

  useEffect(() => {
    if (chatId === null || !firebaseConfigured || user === null) return;
    setDocState({ s: "loading" });
    const unsubscribe = onSnapshot(
      doc(db, "groups", chatId),
      (snapshot) => {
        if (!snapshot.exists()) {
          setDocState({ s: "missing" });
          return;
        }
        const data = snapshot.data();
        setDocState({
          s: "ready",
          group: {
            name: typeof data.group_name === "string" ? data.group_name : null,
            active: data.active === true,
            scams: typeof data.scams_blocked === "number" ? data.scams_blocked : 0,
            subscription:
              typeof data.subscription_status === "string"
                ? data.subscription_status
                : null,
            pairs: extractFaqPairs(data.faq_pairs),
          },
        });
      },
      (error) => {
        console.error(error);
        setDocState(
          error instanceof FirebaseError && error.code === "permission-denied"
            ? { s: "denied" }
            : { s: "error" },
        );
      },
    );
    return unsubscribe;
  }, [chatId, user]);

  function connect(id: string) {
    setChatId(id);
    setDocState({ s: "idle" });
    persistChatId(id);
    updateUrl(id);
  }

  const showDocState =
    docState.s !== "idle" ? docState : chatId !== null ? { s: "loading" as const } : null;

  let content: React.ReactNode;
  if (!firebaseConfigured) {
    content = <SetupNotice />;
  } else if (!mounted || loading) {
    content = <HeroSkeleton />;
  } else if (user === null) {
    content = (
      <SignInPrompt context="Sign in to see your group's dashboard." />
    );
  } else if (chatId === null) {
    content = (
      <div className="mt-12">
        <ChatPicker idPrefix="panel" onConnect={connect} variant="panel" />
        <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink-soft">
          The dashboard follows one group at a time. Switch any time from the
          masthead.
        </p>
      </div>
    );
  } else {
    content = (
      <>
        {showDocState?.s === "loading" && <HeroSkeleton />}
        {showDocState?.s === "missing" && <MissingNotice />}
        {showDocState?.s === "error" && <ConnectionError />}
        {showDocState?.s === "denied" && <DeniedNotice />}
        {showDocState?.s === "ready" && (
          <>
            <section className="mt-10">
              <BlockedCounter value={showDocState.group.scams} />
              <GroupLine
                name={showDocState.group.name}
                active={showDocState.group.active}
                subscription={showDocState.group.subscription}
              />
            </section>

            <section className="mt-14 border-t border-rule pt-8">
              <div className="grid gap-10 lg:grid-cols-12">
                <div className="lg:col-span-5">
                  <FaqForm
                    chatId={chatId}
                    docExists={showDocState.s === "ready"}
                  />
                </div>
                <div className="lg:col-span-7 lg:border-l lg:border-rule lg:pl-10">
                  <FaqList chatId={chatId} pairs={showDocState.group.pairs} />
                </div>
              </div>
            </section>
          </>
        )}
      </>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[880px] flex-col px-6 md:px-10">
      <header className="pt-10">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="font-display text-[26px] font-semibold leading-none tracking-[-0.01em]">
            Launch <span className="font-medium italic">Guard</span>
          </h1>
          <p className="kicker text-right">Telegram moderation · Web3 founders</p>
        </div>
        <div className="mt-4 border-t-2 border-ink" />
        <div className="mt-[3px] border-t border-ink" />

        <div className="flex flex-wrap items-end justify-between gap-4 py-3">
          <p className="min-h-[1.5rem] font-display text-sm italic text-ink-soft">
            {dateline}
          </p>
          {mounted && user !== null && chatId !== null && (
            <ChatPicker idPrefix="bar" onConnect={connect} variant="bar" />
          )}
        </div>
        {mounted && user !== null && (
          <div className="flex items-baseline justify-between gap-4 border-t border-rule py-2">
            <span className="font-mono text-[12px] text-ink-soft">
              {user.email ?? user.uid}
            </span>
            <button
              type="button"
              onClick={() => {
                setDocState({ s: "idle" });
                void signOutUser();
              }}
              className="btn-text-danger"
            >
              Sign out
            </button>
          </div>
        )}
        <div className="border-t border-rule" />
      </header>

      <main className="grow">{content}</main>

      <footer className="mt-16 flex flex-wrap items-baseline justify-between gap-2 border-t border-rule py-5">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs text-ink-soft">
            Launch Guard — Telegram moderation for Web3 founders
          </p>
          <span className="text-ink-faint">·</span>
          <Link
            href="/admin"
            className="text-xs text-ink-soft hover:text-ink font-mono font-medium underline"
          >
            Admin Console
          </Link>
        </div>
        <p className="text-xs text-ink-soft">Live via Firestore, updates in real time</p>
      </footer>
    </div>
  );
}

function HeroSkeleton() {
  return (
    <div className="mt-10 animate-pulse" aria-hidden="true">
      <p className="sr-only">Loading group</p>
      <div className="h-3 w-32 bg-rule" />
      <div className="mt-4 border-y border-rule py-8">
        <div className="h-20 w-64 bg-rule md:h-24 md:w-72" />
      </div>
      <div className="mt-4 h-3 w-56 bg-rule" />
    </div>
  );
}

function MissingNotice() {
  return (
    <section className="mt-12 border border-rule-strong px-8 py-10 md:px-10">
      <p className="kicker">Not connected</p>
      <h2 className="mt-2 max-w-lg font-display text-2xl tracking-tight md:text-[28px] md:leading-snug">
        No group connected yet — add the bot to your group (see /connect)
      </h2>
      <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-soft">
        The counter starts as soon as the bot joins and blocks its first scam.
        Check the chat ID in the masthead matches the group the bot was added to.
      </p>
    </section>
  );
}

function ConnectionError() {
  return (
    <section className="mt-12 border-l-2 border-signal py-1 pl-5">
      <h2 className="font-display text-xl tracking-tight">
        Lost the live connection
      </h2>
      <p className="mt-2 max-w-md text-[15px] leading-relaxed text-ink-soft">
        The dashboard can&apos;t reach Firestore right now. Check your network
        and the keys in{" "}
        <span className="font-mono text-[13px] text-ink">.env.local</span>, then
        reload the page.
      </p>
    </section>
  );
}

function DeniedNotice() {
  return (
    <section className="mt-12 border-l-2 border-signal py-1 pl-5">
      <h2 className="font-display text-xl tracking-tight">
        This group belongs to another account.
      </h2>
      <p className="mt-2 max-w-md text-[15px] leading-relaxed text-ink-soft">
        The founder who claimed it in{" "}
        <span className="font-mono text-[13px] text-ink">/connect</span> is the
        only one who can see its dashboard. Sign out, sign in with that
        account, or connect a group you own.
      </p>
    </section>
  );
}
