import { useQuery } from "@tanstack/react-query";

import { getAsset, type AssetResponse, type UUID } from "../api/client";

export function useAsset(assetId: UUID | null | undefined) {
  return useQuery<AssetResponse>({
    enabled: Boolean(assetId),
    queryKey: ["asset", assetId],
    queryFn: () => getAsset(assetId as UUID),
    staleTime: 60_000,
  });
}
