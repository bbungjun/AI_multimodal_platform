# Issue170 — Favicon 수정과 Agent QA 재검증

## 결과

**Mock Verified.** Chrome DevTools MCP로 같은 로그인 흐름을 재실행한 결과,
예상 밖 Console 오류가 1건에서 0건으로 줄고 기존 9개 검사가 모두 통과했다.
에이전트의 발견 → 제품 수정 → 실제 브라우저 재검증을 완료한 좁은 사례다.

- [Issue170](https://github.com/bbungjun/AI_multimodal_platform/issues/170)
- 선행 실행기: [draft PR169](https://github.com/bbungjun/AI_multimodal_platform/pull/169).
  이번 브랜치는 그 head에서 시작했으며 새 draft PR도 main을 대상으로 한다.
  PR169 병합 전에는 main 대비 diff에 선행 하네스가 포함된다.
- 검증 코드: `f06dfd7059eeddb7120006710e2565993e01ce5a`.
- [수정 전 증거](../evidence/issue-168/devtools-login-receipt.json),
  [수정 후 증거](../evidence/issue-170/devtools-login-receipt.json).

## 배경과 원인

Issue168에서 로그인은 성공했지만 `/favicon.ico` 요청이404를 반환하고 Console에
resource-load 오류를 남겼다. `frontend/index.html`에 명시적인 favicon link가 없고
제공되는 icon asset도 없어 Chrome의 기본 favicon 요청을 처리하지 못했다.
인증이나 DB 결함이 아닌 frontend 정적 리소스 누락이다.

## 수정과 판단

- `frontend/public/favicon.svg`에 기존 CreativeOps 심볼의 선과 보라색 gradient를 재사용.
- HTML에 `rel=icon`, `type=image/svg+xml`, `/favicon.svg`를 명시.
- DevTools 증거 수집의 공개 경로 allowlist에 `/favicon.svg`만 추가하고 parser 검증을 확장.
- Console 오류 판정과 기존 9개 검사 조건은 변경하지 않았다. 오류를 무시하거나
  요청을 차단하는 방식, 빈 data URL로 icon 요청만 없애는 방식은 사용하지 않았다.
- 원래 실패 receipt는 덮어쓰지 않는다. 제품 변경은 HTML link와 SVG에 한정된다.

## 실제 재검증

Chrome153 / DevTools MCP1.9.0 / mock OAuth / 실제 backend·Postgres·Redis·worker 환경에서,
새 QA Chrome 프로필을 사용했다. 에이전트는 `take_snapshot`에서 관측한 로그인 버튼을
MCP `click`으로 직접 눌렀고 Network와 Console을 조회했다.

| 측정 항목 | 수정 전 Issue168 | 수정 후 Issue170 |
|---|---|---|
| 브라우저 icon 요청 | `/favicon.ico`404 | `/favicon.svg`200 |
| 예상 밖 Console 오류 | 1 | 0 |
| 로그인 start / callback / me | 307 / 303 / 200 | 307 / 303 / 200 |
| 인증 작업 공간 표시 | 정상 | 정상 |
| 기존 로그인 QA 검사 | 8/9 | 9/9 |
| 브라우저 페이지 외부 HTTP 요청 | 0 | 0 |
| Chrome/MCP 및 owned runtime 잔존 | 0 | 0 |
| 실행기 최종 결과 | exit1 / complete=false | exit0 / complete=true |

로그인 전 `/api/auth/me`401은 기존부터 기대된 익명 응답이며 동일한 기준으로 분류했다.
React Router future-flag 경고는 여전히 존재한다. 따라서 'Console 메시지 전체0'으로
표현하지 않는다. 이번 실행은 준비·조작·정리 포함58.656초였으며, 이전85.563초와의
차이는 에이전트 입력 간격에도 영향을 받으므로 latency 개선 수치로 사용하지 않는다.

## 실행한 검증

```powershell
# frontend에서
npm run lint
npm run build
Get-FileHash public/favicon.svg
Get-FileHash dist/favicon.svg

# repository root에서
npm test --prefix qa/devtools
$env:AI_PROVIDER = "mock"
python -m pytest backend/tests/test_devtools_login_qa.py backend/tests/test_verify_mock_oauth_browser.py -q
docker compose --env-file .env.example config --quiet
python scripts/devtools_login_qa.py
git diff --check
```

- frontend lint/build PASS. SVG XML 파싱 및 public/dist 파일 hash 일치.
- QA Node tests5 PASS, 관련 Python tests6 PASS, Compose/diff PASS.
- 대화형 MCP 실행은 [Issue168 재현 절차](issue-168-devtools-login-qa.md#재현)를 사용.
- source hash와 revision이 실행 전후 동일했고 `browser.cleanup=0`,
  `runtime_cleanup=0`을 확인. 종료 후 QA Chrome 프로세스0 및18156 listener 없음 확인.
- 이번 변경에서 전체 backend/Chromium suite와 live provider는 로컬 재실행하지 않았다.
  GitHub CI는 별도 실행 결과이며 이 대화형 QA 자체의 자동 실행을 의미하지 않는다.

## 영향·남은 일·되돌리기

실제 Chrome이 유효한 탭 아이콘을 받아 불필요한404와 해당 Console 오류가 사라졌다.
검증 범위는 local mock 로그인이다. 생성·영상·다운로드 전체 흐름이나 배포 환경의
favicon cache 및 다른 브라우저까지 검증한 것은 아니다.

다음 QA 작업은 이미지 생성 사용자 흐름과 증거 보존 확장이다. Hook이나 자동 병합은
추가하지 않았다. rollback은 HTML link와 SVG 추가를 되돌리는 것이며, 원래404가
다시 발생할 수 있다. migration·인프라·계정 데이터 변경은 없다.
