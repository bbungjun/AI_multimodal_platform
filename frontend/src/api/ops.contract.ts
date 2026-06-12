import { getOpsHealth, type OpsHealthResponse } from "./client";

function expectOpsClientContract() {
  const result: Promise<OpsHealthResponse> = getOpsHealth();

  void result;
}

void expectOpsClientContract;
