# Frontend Browser Smoke Runbook

작성일: 2026-05-27

이 문서는 KRAFTON take-home assignment 복구본을 비용 없이 브라우저에서 검수하기
위한 수동 smoke 절차입니다. 목표는 UI를 pixel-perfect로 비교하는 것이 아니라,
최종 제출물의 핵심 사용자 흐름이 `AI_PROVIDER=mock`에서 끊기지 않는지 확인하는
것입니다.

## 안전 기준

- 실제 Vertex/Gemini/Imagen/Veo 호출은 하지 않습니다.
- `.env`, service-account JSON, API key, private credential은 출력하거나
  커밋하지 않습니다.
- 검수는 `docker compose --env-file .env.example ...`로 실행한 mock mode만
  사용합니다.
- 검수 중 생성한 disposable job만 삭제합니다. 기존 review job은 삭제하지 않습니다.
- browser console의 아래 메시지는 blocking failure로 보지 않습니다.
  - React DevTools 설치 안내
  - React Router v7 future flag warning
  - `/favicon.ico` 404

## 준비

```powershell
git status --short --branch
git diff --cached --name-only

docker compose --env-file .env.example up -d --build
docker compose --env-file .env.example ps
```

기대 상태:

- `db`, `backend`, `frontend`가 모두 `Up`
- frontend: `http://127.0.0.1:5173`
- backend proxy: `http://127.0.0.1:5173/api/...`

health 확인:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health" -Method Get
```

기대 상태:

- `ok=true`
- `ready=true`
- `vertex.status=mock_provider`

## Prompt Enhancement Smoke

목표:

- Gemini mock enhancement 초안이 생성됩니다.
- 초안은 자동으로 generation prompt를 덮어쓰지 않습니다.
- 사용자가 edit/accept한 prompt만 최종 generation payload prompt가 됩니다.
- 생성된 job에 `enhancement_id`가 연결됩니다.

브라우저 절차:

1. `http://127.0.0.1:5173/generate`를 엽니다.
2. mode는 `T2I`를 선택합니다.
3. prompt에 식별 가능한 문구를 입력합니다.
   - 예: `prompt enhancement smoke recovery`
4. `Enhance prompt`를 클릭합니다.
5. `Review Enhanced Prompt` 패널이 보이는지 확인합니다.
6. enhanced draft textarea에 짧은 문구를 추가로 적습니다.
   - 예: ` accepted smoke edit`
7. `Accept draft`를 클릭합니다.
8. Request Builder의 main prompt가 수정된 draft로 바뀌었는지 확인합니다.
9. `Generate`를 클릭합니다.
10. Job Detail로 이동하고 job이 `completed`가 될 때까지 기다립니다.

API 확인:

```powershell
$jobId = "<job-detail-url의 uuid>"
$job = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations/$jobId"
$job.state
$job.enhancement_id
$job.prompt
$job.assets.Count
```

기대 상태:

- `state`는 `completed`
- `enhancement_id`는 null이 아님
- `prompt`는 accept한 main prompt와 일치
- image asset이 1개 이상 있음

## History Filter And Delete Smoke

목표:

- History 화면이 mode/state/model/page size/asset type filter를 표시합니다.
- terminal job에는 Delete 버튼이 보입니다.
- Delete는 disposable terminal job에만 수행합니다.
- 삭제 후 detail API가 404를 반환합니다.

disposable T2I job 생성:

```powershell
$payload = @{
  mode = "t2i"
  prompt = "history delete disposable smoke"
  model = "imagen-4.0-fast-generate-001"
  aspect_ratio = "1:1"
  number_of_images = 1
} | ConvertTo-Json

$job = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -Method Post `
  -ContentType "application/json" `
  -Body $payload

$job.id
```

완료 대기:

```powershell
$jobId = $job.id
do {
  Start-Sleep -Seconds 1
  $current = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations/$jobId"
  $current.state
} while ($current.state -notin @("completed", "failed", "cancelled"))
```

브라우저 절차:

