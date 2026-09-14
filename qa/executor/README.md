# Agent QA Chrome DevTools Executor

이 Module은 Impact Selector가 선택한 scenario 하나를 소유 mock runtime과 실제 Chrome에서
실행한다. 현재 제공하는 첫 Adapter는 `auth_login`이다.

```powershell
python scripts/agent_qa_executor.py `
  --base <서로 다른 40자리 base commit SHA> `
  --head <현재 HEAD의 40자리 commit SHA> `
  --scenario auth_login
```

실행기는 현재 HEAD와 head 입력이 같고 tracked source가 clean일 때만 동작한다. base/head로
Selection Manifest를 다시 만들며, `auth_login`이 선택되지 않았으면 Docker·Chrome을
시작하지 않고 `NOT_APPLICABLE`을 반환한다.

선택된 경우 fresh Postgres/Redis/backend/dispatcher/worker, Vite, Chrome, Chrome DevTools
MCP를 소유한다. navigation, accessibility snapshot, click, read-only pathname/session probe,
Network와 Console 검사는 DevTools MCP를 통과한다. 결과는 ignored
`output/playwright/agent-qa-auth-*/execution.json`에 정제 JSON으로 남는다.

## 판정

- 제품 assertion false: `FAIL`
- 도구 실패, 필수 evidence 미수집, 외부 요청, 예상 밖 Console 오류, source 변경,
  cleanup 미확인·실패: `BLOCKED`
- contract assertion 7개와 모든 guard 통과: `PASS`
- Impact Selector가 해당 scenario를 제외: `NOT_APPLICABLE`이며 runtime 미시작

보고서에는 prompt, identity, cookie, OAuth query, header와 body를 기록하지 않는다.
브라우저 JSON도 허용된 route/status/method, boolean, count, 버전만 Python seam을 통과한다.
현재 다른 9개 scenario Adapter, 전체 Receipt, CI gate와 merge decision은 제공하지 않는다.
