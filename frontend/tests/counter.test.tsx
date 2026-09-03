import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("@/lib/firebase", () => ({
  app: {},
  db: {},
  firebaseConfigured: true,
}));

import { BlockedCounter } from "@/components/BlockedCounter";
import { formatIncrement, formatScamCount } from "@/lib/counter";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

afterEach(cleanup);

describe("formatScamCount", () => {
  it("renders zero and small values without grouping", () => {
    expect(formatScamCount(0)).toBe("0");
    expect(formatScamCount(7)).toBe("7");
  });

  it("groups thousands", () => {
    expect(formatScamCount(1287)).toBe("1,287");
    expect(formatScamCount(1234567)).toBe("1,234,567");
  });

  it("falls back to zero for missing or malformed input", () => {
    expect(formatScamCount(Number.NaN)).toBe("0");
    expect(formatScamCount(-5)).toBe("0");
    expect(formatScamCount(12.9)).toBe("12");
  });
});

describe("formatIncrement", () => {
  it("formats a single-block increment", () => {
    expect(formatIncrement(1283, 1284)).toBe("+1");
  });

  it("formats multi-unit jumps", () => {
    expect(formatIncrement(10, 23)).toBe("+13");
    expect(formatIncrement(999, 2001)).toBe("+1,002");
  });

  it("returns null when the count did not rise", () => {
    expect(formatIncrement(5, 5)).toBeNull();
    expect(formatIncrement(9, 8)).toBeNull();
  });
});

describe("BlockedCounter", () => {
  it("shows zero with its live-region text on first load", () => {
    render(<BlockedCounter value={0} />);
    expect(screen.getByText("Scams blocked")).toBeTruthy();
    expect(screen.getByText("0")).toBeTruthy();
    expect(screen.getByText("0 scams blocked")).toBeTruthy();
  });

  it("renders grouped numbers in the hero and the live region", () => {
    render(<BlockedCounter value={2048} />);
    expect(screen.getByText("2,048")).toBeTruthy();
    expect(screen.getByText("2,048 scams blocked")).toBeTruthy();
  });

  it("keeps the caption honest about what the number means", () => {
    render(<BlockedCounter value={3} />);
    expect(
      screen.getByText("Every count is a scam deleted before your members saw it."),
    ).toBeTruthy();
  });
});
