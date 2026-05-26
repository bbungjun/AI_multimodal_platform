import { useQuery } from "@tanstack/react-query";

import { getGeneration, type JobResponse, type JobState, type UUID } from "../api/client";

const terminalStates: JobState[] = ["completed", "failed", "cancelled"];

export function useJob(jobId: UUID | undefined) {
  return useQuery<JobResponse>({
    enabled: Boolean(jobId),
    queryKey: ["job", jobId],
    queryFn: () => getGeneration(jobId as UUID),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      if (!state || terminalStates.includes(state)) {
        return false;
      }
      return 2000;
    },
  });
}

export function isTerminalJobState(state: JobState): boolean {
  return terminalStates.includes(state);
}
