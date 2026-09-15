from __future__ import annotations

import gc
import importlib
import importlib.metadata
import importlib.util
import json
import math
import os
import statistics
import sys
import tempfile
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schemas import (
    BenchmarkCase,
    EvidenceKind,
    MetricAdapterConfig,
    MetricName,
    file_sha256,
    load_benchmark_cases,
    prompt_sha256,
)


OFFLINE_ROOT = Path(__file__).resolve().parent
EVAL_ROOT = OFFLINE_ROOT.parent
DEFAULT_PROFILE_PATH = OFFLINE_ROOT / "scorer_profile.v1.json"
DEFAULT_BENCHMARK_PATH = EVAL_ROOT / "benchmark.v1.jsonl"
REQUIRED_METRICS = {metric.value for metric in MetricName}
MODEL_KEYS = {
    "clip_flant5_xl",
    "flan_t5_xl_tokenizer",
    "clip_vit_large_patch14_336",
    "image_reward",
    "bert_base_uncased_tokenizer",
    "blip_vqa_base",
    "all_mpnet_base_v2",
}


class OfflineScorerError(RuntimeError):
    """Raised when the real-model scorer boundary cannot run safely."""


@dataclass(frozen=True)
class ScorerProfile:
    path: Path
    data: Mapping[str, Any]

    @property
    def profile_id(self) -> str:
        return str(self.data["profile_id"])

    @property
    def sha256(self) -> str:
        return file_sha256(self.path)


@dataclass(frozen=True)
class TifaQuestion:
    case_id: str
    qa_id: str
    question: str
    choices: tuple[str, ...]
    answer: str
    element_type: str


@dataclass(frozen=True)
class EvaluationInputs:
    cases: tuple[BenchmarkCase, ...]
    questions_by_case: Mapping[str, tuple[TifaQuestion, ...]]
    questions_by_prompt_hash: Mapping[str, tuple[TifaQuestion, ...]]
    canonical_reviews: Mapping[str, Mapping[str, Any]]


