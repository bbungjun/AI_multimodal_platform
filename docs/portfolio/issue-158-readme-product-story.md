# Issue #158 — 제품 소개 중심 README와 실제 UI 촬영

## 배경과 문제

채용 관계자가 저장소를 열었을 때 제품의 목적과 개인 개발 범위를 먼저 이해할 수
있도록 README를 개편했다. 기존 문서는 운영 구조, 신뢰성 설계, 검증 표를 먼저
보여주고 실제 사용 화면은 106행에서 시작했다. 구현 내용은 풍부했지만 무엇을
만들었고 왜 만들었는지 이해하기 전에 내부 기술 용어를 읽어야 했다.

사용자와 합의한 구성은 소개, 서비스 화면, 개발 배경·목표, 사용자 흐름, 개인 개발
범위, 문제 해결 사례, 아키텍처·스택이다. 전체 1인 개발임을 명시하고 별도의 검증
현황·빠른 시작·문서 모음 섹션은 제외했다. 기획의 개인적 일화나 확인되지 않은
고객 수·업무 효율 성과는 추가하지 않았다.

## 관측과 판단

- 최신 제품 코드에는 사용자 소유권, 크레딧, 개인 사용량과 Master 콘솔이 있다.
  기존 생성 화면만으로는 이 범위가 전달되지 않아 최신 UI를 직접 촬영했다.
- 실행 중인 기존 preview에는 worker/dispatcher가 없고 최신 검증 환경과 다르다.
  이 환경을 변경하지 않고 G11B의 `BrowserRuntime`/`MemoryIdentity`를 재사용했다.
- 최초 촬영은 현재 화면과 다른 초기 heading을 기다리다가 실패했다. 현재 컴포넌트의
  빈 프롬프트 제목을 확인해 selector를 수정했다. 이 실패에서도 소유한 자원은 정리됐다.
- 첫 성공 촬영의 결과·관리 화면은 세로로 길었다. 최종 촬영은 내용을 변경하지 않고
  결과·상태 및 운영 요약 영역으로 crop했다. 사이드바의 고정 장식 지표도 공개 이미지에서
  제외하고 실제 작업 영역을 선택했다.
- Markdown 미리보기의 최초 가로 다이어그램은 글자가 작았다. 세로 흐름으로 바꾸고
  중복 노드를 줄여 다시 Mermaid로 파싱·렌더링했다.

## 구현과 선택 이유

- `README.md`: 제품 설명과 1인 개발을 먼저 소개하고, 기능을 사용자 행동으로 설명한다.
  기술적 사례는 작업 발행, 소유권·크레딧, 배포 복구의 세 가지로 제한했다.
- `scripts/capture_readme.py`: 기존 검증 runtime으로 새 Compose project를 만들고
  준비·seed·촬영·소유 자원 정리와 PNG manifest 생성을 수행한다.
- `frontend/scripts/capture-readme.mjs`: 현재 React UI를 Vite proxy로 실제 backend에
  연결하고 Chromium에서 향상 → 수락 → 생성 → 결과 → 사용량 → Master 조회를 실행한다.
  HTTP 응답 stubbing이나 제품 인증 우회 endpoint는 추가하지 않았다.
- 촬영의 세션은 기존 테스트 전용 fixture로 만들며, 원문은 프로세스 stdin과 메모리에서만
  전달한다. Google OAuth는 비활성화하고 모든 browser 외부 origin 요청은 차단한다.
- PNG는 screenshot API의 mask/crop으로만 가공한다. 프롬프트·구성 요소·파라미터는
  가리고, snapshot은 제목·버튼·표 머리글·progressbar만 수집한다. 세션, 프로필, 전체
  DOM, HAR, provider 응답과 생성 원본 파일은 공개 artifact에 포함하지 않는다.
- 전체 생성 품질은 이 촬영의 목적이 아니다. 결과 PNG는 mock placeholder이며 README
  caption에 명시했다. Master의 9개 계정과 1건 성공도 테스트 데이터임을 명시했다.
- 제품/API/DB schema/배포 설정은 변경하지 않았다. rollback은 문서·촬영 도구·이미지
  변경 commit을 되돌리는 것으로 충분하며 데이터 migration이 없다.

## 재현 방법

전제: 로컬 Docker, Python, Node, 설치된 frontend dependencies와 Playwright Chromium.
`frontend`에서 `npm ci`, `npx playwright install chromium`으로 브라우저 의존성을 준비한다.
repository root에서 다음을 실행한다. 기존 preview를 중지하거나 `.env`를 복사하지 않는다.

```powershell
python scripts/capture_readme.py
```

