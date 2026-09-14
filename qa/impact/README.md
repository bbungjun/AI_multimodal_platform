# CreativeOps Agent QA Impact Selector

이 Module은 Git의 두 immutable revision 사이 변경을 QA Registry scenario에
보수적으로 매핑한다. 외부 Interface는 다음 명령 하나다.

```powershell
python qa/impact/select_impact.py --base <40자리-Git-SHA> --head <40자리-Git-SHA>
```

결과 JSON은 변경 파일, Registry/Policy SHA, 전체 또는 선택 실행 분류, 10개 scenario의
선택·제외 결정과 Selection SHA를 포함한다. branch 이름, working tree, 줄 단위 diff는
입력으로 받지 않는다.

## 선택 우선순위

1. `qa/contracts/`, `qa/impact/`, 공용 runtime·frontend shell 변경은 `FULL_E2E`다.
2. Registry의 `related_paths` 또는 versioned scenario rule과 일치하면
   `TARGETED_E2E`다.
3. 알려지지 않은 경로는 자동 제외하지 않고 fail-safe `FULL_E2E`로 승격한다.
4. 모든 변경이 문서·테스트·인프라 전용 rule과 일치할 때만
   `NO_E2E_REQUIRED`다.
5. 문서와 제품 코드가 섞이면 제품 코드의 선택 범위를 따른다.

`NO_E2E_REQUIRED`는 전체 QA PASS가 아니다. 이후 QA gate가 정적 검사 결과와 함께
판단할 입력이다. Chrome 실행 Receipt를 전부 `NOT_APPLICABLE`로 만들어 PASS시키는
용도로 사용하지 않는다.

## 안전 규칙

- base/head는 서로 다른 40자리 commit SHA여야 한다.
- absolute path, `..`, backslash, control character, `.env`, private key와 credential
  형태의 경로는 거부한다. `.env.example`만 예외로 허용한다.
- rename/copy는 이전 경로와 새 경로를 모두 평가한다.
- 같은 입력은 변경 파일 순서와 관계없이 같은 Selection SHA를 만든다.
