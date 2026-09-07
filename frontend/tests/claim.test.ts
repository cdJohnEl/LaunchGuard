import { describe, expect, it } from "vitest";
import { claimDeniedMessage, claimState } from "@/lib/claim";

describe("claimState", () => {
  it("treats missing, null, and empty owner as unowned", () => {
    expect(claimState(undefined, "u1")).toBe("unowned");
    expect(claimState(null, "u1")).toBe("unowned");
    expect(claimState("", "u1")).toBe("unowned");
  });

  it("recognizes the owner", () => {
    expect(claimState("u1", "u1")).toBe("mine");
  });

  it("recognizes another account's claim", () => {
    expect(claimState("u2", "u1")).toBe("taken");
  });

  it("never matches by truthiness alone", () => {
    expect(claimState("1", "1")).toBe("mine");
    expect(claimState("1", "12")).toBe("taken");
  });
});

describe("claimDeniedMessage", () => {
  it("is null when action is possible", () => {
    expect(claimDeniedMessage("unowned")).toBeNull();
    expect(claimDeniedMessage("mine")).toBeNull();
  });

  it("explains a taken group", () => {
    expect(claimDeniedMessage("taken")).toContain("already claimed");
  });
});
