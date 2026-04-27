"use client";

export type Tier = 1 | 2 | 3 | 4 | 5;

interface TierBadgeProps {
  tier: Tier;
}

const TIER_TITLES: Record<Tier, string> = {
  1: "T1 — Mutation authority, irreversible",
  2: "T2 — Mutation authority, reversible",
  3: "T3 — Read-mutate boundary",
  4: "T4 — Read-only",
  5: "T5 — Passive observation",
};

export function TierBadge({ tier }: TierBadgeProps) {
  return (
    <span
      className="tier-badge"
      data-tier={tier}
      title={TIER_TITLES[tier]}
      aria-label={TIER_TITLES[tier]}
    >
      T{tier}
    </span>
  );
}
