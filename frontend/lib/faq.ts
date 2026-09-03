export const MAX_RESPONSE_LENGTH = 500;

export function validateFaqInput(
  rawKeyword: string,
  rawResponse: string,
): string | null {
  const keyword = rawKeyword.trim();
  const response = rawResponse.trim();
  if (!keyword) return "Enter a keyword.";
  if (keyword.includes(".")) return "A keyword can't contain periods.";
  if (!response) return "Enter a response.";
  if (response.length > MAX_RESPONSE_LENGTH) {
    return `Keep the response under ${MAX_RESPONSE_LENGTH} characters.`;
  }
  return null;
}

export function extractFaqPairs(value: unknown): [string, string][] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string")
    .map(([keyword, response]) => [keyword, response]);
}
