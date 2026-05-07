/**
 * tradeBlotterLogic
 *
 * Pure functions for the trade blotter — exported separately so tests
 * can import them without pulling in React hooks or browser globals.
 */

import type { Trade, TradeStats, TradeStatus } from "./useTradeBlotter";

// Re-export types needed by consumers of this module
export type { Trade, TradeStats, TradeStatus };

// ─── WS event payloads ────────────────────────────────────────────────────────

export interface TradeWsMessage {
  type?: string;
  payload?: Record<string, unknown>;
  ts?: string;
}

// ─── Computed stats ───────────────────────────────────────────────────────────

export function computeStats(trades: Trade[]): TradeStats {
  const todayIso = new Date().toISOString().slice(0, 10);
  let openCount = 0;
  let todayPnl = 0;
  let wins = 0;
  let closedCount = 0;
  let bestTrade = 0;

  for (const t of trades) {
    if (t.status === "open") openCount++;
    if (t.status === "closed" && t.pnl_usd !== undefined) {
      closedCount++;
      if (t.pnl_usd > 0) wins++;
      if (t.pnl_usd > bestTrade) bestTrade = t.pnl_usd;
      const closeDay = (t.closed_at ?? "").slice(0, 10);
      if (closeDay === todayIso) todayPnl += t.pnl_usd;
    }
  }

  return {
    open_count: openCount,
    today_pnl_usd: todayPnl,
    win_rate: closedCount > 0 ? wins / closedCount : 0,
    total_trades: trades.length,
    best_trade_usd: bestTrade,
  };
}

// ─── WS event → trade list mutation ──────────────────────────────────────────

export function applyWsEventToTrades(
  trades: Trade[],
  msg: TradeWsMessage
): Trade[] | null {
  const type = msg.type ?? "";
  const payload = msg.payload ?? {};
  const tradeId = payload.trade_id as string | undefined;

  if (!tradeId && type !== "atlas.order_placed") return null;

  switch (type) {
    case "atlas.order_placed": {
      const id = (payload.trade_id as string | undefined) ?? `ws-${Date.now()}`;
      const existing = trades.findIndex((t) => t.trade_id === id);
      const newTrade: Trade = {
        trade_id: id,
        pair: (payload.pair as string | undefined) ?? "UNKNOWN",
        side: (payload.side as "buy" | "sell" | undefined) ?? "buy",
        direction: payload.direction as "LONG" | "SHORT" | undefined,
        size: (payload.size as number | undefined) ?? 0,
        leverage: payload.leverage as number | undefined,
        entry_price: payload.entry_price as number | undefined,
        status: "placed",
        is_paper: (payload.is_paper as boolean | undefined) ?? true,
        signal_id: payload.signal_id as string | undefined,
        created_at: msg.ts ?? new Date().toISOString(),
      };
      if (existing >= 0) {
        return trades.map((t, i) => (i === existing ? { ...t, ...newTrade } : t));
      }
      return [...trades, newTrade];
    }

    case "atlas.position_opened": {
      if (!tradeId) return null;
      const idx = trades.findIndex((t) => t.trade_id === tradeId);
      if (idx < 0) return null;
      return trades.map((t, i) =>
        i === idx
          ? {
              ...t,
              entry_price: (payload.entry_price as number | undefined) ?? t.entry_price,
              status: "open" as TradeStatus,
              opened_at: (payload.opened_at as string | undefined) ?? msg.ts ?? t.opened_at,
            }
          : t
      );
    }

    case "atlas.position_closed": {
      if (!tradeId) return null;
      const idx = trades.findIndex((t) => t.trade_id === tradeId);
      if (idx < 0) return null;
      return trades.map((t, i) =>
        i === idx
          ? {
              ...t,
              exit_price: payload.exit_price as number | undefined,
              pnl_usd: payload.pnl_usd as number | undefined,
              pnl_pct: payload.pnl_pct as number | undefined,
              status: "closed" as TradeStatus,
              close_reason: payload.close_reason as string | undefined,
              closed_at: (payload.closed_at as string | undefined) ?? msg.ts ?? t.closed_at,
            }
          : t
      );
    }

    case "atlas.order_cancelled": {
      if (!tradeId) return null;
      const idx = trades.findIndex((t) => t.trade_id === tradeId);
      if (idx < 0) return null;
      return trades.map((t, i) =>
        i === idx ? { ...t, status: "cancelled" as TradeStatus } : t
      );
    }

    default:
      return null;
  }
}
