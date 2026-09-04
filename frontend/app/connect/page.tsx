import type { Metadata } from "next";
import { SiteHeader } from "@/components/landing/SiteHeader";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { ConnectFlow } from "@/components/landing/ConnectFlow";

export const metadata: Metadata = {
  title: "Connect your group — Launch Guard",
  description:
    "Paste your Telegram group's chat id to open its Launch Guard dashboard: scams blocked, live status, and FAQ pairs.",
};

export default function ConnectPage() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[880px] flex-col px-6 md:px-10">
      <SiteHeader />
      <main className="grow">
        <ConnectFlow />
      </main>
      <SiteFooter />
    </div>
  );
}
