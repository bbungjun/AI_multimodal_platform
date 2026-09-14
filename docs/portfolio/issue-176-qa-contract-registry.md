# Issue176 — Agent QA Contract와 Scenario Registry v1

## 배경과 문제

Agent가 개발부터 QA까지 수행하고 최종적으로 PR merge 판단을 맡으려면, 브라우저를
조작했다는 사실보다 **무엇을 어떤 증거로 검증했는지**가 먼저 고정돼야 한다. 기존
Issue164·168·170·172·174 QA는 실제 Chrome 흐름과 결함을 기록했지만 실행별 체크리스트가
문서에 흩어져 있어 Agent가 일부 화면만 확인하고 전체 PASS를 선언하거나, 알려진 결함을
예외 처리하거나, 다른 revision의 결과를 재사용할 위험이 있었다.

## 기대 동작과 실제 동작

| 구분 | 내용 |
|---|---|
| 기대 동작 | 같은 revision과 versioned QA 계약을 기준으로 UI·Network·DB·asset 증거를 대조하고, 누락과 실패를 구분한 machine-readable Receipt를 만든다. |
| 이전 상태 | 실행 보고서는 있었지만 공통 scenario schema, 전체 Registry hash, Receipt 판정기가 없었다. |
| 영향 | 검증 범위·증거·cleanup이 불완전해도 Agent가 일관되게 차단할 계약 경계가 없었다. |

## 해결 방법과 판단 근거

`qa/contracts/`를 QA 시스템의 좁고 깊은 계약 Module로 만들었다. 외부 진입점은 다음
명령 하나다.

```powershell
python qa/contracts/verify_registry.py
```

Registry v1은 다음 10개 사용자 흐름을 소유한다.

| Scenario | 핵심 검증 |
|---|---|
| `auth_login` | start307, callback303, session200, logout401, route |
| `prompt_review` | 원문 보존, 편집·수락, 최종 생성 입력 동일성 |
| `t2i_generation` | 입력 제한, Free 정책 거부, 부작용0, PNG decode |
| `t2v_generation` | Free 길이 제한, 상태 전이, video 결과 사용 가능성 |
| `i2v_generation` | source 선택·동일성, 영상 상태·asset |
| `pipeline_generation` | parent/child owner·asset 연결, reservation 정산 |
| `history_navigation` | 필터, offset, pagination, 상세 identity, 삭제 취소 |
| `usage_credits` | plan·잔액·원장·held 정합성, reload |
| `failure_retry` | 실패 asset 부재, retry link, 완료, 중복 과금 방지 |
| `role_ops_master` | User 접근 거부·polling0, Master 화면과 API |

각 assertion은 UI snapshot, URL, Network, Console, DB, asset probe, runtime Receipt,
usage read model, access log 중 필요한 증거를 명시한다. 시나리오는 persona, mock fixture,
관련 코드 경로, 사용자 의도 기반 step, 제외 범위를 함께 보존한다.

판정 우선순위는 제품 기대 위반 `FAIL` > 증거·실행·cleanup 부족 `BLOCKED` > 모든 선택
항목 검증 완료 `PASS`다. 실행 전 선택하지 않은 항목만 `NOT_APPLICABLE`이며 Receipt는
Registry의 모든 scenario를 빠짐없이 포함해야 한다. 전부 제외한 Receipt는 PASS가 아니다.

Registry SHA-256은 registry, scenario/receipt schema, 10개 scenario의 raw bytes 전체를
포함한다. Receipt의 revision과 SHA가 현재 실행 대상과 다르면 stale evidence로 거부한다.
이는 Agent가 과거 성공 결과를 새 코드에 재사용하는 것을 막는 최소 경계다.

Issue174에서 확인된 Free 요청 크기 결함은 allow-fail로 기록하지 않았다. T2I 계약은
초과 요청의 정책 거부와 job/outbox/reservation 부작용0을 요구하므로 현재 제품이 그대로면
실행 단계에서 정직하게 FAIL해야 한다.

## 안전장치와 Trade-off

- Contract와 Receipt는 닫힌 field/vocabulary를 사용한다. 알 수 없는 field, persona,
  operator, evidence source, 중복 ID를 거부한다.
