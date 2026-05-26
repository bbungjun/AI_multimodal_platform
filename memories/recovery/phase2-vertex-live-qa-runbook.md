# Phase 2 Vertex Live QA Runbook

Date: 2026-05-27

이 문서는 Phase 1 복구 이후, 실제 `AI_PROVIDER=vertex` 경로를 수동으로 검증할 때
따라갈 절차입니다.

중요: 이 문서는 "실제 Vertex live QA를 이미 실행했다"는 기록이 아닙니다.
이 문서를 작성하면서 Vertex, Gemini, Imagen, Veo 실제 호출은 하지 않았습니다.

## 현재 결정

이번 복구 세션에서는 비용이 발생하는 실제 Vertex/Gemini/Imagen/Veo 검수를
실행하지 않습니다.

따라서 이 문서는 "나중에 비용 승인을 받고 실제 provider QA를 해야 할 경우의
참고 절차"로만 보관합니다. 현재 제출/인수인계 기준으로는 `AI_PROVIDER=mock` 기반
로컬 검증까지만 완료된 상태이며, `AI_PROVIDER=vertex` live path는 미검증 리스크로
남깁니다.

## 목적

비용 발생을 명시적으로 승인한 뒤에만, 복구된 프로젝트가 최종 제출 당시의 실제
Vertex AI provider 경로로 동작하는지 확인합니다.

확인 대상:

- Gemini 2.5 Flash prompt enhancement
- Imagen 4 text-to-image 생성
- Veo 3 text-to-video 생성
- 완료된 이미지 asset을 source로 쓰는 Veo 3 image-to-video 생성
- T2I -> I2V pipeline 연결

자동화 테스트와 일반 로컬 검증은 계속 `AI_PROVIDER=mock` 경로를 사용합니다.
`AI_PROVIDER=vertex` 검증은 credential, quota, 모델 접근 권한, 실제 비용이 필요하므로
수동 QA로만 다룹니다.

## 실행 전 조건

실제 provider 요청을 보내기 전에 아래 조건을 모두 확인합니다.

- 리뷰어 또는 사용자가 Vertex AI 비용 발생 가능성을 명시적으로 승인했습니다.
- GCP project에 billing이 켜져 있습니다.
- 선택한 region에서 Vertex AI, Gemini, Imagen, Veo 접근 권한이 있습니다.
- service-account JSON 파일이 repo 바깥 경로에 있습니다.
- `.env`는 로컬에만 있고 git에 commit하지 않습니다.
- service-account JSON 내용, API key, private credential, 실제 `.env` 값은 문서,
  터미널 공유 로그, commit, issue comment에 붙여 넣지 않습니다.
- 작업 시작 전 git 상태가 깨끗합니다.

```bash
git status --short --branch
git diff --cached --name-only
```

기대 결과:

- `git status --short --branch`는 `## main...origin/main` 형태입니다.
- `git diff --cached --name-only`는 아무것도 출력하지 않습니다.

## 환경 변수 준비

`.env.example`을 참고해서 로컬 `.env`를 만듭니다.

주의:

- service-account JSON 파일 "내용"을 `.env`에 넣지 않습니다.
- `.env`에는 service-account JSON의 host 절대 경로만 넣습니다.
- JSON 파일은 repo 바깥에 둡니다.

실제 Vertex mode에 필요한 주요 값:

```env
AI_PROVIDER=vertex
GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa.json
GOOGLE_APPLICATION_CREDENTIALS_HOST=/absolute/path/outside/repo/service-account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
```

현재 `docker-compose.yml`은 `GOOGLE_APPLICATION_CREDENTIALS_HOST` 파일을 backend
container 안의 `/secrets/sa.json`으로 read-only mount합니다.
따라서 `GOOGLE_APPLICATION_CREDENTIALS_HOST`는 반드시 host machine의 절대 경로여야
하며, repo 바깥의 JSON 파일을 가리켜야 합니다.

## 설정만 확인하는 명령

아래 명령은 media 생성 요청을 보내지 않아야 합니다.
즉, Imagen/Veo/Gemini 실제 생성 호출이 아닙니다.

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env ps
```

기대 결과:

- Compose config 명령이 exit code `0`으로 끝납니다.
- 이미 live QA 중인 상황이 아니라면, stale project container가 없어야 합니다.

config가 깨끗할 때만 stack을 시작합니다.

```bash
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
```

기대 결과:

- `db`가 healthy입니다.
- backend가 host port `8000`에서 접근 가능합니다.
- frontend가 host port `5173`에서 접근 가능합니다.

## Health 확인

Health check는 provider 설정과 credential을 읽지만, 이미지/비디오 생성 요청은
보내지 않아야 합니다.

PowerShell:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health"
```

기대 응답 형태:

