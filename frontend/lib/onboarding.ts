export const TELEGRAM_DEEP_LINK =
  "https://t.me/web3_replyguy_bot?startgroup&admin=delete_messages";

export const BOT_HANDLE = "@web3_replyguy_bot";

/**
 * Removes one matching pair of surrounding quotes, if present.
 * `"-100123"` -> `-100123`, `'-100123'` -> `-100123`, `"abc'` stays as-is.
 */
function stripSurroundingQuotes(value: string): string {
  if (
    value.length >= 2 &&
    (value.startsWith('"') || value.startsWith("'")) &&
    value.endsWith(value[0])
  ) {
    return value.slice(1, -1);
  }
  return value;
}

/**
 * Normalizes a pasted chat id. Trims whitespace, strips one pair of
 * surrounding quotes, then accepts an optional leading dash followed by
 * digits only. Returns the normalized id, or null when the input is not
 * a chat id (empty, a t.me link, prose, malformed numbers).
 */
export function normalizeChatId(raw: string): string | null {
  const value = stripSurroundingQuotes(raw.trim());
  if (!value) return null;
  return /^-?\d+$/.test(value) ? value : null;
}

/**
 * Field-level error copy for the connect form. Returns null when the input
 * normalizes cleanly; otherwise a message that says exactly what to paste.
 */
export function chatIdInputError(raw: string): string | null {
  if (normalizeChatId(raw) !== null) return null;
  const value = raw.trim();
  if (!value) {
    return "Paste your group's chat id first — it looks like -1001234567890.";
  }
  if (
    /^(https?:\/\/)?(www\.)?t\.me\//i.test(value) ||
    /^https?:\/\//i.test(value)
  ) {
    return "That's a group link, not a chat id. The id is numeric — for example -1001234567890.";
  }
  return "Chat ids are digits with an optional leading dash — for example -1001234567890. Check the value and paste it again.";
}
