import type { JobResponse, PipelineResponse } from "../api/client";
import { toJobSummaryViewModel, toPipelineViewModel } from "./viewModels";

declare const job: JobResponse;
declare const pipeline: PipelineResponse;

const jobView = toJobSummaryViewModel(job);
const pipelineView = toPipelineViewModel(pipeline);

void jobView.id;
void jobView.stateLabel;
void jobView.assets;
void pipelineView.parent.assets;
void pipelineView.child.canRetry;
