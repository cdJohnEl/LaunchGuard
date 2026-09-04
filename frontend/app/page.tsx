import type { Metadata } from "next";
import Link from "next/link";
import { BOT_HANDLE, TELEGRAM_DEEP_LINK } from "@/lib/onboarding";
import { SiteHeader } from "@/components/landing/SiteHeader";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { LiveRecord } from "@/components/landing/LiveRecord";

export const metadata: Metadata = {
  title: "Launch Guard — Telegram moderation for Web3 communities",
  description:
    "A Telegram bot that deletes scams from your group before members see them: a blacklist plus an AI intent check, with instant answers to your FAQ keywords. Setup is three steps.",
};

const ENGINE_ROWS: { term: string; detail: string }[] = [
  {
    term: "Blacklist",
    detail:
      "Known scam wallets, contract addresses, and phrases are deleted the moment they appear.",
  },
  {
    term: "AI intent",
    detail:
      "Messages the list misses get a second read for scam patterns — a seed-phrase request, a too-good trade — and are deleted too.",
  },
  {
    term: "FAQ answers",
    detail:
      "Not every unknown message is a scam. For the questions your members repeat, the bot answers instantly from your keyword pairs.",
  },
];

export default function LandingPage() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[880px] flex-col px-6 md:px-10">
      <SiteHeader />

      <main className="grow">
        {/* Hero: one sentence, one primary action. */}
        <section className="mt-12 md:mt-16">
          <p className="kicker">Telegram bot for Web3 groups</p>
          <h1 className="mt-4 max-w-[24ch] font-display text-[clamp(2.1rem,5.4vw,3.35rem)] font-medium leading-[1.08] tracking-[-0.02em]">
            Launch Guard deletes scams from your Telegram group{" "}
            <span className="italic">before your members see them.</span>
          </h1>
          <p className="mt-5 max-w-[58ch] text-[16px] leading-relaxed text-ink-soft">
            One bot, two filters: a blacklist for known scams and an AI read
            for anything that slips past it. It answers your FAQ keywords too,
            so you stop pasting the same reply at 2am.
          </p>

          <div className="mt-7 flex flex-wrap items-center gap-3">
            <a
              className="btn-primary"
              href={TELEGRAM_DEEP_LINK}
              target="_blank"
              rel="noreferrer"
            >
              Add to group
              <span aria-hidden="true" className="font-mono">
                ↗
              </span>
            </a>
            <Link className="btn-quiet" href="/connect">
              I already added it
            </Link>
          </div>
          <p className="mt-3 font-mono text-xs text-ink-soft">
            Opens Telegram and requests the Delete messages admin right —
            approve it in step 2.
          </p>
        </section>

        {/* The live record: real totals, dotted leaders like the FAQ list. */}
        <LiveRecord />

        {/* Signature element, spent here only: the numbered spine. */}
        <section id="setup" className="mt-16 md:mt-20">
          <p className="kicker">Setup</p>
          <h2 className="mt-3 font-display text-[26px] font-semibold tracking-tight md:text-[30px]">
            Three steps, in this order.
          </h2>

          <ol className="mt-8 border-l border-rule-strong">
            <li className="relative pb-12 pl-8 md:pl-12">
              <span className="station-numeral" aria-hidden="true">
                1
              </span>
              <h3 className="font-display text-[20px] font-semibold tracking-tight">
                Add the bot to your group
              </h3>
              <p className="mt-2 max-w-[52ch] text-[15px] leading-relaxed text-ink-soft">
                The link opens Telegram&apos;s group picker with the Delete
                messages right already requested. Pick your group and confirm.
              </p>
              <p className="mt-3">
                <a
                  className="landing-link"
                  href={TELEGRAM_DEEP_LINK}
                  target="_blank"
                  rel="noreferrer"
                >
                  Add to group{" "}
                  <span aria-hidden="true" className="font-mono">
                    ↗
                  </span>
                </a>
              </p>
            </li>

            <li className="relative pb-12 pl-8 md:pl-12">
              <span className="station-numeral" aria-hidden="true">
                2
              </span>
              <h3 className="font-display text-[20px] font-semibold tracking-tight">
                Make the bot an admin
              </h3>
              <p className="mt-2 max-w-[52ch] text-[15px] leading-relaxed text-ink-soft">
                In the group, open{" "}
                <strong className="font-semibold text-ink">
                  Settings → Administrators → Add admin
                </strong>
                , choose{" "}
                <span className="font-mono text-[13px] text-ink">
                  {BOT_HANDLE}
                </span>
                , and turn on{" "}
                <strong className="font-semibold text-ink">
                  Delete messages
                </strong>
                . Without that right the bot can&apos;t remove anything.
              </p>
            </li>

            <li className="relative pb-12 pl-8 last:pb-0 md:pl-12">
              <span className="station-numeral" aria-hidden="true">
                3
              </span>
              <h3 className="font-display text-[20px] font-semibold tracking-tight">
                Connect your chat id and set your FAQ
              </h3>
              <p className="mt-2 max-w-[52ch] text-[15px] leading-relaxed text-ink-soft">
                Every group has a numeric chat id. Paste it once and your
                dashboard follows the group — scams blocked, live status, and
                the keyword → answer pairs the bot replies with instantly.
              </p>
              <p className="mt-3">
                <Link className="landing-link" href="/connect">
                  Connect your group{" "}
                  <span aria-hidden="true" className="font-mono">
                    →
                  </span>
                </Link>
              </p>
            </li>
          </ol>
        </section>

        {/* The engine: what the two tiers plus the FAQ actually do. */}
        <section className="mt-16 md:mt-20">
          <p className="kicker">The engine</p>
          <h2 className="mt-3 font-display text-[26px] font-semibold tracking-tight md:text-[30px]">
            How it decides what to delete.
          </h2>
          <dl className="mt-6">
            {ENGINE_ROWS.map((row) => (
              <div
                key={row.term}
                className="grid gap-1 border-t border-rule py-5 md:grid-cols-[140px_1fr] md:gap-6"
              >
                <dt className="text-[15px] font-semibold text-ink">
                  {row.term}
                </dt>
                <dd className="max-w-[62ch] text-[15px] leading-relaxed text-ink-soft">
                  {row.detail}
                </dd>
              </div>
            ))}
          </dl>
          <div className="border-t border-rule" />
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
