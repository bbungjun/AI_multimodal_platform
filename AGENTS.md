# CreativeOps Studio 작업 지침

이 워크스페이스는 개인 프로덕션 포트폴리오 프로젝트인
`bbungjun/AI_multimodal_platform`의 개발 공간입니다.

목표는 특정 제출물의 흔적을 보존하는 것이 아니라, Vertex AI 기반 멀티모달 생성
서비스를 실제로 운영 가능한 수준까지 키우는 것입니다. 새 기능을 넣을 때도 항상
사용자가 실제로 이미지를 만들고, 프롬프트를 다듬고, 작업 결과를 관리하는 흐름을
더 안정적으로 만드는지부터 판단합니다.

## 제품 방향

- 핵심 서비스는 멀티모달 콘텐츠 생성 스튜디오입니다.
- 지원 범위는 Imagen text-to-image, Veo text-to-video/image-to-video, Gemini 기반
  prompt enhancement입니다.
- RAG, ETL, 챗봇, LLMOps 기능은 제품 가치가 분명할 때만 추가합니다.
- 첫 화면은 실제 작업 공간이어야 하며, 마케팅 랜딩 페이지보다 사용 가능한 생성
  경험을 우선합니다.
- mock mode에서도 생성, 미리보기, 파일 서빙, 작업 상태 흐름이 끝까지 검증되어야
  합니다.

## 포트폴리오/지원 직무 방향

이 프로젝트는 현대오토에버 Platform Engineer 직무, 특히 `AI 플랫폼 구축/운영`
포지션의 역량을 실제로 기르기 위한 개인 프로젝트입니다. 단순히 AI API를 호출하는
앱이 아니라, AI 기능을 실제 운영 가능한 Kubernetes 기반 플랫폼 위에 배포하고
검증하는 경험을 만드는 것이 핵심입니다.

채용 공고의 `AI 플랫폼 구축/운영` 포지션은 HMC/KIA AI 플랫폼 운영, 대규모 GPU
인프라 기반 K8S 구축/관리, 운영 자동화, 분산 학습 GPU 모니터링 고도화 및 성능
개선을 다룹니다. 이 repo의 작업은 다음 역량을 증명하는 방향으로 우선순위를 둡니다.

- Docker/Container, Kubernetes Pod/Service/Secret/ConfigMap/Deployment 이해와 운영
- GCP GKE, Terraform, Artifact Registry, Cloud SQL, Redis, GCS, Workload Identity
  기반의 클라우드 인프라 구축
- CI/CD, 이미지 build/push, 배포 runbook, 운영 자동화 스크립트
- health/readiness, k6 부하테스트, 장애 재현, 로그 기반 원인 분석
- Prometheus/Grafana 또는 Cloud Monitoring 기반 관측성, 알림, 대시보드
- HPA, resource request/limit, rollout, recovery, 비용/쿼터/장애 대응
- GPU node pool, taint/toleration, nodeSelector, NVIDIA device plugin, GPU metric
  수집 등 GPU 인프라 운영 설계 및 향후 실습
- AI/ML 서비스 배포 관점의 provider boundary, retry, rate limit, prompt/generation
  failure handling

이력서나 면접에서 말할 때는 구현한 것과 아직 설계/학습 단계인 것을 구분합니다.
현재까지 실제 구현한 것은 GKE/Terraform 배포, Kubernetes workload 운영,
Workload Identity, Vertex AI 연동, runbook, mock/vertex 모드 분리, k6 부하테스트와
장애 신호 분석입니다. GPU 인프라와 분산 학습 운영은 아직 실제 구현 전이므로,
앞으로의 보강 작업으로 추적합니다.

## 저장소와 Git

- 기본 브랜치는 `main`입니다.
- 원격 저장소는 `origin -> https://github.com/bbungjun/AI_multimodal_platform.git`
  입니다.
- 구현 작업은 먼저 GitHub Issue를 발행해 범위와 수용 기준을 기록합니다.
- 작업 브랜치는 해당 Issue에서 만들고 `codex/issue-번호-짧은-설명` 형식을
  사용합니다.
