"use client";

import { useEffect, useState } from "react";
import {
  collection,
  getAggregateFromServer,
  count,
  query,
  sum,
  where,
} from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import { formatScamCount } from "@/lib/counter";
import { SetupRequired } from "@/components/landing/SetupRequired";

type RecordState =
  | { s: "loading" }
  | { s: "error" }
  | { s: "ready"; blocked: number; groups: number };

/**
 * The live record: total scams blocked (server-side sum of scams_blocked) and
 * groups protected (server-side count of docs with active true). Aggregations,
 * not document downloads: visitors never read other founders' docs, and the
 * numbers survive locked-down rules. Quiet while loading, honest when
 * Firestore is down, and an honest zero when nothing has been blocked yet.
 */
export function LiveRecord() {
  const [state, setState] = useState<RecordState>({ s: "loading" });

  useEffect(() => {
    if (!firebaseConfigured) return;
    let cancelled = false;
    (async () => {
      try {
        const groups = collection(db, "groups");
        const [blockedAgg, activeAgg] = await Promise.all([
          getAggregateFromServer(groups, { blocked: sum("scams_blocked") }),
          getAggregateFromServer(query(groups, where("active", "==", true)), {
            protected: count(),
          }),
        ]);
        const blocked = Math.max(0, Math.trunc(blockedAgg.data().blocked ?? 0));
        const groupsActive = activeAgg.data().protected ?? 0;
        if (!cancelled) setState({ s: "ready", blocked, groups: groupsActive });
      } catch (error) {
        console.error(error);
        if (!cancelled) setState({ s: "error" });
      }
    })();
    return () => {
      cancelled = true;
    };
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