- prompt 원문, cookie, Authorization, OAuth code/state, 계정 식별자와 개인 PC absolute
  path를 저장하지 않는다. 값 비교는 실행 중 수행하고 boolean 또는 안전한 집계만 남긴다.
- Receipt는 source unchanged와 browser/MCP/Vite/runtime cleanup 수를 요구한다. 하나라도
  남으면 제품 assertion이 모두 참이어도 BLOCKED다.
- JSON Schema만 두지 않고 Python 표준 라이브러리 validator를 함께 제공했다. 다음 단계
  실행기와 CI가 추가 dependency 없이 동일한 판정을 사용할 수 있기 때문이다.
- 이번 slice는 계약만 구현했다. Chrome/DevTools executor, 변경 영향 selector, fixture
  lifecycle, evidence capture, CI gate, merge policy는 아직 구현하지 않았다.

## 검증

### 환경과 전제조건

- Provider mode: contract 기준 `mock`; 실제 provider 호출0.
- Runtime: Python contract validator만 실행; Docker/Chrome 미실행.
- 비용: 외부 AI 생성 요청0, 클라우드 비용0.

### 명령과 결과

| 명령 | 결과 | 판정 |
|---|---|---|
| `python qa/contracts/verify_registry.py` | scenario10, assertion68, Receipt contract true, stable SHA 출력 | PASS |
| `python -m pytest backend/tests/test_qa_contract_registry.py -q` | 18 passed | PASS |
| backend `python -m pytest` | 1824 passed, 3 guarded skipped, 기존 Windows/Bash path 검사 1 failed | 기존 환경 예외 재현 |
| backend 동일 실행에서 기존 path 검사만 제외 | 1824 passed, 3 skipped, 1 deselected | PASS |
| frontend `npm run lint`, `npm run build` | TypeScript 검사와 Vite production build 완료 | PASS |
| `docker compose --env-file .env.example config --quiet` | 유효한 Compose 구성 | PASS |
| `docker compose config --quiet` | 로컬 `.env`에 `POSTGRES_USER`가 없어 interpolation 중단 | BLOCKED |
| `git diff --check` | whitespace error 없음 | PASS |

테스트는 schema 변경 시 SHA 변경, absolute/상위 경로 거부, secret-like field 거부,
완전한 Receipt PASS, assertion false FAIL, evidence 누락 BLOCKED, cleanup/source 변경
BLOCKED, 전체 미선택 BLOCKED, scenario 누락·unknown assertion·stale revision 거부,
Free 정책의 strict contract를 검증한다.

전체 backend의 유일한 실패는 `bash -n`에 Windows absolute path를 넘기면서
`C:AI_multimodal_platform...`로 해석되는 기존 host-path 검사다. 동일 검사를 제외하면
1824개가 통과했다. default Compose BLOCKED도 제품/계약 결함이 아니라 로컬 `.env`의
필수 비밀 없는 변수 부재이며 `.env`를 읽거나 수정하지 않았다.

## 결과와 영향

- Agent QA가 따라야 할 제품 흐름과 증거 기준이 10개 scenario/68개 assertion으로
  machine-readable하게 고정됐다.
- QA 결과를 PASS/FAIL/BLOCKED/NOT_APPLICABLE로 재현 가능하게 판정하고, 어떤 계약과
  code revision에서 나온 결과인지 hash로 묶을 수 있다.
- Evidence level: `Implemented`. 실제 E2E 자동 실행 또는 PR merge 자동화 완료를
  의미하지 않는다.

## 남은 위험과 다음 단계

1. 변경 파일을 관련 scenario에 보수적으로 매핑하는 impact selector를 구현한다.
2. 격리 mock fixture와 실제 Chrome DevTools executor가 assertion evidence를 Receipt로
   수집하도록 한다.
3. 기존 backend/frontend 회귀와 E2E Receipt를 하나의 QA gate로 합친다.
4. 마지막에만 branch protection, stale revision 재검사, 위험도 정책을 포함한 merge
   decision을 추가한다. 제품 FAIL이나 BLOCKED에서는 merge 권한을 주지 않는다.

실제 Google/Vertex, 영상 품질, cloud ingress, mobile viewport와 concurrency/race는 별도
계약 및 비용·안전 승인 없이는 이 결과로 주장하지 않는다.
