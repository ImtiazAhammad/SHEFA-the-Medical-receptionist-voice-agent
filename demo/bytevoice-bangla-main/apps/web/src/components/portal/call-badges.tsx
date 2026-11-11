import { Badge, LivePill } from "@/components/portal/badge";
import { CALL_OUTCOME_LABELS, CALL_STATUS_LABELS } from "@/constants/portal";
import type { CallOutcome, CallStatus } from "@/types/database";

export function CallStatusBadges({ status, outcome }: { status: CallStatus; outcome: CallOutcome | null }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {status === "in_progress" ? (
        <LivePill />
      ) : status === "failed" ? (
        <Badge tone={CALL_STATUS_LABELS.failed.tone}>{CALL_STATUS_LABELS.failed.label}</Badge>
      ) : null}
      {outcome ? (
        <Badge tone={CALL_OUTCOME_LABELS[outcome].tone}>{CALL_OUTCOME_LABELS[outcome].label}</Badge>
      ) : status === "completed" ? (
        <Badge tone="slate">Processing</Badge>
      ) : null}
    </span>
  );
}