def load_scorer_profile(path: Path | str = DEFAULT_PROFILE_PATH) -> ScorerProfile:
    profile_path = Path(path).resolve()
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OfflineScorerError(f"Cannot load scorer profile {profile_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OfflineScorerError("Scorer profile must be a JSON object")
    _validate_profile_shape(data)
    profile = ScorerProfile(profile_path, data)
    _verify_profile_file_hashes(profile)
    return profile


def _validate_profile_shape(data: Mapping[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise OfflineScorerError("Only scorer profile schema_version=1 is supported")
    if not isinstance(data.get("profile_id"), str) or not data["profile_id"].strip():
        raise OfflineScorerError("Scorer profile requires a non-empty profile_id")
    metrics = data.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != REQUIRED_METRICS:
        raise OfflineScorerError(
            "Scorer profile metrics must define vqascore, image_reward, and tifa"
        )
    adapters = [metrics[name].get("adapter") for name in sorted(metrics)]
    if any(not isinstance(adapter, str) or not adapter for adapter in adapters):
        raise OfflineScorerError("Every metric requires an adapter name")
    if len(adapters) != len(set(adapters)):
        raise OfflineScorerError("Metric adapter names must be unique")

    snapshots = data.get("model_snapshots")
    if not isinstance(snapshots, list):
        raise OfflineScorerError("model_snapshots must be a list")
    snapshot_keys = {snapshot.get("key") for snapshot in snapshots}
    if snapshot_keys != MODEL_KEYS or len(snapshots) != len(MODEL_KEYS):
        raise OfflineScorerError(
            "model_snapshots must define every required model exactly once"
        )
    for snapshot in snapshots:
        revision = snapshot.get("revision")
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision)
        ):
            raise OfflineScorerError(
                f"Model {snapshot.get('key')!r} requires a 40-character commit revision"
            )
        patterns = snapshot.get("allow_patterns")
        if not isinstance(patterns, list) or not patterns:
            raise OfflineScorerError(
                f"Model {snapshot.get('key')!r} requires allow_patterns"
            )

    calibration = data.get("calibration")
    if not isinstance(calibration, dict):
        raise OfflineScorerError("Scorer profile requires calibration settings")
    if calibration.get("algorithm") != "repeat-max-deviation-v1":
        raise OfflineScorerError("Unsupported calibration algorithm")
    if not isinstance(calibration.get("repetitions"), int) or calibration["repetitions"] < 2:
        raise OfflineScorerError("Calibration repetitions must be at least 2")
    floors = calibration.get("minimum_floors")
    if not isinstance(floors, dict) or set(floors) != REQUIRED_METRICS:
        raise OfflineScorerError("Calibration floors must define all three metrics")
    if any(
        not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
        for value in floors.values()
    ):
        raise OfflineScorerError("Calibration floors must be finite and non-negative")


def _verify_profile_file_hashes(profile: ScorerProfile) -> None:
    checks = (
        profile.data["runtime_lock"],
        profile.data["adapter_lock"],
        profile.data["canonical_prompt_review"],
        profile.data["metrics"]["tifa"],
    )
    for item in checks:
        relative_path = item.get("path") or item.get("questions_path")
        expected = item.get("sha256") or item.get("questions_sha256")
        if not isinstance(relative_path, str) or not isinstance(expected, str):
            raise OfflineScorerError("Profile file references require path and sha256")
        path = _profile_relative_path(profile, relative_path)
        if not path.is_file():
            raise OfflineScorerError(f"Pinned scorer input is missing: {relative_path}")
        if file_sha256(path) != expected:
            raise OfflineScorerError(
                f"Pinned scorer input hash does not match profile: {relative_path}"
            )


def _profile_relative_path(profile: ScorerProfile, relative_path: str) -> Path:
    path = (profile.path.parent / relative_path).resolve()
    try:
        path.relative_to(profile.path.parent.resolve())
    except ValueError as exc:
        raise OfflineScorerError(
            f"Scorer profile path escaped its directory: {relative_path}"
        ) from exc
    return path


def validate_evaluation_inputs(
    profile: ScorerProfile,
    benchmark_path: Path | str = DEFAULT_BENCHMARK_PATH,
) -> EvaluationInputs:
    benchmark = Path(benchmark_path).resolve()
    cases = tuple(case for case in load_benchmark_cases(benchmark) if case.enabled)
    if not cases:
        raise OfflineScorerError("Benchmark contains no enabled cases")

    review_config = profile.data["canonical_prompt_review"]
    review_path = _profile_relative_path(profile, review_config["path"])
    review_data = json.loads(review_path.read_text(encoding="utf-8"))
    if review_data.get("schema_version") != 1:
        raise OfflineScorerError("Canonical prompt review must use schema_version=1")
    if review_data.get("benchmark_sha256") != file_sha256(benchmark):
        raise OfflineScorerError(
            "Canonical prompt review was not performed against this benchmark hash"
        )
    reviews = review_data.get("reviews")
    if not isinstance(reviews, list):
        raise OfflineScorerError("Canonical prompt reviews must be a list")
    review_by_case = {review.get("case_id"): review for review in reviews}
    if len(review_by_case) != len(reviews):
        raise OfflineScorerError("Canonical prompt reviews contain duplicate case_id values")

    korean_cases = {case.case_id: case for case in cases if case.language.value == "ko"}
    if set(review_by_case) != set(korean_cases):
        raise OfflineScorerError(
            "Canonical prompt reviews must cover every enabled Korean case exactly once"
        )
    for case_id, case in korean_cases.items():
        review = review_by_case[case_id]
        if review.get("status") != "reviewed":
            raise OfflineScorerError(f"Korean case {case_id} is not marked reviewed")
        if review.get("original_prompt") != case.original_prompt:
            raise OfflineScorerError(f"Korean case {case_id} review changed the original prompt")
        if review.get("canonical_prompt_en") != case.evaluation_prompt_en:
            raise OfflineScorerError(
                f"Korean case {case_id} review does not match evaluation_prompt_en"
            )
        if not case.evaluation_prompt_en_reviewed:
            raise OfflineScorerError(
                f"Korean case {case_id} benchmark is not marked English-reviewed"
            )

    questions_path = _profile_relative_path(
        profile,
        profile.data["metrics"]["tifa"]["questions_path"],
    )
    questions_by_case = _load_tifa_questions(questions_path)
    expected_case_ids = {case.case_id for case in cases}
    if set(questions_by_case) != expected_case_ids:
        missing = sorted(expected_case_ids - set(questions_by_case))
        extra = sorted(set(questions_by_case) - expected_case_ids)
        raise OfflineScorerError(
            f"Frozen TIFA questions do not match enabled benchmark cases; "
            f"missing={missing} extra={extra}"
        )

    questions_by_prompt_hash: dict[str, tuple[TifaQuestion, ...]] = {}
    for case in cases:
        canonical_prompt = canonical_evaluation_prompt(case)
        canonical_hash = prompt_sha256(canonical_prompt)
        if canonical_hash in questions_by_prompt_hash:
            raise OfflineScorerError("Canonical evaluation prompts must be unique for TIFA lookup")
        questions_by_prompt_hash[canonical_hash] = questions_by_case[case.case_id]
    return EvaluationInputs(
        cases=cases,
        questions_by_case=questions_by_case,
        questions_by_prompt_hash=questions_by_prompt_hash,
        canonical_reviews=review_by_case,
    )


def canonical_evaluation_prompt(case: BenchmarkCase) -> str:
    if case.evaluation_prompt_en and case.evaluation_prompt_en_reviewed:
        return case.evaluation_prompt_en
    return case.evaluation_prompt


def _load_tifa_questions(path: Path) -> dict[str, tuple[TifaQuestion, ...]]:
    by_case: dict[str, list[TifaQuestion]] = {}
    qa_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OfflineScorerError(
                f"Invalid TIFA JSON at {path}:{line_number}: {exc}"
            ) from exc
        expected_fields = {
            "schema_version",
            "case_id",
            "qa_id",
            "question",
            "choices",
            "answer",
            "element_type",
        }
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise OfflineScorerError(
                f"TIFA question {path}:{line_number} has invalid fields"
            )
        if value["schema_version"] != 1:
            raise OfflineScorerError(
                f"TIFA question {path}:{line_number} must use schema_version=1"
            )
        choices = value["choices"]
        if (
            not isinstance(choices, list)
            or len(choices) < 2
            or any(not isinstance(choice, str) or not choice.strip() for choice in choices)
            or len(choices) != len(set(choices))
        ):
            raise OfflineScorerError(
                f"TIFA question {path}:{line_number} requires unique non-empty choices"
            )
        if value["answer"] not in choices:
            raise OfflineScorerError(
                f"TIFA question {path}:{line_number} answer is not one of its choices"
            )
        if value["qa_id"] in qa_ids:
            raise OfflineScorerError(f"Duplicate TIFA qa_id: {value['qa_id']}")
        qa_ids.add(value["qa_id"])
        question = TifaQuestion(
            case_id=value["case_id"],
            qa_id=value["qa_id"],
            question=value["question"],
            choices=tuple(choices),
            answer=value["answer"],
            element_type=value["element_type"],
        )
        by_case.setdefault(question.case_id, []).append(question)
    if not by_case:
        raise OfflineScorerError("Frozen TIFA question file contains no records")
    return {case_id: tuple(questions) for case_id, questions in by_case.items()}


def metric_adapter_configs(profile: ScorerProfile) -> tuple[MetricAdapterConfig, ...]:
    configs: list[MetricAdapterConfig] = []
    snapshots = {
        item["key"]: {"repo_id": item["repo_id"], "revision": item["revision"]}
        for item in profile.data["model_snapshots"]
    }
    for metric in MetricName:
        config = profile.data["metrics"][metric.value]
        settings: dict[str, Any] = {
            "profile_id": profile.profile_id,
            "profile_sha256": profile.sha256,
            "implementation": config["implementation"],
            "limitations": config["limitations"],
            "model_snapshots": snapshots,
        }
        if metric == MetricName.TIFA:
            settings["questions_sha256"] = config["questions_sha256"]
        configs.append(
            MetricAdapterConfig(
                metric=metric,
                adapter=config["adapter"],
                model_revision=config["model_revision"],
                evidence_kind=EvidenceKind.REAL,
                settings=settings,
            )
        )
    return tuple(configs)


def prepare_model_cache(profile: ScorerProfile, cache_root: Path | str) -> None:
    root = _safe_cache_root(cache_root)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise OfflineScorerError(
            "huggingface-hub is unavailable; run this command inside the scorer container"
        ) from exc

    root.mkdir(parents=True, exist_ok=True)
    for snapshot in profile.data["model_snapshots"]:
        destination = model_snapshot_path(root, snapshot)
        marker = destination / profile.data["cache_policy"]["marker_filename"]
        if _marker_matches(marker, snapshot):
            continue
        marker.unlink(missing_ok=True)
        destination.mkdir(parents=True, exist_ok=True)
        try:
            snapshot_download(
                repo_id=snapshot["repo_id"],
                revision=snapshot["revision"],
                allow_patterns=snapshot["allow_patterns"],
                local_dir=destination,
            )
        except Exception as exc:
            marker.unlink(missing_ok=True)
            raise OfflineScorerError(
                f"Failed to prepare pinned model {snapshot['key']}@{snapshot['revision']}: {exc}"
            ) from exc
        payload = {
            "schema_version": 1,
            "key": snapshot["key"],
            "repo_id": snapshot["repo_id"],
            "revision": snapshot["revision"],
            "profile_sha256": profile.sha256,
        }
        _atomic_json_write(marker, payload)


def verify_model_cache(profile: ScorerProfile, cache_root: Path | str) -> None:
    root = _safe_cache_root(cache_root)
    missing: list[str] = []
    marker_name = profile.data["cache_policy"]["marker_filename"]
    for snapshot in profile.data["model_snapshots"]:
        destination = model_snapshot_path(root, snapshot)
        marker = destination / marker_name
        if not _marker_matches(marker, snapshot):
            missing.append(f"{snapshot['key']}@{snapshot['revision']}")
            continue
        payload_files = [
            path
            for path in destination.rglob("*")
            if path.is_file()
            and path.name != marker_name
            and ".cache" not in path.parts
        ]
        if not payload_files:
            missing.append(f"{snapshot['key']}@{snapshot['revision']} (empty)")
    if missing:
        raise OfflineScorerError(
            "Pinned model cache is incomplete. Run the explicit prepare step first: "
            + ", ".join(missing)
        )


def _safe_cache_root(cache_root: Path | str) -> Path:
    root = Path(cache_root).expanduser().resolve()
    if root == EVAL_ROOT.resolve() or EVAL_ROOT.resolve() in root.parents:
        expected = (EVAL_ROOT / ".model-cache").resolve()
        if root != expected and expected not in root.parents:
            raise OfflineScorerError(
                "Model cache inside the evaluation package must be under ignored .model-cache/"
            )
    return root


def model_snapshot_path(cache_root: Path, snapshot: Mapping[str, Any]) -> Path:
    return cache_root / "models" / snapshot["key"] / snapshot["revision"]


def _marker_matches(marker: Path, snapshot: Mapping[str, Any]) -> bool:
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        value.get("schema_version") == 1
        and value.get("key") == snapshot["key"]
        and value.get("repo_id") == snapshot["repo_id"]
        and value.get("revision") == snapshot["revision"]
    )


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def resolve_device(requested: str) -> str:
    if requested not in {"auto", "cpu", "cuda"}:
        raise OfflineScorerError("device must be one of auto, cpu, or cuda")
    try:
        import torch
    except ImportError as exc:
        raise OfflineScorerError(
            "PyTorch is unavailable; run this command inside the scorer container"
        ) from exc
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise OfflineScorerError("CUDA was requested but torch.cuda.is_available() is false")
    return requested


