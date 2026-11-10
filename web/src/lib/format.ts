const dateFmt = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC" });

/** UTC calendar date, YYYY-MM-DD. Section 8 evaluates against the UTC date. */
export function isoDate(value: string | undefined): string {
  if (!value) return "—";
  return value.length === 10 ? value : dateFmt.format(new Date(value));
}

/** Days from `from` to `to`, by UTC calendar date. */
export function daysBetween(from: string, to: string): number {
  const a = Date.parse(isoDate(from));
  const b = Date.parse(isoDate(to));
  return Math.round((b - a) / 86_400_000);
}

export function percent(part: number, whole: number): string {
  return whole === 0 ? "—" : `${Math.round((part / whole) * 100)}%`;
}

/** `control--mfa-privileged` → `mfa-privileged`. */
export function slug(id: string): string {
  return id.includes("--") ? id.slice(id.indexOf("--") + 2) : id;
}
