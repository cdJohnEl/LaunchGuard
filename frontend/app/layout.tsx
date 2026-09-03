import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Launch Guard",
  description: "Telegram community protection for Web3 founders.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
