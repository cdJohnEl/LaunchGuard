export function formatScamCount(value: number): string {
  if (!Number.isFinite(value)) return "0";
  return Math.max(0, Math.trunc(value)).toLocaleString("en-US");
}

export function formatIncrement(previous: number, next: number): string | null {
  if (!Number.isFinite(previous) || !Number.isFinite(next)) return null;
  const delta = Math.trunc(next) - Math.trunc(previous);
  return delta > 0 ? `+${delta.toLocaleString("en-US")}` : null;
}
