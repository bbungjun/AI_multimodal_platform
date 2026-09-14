# CreativeOps Agent QA Contracts

이 디렉터리는 Agent QA가 **무엇을 검증해야 하는지**와 **어떤 증거가 있어야
통과할 수 있는지**를 정의한다. Chrome 조작 구현이나 Skill 실행 순서는 여기의
외부 Interface가 아니다.

```powershell
python qa/contracts/verify_registry.py
```

명령은 모든 scenario를 닫힌 vocabulary로 검사하고 Registry SHA-256과 계약 수를
JSON으로 출력한다. 다음 Goal의 변경 영향 분석기, QA Skill과 Receipt 생성기는 이
검증된 Registry를 입력으로 사용한다.

## 판정 규칙

1. 선택한 scenario의 product assertion이 하나라도 false면 `FAIL`.
2. product assertion 실패는 없지만 필수 assertion/evidence 또는 도구 결과가
   부족하면 `BLOCKED`.
3. 모든 필수 assertion/evidence가 있고 cleanup이 모두0이며 실행 전후 source가
   같을 때만 전체 `PASS`.
4. `NOT_APPLICABLE`은 실행 전에 선택하지 않은 scenario에만 사용한다.
5. 알려진 결함은 `allow_failure`로 통과시키지 않는다. Registry는 올바른 제품 계약을
   유지하고 실제 실행 결과가 이를 위반하면 `FAIL`을 낸다.

## 비밀정보와 경로

Contract와 Receipt에는 prompt 원문, cookie, Authorization, OAuth code/state,
계정 식별 정보와 개인 PC absolute path를 저장하지 않는다. 비교가 필요하면 실행
중 메모리에서 수행하고 boolean 또는 안전한 hash 결과만 남긴다.
