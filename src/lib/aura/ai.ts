import { createServerFn } from "@tanstack/react-start";

export type ResearchInput = {
  symbol: string;
  name: string;
  action: string;
  confidence: number;
  regime: string;
  regimeNotes: string;
  strategy: string;
  strategyReason: string;
  invalidation: string;
  similar: string;
  evidence: string[];
  contradictions: string[];
  risk: string;
  indicators: string;
  lineage: string;
};

export const reviewSetup = createServerFn({ method: "POST" })
  .validator((input: ResearchInput) => input)
  .handler(async ({ data }) => {
    const apiKey = process.env.XAI_API_KEY;
    if (!apiKey) {
      return { ok: false as const, error: "AI research is unavailable in this environment." };
    }

    const system = `You are AURA's research analyst for Indian cash equities. You do not place orders. You do not predict the future. You do not invent numbers.

Rules:
- Use ONLY the computed evidence provided. If a figure is missing, say so.
- Separate signal, probability, confidence, risk, historical evidence, and uncertainty.
- Never claim a strategy is profitable unless the provided metrics say so.
- Never guarantee returns. Never say "100%" or "sure shot".
- If contradictions exist, lead with them.
- Cite the strategy version and dataset version when you refer to the signal.
- End with: what would invalidate the view, and what a risk manager would refuse.
- Keep it under 280 words. Plain professional English. No emoji. No hype.`;

    const user = `Symbol: ${data.symbol} (${data.name})
Action from decision engine: ${data.action}
Confidence: ${(data.confidence * 100).toFixed(0)}%
Risk tag: ${data.risk}
Regime: ${data.regime} — ${data.regimeNotes}
Strategy: ${data.strategy}
Strategy reason: ${data.strategyReason}
Invalidation: ${data.invalidation}
Similarity: ${data.similar}
Evidence:
- ${data.evidence.join("\n- ")}
Contradictions:
- ${data.contradictions.join("\n- ")}
Indicators: ${data.indicators}
Lineage: ${data.lineage}

Write a research note. Do not recommend live trading. This is a paper environment with simulated data.`;

    const res = await fetch("https://api.x.ai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "grok-4.5",
        max_tokens: 700,
        temperature: 0.3,
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
      }),
    });
    if (!res.ok) {
      return { ok: false as const, error: `Research desk unavailable (${res.status}).` };
    }
    const body = (await res.json()) as {
      choices: { message: { content: string } }[];
    };
    return { ok: true as const, text: body.choices[0]?.message.content ?? "" };
  });
