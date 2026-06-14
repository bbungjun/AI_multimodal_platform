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
    title: deadLetter ? "수동 복구가 필요합니다" : "운영자 검토가 필요합니다",
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
    return "자동 provider 재시도가 모두 소진되었습니다. 새 재시도 작업을 만들기 전에 실패 원인을 확인하세요.";
  }

  if (action === "manual_retry_or_inspect") {
    return "다시 시도하기 전에 운영자 검토가 필요한 작업입니다.";
  }

  return "이 작업을 재시도하기 전에 실패 컨텍스트를 확인하세요.";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}
