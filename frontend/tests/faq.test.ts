import { describe, expect, it } from "vitest";
import {
  MAX_RESPONSE_LENGTH,
  extractFaqPairs,
  validateFaqInput,
} from "@/lib/faq";

describe("validateFaqInput", () => {
  it("rejects an empty keyword", () => {
    expect(validateFaqInput("", "The answer")).toBe("Enter a keyword.");
  });

  it("rejects a whitespace-only keyword", () => {
    expect(validateFaqInput("   ", "The answer")).toBe("Enter a keyword.");
  });

  it("rejects a keyword containing a period", () => {
    expect(validateFaqInput("contract.address", "The answer")).toBe(
      "A keyword can't contain periods.",
    );
  });

  it("rejects an empty response", () => {
    expect(validateFaqInput("price", "")).toBe("Enter a response.");
  });

  it("rejects a whitespace-only response", () => {
    expect(validateFaqInput("price", "   ")).toBe("Enter a response.");
  });

  it("rejects a response over the length cap", () => {
    const long = "a".repeat(MAX_RESPONSE_LENGTH + 1);
    expect(validateFaqInput("price", long)).toBe(
      `Keep the response under ${MAX_RESPONSE_LENGTH} characters.`,
    );
  });

  it("accepts a pair at exactly the length cap", () => {
    const atCap = "a".repeat(MAX_RESPONSE_LENGTH);
    expect(validateFaqInput("price", atCap)).toBeNull();
  });

  it("accepts a valid pair", () => {
    expect(validateFaqInput("contract address", "It's pinned above.")).toBeNull();
  });

  it("accepts inputs that only need trimming", () => {
    expect(validateFaqInput("  price  ", " Check the chart. ")).toBeNull();
  });
});

describe("extractFaqPairs", () => {
  it("returns an empty array for missing or non-map values", () => {
    expect(extractFaqPairs(undefined)).toEqual([]);
    expect(extractFaqPairs(null)).toEqual([]);
    expect(extractFaqPairs("nope")).toEqual([]);
    expect(extractFaqPairs(42)).toEqual([]);
  });

  it("keeps string values and drops everything else", () => {
    expect(extractFaqPairs({ a: "1", broken: 2, c: "3" })).toEqual([
      ["a", "1"],
      ["c", "3"],
    ]);
  });

  it("returns an empty array for an empty map", () => {
    expect(extractFaqPairs({})).toEqual([]);
  });
});
