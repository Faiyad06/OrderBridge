// Display formatting only. Authoritative arithmetic happens on the server in integer minor units.
export function cny(minor: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (minor === null || minor === undefined) return "—";
  const neg = minor < 0;
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const cents = (abs % 100).toString().padStart(2, "0");
  return `${neg ? "-" : opts.sign ? "+" : ""}CNY ${whole}.${cents}`;
}

export function cnyShort(minor: number): string {
  const v = Math.round(minor / 100);
  const k = Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`;
  return k;
}

export const toDecimalString = (minor: number) => `${Math.trunc(minor / 100)}.${String(Math.abs(minor % 100)).padStart(2, "0")}`;

export const statusLabel: Record<string, string> = {
  synthetic: "Synthetic", assumed: "Assumed", parsed_unconfirmed: "Parsed, unconfirmed", user_confirmed: "User confirmed", missing: "Missing",
};