```json
{
  "ok": true,
  "ready": true,
  "service": "vertex-studio",
  "db": "up",
  "vertex": {
    "ready": true,
    "status": "ready",
    "credentials": "available",
    "project": "configured",
    "location": "us-central1"
  }
}
```

`ready`가 `false`이면 여기서 멈춥니다.
그 상태에서는 비용이 발생하는 QA 요청을 보내지 않습니다.
기록할 때도 `ready`, `status`, `credentials`, `project`, `location` 같은 public field만
적고, credential 경로나 JSON 내용은 적지 않습니다.

## Job polling helper

generation API는 비동기 job 방식입니다.
job이 `completed`, `failed`, `cancelled` 중 하나가 될 때까지 기다리려면 아래
PowerShell 함수를 사용합니다.

```powershell
function Wait-Generation {
  param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [int]$MaxAttempts = 120,
    [int]$DelaySeconds = 5
  )

  for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
    $job = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/generations/$JobId"
    if ($job.state -in @("completed", "failed", "cancelled")) {
      return $job
    }
    Start-Sleep -Seconds $DelaySeconds
  }

  throw "Generation $JobId did not reach a terminal state."
}
```

## 비용 발생 가능 QA 순서

아래 단계부터는 실제 Vertex 비용이 발생할 수 있습니다.

비용을 줄이려면 가장 작은 범위부터 실행합니다.
T2I가 먼저 통과한 뒤에만 I2V 또는 pipeline을 실행합니다.
같은 세션에서 direct I2V와 pipeline을 둘 다 실행할 필요는 없습니다.

### 1. Gemini Prompt Enhancement

이 요청은 Gemini/Vertex 비용이 발생할 수 있습니다.

```powershell
$enhanceBody = @{
  prompt = "A cinematic rainy Seoul alley at night with neon reflections"
  target_mode = "t2i"
  target_model = "imagen-4.0-fast-generate-001"
  creativity_preset = "balanced"
} | ConvertTo-Json

$enhancement = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/prompts/enhance" `
  -ContentType "application/json" `
  -Body $enhanceBody

$enhancement
```

기대 결과:

- 응답에 `id`, `original`, `enhanced`, `components`, `target_mode`,
  `target_model`, `llm_model`, `creativity_preset`, `temperature`가 있습니다.
- `llm_model`은 `gemini-2.5-flash`입니다.
- prompt enhancement만 수행하며 generation job은 자동 생성되지 않습니다.

### 2. Imagen Text-To-Image

이 요청은 Imagen/Vertex 비용이 발생할 수 있습니다.

```powershell
$t2iBody = @{
  mode = "t2i"
  prompt = "A cinematic rainy Seoul alley at night with neon reflections"
  model = "imagen-4.0-fast-generate-001"
  aspect_ratio = "1:1"
  number_of_images = 1
} | ConvertTo-Json

$t2iJob = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -ContentType "application/json" `
  -Body $t2iBody

$t2iDone = Wait-Generation -JobId $t2iJob.id -MaxAttempts 60 -DelaySeconds 5
$t2iDone
```

기대 결과:

- job state가 `completed`가 됩니다.
- `mode`는 `t2i`입니다.
- `vertex_charged`는 `true`입니다.
- asset이 최소 1개 있고, `kind=image`, `mime=image/png`, `/files/...` URL을 가집니다.

이미지 파일을 받아보고 싶으면:

```powershell
$imageUrl = "http://127.0.0.1:5173$($t2iDone.assets[0].url)"
Invoke-WebRequest -Uri $imageUrl -OutFile "$env:TEMP\vertex-t2i-output.png"
```

### 3. Veo Text-To-Video

이 요청은 Veo/Vertex 비용이 발생할 수 있고, T2I보다 오래 걸릴 수 있습니다.

```powershell
$t2vBody = @{
  mode = "t2v"
  prompt = "A slow dolly forward through a rainy neon Seoul alley"
  model = "veo-3.0-fast-generate-001"
  aspect_ratio = "16:9"
  duration_sec = 4
} | ConvertTo-Json

$t2vJob = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -ContentType "application/json" `
  -Body $t2vBody

$t2vDone = Wait-Generation -JobId $t2vJob.id -MaxAttempts 180 -DelaySeconds 10
$t2vDone
```

기대 결과:

- 정상이라면 job state가 `completed`가 됩니다.
- Vertex가 요청을 거절하면 app의 public error shape로 실패가 기록됩니다.
- `mode`는 `t2v`입니다.
- 성공한 job에는 `vertex_operation_name`, `vertex_charged=true`,
  `video/mp4` asset이 있습니다.

### 4. T2I asset으로 Veo Image-To-Video

이 요청은 Veo/Vertex 비용이 발생할 수 있습니다.
T2I job이 완료되어 usable image asset이 있을 때만 실행합니다.

