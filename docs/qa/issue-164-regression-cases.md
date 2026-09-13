# Issue164 — AI 탐색 결과에서 도출한 E2E 회귀 명세

상태: **테스트 케이스 명세 작성됨 / 새 자동 실행 코드 미구현**.
기준 revision과 실제 실행 기록은 [QA 보고서](../portfolio/issue-164-ai-ui-qa.md)를 따른다.
계약 기반 기대값을 사용하며 이번에 관측한 버그를 성공 조건으로 고정하지 않는다.

모든 신규 실행은 명시적인 mock 환경·격리 계정·예산 내에서 수행해야 한다. fixture에
충분한 크레딧을 부여하는 준비와 권한 설정은 운영 사용자 데이터 수정과 구분한다.
로그에는 prompt/OAuth code/state/cookie/profile 원문을 포함하지 않는다.

| TC | Given | When | Then (회귀 합격 기준) | 현재 테스트 / 이번 관측 |
|---|---|---|---|---|
| TC01 | Free·잔액 충분 | Fast 이미지2장 요청을 UI 또는 직접HTTP로 제출 | 명시적인 정책 오류로 거절, Job/outbox/예약/과금 생성0. UI에는1장 한도가 안내됨 | 정책값 unit만 존재. QA20은201/completed → FAIL |
| TC02 | Free·잔액 충분 | Veo Fast6초 및8초를 각각 요청 |4초 초과 거절. 허용4초는 완료. 거절 시 신규 Job/예약0 | 요청별 Free cap E2E 없음. QA22의6초201 → FAIL |
| TC03 | Free 계정 | 모델 선택기를 열고 Standard/Ultra 선택 시도 | 사용 가능 모델만 선택하거나 제한과 변경 방법 안내. 직접HTTP 금지 모델은403 | backend meter 거절 있음. UI 안내/문구 없음 |
| TC04 | 잔액이 Pipeline 예상 예약액 미만 | Pipeline 생성 클릭 | 비용/부족분과 조치가 이해 가능한 문구. Job/outbox/예약0. raw code만 노출하지 않음 | backend quota 거절 있음. QA26 raw code → UX FAIL |
| TC05 | 일반 사용자 | 메뉴 확인·운영 클릭 및 직접 ops API 호출 | 역할에 맞는 메뉴/설명. ops API403은 유지. 권한 없는 polling 반복 없음 | backend 권한 검사 있음. QA25 메뉴 및 raw code 노출 |
| TC06 | 홈 화면 | 모델/템플릿/두 설정/검색을 각 조작 | 명세된 화면을 열거나 미지원임을 표시하고 비활성. 무반응 클릭 없음 | 해당 E2E 없음. QA01–04/41 무반응 |
| TC07 |0개/1개/10개 서로 다른 기록 fixture | 기록을 열고 새 작업 후 재조회 | 메뉴 개수는 정의된 기준의 실제 수와 일치하거나 개수 표시를 제거 | 해당 E2E 없음. QA29/36에서8 고정 |
| TC08 | mock 영상 완료 | 상세의 재생 컨트롤 조작 | 재생 가능한 fixture면 loadeddata/play/time progression 검증. placeholder 정책이면 명시적 안내·파일 열기 fallback 제공 | bytes unit만 존재. QA13/23 재생 불가 |
| TC09 | 단일/복수 이미지 및 영상 완료 | 각 결과의 다운로드 버튼 클릭 | 브라우저 download 이벤트·MIME/파일 길이·소유권을 검증. 세션 없는/다른 사용자 파일은 거절 | backend 파일GET 테스트 있음. 실제 다운로드 UI 없음 |
| TC10 | 원본 입력과 enhancement 초안 | 버리기/원본 유지/편집 후 수락을 각각 실행 | 앞2개는 원본 유지. 수락은 편집 값이 최종 generation payload와 일치. 의도치 않은 자동 대체 없음 | 캡처 script 수락 있음. 세 경로 정식 E2E는 없음; 이번 수동 AI 관측 정상 |
| TC11 | 이미지2개가 있는 완료 작업 | 각 I2V 버튼 클릭·모션 입력·생성 | 각각 정확한 source_asset_id로 실제 Job 생성. 소스 미선택은 비활성/거절 | backend 소유권 있음. 다중 이미지 버튼 연결 E2E 없음; 이번 소스 선택 정상 |
| TC12 | 이미지→영상 양단 예약에 충분한 격리 예산 | Pipeline 생성 버튼 클릭 | parent/child 둘 다 완료·상세 표시·파일 접근·실제 예약/정산 일치 | 실HTTP pipeline 검증 있음. 이번 일반사용자 UI는402로 성공 경로 미검증 |
| TC13 | 의도적 mock 실패 Job | 상세 및 기록에서 각각 재시도 | 새 Job/원본 링크·확정payload 보존·과금 중복 없음. sentinel 유지면 실패가 예상 결과 | API retry proof 있음. 양쪽 버튼 정식 browser 회귀 부족; 이번201 정상 |
| TC14 | 기록11개 이상·필터별 fixture | 각 필터·페이지 크기·다음/이전·행 클릭 | query/행수/offset/상세 일치, 변경 시 offset0, 빈 결과와 비활성 상태 정상 | API list/filter proof 있음. 전체 UI E2E 없음; 이번10행 경계 정상 |
| TC15 | 이번 실행이 소유한 삭제 대상1개 | 삭제→취소, 다시 삭제→확인을 각각 수행 | 취소는 DELETE0; 확인은DELETE1·204·목록 감소·파일 접근 불가·재시도/부모 데이터 보존 | API 삭제 proof 있음. 이번 확인 dialog 도구 한계로 취소 경로 미검증 |
| TC16 | authenticated workspace | 계정 열기·Escape·로그아웃·비공개 링크·재로그인 | 팝오버 접근성/게이트/세션종료 정상; 새로 선택한 허용 복귀 경로 보존 | auth suite 있음. logout 이후 익명 메뉴 이동 F08 분기 없음 |
| TC17 | 사용량 정상/503/네트워크 실패 fixture | 새로고침/다시 시도 | 요청 중복 방지·예전 값 격리·복구 상태 표시 | `usage-ux.spec.ts`에 이미 있음. 정상 경로 이번에도 확인 |

TC15의 확인 동작은 제품의 되돌릴 수 없는 삭제를 발생시킨다. 자동화 도구가
dialog를 자동 처리하는지 사전 검증하고, 승인 경계가 보존되는 실행기를 사용한다.
이번 도구 timeout을 취소 성공이나 확인창 검증 성공으로 간주하면 안 된다.

이 명세를 구현할 때 API helper로 POST한 테스트와 실제 생성 버튼을 클릭한 테스트를
구별한다. `HTTP201`, `state=completed`, `video/mp4` 각각만으로 미디어 전달/재생
성공을 판정하지 않는다.
