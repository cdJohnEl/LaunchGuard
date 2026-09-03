import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#FAF9F6",
        ink: {
          DEFAULT: "#1C1917",
          soft: "#57534E",
          faint: "#A8A29E",
          hover: "#33302C",
        },
        rule: {
          DEFAULT: "#E7E5E4",
          strong: "#D6D3D1",
        },
        signal: {
          DEFAULT: "#B42318",
          tint: "#F7E9E7",
        },
      },
      fontFamily: {
        display: [
          "var(--font-newsreader)",
          "Charter",
          "Georgia",
          "Times New Roman",
          "serif",
        ],
        sans: [
          "var(--font-inter)",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "var(--font-plexmono)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
