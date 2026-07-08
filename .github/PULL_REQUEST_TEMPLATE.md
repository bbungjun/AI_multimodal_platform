## 작업 내용

> 이 PR에서 무엇을 구현/수정했는지 간략하게 설명해 주세요.

## 변경 사항

- 
- 
- 

## 관련 이슈

Closes #

## 검증

- [ ] `git diff --check`
- [ ] `git status --short --branch`
- [ ] `git diff --cached --name-only`
- [ ] Backend: `cd backend && $env:AI_PROVIDER = "mock"; python -m pytest`
- [ ] Frontend: `cd frontend && npm run build`
- [ ] Compose: `docker compose --env-file .env.example config --quiet`
- [ ] 필요 시 smoke: `python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90`

## Provider / 비용 / 비밀정보

- [ ] 기본 검증은 `AI_PROVIDER=mock` 기준으로 수행했다.
- [ ] Vertex live QA 또는 cloud apply가 있다면 비용 위험과 목적을 명시했다.
- [ ] `.env`, ADC 파일, service-account JSON, API key, private key를 커밋하지 않았다.
- [ ] credential 값이나 credential JSON 내용을 PR 본문/로그/문서에 붙이지 않았다.

## Terraform / 배포 영향

- [ ] Terraform 변경 없음
- [ ] Terraform 변경 있음: `terraform fmt -recursive -check`, `terraform init -backend=false`, `terraform validate` 결과를 남겼다.
- [ ] 실제 cloud apply 없음
- [ ] 실제 cloud apply 있음: 대상 project/account, region, 생성/삭제 리소스, rollback 방법을 남겼다.

## 리뷰어 참고사항

> 리뷰어가 특히 집중해서 봐야 할 부분, 남은 위험, 의도적으로 미룬 작업을 적어 주세요.
