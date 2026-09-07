"use client";

import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import { formatScamCount } from "@/lib/counter";
import { SetupRequired } from "@/components/landing/SetupRequired";

type StatsDoc = { total_blocked: number; active_groups: number };

type RecordState =
  | { s: "loading" }
  | { s: "error" }
  | { s: "ready"; blocked: number; groups: number };

function readStats(data: Record<string, unknown> | undefined): StatsDoc {
  const blocked = typeof data?.total_blocked === "number" ? data.total_blocked : 0;
  const groups = typeof data?.active_groups === "number" ? data.active_groups : 0;
  return {
    total_blocked: Number.isFinite(blocked) ? Math.max(0, Math.trunc(blocked)) : 0,
    active_groups: Number.isFinite(groups) ? Math.max(0, Math.trunc(groups)) : 0,
  };
}

/**
 * The live record, from the world-readable public/stats doc the bot
 * maintains (total scams blocked + active group count). Real-time via
 * onSnapshot; honest zeros; honest outage state.
 */
export function LiveRecord() {
  const [state, setState] = useState<RecordState>({ s: "loading" });

  useEffect(() => {
    if (!firebaseConfigured) return;
    const unsubscribe = onSnapshot(
      doc(db, "public", "stats"),
      (snapshot) => {
        if (!snapshot.exists()) {
          // No stats doc yet: nothing has happened. Honest zeros.
          setState({ s: "ready", blocked: 0, groups: 0 });
          return;
        }
        const stats = readStats(snapshot.data());
        setState({ s: "ready", blocked: stats.total_blocked, groups: stats.active_groups });
      },
      (error) => {
        console.error(error);
        setState({ s: "error" });
      },
    );
    return unsubscribe;
  }, []);

  if (!firebaseConfigured) {
    return (
      <section className="mt-14 md:mt-16" aria-label="Live record">
        <p className="kicker">Live record</p>
        <div className="mt-4">
          <SetupRequired heading="Live counts aren't wired up yet" />
        </div>
      </section>
    );
  }

  return (
    <section className="mt-14 md:mt-16" aria-label="Live record">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="kicker">Live record</h2>
        <p className="kicker flex items-center gap-2">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full bg-signal"
            aria-hidden="true"
          />
          Live
        </p>
      </div>

      {state.s === "loading" && (
        <div className="mt-4 min-h-[5.5rem] border-y border-rule py-5">
          <p className="sr-only">Loading live counts</p>
          <div className="h-3 w-56 bg-rule" aria-hidden="true" />
          <div className="mt-4 h-3 w-44 bg-rule" aria-hidden="true" />
        </div>
      )}

      {state.s === "error" && (
        <div className="mt-4 border-y border-rule py-5">
          <p aria-live="polite" className="sr-only">
            Live counts unavailable
          </p>
          <p className="max-w-[58ch] text-[15px] leading-relaxed text-ink-soft">
            Live counts are unavailable right now — the record didn&apos;t
            answer. The setup steps below don&apos;t depend on it.
          </p>
        </div>
      )}

      {state.s === "ready" && (
        <>
          <p aria-live="polite" className="sr-only">
            {`${formatScamCount(state.blocked)} scams blocked across ${state.groups} ${
              state.groups === 1 ? "group" : "groups"
            }`}
          </p>
          <dl className="mt-4 border-y border-rule py-5">
            <div className="flex items-baseline gap-3">
              <dt className="text-[15px] text-ink">Scams blocked, all groups</dt>
              <span className="leader" aria-hidden="true" />
              <dd className="font-mono text-[17px] tabular-nums text-ink">
                <span key={state.blocked} className="stat-rise">
                  {formatScamCount(state.blocked)}
                </span>
              </dd>
            </div>
            <div className="mt-3 flex items-baseline gap-3">
              <dt className="text-[15px] text-ink">Groups protected right now</dt>
              <span className="leader" aria-hidden="true" />
              <dd className="font-mono text-[17px] tabular-nums text-ink">
                <span key={state.groups} className="stat-rise">
                  {state.groups.toLocaleString("en-US")}
                </span>
              </dd>
            </div>
          </dl>
        </>
      )}

      <p className="mt-3 font-display text-[15px] italic leading-snug text-ink-soft">
        Counted live from the bot&apos;s own record. Zero means nothing has
        been blocked yet.
      </p>
    </section>
  );
}
