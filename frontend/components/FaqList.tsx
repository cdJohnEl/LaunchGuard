"use client";

import { useMemo, useState } from "react";
import { deleteField, doc, updateDoc } from "firebase/firestore";
import { db } from "@/lib/firebase";

type FaqListProps = {
  chatId: string;
  pairs: [string, string][];
};

export function FaqList({ chatId, pairs }: FaqListProps) {
  const sorted = useMemo(
    () => [...pairs].sort((a, b) => a[0].localeCompare(b[0])),
    [pairs],
  );
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(keyword: string) {
    if (deleting !== null) return;
    setError(null);
    setDeleting(keyword);
    try {
      await updateDoc(doc(db, "groups", chatId), {
        [`faq_pairs.${keyword}`]: deleteField(),
      });
    } catch (cause) {
      console.error(cause);
      setError(`Couldn't remove "${keyword}". Check your connection and try again.`);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="kicker">Configured pairs</h2>
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">
          {sorted.length === 1 ? "1 pair" : `${sorted.length} pairs`}
        </span>
      </div>

      {error !== null && (
        <p role="alert" className="err mt-3">
          {error}
        </p>
      )}

      {sorted.length === 0 ? (
        <p className="mt-4 font-display text-[17px] italic leading-snug text-ink-soft">
          No pairs yet. Save a keyword and the bot answers it immediately.
        </p>
      ) : (
        <ul className="mt-1 divide-y divide-rule">
          {sorted.map(([keyword, response]) => (
            <li key={keyword} className="py-4">
              <div className="flex items-baseline gap-3">
                <h3
                  className="min-w-0 truncate font-mono text-[13px] font-medium tracking-tight"
                  title={keyword}
                >
                  {keyword}
                </h3>
                <span className="leader" aria-hidden="true" />
                <button
                  type="button"
                  onClick={() => remove(keyword)}
                  disabled={deleting !== null}
                  className="btn-text-danger shrink-0"
                >
                  {deleting === keyword ? "Removing…" : "Remove"}
                </button>
              </div>
              <p className="mt-1 max-w-[52ch] font-display text-[17px] leading-snug">
                {response}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
