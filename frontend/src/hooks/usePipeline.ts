import { useQuery } from "@tanstack/react-query";

import { getPipeline, type PipelineResponse, type UUID } from "../api/client";
import { isTerminalJobState } from "./useJob";

export function usePipeline(parentJobId: UUID | undefined) {
  return useQuery<PipelineResponse>({
    enabled: Boolean(parentJobId),
    queryKey: ["pipeline", parentJobId],
    queryFn: () => getPipeline(parentJobId as UUID),
    refetchInterval: (query) => {
      const pipeline = query.state.data;
      if (
        pipeline &&
        isTerminalJobState(pipeline.parent.state) &&
        isTerminalJobState(pipeline.child.state)
      ) {
        return false;
      }
      return 2000;
    },
  });
}