- 검증이 끝나면 브랜치를 push하고 `main` 대상으로 draft PR을 엽니다.
- 작업을 시작할 때는 `AGENTS.md`를 읽은 뒤 `docs/current-work.md`를 읽어 현재
  작업 상태, 마지막 검증 결과, 다음 단계, 주의사항을 먼저 확인합니다.
- 작업을 마칠 때는 `docs/current-work.md`에 이번에 어디까지 했는지, 남은 일,
  검증 명령과 결과를 갱신합니다. 노트북과 데스크톱을 오가며 같은 repo를 쓰기
  위한 handoff source of truth입니다.
- 문서에는 개인 PC의 absolute path를 고정하지 않습니다. 경로가 필요하면
  repository root 기준 상대 경로나 `git rev-parse --show-toplevel`로 확인하는
  방식으로 씁니다.
- 작업 전후에는 반드시 확인합니다.

```bash
git status --short --branch
git diff --cached --name-only
```

- 변경은 작고 의미 있는 단위로 커밋합니다.
- 사용자가 막지 않는 한 중요한 체크포인트는 push까지 진행해도 됩니다.
- `git reset --hard`, `git checkout -- <path>`처럼 사용자 변경을 지울 수 있는
  명령은 명시 요청 없이는 사용하지 않습니다.
- 현재 작업과 무관한 dirty change는 되돌리지 않고 그대로 둡니다.

## 비밀정보 안전

- `.env`, ADC 파일, service-account JSON, API key, private key 내용은 읽지 않고
  출력하지 않고 커밋하지 않습니다.
- credential 파일의 경로는 필요할 때만 환경변수 이름 수준으로 다룹니다.
- `.env.example`에는 로컬 실행에 필요한 비밀이 없는 값만 둡니다.
- 테스트와 기본 compose 검증은 `AI_PROVIDER=mock` 기준으로 수행합니다.
- 실제 Vertex 호출은 비용이 발생할 수 있으므로 사용자가 의도한 상황에서만
  진행합니다.

## Provider 경계

- `AI_PROVIDER=mock`
  - credential 없이 동작해야 합니다.
  - Vertex, Gemini, Imagen, Veo를 실제 호출하면 안 됩니다.
  - deterministic PNG/video placeholder/prompt draft로 앱 흐름을 검증합니다.
- `AI_PROVIDER=vertex`
  - 실제 Vertex AI 경로입니다.
  - SDK는 `google-genai`를 사용하고 `genai.Client(vertexai=True, ...)` 경계를
    유지합니다.
  - ADC 또는 service-account는 opaque credential로 취급합니다.

Provider 선택은 좁은 service boundary 안에서 처리합니다. API, DB model, job services,
state machine, storage helper, frontend는 가능한 한 provider 종류를 몰라야 합니다.

## Docker Compose 실행 모드

mock용 이미지와 Vertex용 이미지를 따로 빌드하지 않습니다. 같은 backend/worker 이미지를
사용하고, 실행 시점의 env와 compose override로 provider를 선택합니다.

Mock 로컬 개발/기본 검증:

```powershell
# .env 기준 AI_PROVIDER=mock이어야 합니다.
docker compose up -d --build
```

Vertex 실제 API QA:

```powershell
# .env 기준 AI_PROVIDER=vertex, GOOGLE_APPLICATION_CREDENTIALS,
# GOOGLE_APPLICATION_CREDENTIALS_HOST가 설정되어 있어야 합니다.
docker compose -f docker-compose.yml -f docker-compose.vertex.yml up -d --build
```

주의:

- `.env`가 `AI_PROVIDER=vertex`인데 `docker-compose.vertex.yml` 없이 실행하면
  credential mount가 빠져 Vertex readiness가 실패할 수 있습니다.
- `.env`가 `AI_PROVIDER=mock`이면 `docker-compose.vertex.yml`을 붙이지 않습니다.
- 실제 Vertex 모드는 Imagen/Veo/Gemini 호출 비용이 발생할 수 있으므로 QA 목적이
  분명할 때만 사용합니다.