def validate_resources(
    profile: ScorerProfile,
    device: str,
    metrics: Sequence[MetricName],
) -> None:
    policy = profile.data["resource_policy"][device]
    if device == "cuda":
        import torch

        total_gib = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        minimum = float(policy["minimum_total_vram_gib"])
        if total_gib < minimum:
            raise OfflineScorerError(
                f"CUDA device has {total_gib:.1f} GiB VRAM; scorer profile requires "
                f"at least {minimum:.1f} GiB"
            )
        return
    minimum_by_metric = policy["minimum_available_ram_gib_by_metric"]
    minimum = max(float(minimum_by_metric[metric.value]) for metric in metrics)
    available = _available_memory_gib()
    if available is not None and available < minimum:
        raise OfflineScorerError(
            f"CPU scorer has {available:.1f} GiB available memory; selected metrics require "
            f"at least {minimum:.1f} GiB. Use a larger Docker memory limit or CUDA."
        )


def _available_memory_gib() -> float | None:
    candidates: list[int] = []
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                candidates.append(int(line.split()[1]) * 1024)
                break
    except OSError:
        pass
    try:
        limit_text = Path("/sys/fs/cgroup/memory.max").read_text(encoding="utf-8").strip()
        current_text = Path("/sys/fs/cgroup/memory.current").read_text(encoding="utf-8").strip()
        if limit_text != "max":
            candidates.append(max(0, int(limit_text) - int(current_text)))
    except (OSError, ValueError):
        pass
    if not candidates:
        return None
    return min(candidates) / (1024**3)


