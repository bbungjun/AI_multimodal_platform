# Issue178 — Agent QA 변경 영향 Selector v1

- [Issue178](https://github.com/bbungjun/AI_multimodal_platform/issues/178)
- [일반 PR179](https://github.com/bbungjun/AI_multimodal_platform/pull/179)
- 선행 계약: [Issue176](https://github.com/bbungjun/AI_multimodal_platform/issues/176) /
  [PR177](https://github.com/bbungjun/AI_multimodal_platform/pull/177)

## 배경과 문제

Issue176은 Agent QA가 검증할 10개 사용자 흐름과 68개 assertion을 고정했다. 그러나
모든 PR에서 10개 Chrome journey를 항상 실행하면 느리고, Agent가 임의로 일부만 고르면
회귀 누락을 신뢰할 수 없다. 따라서 변경된 코드와 실행할 scenario 사이 선택 자체도
versioned하고 검증 가능한 계약이어야 한다.

## 기대 동작과 이전 상태

| 구분 | 내용 |
|---|---|
| 기대 동작 | immutable base/head의 변경 파일을 scenario로 결정적으로 매핑하고 선택·제외 모두 근거를 남긴다. |
| 이전 상태 | Registry는 있지만 변경 영향 분석기가 없어 Agent 판단에 따라 범위가 달라질 수 있었다. |
| 주요 위험 | unknown 파일 자동 제외, rename 이전 경로 누락, docs와 제품 코드 혼합 시 과소 선택, 과거 revision 재사용 |

## Module과 Interface

Impact Selector는 순수 선택 로직을 깊은 Module로 두고 Git subprocess는 변경 목록을
제공하는 얇은 Adapter로 제한했다. 호출자와 테스트가 알아야 할 외부 Interface는 다음
명령 하나다.

```powershell
python qa/impact/select_impact.py --base <40자리-Git-SHA> --head <40자리-Git-SHA>
```

branch 이름이나 working tree를 허용하지 않고 서로 다른 commit SHA만 받는다. Git Adapter는
`--name-status -z --find-renames` 결과를 `Change(status, path, previous_path)`로 변환한다.
선택 Module은 Git이나 파일 시스템을 호출하지 않으므로 같은 입력은 같은 Manifest를 낸다.

## 선택 정책

| 우선순위 | 입력 | 결과 |
|---:|---|---|
| 1 | `qa/contracts/`, `qa/impact/`, 공용 runtime·frontend shell | `FULL_E2E` |
| 2 | Registry `related_paths` 또는 domain rule | `TARGETED_E2E` |
| 3 | 명시적 rule이 없는 경로 | fail-safe `FULL_E2E` + `unknown_path_fallback` |
| 4 | 변경 전체가 docs/tests/infra rule | `NO_E2E_REQUIRED` |

문서와 제품 코드가 섞이면 제품 선택이 우선한다. 여러 targeted rule의 합집합이 10개
scenario 전체가 되면 `FULL_E2E`로 분류한다. 파일 삭제도 기존 경로의 scenario를 선택하며,
rename/copy는 이전 경로와 새 경로를 모두 평가한다. 새 위치가 unknown이면 전체 E2E로
승격하므로 이동으로 검증을 회피할 수 없다.

`NO_E2E_REQUIRED`는 Chrome Receipt의 PASS가 아니다. 이후 통합 QA gate에서 정적 검사와
함께 사용할 명시적 “로컬 브라우저 E2E 불필요” 결과다. Issue176 Receipt를 전부
`NOT_APPLICABLE`로 채워 PASS시키지 않는다.

## Manifest와 무결성

Manifest는 다음을 포함한다.

- base/head commit SHA
- Registry SHA와 Policy+Manifest Schema SHA
- status·현재 경로·이전 경로가 정렬된 변경 목록
- unmatched path 목록
- 10개 scenario 각각의 selected, reason, rule IDs
- canonical JSON 기반 Selection SHA

Validator는 field와 vocabulary만 확인하지 않는다. Manifest의 변경 목록으로 선택을 다시
계산해 결과 전체가 동일한지 확인한다. 누군가 selected 값을 바꾸고 Selection SHA까지 다시
만들어도 policy 재계산과 다르면 `impact_manifest_mapping_invalid`로 거부한다.

## 안전장치

- absolute path, 상위 경로 `..`, backslash, control character를 거부한다.
- `.env`, private-key, service-account, credential 형태와 PEM/key 파일 경로를 거부한다.
  비밀 없는 `.env.example`만 허용한다.
- duplicate path, 잘못된 rename/copy shape, 빈 diff, 같은 base/head를 거부한다.
- stderr와 diff 본문을 Manifest에 보존하지 않아 secret 내용이 evidence로 유입되지 않는다.
- 제품 코드나 migration, Skill, Hook, CI required check를 변경하지 않는다.

## 검증

### 환경과 전제조건

- Provider 호출0, Docker/Chrome 실행0, 클라우드 비용0.
- Issue176 Registry v1을 입력으로 사용한다.

### 명령과 결과

| 명령 또는 시나리오 | 결과 | 판정 |
|---|---|---|
| `python -m pytest backend/tests/test_qa_impact_selector.py -q` | 27 passed | PASS |
| `python -m py_compile qa/impact/selector.py qa/impact/select_impact.py` | syntax error0 | PASS |
| tracked `backend/app/**`, `frontend/src/**` policy audit | 100 paths, unmatched0 | PASS |
| Usage page 단일 변경 | `TARGETED_E2E`, `usage_credits`만 선택 | PASS |
| Generate page 단일 변경 | prompt/T2I/T2V/I2V 4개 선택 | PASS |
| 공용 client 또는 QA 계약 변경 | scenario10 `FULL_E2E` | PASS |
| unknown runtime path | unmatched 기록 + scenario10 `FULL_E2E` | PASS |
| docs-only 변경 | scenario0 `NO_E2E_REQUIRED` | PASS |
| rename/delete Git Adapter | 이전·새 경로 보존 및 영향 유지 | PASS |
| 조작 후 SHA 재계산 Manifest | mapping 재계산으로 거부 | PASS |
| core `070843e` vs 직전 revision 실제 CLI | changed8, selected10, excluded0, unmatched0, `FULL_E2E` | PASS |
| backend `python -m pytest` | 1851 passed, 3 guarded skipped, 기존 Windows/Bash path 검사 1 failed | 기존 환경 예외 재현 |
| backend 동일 실행에서 기존 path 검사만 제외 | 1851 passed, 3 skipped, 1 deselected | PASS |
| frontend `npm run lint`, `npm run build` | TypeScript 검사와 production build 완료 | PASS |
| `docker compose --env-file .env.example config --quiet` | 유효한 Compose 구성 | PASS |
| `git diff --check` | whitespace error 없음 | PASS |

27개 Interface test는 변경 순서 무관성, Policy/Schema hash, 안전하지 않은 경로6종,
invalid/same revision3종, duplicate, mixed docs/product, 실제 임시 Git 저장소 CLI와 rename을
포함한다.

전체 backend의 유일한 실패는 Windows absolute path를 `bash -n`에 넘길 때 경로가
손실되는 기존 host-path 검사다. 해당 검사만 제외하면 1851개가 통과했다.

## 결과와 영향

- Agent가 “어떤 QA를 실행할지”를 임의 서술이 아닌 versioned Policy로 결정할 수 있다.
- 현재 제품 경로100개가 모두 명시적 rule에 포함돼 fallback 빈도를 측정할 기준이 생겼다.
- unknown path는 속도 최적화보다 회귀 누락 방지를 우선해 전체 E2E로 승격한다.
- Evidence level: `Implemented`. 실제 Chrome journey 실행과 PR merge gate는 아직 아니다.

## 남은 위험과 다음 단계

1. Manifest의 selected scenario를 실행할 격리 mock fixture lifecycle을 구현한다.
2. Chrome DevTools Adapter가 UI/URL/Network/Console evidence를 수집하도록 한다.
3. DB/asset/usage probe와 결합해 Issue176 Receipt를 생성하고 validator로 판정한다.
4. 그 다음 static regression, E2E Receipt, cleanup, stale revision을 통합 gate로 묶는다.
5. 마지막 단계에서만 branch protection과 merge decision 권한을 연결한다.

새 제품 경로가 추가될 때 policy coverage 테스트가 명시적 mapping 추가를 요구한다. 실제
Google/Vertex, cloud ingress, mobile, concurrency/race 선택 정책은 별도 live profile 없이
이 구현으로 검증됐다고 주장하지 않는다.
