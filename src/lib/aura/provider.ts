import {
  barsOf as simBarsOf,
  getUniverse,
  seedQuotes as simSeed,
  stepQuotes as simStep,
  type MarketUniverse,
} from "./market";
import type { Bar, Quote, Timeframe } from "./types";

export type DataProviderKind = "SIMULATOR" | "HISTORICAL" | "LIVE";

export interface DataProvider {
  kind: DataProviderKind;
  name: string;
  disclaimer: string;
  getUniverse(): MarketUniverse;
  barsOf(symbol: string, tf?: Timeframe): Bar[];
  seedQuotes(now: number): Record<string, Quote>;
  stepQuotes(
    quotes: Record<string, Quote>,
    dtSec: number,
    now: number,
    tick: number,
  ): Record<string, Quote>;
}

const simulatorProvider: DataProvider = {
  kind: "SIMULATOR",
  name: "AURA simulator",
  disclaimer: "Simulated, corporate-action adjusted. Not a live NSE feed. Not evidence of edge.",
  getUniverse,
  barsOf: simBarsOf,
  seedQuotes: simSeed,
  stepQuotes: simStep,
};

export const activeProvider: DataProvider = simulatorProvider;

export function historicalProvider(): DataProvider {
  return {
    kind: "HISTORICAL",
    name: "Historical (not wired)",
    disclaimer: "HistoricalDataProvider is Phase 3. Refusing rather than inventing a feed.",
    getUniverse() {
      throw new Error("HistoricalDataProvider is not wired.");
    },
    barsOf() {
      throw new Error("HistoricalDataProvider is not wired.");
    },
    seedQuotes() {
      throw new Error("HistoricalDataProvider is not wired.");
    },
    stepQuotes() {
      throw new Error("HistoricalDataProvider is not wired.");
    },
  };
}

export function liveMarketProvider(): DataProvider {
  return {
    kind: "LIVE",
    name: "Live (sealed)",
    disclaimer: "LiveMarketDataProvider is sealed. Do not connect a broker feed from this desk.",
    getUniverse() {
      throw new Error("Live market data is sealed.");
    },
    barsOf() {
      throw new Error("Live market data is sealed.");
    },
    seedQuotes() {
      throw new Error("Live market data is sealed.");
    },
    stepQuotes() {
      throw new Error("Live market data is sealed.");
    },
  };
}
