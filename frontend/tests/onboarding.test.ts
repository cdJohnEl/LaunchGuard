import { describe, expect, it } from "vitest";
import {
  TELEGRAM_DEEP_LINK,
  chatIdInputError,
  normalizeChatId,
} from "@/lib/onboarding";

describe("normalizeChatId", () => {
  it("accepts plain digit ids", () => {
    expect(normalizeChatId("123456789")).toBe("123456789");
    expect(normalizeChatId("1001234567890")).toBe("1001234567890");
  });

  it("accepts ids with a leading dash", () => {
    expect(normalizeChatId("-1001234567890")).toBe("-1001234567890");
    expect(normalizeChatId("-42")).toBe("-42");
  });

  it("trims whitespace around the id", () => {
    expect(normalizeChatId("  -1001234567890 ")).toBe("-1001234567890");
    expect(normalizeChatId("\t123456789\n")).toBe("123456789");
  });

  it("strips one pair of surrounding quotes", () => {
    expect(normalizeChatId('"-1001234567890"')).toBe("-1001234567890");
    expect(normalizeChatId("'123456789'")).toBe("123456789");
    expect(normalizeChatId(' "-1001234567890" ')).toBe("-1001234567890");
  });

  it("rejects a pasted t.me link", () => {
    expect(normalizeChatId("https://t.me/my_group")).toBeNull();
    expect(normalizeChatId("http://t.me/joinchat/AbCdEf")).toBeNull();
    expect(normalizeChatId("t.me/web3_replyguy_bot")).toBeNull();
  });

  it("rejects garbage", () => {
    expect(normalizeChatId("group chat id")).toBeNull();
    expect(normalizeChatId("-100 123 456")).toBeNull();
    expect(normalizeChatId("12,345")).toBeNull();
    expect(normalizeChatId("abc123")).toBeNull();
    expect(normalizeChatId("--100123")).toBeNull();
    expect(normalizeChatId("100123-")).toBeNull();
    expect(normalizeChatId("- 100123")).toBeNull();
  });

  it("rejects empty input", () => {
    expect(normalizeChatId("")).toBeNull();
    expect(normalizeChatId("   ")).toBeNull();
    expect(normalizeChatId('""')).toBeNull();
    expect(normalizeChatId("''")).toBeNull();
  });
});

describe("chatIdInputError", () => {
  it("returns null for ids that normalize", () => {
    expect(chatIdInputError(" -1001234567890 ")).toBeNull();
    expect(chatIdInputError('"123456789"')).toBeNull();
  });

  it("asks for the id when the field is empty", () => {
    expect(chatIdInputError("")).toMatch(/chat id/i);
    expect(chatIdInputError("   ")).toMatch(/chat id/i);
  });

  it("recognizes a pasted invite link", () => {
    expect(chatIdInputError("https://t.me/my_group")).toMatch(/link/i);
  });

  it("states the format for garbage", () => {
    expect(chatIdInputError("hello")).toMatch(/-1001234567890/);
  });
});

describe("deep link contract", () => {
  it("targets the bot with startgroup and the delete-messages admin right", () => {
    expect(TELEGRAM_DEEP_LINK).toBe(
      "https://t.me/web3_replyguy_bot?startgroup&admin=delete_messages",
    );
    expect(TELEGRAM_DEEP_LINK).toContain("startgroup");
    expect(TELEGRAM_DEEP_LINK).toContain("admin=delete_messages");
  });
});
