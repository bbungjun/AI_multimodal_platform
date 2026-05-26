import {
  deleteGeneration,
  type AssetKind,
  type GenerationListParams,
  type UUID,
} from "./client";

// Compile-time guard for the History API shape; this file is not imported by the app bundle.
function expectHistoryClientContract() {
  const selectedAssetKind: AssetKind = "video";
  const historyParams: GenerationListParams = {
    asset_kind: selectedAssetKind,
    limit: 20,
    offset: 0,
  };
  const deleteResult: Promise<void> = deleteGeneration(
    "00000000-0000-0000-0000-000000000000" as UUID,
  );

  void historyParams;
  void deleteResult;
}

void expectHistoryClientContract;
