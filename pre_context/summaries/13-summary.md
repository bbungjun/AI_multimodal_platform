# krafton_assignment_13 요약

## 핵심 주제

I2V와 History 중심의 마지막 사용자 흐름 QA가 길게 이어진 세션입니다. I2V source preview, Generate 활성화 조건, pipeline/JobDetail 대기 UX, Veo provider constraint 문서화, History 필터/삭제/video preview, Prompt Enhancement 장애 진단까지 복구 단서가 많이 들어 있습니다.

## 주요 키워드

- I2V source image preview
- I2V Generate validation
- enhancement optional
- Pipeline I2V waiting UX
- JobDetail source context
- Veo safety filter / personGeneration
- History asset type filter
- terminal job deletion
- dependent job protection
- video preview / Range request
- Prompt Enhancement safe diagnostics
- stale frontend bundle

## 복구에 중요한 내용

- Veo troubleshooting 문서화 방향이 정리되었습니다.
  - I2V는 Live QA에서 성공했습니다.
  - source image에 없는 새 물체/행동을 넣는 I2V prompt는 reject될 수 있으며, 회복 방향은 “선택된 이미지의 내용을 보존하는 motion prompt”입니다.
  - 이전 T2V 실패는 submit/payload/인증 문제가 아니라 polling 이후 provider-side operation failure 또는 empty/filtered/no-output을 generic error로 뭉갠 것이 가장 가능성 높은 원인으로 정리되었습니다.
- Generate 화면의 I2V source preview가 보강되었습니다.
  - `/generate?mode=i2v&source_asset_id=...`로 진입하면 `getAsset(assetId)`로 source asset을 조회합니다.
  - source image를 `cinema-screen` 안에 표시해 사용자가 어떤 이미지를 영상화하는지 바로 볼 수 있게 했습니다.
  - 이 작업은 preview 표시 개선이며 submit payload/schema는 바꾸지 않는 범위로 제한되었습니다.
- I2V Generate 비활성화 문제의 기준이 확정되었습니다.
  - I2V는 prompt enhancement 없이도 `motion prompt + sourceAssetId + 유효한 Veo 옵션`이면 생성 가능해야 합니다.
  - source asset preview 조회 성공 여부나 accepted enhancement 상태가 Generate 버튼을 막으면 안 됩니다.
  - 이후 같은 증상이 다시 보였을 때는 코드상 enhancement gate가 아니라 stale frontend bundle 또는 URL/state에 `source_asset_id`가 없는 상황을 먼저 의심하라는 판단이 남아 있습니다.
- Pipeline T2I -> I2V 대기 UX가 개선되었습니다.
  - Backend/API/state 변경 없이 `PipelinePage` 중심의 frontend-only 개선으로 제한했습니다.
  - 정확한 Vertex progress percent가 없으므로 실제 진행률처럼 보이는 표현은 피하고, state 기반 단계 설명과 “estimated/state-based” 성격의 안내를 사용합니다.
  - Step 2 Veo I2V가 오래 걸릴 때 현재 단계, source image 연결 여부, polling 중임, Veo가 수 분 걸릴 수 있음을 보여주는 방향입니다.
  - I2V preview empty state도 queued/generating/polling/failed/completed-without-asset에 따라 문구를 다르게 두는 방향이 정리되었습니다.
- JobDetailPage의 active I2V 대기 화면도 보강되었습니다.
  - I2V job에 `source_asset_id`가 있고 아직 result asset이 없으면 Asset Viewer에 source image를 `Source context`로 표시합니다.
  - completed I2V에서는 기존 video player가 source preview보다 우선합니다.
  - 문구는 source image가 결과물이 아니라 I2V 입력이라는 점을 분명히 해야 합니다.
- Veo safety/provider constraint가 별도 복구 단서로 남았습니다.
  - children/all-age person I2V는 prompt 품질이나 source 연결 문제가 아니라 Veo `personGeneration` 기본 정책과 project allowlist 제한으로 block될 수 있습니다.
  - 성인 인물 I2V 성공과 children/all-age I2V block을 분리해 기록해야, I2V pipeline 자체가 건강하다는 판단을 유지할 수 있습니다.
  - 실존 브랜드/직장/person-action prompt는 request-level rejection이 날 수 있으므로 generic workplace/calm motion 식으로 재작성하는 것이 회복 방향입니다.
- History 기능이 실제 사용자 관리 흐름 기준으로 확장되었습니다.
  - mode 필터와 별개로 image/video 결과를 구분하는 `asset_kind` 필터가 필요하다고 판단했습니다.
  - terminal 상태의 job 삭제를 지원하되 active/non-terminal job은 보호합니다.
  - pipeline/source dependency가 있는 경우 처음에는 삭제를 강하게 막았으나, 이후 “선택한 terminal job만 독립 삭제” 정책으로 조정되었습니다.
  - 선택 job을 참조하는 dependent job이 모두 terminal이면 `parent_job_id`/`source_asset_id`를 null로 끊고, 선택 job과 그 asset file만 삭제합니다.
  - active dependent job이 있으면 삭제를 차단합니다.
- History video preview가 frontend/backend 경계에서 정리되었습니다.
  - 별도 thumbnail 파일이나 DB schema 변경 없이 저장된 MP4 asset을 작은 `<video>` preview로 보여주는 방향입니다.
  - `/files` 응답은 video preview를 위해 Range request를 지원해야 하며, 기존 path safety는 유지되어야 합니다.
- Prompt Enhancement 장애 진단도 후반에 보강되었습니다.
  - I2V + 짧은 한국어 motion prompt에서 Gemini 응답이 parse/validation 단계에서 실패할 수 있었습니다.
  - backend는 safe diagnostics(`reason`, `field`, `source`)를 노출하고 raw provider output/credential/service account 내용은 노출하지 않는 방향입니다.
  - malformed JSON은 1회 strict retry로 복구하고, schema validation 실패는 성공으로 오인하지 않는 원칙이 재확인되었습니다.
- 중간에 최근 작업을 되돌리는 방향의 dirty diff가 보였고, 복구 시에는 해당 diff가 History/delete/video preview/I2V source 관련 코드를 제거하는지 먼저 확인하라는 단서가 남아 있습니다.
  - 복구 중 같은 상황을 보면 삭제된 기능을 다시 구현하려 하기보다, 먼저 현재 파일이 최신 기능을 잃은 상태인지 비교해야 합니다.

## 원문에서 찾아볼 위치

- Veo/I2V troubleshooting 문서화 판단: 대략 472~538
- I2V source preview 계획과 구현 범위: 대략 615~768
- I2V Generate 활성화 조건과 stale bundle 판단: 대략 855~999, 1661~1898
- Pipeline I2V 대기 UX: 대략 1023~1657
- JobDetail active I2V source context: 대략 1914~2187
- children/all-age I2V safety provider constraint: 대략 2339~2464
- History asset filter/delete/video preview 흐름: 대략 2481~4388
- dirty diff와 최근 기능 보존 판단: 대략 4598~5330
- Prompt Enhancement diagnostics hardening: 대략 5924~6245

## 복구 판단 메모

- 이 파일은 “마지막 기능 polish와 QA에서 실제로 발견한 문제”가 가장 많습니다.
- I2V가 안 되는 것처럼 보이면 source 연결, frontend bundle 최신 여부, provider rejection, safety policy를 분리해서 봐야 합니다.
- History 삭제는 단순 row 삭제가 아니라 storage path safety와 dependent job 보호까지 함께 복구해야 합니다.
- video preview를 복구할 때는 thumbnail 생성보다 `/files` Range support와 frontend `<video>` preview 흐름을 먼저 확인합니다.
