# CreativeOps Studio Portfolio Evidence

이 디렉터리는 CreativeOps Studio의 `AI Full Stack Engineer`, `FDE`,
`AX Consultant`, `AI Platform Engineer` 포트폴리오 근거를 Issue 단위로 보존한다.
제품 기능 목록보다 어떤 사용자·비즈니스·운영 문제가 있었고, 어떤 증거로 원인을
판단했으며, 어떻게 해결하고 성과를 검증했는지를 우선한다.

## Evidence Levels

| 등급 | 의미 | 필요한 근거 |
|---|---|---|
| `Implemented` | 현재 소스에 구현되어 자동 검증할 수 있다. | 코드와 test/build/static validation |
| `Mock Verified` | 외부 서비스는 fake/mock으로 대체하고 로컬 실행 경계를 실제 검증했다. | 격리 runtime, 재현 명령, 결과와 제한 사항 |
| `Live Verified` | 특정 날짜와 revision의 실제 runtime에서 관찰했다. | 실행 환경, 명령, metric, 결과 |
| `Planned` | 설계 또는 Issue만 있고 실제 실행하지 않았다. | 계획, 위험, 후속 Issue |

등급은 현재 runtime 상태와 분리한다. 과거에 검증한 GKE 기능은 `Live Verified`로
유지하지만, 현재 GKE workload와 node pool은 비용 관리를 위해 `Paused` 상태다.
과거 AWS 배포도 실검증 증거는 유지하지만 현재 stack 상태는 `Destroyed`다.

## Current Capability Matrix

