# Issue174 — 일반 사용자 기준 전체 프론트 E2E 탐색 QA

## 결과

**탐색 QA 수행 완료 / 제품 QA 불합격.** 현재 일반 사용자가 접근할 수 있는 주요
화면과 T2I·T2V·I2V·Pipeline, 기록·사용량·운영, 로그인·로그아웃을 실제 Chrome에서
검사했다. test-only 승격 후 Master 콘솔과 Max 전용 모델도 확인했다.

이번 검사는 모든 입력 조합의 전수 조사가 아니다. 기능군별 정상 경로와 대표
정책·실패 경계를 검사한 bounded all-surface audit다.

- [Issue174](https://github.com/bbungjun/AI_multimodal_platform/issues/174)
- 대상 revision: `1748e27e25e8f78a8a05cbf8bd2493171085fed3`.
- 환경: 격리 mock OAuth/Postgres/Redis/backend/dispatcher/worker 2회,
  Chrome 확장 Computer Use, `AI_PROVIDER=mock`.
- [정제 요약 evidence](../evidence/issue-174/full-ui-qa-summary.json).
- 실제 Google·Vertex 요청, 운영 사용자 데이터와 배포 환경 변경은 없다.

## 실행 방법

1. 익명 사용자에서 공통 메뉴와 비공개 화면 접근, 로그인 복귀 경로를 확인했다.
2. 첫 격리 Free 사용자로 T2I2장, I2V4초, T2V6초, Pipeline4초를 실제 UI에서 실행했다.
3. 결과 상세·미디어·Pipeline 연결, Usage와 일반 사용자 Ops를 확인하고 재로그인했다.
4. cleanup0 후 두 번째 격리 사용자로 프롬프트 결정과 실패/재시도를 검사했다.
5. 같은 test-only 사용자를 guarded CLI로 Master 지정하고 overview/users/Audit/Ops와
   Max Imagen Ultra·Veo Standard를 UI에서 확인했다.
6. pagination 전용 실패 Job9개를 격리 DB에 fixture로 추가해10/4행 페이지를 검사했다.
7. 정제 DB 집계와 backend status를 확인한 뒤 두 번째 환경도 cleanup0으로 제거했다.
8. 전체 backend와 frontend Session/Chromium 회귀, lint/build/Compose를 fresh 실행했다.

브라우저 행동은 실제 link/button/input/select로 수행했다. pagination fixture와 Master
지정은 테스트 준비이며 제품 행동으로 세지 않는다. DB 확인은 읽기 전용 집계만 남겼고,
prompt·OAuth 값·cookie·사용자/Job ID 원문은 evidence에서 제외했다.

## 재현된 결함

| ID | 우선순위 | 재현 결과 | 판정 |
|---|---|---|---|
| F01 | P1 | Free에서 이미지2장과 T2V6초가 완료됨. Usage에도 Imagen3장·Veo Fast14,000ms 반영 | 요청 크기 정책 미집행 |
| F02 | P2 | 모델·템플릿·두 설정 버튼 클릭 후 변화 없음. 검색은 조작 가능한 control이 아님 | 미연결 UI |
| F03 | P2 | Free에서 Imagen Standard 선택 가능, 생성 후 `credit_plan_refused` 원문 표시 | entitlement 안내와 오류 번역 부족 |
| F04 | P2 | 일반 사용자에게 운영 메뉴 노출, `master_required` 표시 | 역할 내비게이션 불일치 |
| F05 | P2 | I2V4초·T2V6초·Pipeline4초·Max Standard8초 모두 완료 파일이지만 재생 불가 | mock 영상과 UX 계약 불일치 |
| F06 | P2 | 이미지·영상·Pipeline 상세에 일반적인 다운로드 동작 없음 | 결과 전달 UX 공백 |
| F07 | P3 | 기록5·2·14개에도 사이드바 숫자는8. mock 타임라인은 Vertex AI 문구 사용 | 상태 표시 부정확 |
| F08 | P2 후보 | 익명 `/history` 선택 후 로그인하면 `/generate`로 이동 | 로그인 복귀 의도 유실 |
| F09 | P3 | 표시 가능한 이미지가 있지만 상세 해상도는 `알 수 없음` | asset metadata/UI 공백 |

F01~F08은 Issue164의 결과를 현재 revision에서 재확인했다. F09는 이번 실행에서 추가했다.
Pipeline 잔액 부족 메시지는 `Monthly credits are exhausted.`로 표시되어 과거 raw code보다
개선됐지만 한국어 UI와 비용/부족분 설명은 없다.

## 정상 동작으로 확인한 흐름

### 인증과 입력

- 로그인, 계정 팝오버/Escape, 로그아웃과 재로그인.
- 빈 T2I 프롬프트, I2V 소스 없음, Pipeline 영상 프롬프트 없음에서 생성 비활성.
- 비율·장수·스타일·모델·길이 선택값이 미리보기와 상세 parameters에 반영.
- 향상 후 `버리기`와 `원본 유지`는 원문 유지. 키보드 편집 후 수락은 편집 값을 반영.

### 생성과 복구

- Free T2I2장과 두 I2V 버튼. 첫 이미지에서 I2V4초 완료와 source 연결.
- Free T2V6초 완료. 정책상 거절 대상이므로 완료 자체가 F01 증거다.
- Free Pipeline parent T2I 완료 후 blocked child I2V에 source가 연결되어 둘 다 완료;
  reload 후에도 유지. 남은10 Credit에서 두 번째 Pipeline은 정상적으로 거절됐다.
- Max Imagen Ultra 9:16 이미지, Veo Standard8초, Fast 다중 이미지2개 완료.
  두 번째 이미지의 I2V 버튼도 별도 source query로 연결됐다.
- `[[mock-fail:imagen]]`은 실패 UI와 오류를 표시. 상세·기록 재시도는 새 Job과
  retry 원본 연결을 만들고 sentinel 유지로 예상대로 다시 실패했다.

### 기록·사용량·운영

- mode/result/state/model/limit 필터,0행 메시지, 필터 해제 후 복구.
- fixture 포함14행에서 page size10, 1페이지10행→2페이지4행→1페이지 복귀.
- 삭제 confirm 문구와 취소 확인. dismiss 직후 한 Chrome extension tab이 timeout됐지만
  새 tab에서 Job5개가 유지되어 DELETE 미실행을 확인했다. 영구 삭제 확인은 미검증이다.
- Free Usage: Imagen Fast3장, Veo Fast14,000ms, 차감990/1,000, 가용10, held0.
- Master overview/users/Audit, 사용자 관리 panel, Master Ops 표시. 추가 Master 변경은 미실행.

## 사후 상태와 HTTP

첫 환경은 UI Usage와 Pipeline 결과 확인 후 제거해 DB export를 남기지 않았다.
두 번째 환경의 종료 전 집계는 다음과 같다.

- UI Job6개 + pagination fixture9개 = 총15개; completed3, failed12, retry2.
- image/png3, video/mp41, prompt enhancement3.
- outbox published6, pending/failed0; reservation settled6/released3/held0.
- Master Audit1행은 test-only 승격과 일치.
- backend event165개,5xx0. HTTP event 수는 테스트 수가 아니다.

두 Chrome tab의 Console은 React Router future warning4개/6개만 반환했고 예상 밖 error는
없었다. 익명 `/me`401은 기대 응답이다. Network body/header는 수집하지 않았다.

## 회귀 테스트

```text
Backend 최초: 1806 PASS / 3 guarded SKIP / 1 FAIL
원인: Windows Bash가 release script 절대 경로를 해석하지 못한 기존 host-path 검사
해당 검사만 deselect: 1806 PASS / 3 SKIP / 1 deselected
Frontend Session: 70 PASS
Frontend Chromium: 61 PASS
Frontend lint/build: PASS
.env.example Compose: PASS
```

Chromium suite는1440/920/390/320 auth·usage와1440/390/320 Master 반응형 검사를 포함하지만
fixture HTTP다. 실제 owned runtime 모바일 검증으로 표현하지 않는다. frontend 폴더에서
실수로 root-relative Compose 명령을 실행해 env 파일을 찾지 못했고, repository root에서
동일 명령을 재실행해 통과했다. 제품 실패가 아니다.

## 한계와 다음 단계

실제 Google/Vertex/TLS/ingress, 실제 영상 재생·품질, live mobile viewport, concurrency/race,
다른 사용자 소유권 공격, 영구 삭제 확인과 Master 변경 적용은 이번 브라우저 검증에
포함되지 않는다. 기존 backend proof가 있어도 이번 UI 결과로 주장하지 않는다.

제품 전체 PASS는 F01 등 결함 때문에 불가능하다. 다음 단계는 Free 이미지 장수·영상 길이
admission을 수정하고 실제 HTTP/UI 회귀를 추가하는 것이다. 이후 F02~F06을 개별 Issue로
닫고 이번 체크리스트를 QA Skill 입력으로 사용한다.

두 격리 runtime은 Chrome tab·Vite·backend·DB·Redis·worker와 함께 cleanup0으로 제거됐다.
기존 다른 Docker 프로젝트와 untracked 사용자 파일은 변경하지 않았다.
