"use client";

import { useState } from "react";
import { dispatch, type DispatchResponse } from "@/lib/api";

export default function AtlasPage() {
  const [data, setData] = useState<DispatchResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      setData(await dispatch("show me my portfolio and open positions"));
    } finally {
      setLoading(false);
    }
  };

  const ledger = data?.responses["ledger"];
  const portfolio = ledger?.result.portfolio as
    | { total_value_usd: number; cash: number; holdings: Array<{ symbol: string; qty: number; value_usd: number }> }
    | undefined;
  const isMock = ledger?.result.mock === true;

  return (
    <>
      <h1>ATLAS</h1>
      <p className="muted">Read-only bridge to ATLAS FastAPI. {isMock && "(showing mock data — start ATLAS to see real)"}</p>
      <div className="card" style={{ marginBottom: "1rem" }}>
        <button onClick={refresh} disabled={loading}>
          {loading ? "Fetching…" : "Refresh"}
        </button>
      </div>

      {portfolio && (
        <div className="grid">
          <section className="card">
            <h2>Portfolio</h2>
            <div className="row">
              <span>Total value</span>
              <span className="mono">${portfolio.total_value_usd.toLocaleString()}</span>
            </div>
            <div className="row">
              <span>Cash</span>
              <span className="mono">${portfolio.cash.toLocaleString()}</span>
            </div>
          </section>
          <section className="card">
            <h2>Holdings</h2>
            {portfolio.holdings.map((h) => (
              <div key={h.symbol} className="row">
                <span className="mono">{h.symbol}</span>
                <span className="mono muted">{h.qty}</span>
                <span className="mono">${h.value_usd.toLocaleString()}</span>
              </div>
            ))}
          </section>
        </div>
      )}
    </>
  );
}
