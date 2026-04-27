"use client";

export type VerificationStatus = "verified" | "inference" | "unknown" | "post_state_checked";

interface VerificationPillProps {
  status: VerificationStatus;
  compact?: boolean;
}

const CODES: Record<VerificationStatus, string> = {
  verified: "VR",
  inference: "IN",
  unknown: "UN",
  post_state_checked: "SC",
};

const LABELS: Record<VerificationStatus, string> = {
  verified: "Verified",
  inference: "Inference",
  unknown: "Unknown",
  post_state_checked: "Post-state checked",
};

export function VerificationPill({ status, compact = false }: VerificationPillProps) {
  return (
    <span
      className={compact ? "verification-pill compact" : "verification-pill"}
      data-vstatus={status}
      title={LABELS[status]}
      aria-label={`Verification: ${LABELS[status]}`}
    >
      {compact ? null : CODES[status]}
    </span>
  );
}
