import type { JsonObject, JobResponse } from "../api/types";

export type RepairInfo = {
  action: string | null;
  badge: string;
  deadLetter: boolean;
  detail: string;
  reason: string | null;
  title: string;
};

export function getRepairInfo(error: JsonObject | null): RepairInfo | null {
  if (!error) {
    return null;
  }

  const deadLetter = error.dead_letter === true;
  const action = stringValue(error.repair_action);
  const reason = stringValue(error.dead_letter_reason);

  if (!deadLetter && !action) {
    return null;
  }

  return {
    action,
    badge: deadLetter ? "Dead-letter" : "Repair",
    deadLetter,
    detail: repairDetail({ action, deadLetter, reason }),
    reason,
    title: deadLetter ? "Repair needed" : "Manual review needed",
  };
}

export function hasRepairSignal(job: Pick<JobResponse, "error" | "state">): boolean {
  return job.state === "failed" && getRepairInfo(job.error) !== null;
}

function repairDetail({
  action,
  deadLetter,
  reason,
}: {
  action: string | null;
  deadLetter: boolean;
  reason: string | null;
}): string {
  if (deadLetter && reason === "retry_exhausted") {
    return "Automatic provider retries were exhausted. Inspect the failure before creating a fresh retry job.";
  }

  if (action === "manual_retry_or_inspect") {
    return "This job needs operator review before another retry.";
  }

  return "Review the failure context before retrying this job.";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}
