"use client";

/**
 * /atlas/trades — Live trade blotter page
 *
 * Layout: MockModeBanner → TradeKpiStrip → TradeTable (with filter bar) → TradeDetailDrawer
 * State: useTradeBlotter (REST + WS push), selected trade
 */

import { CSSProperties, useState } from "react";
import { MockModeBanner } from "@/components/atlas/MockModeBanner";
import { TradeKpiStrip } from "@/components/atlas/trades/TradeKpiStrip";
import { TradeTable } from "@/components/atlas/trades/TradeTable";
import { TradeDetailDrawer } from "@/components/atlas/trades/TradeDetailDrawer";
import { useTradeBlotter } from "@/hooks/useTradeBlotter";
import type { Trade } from "@/hooks/useTradeBlotter";
import { Dot } from "@/components/ops/Dot";

export default function TradesPage() {
  const { trades, stats, isLoading, error } = useTradeBlotter();
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
        background: "var(--ops-bg-void)",
      } as CSSProperties}
    >
      <MockModeBanner />

      {/* Page header */}
      <div
        style={{
          borderBottom: "1px solid var(--ops-line)",
          padding: "0.5rem 1rem",
          background: "var(--ops-bg-deep)",
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          flexShrink: 0,
        } as CSSProperties}
      >
        <span
          style={{
            fontFamily: "var(--ops-mono)",
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            fontWeight: 700,
            color: "var(--ops-agent-atlas)",
            textTransform: "uppercase",
          } as CSSProperties}
        >
          ATLAS · TRADES
        </span>

        {isLoading ? (
          <Dot kind="warn" pulse />
        ) : error ? (
          <Dot kind="crit" />
        ) : (
          <Dot kind="ok" pulse />
        )}

        {error && (
          <span
            style={{
              fontFamily: "var(--ops-mono)",
              fontSize: "0.65rem",
              color: "var(--ops-crit)",
            } as CSSProperties}
          >
            {error.message}
          </span>
        )}
      </div>

      {/* KPI strip */}
      <TradeKpiStrip stats={stats} />

      {/* Trade table */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        } as CSSProperties}
      >
        <TradeTable trades={trades} onSelectTrade={setSelectedTrade} />
      </div>

      {/* Detail drawer (slide-in overlay) */}
      <TradeDetailDrawer
        trade={selectedTrade}
        onClose={() => setSelectedTrade(null)}
      />
    </div>
  );
}
