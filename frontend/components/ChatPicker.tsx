"use client";

import { useState } from "react";
import type { FormEvent } from "react";

type ChatPickerProps = {
  idPrefix: string;
  onConnect: (chatId: string) => void;
  variant: "bar" | "panel";
};

export function ChatPicker({ idPrefix, onConnect, variant }: ChatPickerProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const inputId = `${idPrefix}-chat-id`;
  const errorId = `${idPrefix}-chat-error`;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = draft.trim();
    if (!value) {
      setError("Enter a chat ID.");
      return;
    }
    setError(null);
    setDraft("");
    onConnect(value);
  }

  const describedBy = error ? errorId : undefined;

  if (variant === "bar") {
    return (
      <form onSubmit={submit} noValidate className="flex items-end gap-2">
        <div>
          <label htmlFor={inputId} className="kicker block">
            Chat ID
          </label>
          <input
            id={inputId}
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="-1001234567890"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className="input-line w-44 py-1 text-sm"
          />
          {error && (
            <p id={errorId} className="err">
              {error}
            </p>
          )}
        </div>
        <button type="submit" className="btn-quiet">
          Switch
        </button>
      </form>
    );
  }

  return (
    <section className="border border-rule-strong px-8 py-10 md:px-10">
      <p className="kicker">Set up</p>
      <h2 className="mt-2 font-display text-2xl tracking-tight md:text-3xl">
        Connect a group
      </h2>
      <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-soft">
        Enter the chat ID of the Telegram group the bot protects. It looks like{" "}
        <span className="font-mono text-[13px] text-ink">
          -1001234567890
        </span>{" "}
        — the dash included.
      </p>
      <form onSubmit={submit} noValidate className="mt-6 max-w-md">
        <label htmlFor={inputId} className="kicker block">
          Chat ID
        </label>
        <input
          id={inputId}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="-1001234567890"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className="input-line mt-1"
        />
        {error && (
          <p id={errorId} className="err">
            {error}
          </p>
        )}
        <button type="submit" className="btn-primary mt-5">
          Connect group
        </button>
      </form>
    </section>
  );
}