1. `http://127.0.0.1:5173/history`를 엽니다.
2. 생성한 disposable job row를 찾습니다.
3. mode/state/model/page size/asset type filter가 보이는지 확인합니다.
4. `Asset type`을 `Images`로 바꾸면 image asset job이 보이는지 확인합니다.
5. disposable job row에 `Delete` 버튼이 보이는지 확인합니다.
6. disposable job의 `Delete`만 클릭하고 확인창을 승인합니다.
7. row가 사라지는지 확인합니다.

삭제 API 확인:

```powershell
try {
  Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations/$jobId"
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

기대 상태:

- 삭제 후 status code는 `404`
- active/non-terminal job은 삭제 대상으로 사용하지 않음

## T2I Multi-Image And I2V Handoff Smoke

목표:

- `number_of_images=4` T2I 결과가 Job Detail에서 4개 image card로 보입니다.
- 각 image card마다 `Start I2V`가 있습니다.
- 누른 image asset id가 `/generate?mode=i2v&source_asset_id=...`로 전달됩니다.
- Generate 화면에 선택한 source image preview가 표시됩니다.

multi-image job 생성:

```powershell
$payload = @{
  mode = "t2i"
  prompt = "mock multi image gallery recovery smoke"
  model = "imagen-4.0-fast-generate-001"
  aspect_ratio = "1:1"
  number_of_images = 4
} | ConvertTo-Json

$job = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -Method Post `
  -ContentType "application/json" `
  -Body $payload

$job.id
```

완료 및 asset 확인:

```powershell
$jobId = $job.id
do {
  Start-Sleep -Seconds 1
  $current = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations/$jobId"
  $current.state
} while ($current.state -notin @("completed", "failed", "cancelled"))

$current.assets.Count
$current.assets | Select-Object id, kind, url
```

브라우저 절차:

1. `http://127.0.0.1:5173/jobs/<jobId>`를 엽니다.
2. `4 Image Results Ready`가 보이는지 확인합니다.
3. Image 1~4 card와 각 card의 `Start I2V` 버튼을 확인합니다.
4. 특정 image card의 `Start I2V`를 클릭합니다.
5. URL이 `/generate?mode=i2v&source_asset_id=<누른 image asset id>`인지 확인합니다.
6. 왼쪽 cinema 영역에 `Selected I2V source asset ...` 이미지가 보이는지 확인합니다.
7. motion prompt를 입력합니다.
8. I2V `Generate` 버튼이 enabled 되는지 확인합니다.

## Pipeline Smoke

목표:

- parent T2I job과 blocked child I2V job이 함께 생성됩니다.
- parent image asset이 준비되면 child의 `source_asset_id`가 연결됩니다.
- Pipeline detail이 parent/child 상태와 source context를 보여줍니다.

브라우저 절차:

1. `http://127.0.0.1:5173/generate`를 엽니다.
2. mode를 `Pipeline`으로 선택합니다.
3. image prompt와 video prompt를 모두 입력합니다.
4. `Create pipeline`을 클릭합니다.
5. Pipeline detail로 이동하는지 확인합니다.
6. parent가 completed 되고 child가 진행/완료되는지 확인합니다.
7. child I2V 영역에서 source image context가 표시되는지 확인합니다.

API 확인:

```powershell
$pipelineId = "<pipeline-url의 uuid>"
$pipeline = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/pipelines/$pipelineId"
$pipeline.parent.state
$pipeline.child.state
$pipeline.child.source_asset_id
```

기대 상태:

- parent는 `completed`
- child는 mock runner 처리 후 보통 `completed`
- child `source_asset_id`는 parent image asset id와 연결됨

## 종료 전 확인

문서나 코드 변경을 했다면 아래를 확인합니다.

```powershell
git diff --check
git status --short --branch
git diff --cached --name-only
```

Compose를 끄고 싶을 때만 실행합니다.

```powershell
docker compose --env-file .env.example down
```

이번 복구 세션처럼 사용자가 브라우저 검수를 계속할 예정이면 Compose를 끄지 않고
유지해도 됩니다.
