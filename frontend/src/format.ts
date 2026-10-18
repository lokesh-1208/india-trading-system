// Numbers and dates the way an Indian investor reads them.
const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export const missing = (value: unknown) => value === null || value === undefined || Number.isNaN(value);

export function price(value: number | null | undefined) {
  return missing(value) ? "–" : inr.format(value as number);
}
export function rupees(value: number | null | undefined, digits = 0) {
  if (missing(value)) return "–";
  const number = value as number;
  const text = digits ? inr.format(Math.abs(number)) : whole.format(Math.abs(number));
  return `${number < 0 ? "−" : ""}₹${text}`;
}
export function signedRupees(value: number | null | undefined) {
  if (missing(value)) return "–";
  return `${(value as number) >= 0 ? "+" : "−"}₹${whole.format(Math.abs(value as number))}`;
}
export function pct(value: number | null | undefined, digits = 1, signed = true) {
  if (missing(value)) return "–";
  const number = value as number;
  const text = Math.abs(number).toFixed(digits);
  if (!signed) return `${number < 0 ? "−" : ""}${text}%`;
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${text}%`;
}
/** A fraction (0.12) as a percent (12.0%). */
export function share(value: number | null | undefined, digits = 1, signed = false) {
  return missing(value) ? "–" : pct((value as number) * 100, digits, signed);
}
export function num(value: number | null | undefined, digits = 2) {
  return missing(value) ? "–" : (value as number).toLocaleString("en-IN", {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}
export function crore(value: number | null | undefined) {
  if (missing(value)) return "–";
  const number = value as number;
  return number >= 100000 ? `₹${(number / 100000).toFixed(2)} lakh cr` : `₹${whole.format(number)} cr`;
}
export function day(value: string | null | undefined, withYear = false) {
  if (!value) return "–";
  const date = new Date(value);
  return date.toLocaleDateString("en-IN", {
    weekday: "short", day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}),
  });
}
export function dateTime(value: string | null | undefined) {
  if (!value) return "–";
  const date = new Date(value);
  return date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}
export function tone(value: number | null | undefined) {
  if (missing(value) || value === 0) return "muted";
  return (value as number) > 0 ? "up" : "down";
}
