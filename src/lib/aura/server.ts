import { createServerFn } from "@tanstack/react-start";
import { getSql } from "@/lib/db";
import { emptyBook, type PaperBook } from "./paper";
import { STARTING_CASH, type Learning, type PaperFill, type PaperOrder } from "./types";

export type DeskSnapshot = {
  sessionId: string;
  book: PaperBook;
  learnings: Learning[];
  killSwitch: boolean;
  source: "postgres";
  lineage: { id: string; kind: string; name: string; version: string; status: string; notes: string }[];
  cost: {
    id: string;
    version: string;
    verified: boolean;
    sourceNote: string;
  } | null;
};

function newSessionId() {
  return `ps-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

async function openSession(sql: Awaited<ReturnType<typeof getSql>>, book: PaperBook, learnings: Learning[]) {
  const id = newSessionId();
  await sql`
    insert into paper_session (id, starting_cash, status, env, data_source)
    values (${id}, ${STARTING_CASH}, 'open', 'PAPER', 'SIMULATOR')
  `;
  await sql`
    insert into paper_book_state (session_id, cash, realized, daily_pnl, session_start_nav, kill_switch, book_json, learnings_json)
    values (
      ${id},
      ${book.cash},
      ${book.realized},
      ${book.dailyPnl},
      ${book.sessionStartNav},
      ${false},
      ${JSON.stringify(book)},
      ${JSON.stringify(learnings)}
    )
  `;
  return id;
}

export const loadDesk = createServerFn({ method: "GET" }).handler(async (): Promise<DeskSnapshot> => {
  const sql = await getSql();
  const open = await sql<{ id: string }>`
    select id from paper_session where status = 'open' order by started_at desc limit 1
  `;
  let sessionId = open[0]?.id;
  if (!sessionId) {
    sessionId = await openSession(sql, emptyBook(), []);
  }
  const state = await sql<{
    cash: number;
    realized: number;
    daily_pnl: number;
    session_start_nav: number;
    kill_switch: boolean;
    book_json: string;
    learnings_json: string;
  }>`
    select cash, realized, daily_pnl, session_start_nav, kill_switch, book_json, learnings_json
    from paper_book_state where session_id = ${sessionId}
  `;
  const row = state[0];
  let book = emptyBook();
  let learnings: Learning[] = [];
  let killSwitch = false;
  if (row) {
    try {
      book = { ...emptyBook(), ...(JSON.parse(row.book_json) as PaperBook) };
    } catch {
      book = emptyBook();
    }
    try {
      learnings = JSON.parse(row.learnings_json) as Learning[];
      if (!Array.isArray(learnings)) learnings = [];
    } catch {
      learnings = [];
    }
    killSwitch = Boolean(row.kill_switch);
  }
  const lineage = await sql<{
    id: string;
    kind: string;
    name: string;
    version: string;
    status: string;
    notes: string;
  }>`select id, kind, name, version, status, notes from aura_lineage order by kind, name`;
  const costRows = await sql<{
    id: string;
    version: string;
    verified: boolean;
    source_note: string;
  }>`select id, version, verified, source_note from aura_cost_config where is_current = true limit 1`;
  const c = costRows[0];
  return {
    sessionId,
    book,
    learnings,
    killSwitch,
    source: "postgres",
    lineage,
    cost: c
      ? { id: c.id, version: c.version, verified: Boolean(c.verified), sourceNote: c.source_note }
      : null,
  };
});

export const persistDesk = createServerFn({ method: "POST" })
  .validator((input: { sessionId: string; book: PaperBook; learnings: Learning[]; killSwitch: boolean }) => input)
  .handler(async ({ data }) => {
    const sql = await getSql();
    const { sessionId, book, learnings, killSwitch } = data;
    await sql`
      update paper_book_state
      set cash = ${book.cash},
          realized = ${book.realized},
          daily_pnl = ${book.dailyPnl},
          session_start_nav = ${book.sessionStartNav},
          kill_switch = ${killSwitch},
          book_json = ${JSON.stringify(book)},
          learnings_json = ${JSON.stringify(learnings)},
          updated_at = now()
      where session_id = ${sessionId}
    `;
    return { ok: true as const, sessionId };
  });

export const recordPaperOrder = createServerFn({ method: "POST" })
  .validator(
    (input: {
      sessionId: string;
      order: PaperOrder;
      fill?: PaperFill | null;
      lineage?: Record<string, string> | null;
    }) => input,
  )
  .handler(async ({ data }) => {
    const sql = await getSql();
    const o = data.order;
    await sql`
      insert into paper_orders (
        id, session_id, ts_ms, symbol, side, type, qty, limit_price, status,
        fill_price, costs_json, reject_reason, strategy_id, stop_px, target_px, lineage_json
      ) values (
        ${o.id}, ${data.sessionId}, ${o.ts}, ${o.symbol}, ${o.side}, ${o.type}, ${o.qty}, ${o.limitPrice}, ${o.status},
        ${o.fillPrice}, ${o.costs ? JSON.stringify(o.costs) : null}, ${o.rejectReason}, ${o.strategyId},
        ${o.stop}, ${o.target}, ${data.lineage ? JSON.stringify(data.lineage) : null}
      )
      on conflict (id) do update set
        status = excluded.status,
        fill_price = excluded.fill_price,
        costs_json = excluded.costs_json,
        reject_reason = excluded.reject_reason
    `;
    if (data.fill) {
      const f = data.fill;
      await sql`
        insert into paper_fills (id, session_id, order_id, ts_ms, symbol, side, qty, price, costs_json)
        values (${f.id}, ${data.sessionId}, ${f.orderId}, ${f.ts}, ${f.symbol}, ${f.side}, ${f.qty}, ${f.price}, ${JSON.stringify(f.costs)})
        on conflict (id) do nothing
      `;
    }
    return { ok: true as const };
  });

export const recordLearning = createServerFn({ method: "POST" })
  .validator((input: { sessionId: string; item: Learning }) => input)
  .handler(async ({ data }) => {
    const sql = await getSql();
    const l = data.item;
    await sql`
      insert into memory_learning (
        id, session_id, ts_ms, kind, setup, strategy_id, strategy_version_id,
        model_version_id, feature_version_id, dataset_version_id, regime, symbol,
        evidence, sample_size, min_sample_required, confidence, expires_ts, r_multiple
      ) values (
        ${l.id}, ${data.sessionId}, ${l.ts}, ${l.kind}, ${l.setup}, ${l.strategyId}, ${l.strategyVersion},
        ${l.modelVersionId ?? "model:regime-rules-v1"}, ${l.featureVersionId ?? "feature:feat-v1"},
        ${l.datasetVersionId ?? "dataset:sim-in-eq-20240821"}, ${l.regime}, ${l.symbol},
        ${l.evidence}, ${l.sampleSize}, ${l.minSampleRequired ?? 5}, ${l.confidence}, ${l.expiresTs}, ${l.rMultiple}
      )
      on conflict (id) do nothing
    `;
    return { ok: true as const };
  });

export const archiveAndReset = createServerFn({ method: "POST" })
  .validator((input: { sessionId: string }) => input)
  .handler(async ({ data }) => {
    const sql = await getSql();
    await sql`
      update paper_session set status = 'archived', closed_at = now()
      where id = ${data.sessionId} and status = 'open'
    `;
    const book = emptyBook();
    const sessionId = await openSession(sql, book, []);
    return { ok: true as const, sessionId, book };
  });

export const listLineage = createServerFn({ method: "GET" }).handler(async () => {
  const sql = await getSql();
  return sql<{
    id: string;
    kind: string;
    name: string;
    version: string;
    status: string;
    notes: string;
  }>`select id, kind, name, version, status, notes from aura_lineage order by kind, name`;
});
