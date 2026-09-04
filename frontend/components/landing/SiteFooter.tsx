import Link from "next/link";
import { BOT_HANDLE } from "@/lib/onboarding";

export function SiteFooter() {
  return (
    <footer className="mt-16 flex flex-wrap items-baseline justify-between gap-2 border-t border-rule py-5">
      <p className="text-xs text-ink-soft">
        Launch Guard — Telegram moderation for Web3 communities
      </p>
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-ink-soft">
        <span className="font-mono text-[11px]">{BOT_HANDLE}</span>
        <Link href="/dashboard" className="landing-link">
          Dashboard
        </Link>
      </p>
    </footer>
  );
}