class _BaseRealAdapter:
    evidence_kind = EvidenceKind.REAL

    def __init__(self, profile: ScorerProfile, metric: MetricName, device: str) -> None:
        config = profile.data["metrics"][metric.value]
        self.metric = metric
        self.adapter = config["adapter"]
        self.model_revision = config["model_revision"]
        self.device = device
        self._profile = profile

    def close(self) -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def score_many(
        self,
        evaluation_prompts: Sequence[str],
        image_bodies: Sequence[bytes],
    ) -> list[float]:
        """Fallback preserves exact single-item semantics for non-batched adapters."""
        if len(evaluation_prompts) != len(image_bodies):
            raise OfflineScorerError("Prompt and image batch lengths must match")
        return [
            self.score(prompt, image)
            for prompt, image in zip(evaluation_prompts, image_bodies, strict=True)
        ]


class VQAScoreAdapter(_BaseRealAdapter):
    def __init__(self, profile: ScorerProfile, cache_root: Path, device: str) -> None:
        super().__init__(profile, MetricName.VQA_SCORE, device)
        self._model = _load_vqascore_model(profile, cache_root, device)

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        return self.score_many([evaluation_prompt], [image_bytes])[0]

    def score_many(
        self,
        evaluation_prompts: Sequence[str],
        image_bodies: Sequence[bytes],
    ) -> list[float]:
        import contextlib

        import torch

        if not evaluation_prompts or len(evaluation_prompts) != len(image_bodies):
            raise OfflineScorerError("VQAScore prompt and image batch lengths must match")
        image_paths: list[Path] = []
        try:
            for image_bytes in image_bodies:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                    handle.write(image_bytes)
                    image_paths.append(Path(handle.name))
            autocast = (
                torch.autocast(device_type="cpu", dtype=torch.bfloat16)
                if self.device == "cpu"
                else contextlib.nullcontext()
            )
            with autocast:
                result = self._model.forward(
                    [str(path) for path in image_paths], list(evaluation_prompts)
                )
            scores = [float(value.detach().cpu().item()) for value in result]
        finally:
            for path in image_paths:
                path.unlink(missing_ok=True)
        return [_finite_score(self.metric, score) for score in scores]

    def close(self) -> None:
        del self._model
        super().close()


