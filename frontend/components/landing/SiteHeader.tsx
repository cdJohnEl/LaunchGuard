import Link from "next/link";

/**
 * Site chrome shared by the landing pages: the same wordmark, kicker, and
 * double rule the dashboard uses, so every route reads as one publication.
 */
export function SiteHeader() {
  return (
    <header className="pt-10">
      <div className="flex items-baseline justify-between gap-4">
        <Link
          href="/"
          className="font-display text-[26px] font-semibold leading-none tracking-[-0.01em] text-ink"
        >
          Launch <span className="font-medium italic">Guard</span>
        </Link>
        <p className="kicker text-right">Telegram moderation · Web3 founders</p>
      </div>
      <div className="mt-4 border-t-2 border-ink" />
      <div className="mt-[3px] border-t border-ink" />
    </header>
  );
}
