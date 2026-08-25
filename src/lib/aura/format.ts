const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const inrDec = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatInr(n: number, decimals = false): string {
  return (decimals ? inrDec : inr).format(n);
}

export function formatInrCompact(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(2)} L`;
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)}k`;
  return formatInr(n, true);
}

export function formatPct(n: number, digits = 2): string {
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(digits)}%`;
}

export function formatNum(n: number, digits = 2): string {
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPrice(n: number): string {
  if (n >= 1000) return n.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  return n.toFixed(2);
}

export function formatVolume(n: number): string {
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return String(Math.round(n));
}

export function formatIst(ts: number, withTime = true): string {
  const d = new Date(ts);
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  };
  return new Intl.DateTimeFormat("en-IN", opts).format(d);
}

export function signedClass(n: number): "up" | "down" | "flat" {
  if (n > 1e-9) return "up";
  if (n < -1e-9) return "down";
  return "flat";
}

export const REGIME_LABEL: Record<string, string> = {
  BULL_TREND: "Bull trend",
  BEAR_TREND: "Bear trend",
  RANGE: "Range",
  HIGH_VOL: "High volatility",
  LOW_VOL: "Low volatility",
  BREAKOUT: "Breakout",
  MEAN_REVERT: "Mean reversion",
  STRESS: "Stress",
};

export const ACTION_LABEL: Record<string, string> = {
  BUY: "Buy",
  SELL: "Sell",
  HOLD: "Hold",
  SKIP: "Skip",
};