class ImageRewardAdapter(_BaseRealAdapter):
    def __init__(self, profile: ScorerProfile, cache_root: Path, device: str) -> None:
        super().__init__(profile, MetricName.IMAGE_REWARD, device)
        self._model = _load_image_reward_model(profile, cache_root, device)

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        import io

        import torch
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb_image = image.convert("RGB")
        with torch.inference_mode():
            score = float(self._model.score(evaluation_prompt, rgb_image))
        return _finite_score(self.metric, score)

    def close(self) -> None:
        del self._model
        super().close()


class TIFAAdapter(_BaseRealAdapter):
    def __init__(
        self,
        profile: ScorerProfile,
        cache_root: Path,
        device: str,
        questions_by_prompt_hash: Mapping[str, tuple[TifaQuestion, ...]],
    ) -> None:
        super().__init__(profile, MetricName.TIFA, device)
        self._questions_by_prompt_hash = questions_by_prompt_hash
        self._processor, self._vqa_model, self._sbert_tokenizer, self._sbert_model = (
            _load_tifa_models(profile, cache_root, device)
        )
        self.last_question_details: tuple[Mapping[str, Any], ...] = ()

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        import io

        import torch
        import torch.nn.functional as functional
        from PIL import Image

        questions = self._questions_by_prompt_hash.get(prompt_sha256(evaluation_prompt))
        if not questions:
            raise OfflineScorerError(
                "TIFA has no frozen questions for the canonical evaluation prompt"
            )
        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb_image = image.convert("RGB")

        results: list[int] = []
        details: list[Mapping[str, Any]] = []
        inputs = self._processor(
            images=[rgb_image] * len(questions),
            text=[question.question for question in questions],
            return_tensors="pt",
            padding=True,
        ).to(self.device)
        with torch.inference_mode():
            generated_ids = self._vqa_model.generate(**inputs, max_length=50)
        answers = self._processor.batch_decode(generated_ids, skip_special_tokens=True)
        for question, free_form in zip(questions, answers, strict=True):
            multiple_choice = free_form
            if free_form not in question.choices:
                sentences = [free_form, *question.choices]
                encoded = self._sbert_tokenizer(
                    sentences,
                    padding=True,
                    truncation=True,
                    return_tensors="pt",
                ).to(self.device)
                with torch.inference_mode():
                    model_output = self._sbert_model(**encoded)
                token_embeddings = model_output[0]
                mask = encoded["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
                embeddings = torch.sum(token_embeddings * mask, 1) / torch.clamp(
                    mask.sum(1), min=1e-9
                )
                embeddings = functional.normalize(embeddings, p=2, dim=1)
                choice_index = torch.argmax(
                    torch.matmul(embeddings[1:], embeddings[0].unsqueeze(1))
                ).item()
                multiple_choice = question.choices[choice_index]
            correct = int(multiple_choice == question.answer)
            results.append(correct)
            details.append(
                {
                    "qa_id": question.qa_id,
                    "question": question.question,
                    "free_form_answer": free_form,
                    "multiple_choice_answer": multiple_choice,
                    "expected_answer": question.answer,
                    "correct": bool(correct),
                    "element_type": question.element_type,
                }
            )
        self.last_question_details = tuple(details)
        return _finite_score(self.metric, statistics.fmean(results))

    def close(self) -> None:
        del self._processor
        del self._vqa_model
        del self._sbert_tokenizer
        del self._sbert_model
        super().close()


def build_real_adapter(
    metric: MetricName,
    *,
    profile: ScorerProfile,
    cache_root: Path | str,
    device: str,
    inputs: EvaluationInputs,
) -> _BaseRealAdapter:
    root = _safe_cache_root(cache_root)
    verify_model_cache(profile, root)
    _verify_installed_packages(profile)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        if metric == MetricName.VQA_SCORE:
            return VQAScoreAdapter(profile, root, device)
        if metric == MetricName.IMAGE_REWARD:
            return ImageRewardAdapter(profile, root, device)
        if metric == MetricName.TIFA:
            return TIFAAdapter(
                profile,
                root,
                device,
                inputs.questions_by_prompt_hash,
            )
    except OfflineScorerError:
        raise
    except Exception as exc:
        raise OfflineScorerError(
            f"{metric.value} model initialization failed: {type(exc).__name__}: {exc}"
        ) from exc
    raise OfflineScorerError(f"Unsupported metric: {metric}")


def _verify_installed_packages(profile: ScorerProfile) -> None:
    for package in profile.data["packages"]:
        try:
            installed = importlib.metadata.version(package["name"])
        except importlib.metadata.PackageNotFoundError as exc:
            raise OfflineScorerError(
                f"Pinned package {package['name']} is not installed; use the scorer container"
            ) from exc
        if installed != package["version"]:
            raise OfflineScorerError(
                f"Pinned package {package['name']} requires {package['version']}, got {installed}"
            )


def _snapshot_map(profile: ScorerProfile, cache_root: Path) -> dict[str, Path]:
    return {
        snapshot["key"]: model_snapshot_path(cache_root, snapshot)
        for snapshot in profile.data["model_snapshots"]
    }


def _package_root(module_name: str) -> Path:
    spec = importlib.util.find_spec(module_name)
    if spec is None or not spec.submodule_search_locations:
        raise OfflineScorerError(f"Cannot locate installed module {module_name}")
    return Path(next(iter(spec.submodule_search_locations))).resolve()


def _stub_package(name: str, path: Path) -> None:
    current = sys.modules.get(name)
    if current is not None:
        if not getattr(current, "__creativeops_narrow_package__", False):
            raise OfflineScorerError(
                f"{name} was imported through its broad upstream initializer; use a fresh process"
            )
        return
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    module.__creativeops_narrow_package__ = True
    sys.modules[name] = module


def _load_vqascore_model(profile: ScorerProfile, cache_root: Path, device: str) -> Any:
    import torch
    from transformers import AutoTokenizer, CLIPImageProcessor, CLIPVisionModel

    paths = _snapshot_map(profile, cache_root)
    package = _package_root("t2v_metrics")
    _stub_package("t2v_metrics", package)
    _stub_package("t2v_metrics.models", package / "models")
    _stub_package(
        "t2v_metrics.models.vqascore_models",
        package / "models" / "vqascore_models",
    )
    clip_module = importlib.import_module(
        "t2v_metrics.models.vqascore_models.clip_t5_model"
    )
    clip_encoder = importlib.import_module(
        "t2v_metrics.models.vqascore_models.clip_t5.model.multimodal_encoder.clip_encoder"
    )
    dtype = torch.bfloat16

    def load_pinned_vision_tower(instance: Any) -> None:
        instance.image_processor = CLIPImageProcessor.from_pretrained(
            paths["clip_vit_large_patch14_336"],
            local_files_only=True,
        )
        instance.vision_tower = CLIPVisionModel.from_pretrained(
            paths["clip_vit_large_patch14_336"],
            local_files_only=True,
            torch_dtype=dtype,
        )
        instance.vision_tower.requires_grad_(False)
        instance.is_loaded = True

    clip_encoder.CLIPVisionTower.load_model = load_pinned_vision_tower

    def load_pinned_model(
        model_cls: Any,
        model_args: Any,
        *,
        model_path: str | Path | None = None,
        tokenizer_path: str | Path | None = None,
        model_max_length: int | None = None,
        padding_side: str | None = None,
        image_aspect_ratio: str = "pad",
        mmprojector_repo: str | None = None,
        mmprojector_name: str | None = None,
        device: str = device,
        cache_dir: str | Path | None = None,
    ) -> tuple[Any, Any, Any]:
        if mmprojector_repo or mmprojector_name:
            raise OfflineScorerError("Stage-1 VQAScore projector downloads are not supported")
        tokenizer_options: dict[str, Any] = {"local_files_only": True}
        if model_max_length is not None:
            tokenizer_options["model_max_length"] = model_max_length
        if padding_side is not None:
            tokenizer_options["padding_side"] = padding_side
        tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_path,
            use_fast=False,
            **tokenizer_options,
        )
        model = model_cls.from_pretrained(
            model_path,
            local_files_only=True,
            torch_dtype=dtype,
        )
        model.resize_token_embeddings(len(tokenizer))
        vision_tower = model.get_vision_tower()
        if not vision_tower.is_loaded:
            vision_tower.load_model()
        model.to(device=device, dtype=dtype)
        model.requires_grad_(False)
        model.config.image_aspect_ratio = image_aspect_ratio
        model.config.use_cache = False
        model.config.image_grid_pinpoints = None
        model.config.freeze_mm_mlp_adapter = True
        model.eval()
        return tokenizer, model, vision_tower.image_processor

    clip_module.CLIP_T5_MODELS["clip-flant5-xl"]["model"]["path"] = str(
        paths["clip_flant5_xl"]
    )
    clip_module.CLIP_T5_MODELS["clip-flant5-xl"]["tokenizer"]["path"] = str(
        paths["flan_t5_xl_tokenizer"]
    )
    clip_module.load_pretrained_model = load_pinned_model
    return clip_module.CLIPT5Model(
        "clip-flant5-xl",
        device=device,
        cache_dir=str(cache_root),
    )


