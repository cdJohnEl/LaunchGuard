"use client";

import { useEffect, useRef, useState } from "react";
import { formatIncrement, formatScamCount } from "@/lib/counter";

const CHIP_VISIBLE_MS = 1600;

export function BlockedCounter({ value }: { value: number }) {
  const [chip, setChip] = useState<string | null>(null);
  const prevRef = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    const inc = prev === null ? null : formatIncrement(prev, value);
    if (inc === null) {
      setChip(null);
      return;
    }
    setChip(inc);
    timerRef.current = window.setTimeout(
      () => setChip(null),
      CHIP_VISIBLE_MS,
    );
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, [value]);

  const display = formatScamCount(value);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="kicker">Scams blocked</h2>
        <p className="kicker flex items-center gap-2">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full bg-signal"
            aria-hidden="true"
          />
          Live
        </p>
      </div>

      <span className="sr-only" aria-live="polite">
        {`${display} scams blocked`}
      </span>

      <div className="mt-4 border-y border-rule py-6 md:py-8">
        <p className="stat-numeral" aria-hidden="true">
          <span key={value} className="stat-rise tabular-nums">
            {display}
          </span>
          {chip !== null && (
            <span
              key={`${chip}-${value}`}
              className="stat-rise ml-3 align-super font-mono text-lg font-medium text-signal md:text-xl"
              aria-hidden="true"
            >
              {chip}
            </span>
          )}
        </p>
      </div>

      <p className="mt-3 font-display text-[15px] italic leading-snug text-ink-soft">
        Every count is a scam deleted before your members saw it.
      </p>
    </div>
  );
}