| Capability | Level | Evidence | Current state |
|---|---|---|---|
| Mock multimodal golden path | `Live Verified` | [Mock runbook](../runbooks/local-mock.md), [smoke workflow](../../.github/workflows/smoke-mock-golden-path.yml) | 로컬 기본 모드 |
| Durable job/outbox/Celery processing | `Live Verified` | [Architecture](../architecture.md), [job lifecycle](../job-lifecycle.md) | Compose와 GKE에서 검증 |
| GKE, managed data, Workload Identity | `Live Verified` | [GCP Terraform](../../infra/gcp/README.md), [GKE runbook](../runbooks/gcp-gke.md) | 비용 관리 pause |
| HPA와 node-pool autoscaling | `Live Verified` | [Current work evidence](../current-work.md), [HPA Terraform](../../infra/gcp/k8s-hpa.tf) | HPA off, node pool paused |
| Managed Prometheus, alerts, dashboard, SLO | `Live Verified` | [Monitoring Terraform](../../infra/gcp/monitoring.tf), [GKE runbook](../runbooks/gcp-gke.md) | 리소스 보존, workload paused |
| Image scan, SBOM, digest release, rollback | `Live Verified` | [Supply-chain workflow](../../.github/workflows/image-supply-chain.yml), [release script](../../scripts/deploy_gcp_release.sh) | CI 구현 유지 |
| Vertex Gemini/Imagen/Veo boundary | `Live Verified` | [Provider modes](../provider-modes.md), [Vertex pilot runbook](../runbooks/prompt-enhancement-vertex-pilot.md) | 추가 유료 실행 No-Go |
| Prompt enhancement paired evaluation | `Implemented` | [Evaluation gate](../runbooks/prompt-enhancement-evaluation-gate.md), [evaluation package](../../evals/prompt_enhancement) | post-fix live rerun 미수행 |
| Alembic schema control and guarded local reset | `Mock Verified` | [Issue #94 record](issue-94-schema-control.md), [G1 specification](../initiatives/g1-schema-control-spec.md) | Two isolated cycles, drift refusal/recovery, and product golden path passed |
| User and Session persistence | `Mock Verified` | [Issue #96 record](issue-96-user-session-persistence.md), [G2 specification](../initiatives/g2-user-session-persistence-spec.md) | G2 merged; schema reused unchanged by G3 |
| Backend Google OAuth and Session lifecycle | `Mock Verified` | [Issue #98 record](issue-98-auth-session-lifecycle.md), [G3 specification](../initiatives/g3-auth-session-lifecycle-spec.md) | Two real Postgres/Redis cycles, HTTP-to-storage and generation passed; no live Google login |
| Browser login and race-safe Session UX | `Mock Verified` | [Issue #101 record](issue-101-authenticated-workspace-ux.md), [PR #102](https://github.com/bbungjun/AI_multimodal_platform/pull/102) | Module/Chromium/isolated generation and required CI passed; follow-up authorizes CI-gated squash auto-merge (status in PR); no live Google or backend access-control claim |
| Owner persistence and authenticated admission | `Mock Verified` | [Issue105 evidence](issue-105-owner-persistence-admission.md) | New writers; complete read/file/delete/ops isolation remains G4.3 |
| Worker ownership and idempotent pipeline linking | `Mock Verified` | [Issue107 evidence](issue-107-worker-ownership-invariants.md) | Two real PostgreSQL/HTTP/Celery cycles, lock-observed races, Session-expiry independence; no migration, live provider or complete G4.3 access-control claim |
| Metadata owner scoping, safe deletion and private JSON cache | `Mock Verified` | [Issue110 evidence](issue-110-metadata-ownership-access.md) | Two actual cycles, each8 access groups/348 checks/2 deletion races; Linux928 PASS. File/Range/ops remains G4.3B; delivery status in record |
| Per-User credits and Master console | `Planned` | [Initiative source of truth](../initiatives/auth-credits-master-console.md) | Later bounded Goals; not implemented |
| File ownership, Range and Master-only operations | `Implemented` | [Issue112 execution](issue-112-file-ops-access.md) | B16/migration0, unit proof passed; first runtime hit budget and failed, cleanup0. Not Mock Verified; verification replan pending, no PR/merge |
| GPU node pool와 GPU telemetry | `Planned` | [Issue #89](https://github.com/bbungjun/AI_multimodal_platform/issues/89) | 미구현 |
| Distributed training operations | `Planned` | [Issue #89](https://github.com/bbungjun/AI_multimodal_platform/issues/89) | 범위 외, 미구현 |

## Representative Operational Evidence

### Autoscaling And Load

- GKE HPA validation ran 590 k6 iterations and 1,770 HTTP requests.
- Checks passed at 100%, HTTP failure rate was 0%, and request-duration p95 was
  53 ms.
- HPA creation and removal were both applied through Terraform, and the final
  drift check returned no changes.
- The detailed environment, commands, and rollback evidence remain in
  [current-work.md](../current-work.md).

### Detection And Recovery

- A controlled provider failure produced 20 requests, three HTTP 5xx responses,
  a 15% 5xx ratio, and three bounded `vertex_request_invalid` failures.
- Both Terraform-managed alerts opened incidents. After mock-mode recovery,
  both incidents resolved and the Terraform drift check returned no changes.
- The alert design and operator queries are in the
  [GKE runbook](../runbooks/gcp-gke.md).

### Supply Chain And Rollback

- Trivy initially blocked runtime images with fixable HIGH/CRITICAL findings;
  multi-stage/runtime dependency remediation cleared the gate.
- A controlled candidate health failure triggered automatic Terraform rollback
  of API, worker, dispatcher, and frontend image digests.
- All four rollouts recovered and external health returned ready in mock mode.

### Provider Failure Handling

- Bounded Vertex pilot runs exposed structured-response failures and client
  timeout masking.
- The runner preserved prompt-free usage ledgers, persisted a safe failed
  lifecycle, and stopped without silently starting replacement runs.
- The diagnosis and contract-repair boundary are recorded in
  [Vertex prompt enhancement troubleshooting](../troubleshooting/vertex-prompt-enhancement-invalid-response.md).

## Issue Records

G4.3: [Issue109 design](issue-109-ownership-access-design.md)의 A/B 분할 승인 후
[Issue110 A 실행](issue-110-metadata-ownership-access.md)에서 metadata Mock Verified.
A16 구현/B16 후보, actual2cycle/전체 회귀 완료; 최종 delivery는 실행 기록 참조.

| Issue | Record | Status |
|---|---|---|
| [#87](https://github.com/bbungjun/AI_multimodal_platform/issues/87) | [Platform evidence design and record](issue-87-platform-evidence.md) | [PR #91](https://github.com/bbungjun/AI_multimodal_platform/pull/91) merged, CI passed |
| [#88](https://github.com/bbungjun/AI_multimodal_platform/issues/88) | [Mock-first operations evidence design](issue-88-mock-ops-evidence.md) | Design complete, implementation planned |
| [#94](https://github.com/bbungjun/AI_multimodal_platform/issues/94) | [Schema control and safe local reset](issue-94-schema-control.md) | Mock Verified at `6aa8a1f`; [PR #95](https://github.com/bbungjun/AI_multimodal_platform/pull/95) merged |
| [#96](https://github.com/bbungjun/AI_multimodal_platform/issues/96) | [User and Session persistence](issue-96-user-session-persistence.md) | Mock Verified at `2a4c8ab`; [PR #97](https://github.com/bbungjun/AI_multimodal_platform/pull/97) merged |
| [#98](https://github.com/bbungjun/AI_multimodal_platform/issues/98) | [Backend OAuth and Session lifecycle](issue-98-auth-session-lifecycle.md) | Mock Verified at `ec42d61`; [PR #100](https://github.com/bbungjun/AI_multimodal_platform/pull/100), strict-check squash auto-merge |
| [#103](https://github.com/bbungjun/AI_multimodal_platform/issues/103) | [Authenticated mock verification harness](issue-103-authenticated-mock-harness.md) | Mock Verified at `471b76e`; two auth12/scenarios3/cleanup cycles, Linux542 PASS; ownership enforcement remains G4.2/G4.3 |
| [#105](https://github.com/bbungjun/AI_multimodal_platform/issues/105) | [Owner persistence and admission](issue-105-owner-persistence-admission.md) | Mock Verified: schema2/auth1/final admission2, Linux658 PASS; exact20 paths/one migration, delivery linked in record |
| [#107](https://github.com/bbungjun/AI_multimodal_platform/issues/107) | [Worker ownership and pipeline/race proof](issue-107-worker-ownership-invariants.md) | Planned / Goal Prepared: exact11 paths, migration0, baseline282 PASS; no B implementation/runtime proof yet |
| [#89](https://github.com/bbungjun/AI_multimodal_platform/issues/89) | GPU operations and CI/CD evidence | Planned |
| [#90](https://github.com/bbungjun/AI_multimodal_platform/issues/90) | Capacity, recovery, dependency failure, and cost | Planned |

새 기록은 [TEMPLATE.md](TEMPLATE.md)를 복사해 작성한다. `docs/current-work.md`에는
현재 handoff만 간결하게 남기고, 장기간 유지할 문제-해결-결과는 이 디렉터리에서
관리한다.

## Evidence Safety

- credential, access token, Secret payload, prompt 원문과 provider raw response를
  기록하지 않는다.
- 개인 이메일, cloud account number, 실제 project ID와 개인 PC absolute path를
  포트폴리오 artifact에 넣지 않는다.
- 긴 원본 로그보다 실행 명령, 안전한 public error code, metric 요약과 결과를 남긴다.
- 현재 코드로 검증하지 않은 과거 결과에는 날짜 또는 revision을 붙인다.