```powershell
$sourceAssetId = $t2iDone.assets[0].id

$i2vBody = @{
  mode = "i2v"
  prompt = "Slow camera push-in, rain ripples, subtle steam movement"
  model = "veo-3.0-fast-generate-001"
  source_asset_id = $sourceAssetId
  aspect_ratio = "16:9"
  duration_sec = 4
} | ConvertTo-Json

$i2vJob = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/generations" `
  -ContentType "application/json" `
  -Body $i2vBody

$i2vDone = Wait-Generation -JobId $i2vJob.id -MaxAttempts 180 -DelaySeconds 10
$i2vDone
```

기대 결과:

- 정상이라면 job state가 `completed`가 됩니다.
- Vertex가 요청을 거절하면 app의 public error shape로 실패가 기록됩니다.
- `mode`는 `i2v`입니다.
- `source_asset_id`가 완료된 T2I image asset과 같습니다.
- 성공한 job에는 `vertex_operation_name`, `vertex_charged=true`,
  `video/mp4` asset이 있습니다.

### 5. T2I -> I2V Pipeline

이 flow는 Imagen과 Veo 비용이 모두 발생할 수 있습니다.
실제 provider output으로 parent/child pipeline 연결을 검증할 때 사용합니다.

```powershell
$pipelineBody = @{
  image_prompt = "A cinematic rainy Seoul alley at night with a cyclist"
  video_prompt = "Slow dolly forward as the cyclist passes and steam rises"
  image_model = "imagen-4.0-fast-generate-001"
  video_model = "veo-3.0-fast-generate-001"
  image_aspect_ratio = "1:1"
  video_aspect_ratio = "16:9"
  duration_sec = 4
} | ConvertTo-Json

$pipeline = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5173/api/pipelines" `
  -ContentType "application/json" `
  -Body $pipelineBody

$parentDone = Wait-Generation -JobId $pipeline.parent.id -MaxAttempts 60 -DelaySeconds 5
$pipelineState = Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/pipelines/$($pipeline.parent.id)"
$childDone = Wait-Generation -JobId $pipelineState.child.id -MaxAttempts 180 -DelaySeconds 10

$pipelineState
$parentDone
$childDone
```

기대 결과:

- parent job이 `completed`가 되고 image asset을 가집니다.
- child job은 처음에는 blocked 상태였다가 parent image asset 연결 후 unblocked가 됩니다.
- child job의 `source_asset_id`가 parent image asset을 가리킵니다.
- 성공한 child job에는 `vertex_operation_name`, `vertex_charged=true`,
  `video/mp4` asset이 있습니다.

## Frontend 수동 확인

live job이 하나 이상 완료되면 브라우저에서 아래 화면을 확인합니다.

- `http://127.0.0.1:5173/generate`
- `http://127.0.0.1:5173/history`
- `http://127.0.0.1:5173/jobs/{job_id}`

기대 결과:

- API 연결 상태가 정상으로 보입니다.
- History에 live job의 mode, state, model이 맞게 표시됩니다.
- 완료된 image asset preview가 표시됩니다.
- 완료된 video asset은 `/files/...` 경로로 preview/playback이 됩니다.
- Job detail 화면에 state history, request parameters, asset preview가 표시됩니다.

## 결과 기록 방법

실제 live QA를 실행했다면, 결과는 `memories/recovery/` 아래 새 메모에 기록합니다.

기록해도 되는 것은 public field뿐입니다.
credential 경로, JSON 내용, API key, private credential, 전체 terminal log는 기록하지
않습니다.

권장 표:

```markdown
| Check | Result | Evidence | Notes |
|---|---|---|---|
| Health | pass/fail | `ready=true`, `status=ready` | secret 값 없음 |
| Prompt enhance | pass/fail | enhancement id, model id | proprietary prompt면 prompt 생략 |
| T2I | pass/fail | job id, final state, asset mime | credential path 없음 |
| T2V | pass/fail | job id, final state/public error | provider secret 없음 |
| I2V or pipeline | pass/fail | job ids, final states | provider secret 없음 |
```

provider error는 app이 반환하는 public error shape만 기록합니다.

- `code`
- `message`
- `retryable`
- `status_code`
- `operation_name`: app response에 이미 들어 있을 때만 기록

## 종료와 hygiene

검증이 끝나면 live QA stack을 종료합니다.

```bash
docker compose --env-file .env down
```

`down -v`는 local Postgres volume과 asset volume을 삭제해도 되는 경우에만 사용합니다.

마지막으로 repo hygiene을 확인합니다.

```bash
git status --short --branch
git diff --cached --name-only
git ls-files --others --exclude-standard
```

기대 결과:

- `.env`, service-account JSON, credential JSON, generated media, secret
  material이 staged 상태가 아닙니다.
- follow-up memo에는 sanitized public result만 들어 있습니다.
- 리뷰어가 아직 local stack을 사용 중인 경우가 아니라면 Compose container는 꺼져 있습니다.
