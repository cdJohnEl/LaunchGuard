"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { doc, setDoc, updateDoc } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { validateFaqInput } from "@/lib/faq";

const NOTICE_VISIBLE_MS = 2000;

type FaqFormProps = {
  chatId: string;
  docExists: boolean;
};

export function FaqForm({ chatId, docExists }: FaqFormProps) {
  const [keyword, setKeyword] = useState("");
  const [response, setResponse] = useState("");
  const [fieldError, setFieldError] = useState<{
    field: "keyword" | "response";
    message: string;
  } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setFormError(null);

    const trimmedKeyword = keyword.trim();
    const trimmedResponse = response.trim();
    const message = validateFaqInput(trimmedKeyword, trimmedResponse);
    if (message !== null) {
      setFieldError({
        field: /keyword/i.test(message) ? "keyword" : "response",
        message,
      });
      return;
    }

    setFieldError(null);
    setBusy(true);
    try {
      const ref = doc(db, "groups", chatId);
      if (docExists) {
        await updateDoc(ref, { [`faq_pairs.${trimmedKeyword}`]: trimmedResponse });
      } else {
        await setDoc(
          ref,
          { faq_pairs: { [trimmedKeyword]: trimmedResponse } },
          { merge: true },
        );
      }
      setKeyword("");
      setResponse("");
      setNotice("Pair saved.");
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(
        () => setNotice(null),
        NOTICE_VISIBLE_MS,
      );
    } catch (error) {
      console.error(error);
      setFormError("Couldn't save the pair. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  const keywordError = fieldError?.field === "keyword";
  const responseError = fieldError?.field === "response";

  return (
    <div>
      <h2 className="kicker">Add a pair</h2>
      <p className="mt-2 text-[15px] leading-relaxed text-ink-soft">
        When a member&apos;s message contains the keyword, the bot replies with
        the response.
      </p>

      <form onSubmit={save} noValidate className="mt-6">
        <label htmlFor="faq-keyword" className="kicker block text-ink">
          Keyword
        </label>
        <input
          id="faq-keyword"
          type="text"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="contract address"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={keywordError ? true : undefined}
          aria-describedby={keywordError ? "faq-keyword-error" : undefined}
          className="input-line mt-1"
        />
        {keywordError && (
          <p id="faq-keyword-error" className="err">
            {fieldError.message}
          </p>
        )}

        <label htmlFor="faq-response" className="kicker mt-6 block text-ink">
          Response
        </label>
        <textarea
          id="faq-response"
          rows={3}
          value={response}
          onChange={(event) => setResponse(event.target.value)}
          placeholder="The contract address is pinned in our announcements channel."
          aria-invalid={responseError ? true : undefined}
          aria-describedby={responseError ? "faq-response-error" : undefined}
          className="input-line mt-1 resize-y"
        />
        {responseError && (
          <p id="faq-response-error" className="err">
            {fieldError.message}
          </p>
        )}

        <div className="mt-6 flex items-center gap-4">
          <button type="submit" disabled={busy} className="btn-primary">
            {busy ? "Saving…" : "Save pair"}
          </button>
          <p aria-live="polite" className="text-[13px] text-ink">
            {notice}
          </p>
        </div>
        {formError !== null && (
          <p role="alert" className="err">
            {formError}
          </p>
        )}
      </form>
    </div>
  );
}
