# Issue124 — Gemini Prompt Credit Integration

## 배경과 문제

G5는 월간 크레딧과 예약·정산·반환을 구현했지만 실제 제품 호출자가 없었다.
Prompt Enhancement는 호출 전 잔액을 확보하지 않았고, 재전송과 동시 요청을 한 번의
비용으로 식별할 durable request identity도 없었다. G6는 생성 Job이나 Imagen/Veo로
범위를 넓히지 않고 이 한 흐름을 운영 가능한 과금 경계에 연결했다.

## 관측과 원인 분석

초기 v1 Goal의 required UUID는 기존 ownership/golden-path caller 두 곳을 깨뜨렸지만
두 경로가 allowlist에 없었다. 구현 전에 중단하고 사용자 승인 v2에서 같은 exact14
안의 경로를 교체했다. 첫 전체 ownership 실행은 두 synthetic actor가 같은 UUID를
공유해 두 번째 actor가409로 거절되는 harness 결함을 찾았다. 첫 Linux 전체 회귀는
기존 pre-auth 보안 테스트가 의존한 `prompts.enhancer` test seam 제거를 찾았다.

## 해결과 판단 근거

`prompt_credit`를 하나의 deep Module로 두고 route는 actor/payload/session만 넘기는 얇은
adapter로 유지했다. UUID로 bounded reserve/terminal key를 만들고, 최대 세 개 응답을
덮는 결정적 envelope로 먼저 reserve한다. 트랜잭션을 닫고 provider를 호출하며, 성공
결과 insert와 두 meter settle은 원자적이다. provider/저장 실패는 새 트랜잭션에서
hold를 release한다. 동일 owner/UUID/payload만 완료 replay를 허용한다.

held lease를 추측으로 정리하면 provider 결과를 무료 처리하거나 이중 과금할 수 있어
자동 reconciler는 후속 운영 Goal로 남겼다. Harness는 actor별 결정 UUID로 고쳤고,
route의 비동작 compatibility import로 기존 보안 test seam을 보존했다.

## 검증과 결과

- 최종 코드 `87dca6b`: 승인된 non-document14, migration0.
- isolated prompt-credit 2회: 각 four groups, checks35, race1, head0006,
  container/volume/network cleanup0.
- accounting/lifecycle/auth 통과; auth50 p95 8.432ms.
- ownership all/2: complete4,1006.641s. ownership access348/delete race2 두 번,
  file FOVE310/two actors10 stages 두 번, cleanup0.
- tracked-only Linux1461 passed/3 guarded skips. Windows1460 passed/3 skips와
  기존 Bash native127 한 건; untouched base에서도 동일 재현.
- Compose 두 구성, frontend lint/build, Session48, Chromium34 통과.

월간 크레딧이 부족하면 provider 호출 전에402를 받고, 성공한 Prompt Enhancement만
실제 mock/provider usage 단위로 차감된다. 재전송과 동시 요청은 같은 request ID에서
단일 provider crossing과 단일 정산으로 수렴한다.

## Rollback과 남은 위험

Schema 변경이 없어 rollback은 product wiring commit의 reviewed revert가 우선이다.
이미 정산된 ledger를 수동 삭제하거나 migration downgrade하지 않는다. 현재 상태는
Mock Verified이며 실제 Vertex/GCP 사용량·과금을 의미하지 않는다. held reconciliation,
generation/Imagen/Veo 과금, 개인 Usage UI와 live GCP는 후속 Goal이다.
