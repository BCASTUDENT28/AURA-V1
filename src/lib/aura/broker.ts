/**
 * Live execution is sealed. This interface exists so Phase 9 has a place to
 * land. Nothing in V0.1 may import an Angel One or Groww client.
 */
export const LIVE_EXECUTION_ENABLED = false;

export type BrokerKind = "NONE" | "ANGEL_ONE" | "GROWW";

export interface BrokerOrderRequest {
  symbol: string;
  side: "BUY" | "SELL";
  qty: number;
  limitPrice: number;
  stop: number | null;
}

export interface BrokerExecutionInterface {
  kind: BrokerKind;
  name: string;
  live: boolean;
  submit(req: BrokerOrderRequest): Promise<{ ok: false; reason: string }>;
}

export const sealedBroker: BrokerExecutionInterface = {
  kind: "NONE",
  name: "Sealed — paper desk only",
  live: false,
  async submit() {
    return {
      ok: false,
      reason: "Live execution is sealed. AURA V0.1 is a paper desk. Angel One is Phase 9.",
    };
  },
};

export async function submitLiveOrder(req: BrokerOrderRequest) {
  return sealedBroker.submit(req);
}
