import { getAsset, type AssetResponse, type UUID } from "./client";

// Compile-time guard for the asset metadata API used by standalone I2V source previews.
function expectAssetClientContract() {
  const assetResult: Promise<AssetResponse> = getAsset(
    "00000000-0000-0000-0000-000000000000" as UUID,
  );

  void assetResult;
}

void expectAssetClientContract;
