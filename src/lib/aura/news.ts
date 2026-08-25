import { hashString, mulberry32 } from "./rng";
import type { NewsItem } from "./types";
import { PAPER_OPEN } from "./market";

const RAW: { headline: string; source: string; symbols: string[]; event: string; sentiment: number; impact: NewsItem["impact"] }[] = [
  { headline: "RBI holds repo rate; signals data-dependent path on liquidity", source: "Mint", symbols: ["HDFCBANK", "ICICIBANK", "SBIN", "NIFTY"], event: "Macro", sentiment: 0.12, impact: "HIGH" },
  { headline: "Reliance commissions new KG-D6 well; Street watches capex cadence", source: "ET", symbols: ["RELIANCE"], event: "Guidance", sentiment: 0.18, impact: "MEDIUM" },
  { headline: "TCS wins multi-year European bank mandate; deal TCV not disclosed", source: "Business Standard", symbols: ["TCS", "INFY", "HCLTECH"], event: "Contract", sentiment: 0.34, impact: "MEDIUM" },
  { headline: "SEBI reiterates algo-order tagging and static-IP rules for API users", source: "NSE circular", symbols: ["NIFTY"], event: "Regulatory", sentiment: 0, impact: "HIGH" },
  { headline: "Maruti flags rural demand softness in two-wheeler-adjacent commentary", source: "CNBC-TV18", symbols: ["MARUTI", "M&M", "TATAMOTORS"], event: "Guidance", sentiment: -0.22, impact: "MEDIUM" },
  { headline: "Sun Pharma US facility inspection closed without action, company says", source: "Reuters", symbols: ["SUNPHARMA", "CIPLA", "DRREDDY"], event: "Regulatory", sentiment: 0.28, impact: "MEDIUM" },
  { headline: "FII selling in banks continues for a third session; DII absorbs", source: "NDTV Profit", symbols: ["HDFCBANK", "ICICIBANK", "AXISBANK", "BANKNIFTY"], event: "Flows", sentiment: -0.15, impact: "MEDIUM" },
  { headline: "NTPC board to consider commercial-paper issue; no equity dilution", source: "BSE filing", symbols: ["NTPC", "POWERGRID"], event: "Capital", sentiment: 0.05, impact: "LOW" },
  { headline: "Bharti Airtel ARPU commentary mixed as tariff hikes anniversary", source: "Moneycontrol", symbols: ["BHARTIARTL"], event: "Earnings", sentiment: -0.08, impact: "MEDIUM" },
  { headline: "Crude slip eases OMCs; ONGC tracks the move lower in early trade", source: "Bloomberg", symbols: ["ONGC", "RELIANCE"], event: "Macro", sentiment: 0.1, impact: "LOW" },
  { headline: "IT hiring freeze chatter returns; mid-tier names more exposed", source: "The Hindu Business Line", symbols: ["WIPRO", "HCLTECH", "INFY"], event: "Sector", sentiment: -0.19, impact: "MEDIUM" },
  { headline: "Ultratech utilisation ticks up; cement prices stable in west", source: "ET Now", symbols: ["ULTRACEMCO"], event: "Sector", sentiment: 0.16, impact: "LOW" },
  { headline: "Bajaj Finance AUM growth in line; management flags competitive NIMs", source: "Company", symbols: ["BAJFINANCE"], event: "Earnings", sentiment: 0.04, impact: "MEDIUM" },
  { headline: "Tata Steel European operations remain a drag; India spreads hold", source: "Reuters", symbols: ["TATASTEEL", "JSWSTEEL"], event: "Guidance", sentiment: -0.11, impact: "MEDIUM" },
  { headline: "L&T mega-project pipeline cited by brokerages as FY27 support", source: "Kotak note", symbols: ["LT"], event: "Sector", sentiment: 0.22, impact: "LOW" },
];

export function getNews(now = PAPER_OPEN): NewsItem[] {
  const rng = mulberry32(hashString("news-v1"));
  return RAW.map((r, i) => ({
    id: `n-${i}`,
    ts: now - Math.floor(rng() * 36) * 3600000 - i * 900000,
    headline: r.headline,
    source: r.source,
    symbols: r.symbols,
    sentiment: r.sentiment,
    event: r.event,
    impact: r.impact,
  })).sort((a, b) => b.ts - a.ts);
}

export const NEWS_DISCLAIMER =
  "SAMPLE headlines with deterministic timestamps — not a live news feed. Sentiment is a label, not an impact forecast, and never places orders.";