## 아키텍처 규칙

- Backend는 FastAPI, SQLAlchemy, Postgres를 기준으로 둡니다.
- Frontend는 React, Vite, TypeScript를 기준으로 둡니다.
- Docker Compose는 `db`, `redis`, `backend`, `dispatcher`, `frontend`, `worker`를 실행합니다.
- Job은 Postgres에 저장하고 outbox dispatcher가 Redis/Celery로 `job_id`만 발행하며,
  Celery worker가 Postgres에서 최신 job을 다시 읽어 처리합니다.
- GCS, 새 DB, 새 frontend framework, 새 queue/routing 정책은 명시적인 설계 결정 없이
  추가하지 않습니다.
- 모든 job 상태 변경은 `backend/app/state_machine.py`의 transition 경계를 거칩니다.
- asset 파일 쓰기, 읽기, 삭제, 스트리밍은 storage helper를 거칩니다.
- 사용자 입력 filename을 파일 경로에 직접 사용하지 않습니다.
- Veo 결과는 기본적으로 inline bytes를 `DATA_DIR`에 저장하는 흐름을 유지합니다.
- Prompt Enhancement는 자동 대체가 아니라 review, edit, accept 가능한 초안입니다.
- 최종 generation prompt의 source of truth는 사용자가 확인한 generation payload입니다.

## 문서 기준

제품과 구현 설명은 다음 문서를 우선 기준으로 삼습니다.

- `README.md`
- `docs/current-work.md`
- `docs/architecture.md`
- `docs/provider-modes.md`
- `docs/job-lifecycle.md`
- `docs/storage-and-assets.md`
- `docs/testing.md`
- `docs/runbooks/local-mock.md`
- `docs/runbooks/vertex-live-qa.md`
- `docs/adr/`

### Document Load Policy

Do not read every Markdown file before each task. Start with
`docs/current-work.md`, then open only the one or two reference docs directly
related to the change. Use `README.md` for setup/user-facing context,
`docs/runbooks/*` for operations, `docs/testing.md` for verification, and
`docs/adr/` only when an architectural decision is being revisited.

문서를 수정할 때는 현재 코드, env, API contract와 맞춰 씁니다. 과거 맥락을 그대로
옮기기보다 지금 제품을 이해하는 데 필요한 정보만 남깁니다.

## 검증 체크리스트

좁은 검증부터 실행합니다.

Backend:

```bash
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Frontend:

```bash
cd frontend
npm run build
```

Docker Compose:

```bash
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Hygiene:

```bash
git diff --check
git status --short --branch
git diff --cached --name-only
```

명령이 실패하면 첫 번째 구체적인 에러부터 진단합니다. 추측으로 대규모 rewrite를
하지 않습니다.

## 개발 우선순위

1. Repo detox와 문서 정합성을 깨끗하게 유지합니다.
2. mock mode에서 전체 생성 흐름을 빠르고 안정적으로 검증합니다.
3. 실제 Vertex mode의 credential, 비용, 실패 처리를 운영 관점에서 단단하게 만듭니다.
4. 생성 스튜디오 UX를 개선합니다.
5. 작업 라이브러리, 상태 추적, asset 관리, 실패 재시도 경험을 제품화합니다.
6. 관측성, 평가, 배포, 보안은 실제 운영에 필요한 범위부터 단계적으로 추가합니다.

## 작업 방식

- 먼저 현재 코드, `docs/current-work.md`, 관련 문서를 읽고, 기존 패턴에 맞춰 작게 고칩니다.
- 구현 세부사항이 열려 있으면 가장 보수적이고 검증 가능한 선택을 합니다.
- 기능을 추가할 때는 API contract, DB 상태, frontend 흐름, 테스트를 함께 봅니다.
- 사용자가 한국어로 요청하면 결과 정리도 한국어로 합니다.
- 완료라고 말하기 전에 fresh verification을 실행하고 결과를 확인합니다.
