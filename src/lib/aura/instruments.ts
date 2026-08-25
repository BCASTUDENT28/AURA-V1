import type { Instrument } from "./types";

export const INSTRUMENTS: Instrument[] = [
  { symbol: "NIFTY", name: "Nifty 50", sector: "Index", kind: "index", base: 24862, tick: 0.05, lot: 1, avgVolume: 2.4e8 },
  { symbol: "BANKNIFTY", name: "Nifty Bank", sector: "Index", kind: "index", base: 51240, tick: 0.05, lot: 1, avgVolume: 8.1e7 },
  { symbol: "RELIANCE", name: "Reliance Industries", sector: "Energy", kind: "equity", base: 1478, tick: 0.05, lot: 1, avgVolume: 6.2e6 },
  { symbol: "TCS", name: "Tata Consultancy", sector: "IT", kind: "equity", base: 4124, tick: 0.05, lot: 1, avgVolume: 2.1e6 },
  { symbol: "HDFCBANK", name: "HDFC Bank", sector: "Banks", kind: "equity", base: 1682, tick: 0.05, lot: 1, avgVolume: 1.4e7 },
  { symbol: "INFY", name: "Infosys", sector: "IT", kind: "equity", base: 1786, tick: 0.05, lot: 1, avgVolume: 6.8e6 },
  { symbol: "ICICIBANK", name: "ICICI Bank", sector: "Banks", kind: "equity", base: 1284, tick: 0.05, lot: 1, avgVolume: 1.1e7 },
  { symbol: "HINDUNILVR", name: "Hindustan Unilever", sector: "FMCG", kind: "equity", base: 2488, tick: 0.05, lot: 1, avgVolume: 1.4e6 },
  { symbol: "ITC", name: "ITC", sector: "FMCG", kind: "equity", base: 492, tick: 0.05, lot: 1, avgVolume: 1.2e7 },
  { symbol: "SBIN", name: "State Bank of India", sector: "Banks", kind: "equity", base: 812, tick: 0.05, lot: 1, avgVolume: 1.5e7 },
  { symbol: "BHARTIARTL", name: "Bharti Airtel", sector: "Telecom", kind: "equity", base: 1648, tick: 0.05, lot: 1, avgVolume: 5.4e6 },
  { symbol: "BAJFINANCE", name: "Bajaj Finance", sector: "Finance", kind: "equity", base: 9120, tick: 0.05, lot: 1, avgVolume: 9.2e5 },
  { symbol: "LT", name: "Larsen & Toubro", sector: "Infra", kind: "equity", base: 3584, tick: 0.05, lot: 1, avgVolume: 1.8e6 },
  { symbol: "HCLTECH", name: "HCL Technologies", sector: "IT", kind: "equity", base: 1688, tick: 0.05, lot: 1, avgVolume: 3.2e6 },
  { symbol: "AXISBANK", name: "Axis Bank", sector: "Banks", kind: "equity", base: 1124, tick: 0.05, lot: 1, avgVolume: 8.4e6 },
  { symbol: "ASIANPAINT", name: "Asian Paints", sector: "FMCG", kind: "equity", base: 2486, tick: 0.05, lot: 1, avgVolume: 1.1e6 },
  { symbol: "MARUTI", name: "Maruti Suzuki", sector: "Auto", kind: "equity", base: 12480, tick: 0.05, lot: 1, avgVolume: 4.8e5 },
  { symbol: "SUNPHARMA", name: "Sun Pharma", sector: "Pharma", kind: "equity", base: 1722, tick: 0.05, lot: 1, avgVolume: 2.4e6 },
  { symbol: "TITAN", name: "Titan Company", sector: "Consumer", kind: "equity", base: 3488, tick: 0.05, lot: 1, avgVolume: 1.2e6 },
  { symbol: "ULTRACEMCO", name: "UltraTech Cement", sector: "Cement", kind: "equity", base: 11840, tick: 0.05, lot: 1, avgVolume: 3.6e5 },
  { symbol: "M&M", name: "Mahindra & Mahindra", sector: "Auto", kind: "equity", base: 2784, tick: 0.05, lot: 1, avgVolume: 2.8e6 },
  { symbol: "TATAMOTORS", name: "Tata Motors", sector: "Auto", kind: "equity", base: 784, tick: 0.05, lot: 1, avgVolume: 1.4e7 },
  { symbol: "TATASTEEL", name: "Tata Steel", sector: "Metals", kind: "equity", base: 154, tick: 0.05, lot: 1, avgVolume: 2.8e7 },
  { symbol: "NTPC", name: "NTPC", sector: "Energy", kind: "equity", base: 412, tick: 0.05, lot: 1, avgVolume: 1.1e7 },
  { symbol: "POWERGRID", name: "Power Grid", sector: "Energy", kind: "equity", base: 328, tick: 0.05, lot: 1, avgVolume: 9.4e6 },
  { symbol: "ONGC", name: "ONGC", sector: "Energy", kind: "equity", base: 268, tick: 0.05, lot: 1, avgVolume: 1.6e7 },
  { symbol: "WIPRO", name: "Wipro", sector: "IT", kind: "equity", base: 512, tick: 0.05, lot: 1, avgVolume: 7.2e6 },
  { symbol: "CIPLA", name: "Cipla", sector: "Pharma", kind: "equity", base: 1548, tick: 0.05, lot: 1, avgVolume: 1.6e6 },
  { symbol: "DRREDDY", name: "Dr. Reddy's", sector: "Pharma", kind: "equity", base: 1284, tick: 0.05, lot: 1, avgVolume: 8.4e5 },
  { symbol: "JSWSTEEL", name: "JSW Steel", sector: "Metals", kind: "equity", base: 968, tick: 0.05, lot: 1, avgVolume: 4.2e6 },
];

export const BY_SYMBOL: Record<string, Instrument> = Object.fromEntries(
  INSTRUMENTS.map((i) => [i.symbol, i]),
);

export const SECTORS = [
  "Index",
  "Banks",
  "IT",
  "Energy",
  "Auto",
  "FMCG",
  "Pharma",
  "Metals",
  "Finance",
  "Infra",
  "Telecom",
  "Cement",
  "Consumer",
] as const;

export const UNIVERSE_NOTE =
  "NIFTY 50 subset + BANKNIFTY. Simulated, corporate-action adjusted. Not a live feed.";

export function getInstrument(symbol: string): Instrument {
  const i = BY_SYMBOL[symbol];
  if (!i) throw new Error(`Unknown instrument ${symbol}`);
  return i;
}