def _load_image_reward_model(
    profile: ScorerProfile,
    cache_root: Path,
    device: str,
) -> Any:
    import torch
    from transformers import BertTokenizer

    paths = _snapshot_map(profile, cache_root)
    package = _package_root("ImageReward")
    _stub_package("ImageReward", package)
    _stub_package("ImageReward.models", package / "models")
    _stub_package("ImageReward.models.BLIP", package / "models" / "BLIP")
    blip_pretrain = importlib.import_module("ImageReward.models.BLIP.blip_pretrain")

    def init_pinned_tokenizer() -> Any:
        tokenizer = BertTokenizer.from_pretrained(
            paths["bert_base_uncased_tokenizer"],
            local_files_only=True,
        )
        tokenizer.add_special_tokens({"bos_token": "[DEC]"})
        tokenizer.add_special_tokens({"additional_special_tokens": ["[ENC]"]})
        tokenizer.enc_token_id = tokenizer.additional_special_tokens_ids[0]
        return tokenizer

    blip_pretrain.init_tokenizer = init_pinned_tokenizer
    reward_module = importlib.import_module("ImageReward.ImageReward")
    med_config = paths["image_reward"] / "med_config.json"
    checkpoint = paths["image_reward"] / "ImageReward.pt"
    if not med_config.is_file() or not checkpoint.is_file():
        raise OfflineScorerError("Pinned ImageReward checkpoint files are incomplete")
    model = reward_module.ImageReward(device=device, med_config=str(med_config)).to(device)
    state_dict = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict, strict=False)
    model.eval()
    model.requires_grad_(False)
    return model


