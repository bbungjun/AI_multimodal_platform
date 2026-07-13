# Prompt Enhancement Benchmark and Mock-First Evaluation Plan

**Status:** Planned under GitHub Issue
[#59](https://github.com/bbungjun/AI_multimodal_platform/issues/59)

**Implementation queue:** Issues
[#60](https://github.com/bbungjun/AI_multimodal_platform/issues/60) through
[#66](https://github.com/bbungjun/AI_multimodal_platform/issues/66)

## Purpose

CreativeOps Studio can create, review, edit, and accept a Gemini prompt
enhancement, but the current product does not measure whether the accepted
enhancement improves the resulting image. Text-level correctness, provider
reliability, and successful image generation are necessary operational checks;
they are not evidence that prompt enhancement adds product value.

This plan adds a reproducible T2I benchmark that compares images generated from
the user's original prompt with images generated from an accepted enhanced
prompt. The first delivery boundary is a complete, deterministic
`AI_PROVIDER=mock` flow. No live Gemini or Imagen call is authorized by this
plan. A cost-bounded Vertex pilot is a separate final task that starts only
after the mock gate passes and the user explicitly approves it.

## Decisions

- Evaluate T2I first. T2V and I2V require different temporal and source-image
  metrics and are out of scope for this benchmark.
- Compare two paired arms: `raw` and `enhanced`.
- Score both arms against the same original user intent, never against the
  enhanced prompt.
- Report VQAScore, ImageReward, and TIFA separately. Do not create a composite
  score until there is evidence that a weighted score is meaningful.
- Treat a benchmark prompt, not an individual generated image, as the
  statistical unit.
- Keep the evaluation harness and heavy scorer dependencies outside the
  production backend and worker dependency set.
- Reuse the existing HTTP enhancement, generation, job, asset, and storage
  contracts so the benchmark exercises the real product flow.
- Keep generated images, model caches, and run artifacts local and ignored.
  Versioned schemas, benchmark definitions, and aggregate reports may be
  committed.
- Mock scores prove orchestration only. They must be visibly marked synthetic
  and must never be presented as image-quality evidence.

## Required Prompt Contract

ADR 0004 states that the prompt submitted in the generation payload is the
source of truth. The benchmark cannot be trusted until runtime execution obeys
that contract.

The current accepted-enhancement flow can send an edited `prompt` together with
an `enhancement_id`, while the backend can recover a hidden provider prompt from
the stored enhancement and prefer it during provider execution. That creates a
risk that the text the user reviewed and the text sent to Imagen are different.

Issue #60 must establish these invariants before paired evaluation begins:

1. `GenerationCreate.prompt` is the exact text passed to the generation
   provider.
2. `enhancement_id` records provenance only; it does not silently override the
   submitted prompt.
3. `Job.prompt` remains the auditable execution prompt.
4. `PromptEnhancement.original`, `PromptEnhancement.enhanced`, enhancer model,
   template version, target mode, target model, and creativity preset remain
   available as enhancement provenance.
5. Each evaluation arm records a SHA-256 hash of the exact execution prompt.
6. If a future provider-specific translation is needed, it must be visible and
   explicitly submitted or accepted. It cannot be a stale hidden rewrite.

With this contract, the paired requests are unambiguous:

```text
raw arm:
  prompt = original_prompt
  enhancement_id = null

enhanced arm:
  prompt = accepted_enhanced_prompt
  enhancement_id = persisted enhancement id
```

## Metric Contract

For benchmark case `i`, let `p_i` be the original user prompt or its frozen,
reviewed canonical evaluation prompt. Let `R_i` be the Raw images and `E_i` be
the Enhanced images.

```text
VQA delta(i) = mean(VQAScore(p_i, E_i))
             - mean(VQAScore(p_i, R_i))

Reward delta(i) = mean(ImageReward(p_i, E_i))
                - mean(ImageReward(p_i, R_i))

TIFA delta(i) = mean(TIFA(p_i, E_i))
              - mean(TIFA(p_i, R_i))
```

The reference prompt must not change between arms. Scoring the Enhanced arm
against the enhanced prompt would reward details invented by the enhancer and
would not measure preservation of the user's original intent.

### Metric roles

| Metric | Role | Interpretation |
| --- | --- | --- |
| VQAScore | Primary alignment signal | Whether the image depicts the complete original request |
| ImageReward | Learned preference signal | Whether the result is visually preferable or polished |
| TIFA | Fine-grained faithfulness diagnostic | Which objects, attributes, counts, and relations were satisfied |

FID, SSIM, LPIPS, and raw pixel difference are not acceptance metrics for this
work. They can measure distribution or image difference, but they cannot decide
whether an enhancement better satisfies the user's request.

## Evaluation Package Boundary

The initial harness should live under a separate repository area:

```text
evals/prompt_enhancement/
  README.md
  pyproject.toml
  schemas.py
  benchmark.v1.jsonl
  generate_pairs.py
  score_pairs.py
  summarize.py
  fixtures/
```

This boundary keeps PyTorch, scorer checkpoints, and evaluator-specific
libraries out of `backend/pyproject.toml` and the production backend/worker
image. The runner calls the existing application over HTTP. It does not import
database sessions or bypass the outbox, dispatcher, state machine, or storage
helpers.

The first implementation stores evaluation state in versioned local artifacts,
not in new database tables. Moving evaluation into the online product would
require a later product decision and, if it adds a new queue or database state
machine, an ADR.

## Versioned Data Contracts

### Benchmark case

Each JSONL record should contain at least:

```json
{
  "schema_version": 1,
  "case_id": "en-short-subject-001",
  "source": "creativeops-benchmark-v1",
  "language": "en",
  "category": "short_subject",
  "original_prompt": "a small blue cup on a desk",
  "evaluation_prompt": "a small blue cup on a desk",
  "target_mode": "t2i",
  "target_model": "imagen-4.0-fast-generate-001",
  "creativity_preset": "balanced",
  "aspect_ratio": "1:1",
  "samples_per_arm": 2,
  "enabled": true
}
```

Korean cases may add a reviewed `evaluation_prompt_en` because the open scorer
models may not have equivalent Korean capability. The original Korean prompt,
the canonical English evaluation prompt, and the review status must be retained
so Korean results can be reported separately rather than mixed silently with
English results.

### Run manifest

The run manifest should contain:

- schema version and run id
- Git commit SHA and dirty-worktree flag
- provider mode
- benchmark file hash
- enhancer model and enhancement-template version/hash
- generation model and effective generation parameters
- metric adapter names, model revisions, and configuration
- start/completion timestamps and current lifecycle state
- Raw/Enhanced request ordering policy
- prompt hashes, job ids, asset ids, file hashes, failures, and retry counts
- mock/real evidence classification
- bootstrap seed, resample count, and metric-specific tie thresholds

### Local artifact layout

```text
evals/prompt_enhancement/runs/<run-id>/
  manifest.json
  pairs.jsonl
  images/
  scores.jsonl
  summary.json
  report.md
```

The entire `runs/` directory and evaluator model cache must be ignored. A
reviewed aggregate report can be copied into a versioned evidence location only
when it contains no generated media, credential, token, or sensitive local
path.

## Evaluation Lifecycle

The local evaluation manifest tracks orchestration state independently of job
state. Individual generation jobs continue to use the existing application
state machine.

```text
planned
  -> enhancing
  -> generating_raw
  -> generating_enhanced
  -> collecting_assets
  -> scoring
  -> summarizing
  -> completed
```

Any stage may transition to `failed` with a controlled public error code and a
resumable checkpoint. Rerunning the same run id must reuse completed arm/job
records and must not create duplicate generation jobs.

Raw/Enhanced submission order should alternate by `case_id` so a systematic
provider-time effect does not always favor the same arm.

## Benchmark Composition

### Mock fixture

Use four to six deterministic cases that cover:

- English and Korean
- short and already-detailed prompts
- a multi-object/count or spatial-relation prompt
- one controlled enhancement or generation failure

The fixture exists only to verify the state flow and report schema.

### Vertex pilot

After the mock gate and explicit approval, Issue #66 is limited to:

- 20 benchmark cases
- two Raw and two Enhanced images per case
- 20 prompt-enhancement requests at most
- 80 generated images at most
- `balanced` creativity preset
- one approved Imagen model and one aspect ratio

The request count, failure count, latency, and cost-relevant operation count
must be recorded. A full benchmark does not start automatically after the
pilot.

### Full benchmark candidate

The later candidate benchmark contains 100 prompts:

- 50 Korean and 50 English prompts
- balanced coverage of short subject, detailed subject, multi-object,
  count/spatial, and style/lighting categories
- four Raw and four Enhanced images per case

This would produce up to 800 images and therefore requires a separate decision
after the pilot report.

## Statistical Protocol

1. Calculate each metric for every generated image.
2. Average image scores within each case and arm.
3. Calculate the paired Enhanced-minus-Raw delta for each case.
4. Aggregate case deltas, not individual images, to avoid treating correlated
   images from one prompt as independent samples.
5. Report mean delta, median delta, and a paired bootstrap 95% confidence
   interval. The run manifest records the bootstrap seed and iteration count.
6. Report win/tie/loss using a scorer-specific epsilon recorded before the
   paid run. Task #65 calibrates epsilon from repeated-score noise; it must not
   be chosen after seeing Vertex results.
7. Slice results by language, prompt category, and prompt specificity.
8. Report missing/failed cases separately. Do not silently drop them.

No single composite score is used. A strong product result requires VQAScore
and ImageReward improvement without a material TIFA regression. A partial
result may justify enhancement only for specific prompt categories; the UI
should not present a universal quality claim if the benefit is conditional.

## Task Breakdown

### Task 1 — Execution prompt source-of-truth and provenance

**Issue:** [#60](https://github.com/bbungjun/AI_multimodal_platform/issues/60)

**Depends on:** none

**Work:**

- Add regression tests for edited enhancement acceptance.
- Make the submitted generation prompt the exact provider input.
- Preserve enhancement linkage as provenance without hidden override.
- Record the enhancer/template/model metadata needed by the benchmark.

**Done when:** API and job-handler tests prove the accepted/edited prompt is
the executed prompt in mock mode.

### Task 2 — Benchmark and artifact schemas

**Issue:** [#61](https://github.com/bbungjun/AI_multimodal_platform/issues/61)

**Depends on:** Task 1

**Work:**

- Create the isolated evaluation package skeleton.
- Define validated benchmark, run, arm, asset, score, and summary schemas.
- Add schema-version rejection and resumable manifest writes.
- Add ignore rules for run artifacts and model caches.

**Done when:** valid fixtures round-trip and invalid/incompatible manifests fail
with actionable errors.

### Task 3 — Mock paired-generation runner

**Issue:** [#62](https://github.com/bbungjun/AI_multimodal_platform/issues/62)

**Depends on:** Tasks 1 and 2

**Work:**

- Require `AI_PROVIDER=mock`.
- Call the prompt-enhancement and generation HTTP APIs.
- Create matched Raw and Enhanced jobs and poll them to terminal state.
- Download assets through the public file boundary and hash them.
- Resume completed cases without duplicate jobs.
- Alternate Raw/Enhanced submission order.

**Done when:** a fixture run produces complete paired manifests and local image
artifacts without constructing a Vertex client.

### Task 4 — Mock metric adapters and statistics

**Issue:** [#63](https://github.com/bbungjun/AI_multimodal_platform/issues/63)

**Depends on:** Tasks 2 and 3

**Work:**

- Define a common scorer adapter contract.
- Add deterministic synthetic VQAScore, ImageReward, and TIFA adapters.
- Enforce original/canonical-prompt scoring for both arms.
- Produce per-image, per-case, aggregate, and sliced statistics.
- Generate `summary.json` and `report.md`.

**Done when:** fixed fixture inputs produce byte-stable statistical outputs and
all synthetic scores are clearly labeled as mock evidence.

### Task 5 — Mock end-to-end gate

**Issue:** [#64](https://github.com/bbungjun/AI_multimodal_platform/issues/64)

**Depends on:** Tasks 1 through 4

**Work:**

- Add a mock-only smoke command from benchmark manifest to final report.
- Verify resume after interruption and one controlled failure.
- Verify no provider credential or remote scorer is required.
- Document the paid-run go/no-go checklist.
- Run the repository quality gates appropriate to touched code.

**Done when:** the complete flow passes fresh in mock mode and every item in the
mock gate below is checked.

### Task 6 — Real offline scorer adapters

**Issue:** [#65](https://github.com/bbungjun/AI_multimodal_platform/issues/65)

**Depends on:** Tasks 4 and 5

**Work:**

- Pin VQAScore, ImageReward, and TIFA model/code revisions.
- Keep their dependencies isolated from the production application image.
- Freeze and review TIFA question-answer sets for the benchmark.
- Validate Korean canonical prompts and report Korean separately.
- Calibrate scorer-specific tie thresholds before the Vertex pilot.

**Done when:** local fixture images can be scored by all three real adapters,
with model revisions and limitations recorded, without any Vertex call.

### Task 7 — Cost-bounded Vertex pilot

**Issue:** [#66](https://github.com/bbungjun/AI_multimodal_platform/issues/66)

**Depends on:** Tasks 5 and 6 plus explicit user approval

**Work:**

- Verify the personal GCP account/project guard and Vertex readiness.
- Run only the approved 20-case, 80-image maximum pilot.
- Score locally and generate the paired report.
- Record provider failures, request counts, latency, and cost-relevant counts.
- Decide whether a full benchmark or product integration is justified.

**Done when:** the report distinguishes measured Vertex evidence from mock
workflow evidence and recommends proceed, narrow, revise, or stop.

## Mock-to-Vertex Go/No-Go Gate

No live prompt-enhancement or Imagen request may run until all are true:

- [ ] Issue #60 proves the exact execution-prompt contract.
- [ ] Versioned benchmark and run schemas validate.
- [ ] Raw and Enhanced mock jobs complete with matched parameters.
- [ ] Resume does not duplicate completed work.
- [ ] Controlled failure is recorded and does not corrupt the report.
- [ ] VQAScore, ImageReward, and TIFA mock adapter outputs remain separate.
- [ ] Both arms are scored against the same original/canonical prompt.
- [ ] Paired statistics and confidence intervals are reproducible.
- [ ] Artifacts and model caches are ignored and unstaged.
- [ ] Tests prove mock mode constructs no Vertex client.
- [ ] Real offline scorer revisions and limitations are recorded.
- [ ] Pilot request/image caps are approved explicitly by the user.

## Verification Strategy

Each task starts with focused unit tests. Task 5 runs the complete no-cost gate.
The expected final mock verification includes:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest

cd ..\frontend
npm run build

cd ..
docker compose --env-file .env.example config --quiet
python scripts/verify_local.py
git diff --check
git status --short --branch
git diff --cached --name-only
```

Evaluation-specific verification commands will be added by Issues #61-#64 and
must refuse `.env`, require mock mode, and avoid printing environment values.

## Risks and Controls

- **Enhancer self-grading:** The enhancer model must not define the reference
  prompt or judge its own rewrite. The original/frozen prompt remains the
  reference.
- **Korean scorer bias:** Korean cases use reviewed canonical evaluation text
  and remain a separate reporting slice.
- **Metric gaming:** No composite score and no post-hoc threshold selection.
- **Random generation variance:** Use multiple images per arm and case-level
  paired aggregation. Use matched seeds only if the provider contract supports
  them explicitly.
- **Production image bloat:** Heavy scorer dependencies stay in the evaluation
  package.
- **Cost overrun:** The mock gate precedes a hard-capped pilot; a full benchmark
  needs a later decision.
- **False mock evidence:** Mock reports include an explicit synthetic-evidence
  marker and cannot satisfy a product-quality claim.

## Research References

- [VQAScore and GenAI-Bench](https://arxiv.org/abs/2406.13743)
- [TIFA](https://openaccess.thecvf.com/content/ICCV2023/papers/Hu_TIFA_Accurate_and_Interpretable_Text-to-Image_Faithfulness_Evaluation_with_Question_Answering_ICCV_2023_paper.pdf)
- [ImageReward](https://arxiv.org/abs/2304.05977)
- [GenEval](https://arxiv.org/abs/2310.11513)
- [Promptist](https://arxiv.org/abs/2212.09611)