- 입력 환경 파일은 `.env.example`로 고정하고 외부 URL/project 지정 인자는 받지 않는다.
- backend는 새 loopback ephemeral port, frontend는 충돌 검사한 `127.0.0.1:18155`를 쓴다.
- 출력은 `output/playwright/readme/`의 PNG 5개, 제한된 UI snapshot, receipt와 manifest다.
- 성공 receipt는 screenshots=5, mock_generations=1, prompt_reviews=1,
  external_requests=0, cleanup=0이다. 실패 receipt를 성공 증거로 사용하지 않는다.
- 출력 이미지를 직접 열어 가림과 crop을 확인한 다음 선택한 PNG, `snapshots.json`,
  `capture-manifest.json`만 `docs/assets/readme/`에 복사한다.
- 촬영 도구는 소유 label을 확인한 runtime만 정리한다. 광범위한 Docker prune은 사용하지 않는다.

## 검증과 증거

2026-09-06, 제품 기준 revision `c409f98`, Windows 로컬 mock 환경.

| 확인 | 결과 |
|---|---|
| 격리 실제 browser/API/DB/worker 촬영 | 2회 성공, 최종 5개 PNG와 UI snapshot 반영 |
| 최종 촬영 사용자 흐름 | 프롬프트 향상·수락 1회, 이미지 생성 1회, 파일 decode, 사용량 차감 및 예약 해제 확인 |
| 외부 요청·정리 | browser 외부 요청 0, 소유 Compose 자원 잔존 0, frontend port 해제 |
| 기존 preview | 작업 전후 기존 4개 컨테이너 계속 실행, 재시작·seed·migration 없음 |
| 관련 기존 backend tests | `backend`에서 아래 명령으로 12 passed |
| frontend | `npm run build`, `npm run lint` PASS |
| 촬영 도구 syntax | `python -m py_compile scripts/capture_readme.py`, `node --check frontend/scripts/capture-readme.mjs` PASS |
| Compose | `docker compose --env-file .env.example config --quiet` PASS |
| 기본 Compose | `docker compose config --quiet`는 로컬 POSTGRES_USER 미설정으로 실패. 실제 환경 파일은 읽거나 변경하지 않음 |
| 문서 | 상대 링크·이미지 10개 존재, PNG signature·크기·SHA-256 확인, snapshot의 ID·이메일·프롬프트 제외 확인 |
| 렌더링 | GitHub Markdown API 렌더링, Mermaid CLI SVG 생성, 로컬 브라우저에서 문서·그림 확인 |

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_browser_acceptance_support.py tests/test_browser_acceptance_fixtures.py tests/test_verify_browser_acceptance.py -q
```

초기 테스트 명령을 repository root에서 실행했을 때 `tests` import collection이 실패했다.
문서에 지정된 `backend` 작업 디렉터리에서 재실행해 통과했으며 제품 코드는 수정하지 않았다.

공개 증거:

- [촬영 manifest](../assets/readme/capture-manifest.json): 제품 기준 revision, 크기, 파일 hash, 성공 receipt
- [제한된 UI snapshots](../assets/readme/snapshots.json): 선택한 실제 화면의 제목·조작 요소
- [Studio](../assets/readme/studio.png), [프롬프트 검토](../assets/readme/prompt-review.png),
  [생성 결과](../assets/readme/generation-result.png), [사용량](../assets/readme/usage.png),
  [Master](../assets/readme/master.png)

## 결과와 남은 범위

README에서 제품의 용도, 제작 흐름, 전체 개인 개발 범위와 세 가지 판단을 읽을 수 있다.
기술 목록·실행 매뉴얼 위주의 318행을 172행으로 정리했다. 검증 근거는 해당 사례에만
연결했다. 채용 전환율 개선이나 사용자 업무 시간 절감은 측정하지 않았다.

촬영은 실제 Google 로그인, 유료 Imagen/Veo 생성 품질, 최신 인증·크레딧 기능의
클라우드 통합 검증을 증명하지 않는다. 기존 G11 live gate 및 과거 클라우드 증거 등급은
변경하지 않았다. 실제 생성 결과를 새로 촬영하려면 별도의 의도된 Vertex QA가 필요하다.

Issue: [#158](https://github.com/bbungjun/AI_multimodal_platform/issues/158)
Branch: `codex/issue-158-readme-product-story`

Core commit: `b94a954` (push 완료). [Draft PR #159](https://github.com/bbungjun/AI_multimodal_platform/pull/159)
를 main 대상으로 열었다. 이 기록은 로컬 검증 결과이며 PR CI 결과나 main 병합을 대신하지 않는다.