def _load_tifa_models(
    profile: ScorerProfile,
    cache_root: Path,
    device: str,
) -> tuple[Any, Any, Any, Any]:
    from transformers import (
        AutoProcessor,
        AutoTokenizer,
        BlipForQuestionAnswering,
        MPNetModel,
    )

    paths = _snapshot_map(profile, cache_root)
    processor = AutoProcessor.from_pretrained(
        paths["blip_vqa_base"],
        local_files_only=True,
    )
    vqa_model = BlipForQuestionAnswering.from_pretrained(
        paths["blip_vqa_base"],
        local_files_only=True,
    ).to(device)
    vqa_model.eval()
    vqa_model.requires_grad_(False)
    sbert_tokenizer = AutoTokenizer.from_pretrained(
        paths["all_mpnet_base_v2"],
        local_files_only=True,
    )
    sbert_model = MPNetModel.from_pretrained(
        paths["all_mpnet_base_v2"],
        local_files_only=True,
    ).to(device)
    sbert_model.eval()
    sbert_model.requires_grad_(False)
    return processor, vqa_model, sbert_tokenizer, sbert_model


def calibrate_tie_threshold(
    metric: MetricName,
    scores: Sequence[float],
    profile: ScorerProfile,
) -> Mapping[str, Any]:
    calibration = profile.data["calibration"]
    if len(scores) != calibration["repetitions"]:
        raise OfflineScorerError(
            f"Calibration for {metric.value} requires exactly "
            f"{calibration['repetitions']} repeated scores"
        )
    finite_scores = [_finite_score(metric, float(score)) for score in scores]
    median = statistics.median(finite_scores)
    max_deviation = max(abs(score - median) for score in finite_scores)
    floor = float(calibration["minimum_floors"][metric.value])
    threshold = max(floor, float(calibration["noise_multiplier"]) * max_deviation)
    return {
        "metric": metric.value,
        "scores": finite_scores,
        "median": median,
        "max_absolute_deviation": max_deviation,
        "minimum_floor": floor,
        "noise_multiplier": float(calibration["noise_multiplier"]),
        "tie_threshold": threshold,
        "algorithm": calibration["algorithm"],
    }


def _finite_score(metric: MetricName, score: float) -> float:
    if not math.isfinite(score):
        raise OfflineScorerError(f"{metric.value} returned a non-finite score")
    return score
