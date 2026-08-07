#!/usr/bin/env python3
"""Pragmatic, resumable G4IRSF17 source-flow evidence campaign.

This runner is intentionally a thin orchestration layer.  It reuses the
G4IRSF15 native causal target-pair binding and the already published target
address frame instead of rebuilding a second simulator or re-sealing old
artifacts.  The implemented scope is deliberately limited to:

* native source-wait attribution against matched H5/off bag results;
* real, competitive top-2 I1 pilot planning and matched-pair execution;
* I1 effect/support analysis, including bounded H_system sampling; and
* optional state-aliasing/model-report hooks supplied by ``czr005.g4irsf17``.

Closed-loop ladders, fault campaigns, and scale benchmarks are orchestrated
by ``run_g4irsf17_system_campaign.py``; they are outside this focused runner.

Delta convention
----------------
Every reported delta is ``treatment - baseline``.  For source-wait diagnosis
the treatment is H5 and the baseline is matched E4/off.  For I1 the treatment
admits the second ready candidate and the baseline keeps the native F2/Q0
winner.  Negative time deltas are therefore improvements.

Externality and CVaR convention
-------------------------------
At H_system, "other bags" are realized affected runtime bags excluding the
two directly reordered I1 bags.  Externality is the sum of their completion
time deltas.  CVaR95 is the arithmetic mean of the worst
``max(1, ceil(0.05 * n))`` non-negative other-bag harms.  H_bag never silently
claims zero externality: its externality fields are empty and its utility is
explicitly marked direct-only.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import inspect
import io
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005.g4irsf17.features import (  # noqa: E402
    CANDIDATE_FEATURES,
    CANONICAL_OBSERVATION_FEATURES,
    CONTEXT_FEATURES,
    PAIRWISE_FEATURES,
    canonical_feature_vector,
    pairwise_feature_vector,
)


CAMPAIGN_MANIFEST_PATH = Path(
    "artifacts/manifests/g4irsf17_campaign_manifest.json"
)
CAMPAIGN_LOG_PATH = Path("outputs/reports/g4irsf17_campaign_log.md")

SOURCE_WAIT_LEDGER_PATH = Path(
    "outputs/tables/g4irsf17_source_wait_cause_ledger.csv"
)
SOURCE_WAIT_TOPOLOGY_PATH = Path(
    "outputs/tables/g4irsf17_source_wait_topology_attribution.csv"
)
SOURCE_WAIT_REPORT_PATH = Path(
    "outputs/reports/g4irsf17_source_wait_diagnosis.md"
)

G15_TARGET_FRAME_PATH = Path(
    "artifacts/datasets/g4irsf15_causal_target_address_frame.jsonl.zst"
)
I1_PLAN_PATH = Path("artifacts/datasets/g4irsf17_i1_pilot_plan.json")
I1_DATASET_PATH = Path(
    "artifacts/datasets/g4irsf17_i1_causal_pilot.jsonl.zst"
)
I1_EFFECTS_PATH = Path("outputs/tables/g4irsf17_i1_effects.csv")
I1_SUPPORT_REPORT_PATH = Path(
    "outputs/reports/g4irsf17_i1_causal_support.md"
)
I1_RUNSTATE_ROOT = Path("outputs/runstate/g4irsf17_i1_pilot")

ALIASING_REPORT_PATH = Path(
    "outputs/reports/g4irsf17_state_aliasing_audit.md"
)
FEATURE_ABLATION_PATH = Path(
    "outputs/tables/g4irsf17_feature_ablation.csv"
)
MODEL_REPORT_PATH = Path(
    "outputs/reports/g4irsf17_i1_model_decision.md"
)

SCHEMA_MANIFEST = "czr005.g4irsf17.campaign.v1"
LEGACY_SCHEMA_MANIFEST = "czr005.g4irsf17.campaign_manifest.v1"
SCHEMA_I1_PLAN = "czr005.g4irsf17.i1_pilot_plan.v1"
SCHEMA_I1_CHUNK = "czr005.g4irsf17.i1_pair_chunk.v1"
SCHEMA_I1_RECORD = "czr005.g4irsf17.i1_causal_record.v1"

EPSILON = 1.0e-9
MAX_H_SYSTEM_SAMPLES = 32
SOURCE_WAIT_TELEMETRY_MIN_COVERAGE = 0.80
DEADLINE_MISS_PENALTY_SECONDS = 3_600.0

BENEFICIAL_SUPPORT = {"train": 32, "calibration": 8, "validation": 8}
MIN_BENEFICIAL_SOURCES = 3
MIN_BENEFICIAL_TIME_BUCKETS = 3
MIN_BENEFICIAL_LEG_TYPES = 2

CANONICAL_WAIT_REASONS = (
    "SOURCE_SERVICE_NOT_READY",
    "FIRST_EDGE_CREDIT_UNAVAILABLE",
    "DESTINATION_QUEUE_CAPACITY",
    "DESTINATION_MERGE_TOKEN",
    "PHYSICAL_FAULT_OR_GENERATION",
    "SUPERVISOR_HOLD",
    "PIBT_OR_RECOVERY_TRANSACTION",
    "OTHER_EXPLICIT_REASON",
)

WAIT_REASON_ALIASES = {
    "SOURCE_NOT_READY": "SOURCE_SERVICE_NOT_READY",
    "SERVICE_NOT_READY": "SOURCE_SERVICE_NOT_READY",
    "FIRST_EDGE_CREDIT": "FIRST_EDGE_CREDIT_UNAVAILABLE",
    "FIRST_EDGE_CREDIT_BLOCKED": "FIRST_EDGE_CREDIT_UNAVAILABLE",
    "DESTINATION_FULL": "DESTINATION_QUEUE_CAPACITY",
    "DESTINATION_QUEUE_FULL": "DESTINATION_QUEUE_CAPACITY",
    "MERGE_TOKEN": "DESTINATION_MERGE_TOKEN",
    "MERGE_TOKEN_UNAVAILABLE": "DESTINATION_MERGE_TOKEN",
    "PHYSICAL_FAULT": "PHYSICAL_FAULT_OR_GENERATION",
    "FAULT_GENERATION": "PHYSICAL_FAULT_OR_GENERATION",
    "SUPERVISOR_WAIT": "SUPERVISOR_HOLD",
    "PIBT_TRANSACTION": "PIBT_OR_RECOVERY_TRANSACTION",
    "RECOVERY_TRANSACTION": "PIBT_OR_RECOVERY_TRANSACTION",
    "OTHER": "OTHER_EXPLICIT_REASON",
}

# SOURCE_SERVICE_NOT_READY and SUPERVISOR_HOLD are the only classes whose
# service choice can be changed directly at this source opportunity.  Credit,
# capacity, and merge token blocks are downstream backpressure, even when the
# symptom is observed at a source.
SOURCE_LOCAL_REASONS = frozenset(
    {"SOURCE_SERVICE_NOT_READY", "SUPERVISOR_HOLD"}
)
DOWNSTREAM_REASONS = frozenset(
    {
        "FIRST_EDGE_CREDIT_UNAVAILABLE",
        "DESTINATION_QUEUE_CAPACITY",
        "DESTINATION_MERGE_TOKEN",
    }
)
FAULT_RECOVERY_REASONS = frozenset(
    {
        "PHYSICAL_FAULT_OR_GENERATION",
        "PIBT_OR_RECOVERY_TRANSACTION",
    }
)


class CampaignError(RuntimeError):
    """Raised for an actionable campaign input or evidence error."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CampaignError(message)


def _pick(row: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def _number(value: Any, label: str, *, default: float | None = None) -> float:
    if value in (None, "") and default is not None:
        return default
    if isinstance(value, bool):
        raise CampaignError(f"{label}: boolean is not numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CampaignError(f"{label}: expected finite number, got {value!r}") from exc
    if not math.isfinite(result):
        raise CampaignError(f"{label}: expected finite number, got {value!r}")
    return result


def _integer(value: Any, label: str, *, default: int | None = None) -> int:
    if value in (None, "") and default is not None:
        return default
    number = _number(value, label)
    if not number.is_integer():
        raise CampaignError(f"{label}: expected integer, got {value!r}")
    return int(number)


def _boolean(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False
    raise CampaignError(f"expected boolean, got {value!r}")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=_json_default,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, _json_bytes(value))


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str] | None = None,
) -> None:
    if fieldnames is None:
        names: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for name in row:
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        fieldnames = names
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fieldnames), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: _csv_value(row.get(name)) for name in fieldnames})
    _atomic_write(path, stream.getvalue().encode("utf-8"))


def _zstandard() -> Any:
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - dependency is in pyproject
        raise CampaignError(
            "zstandard>=0.23 is required for G17 causal datasets"
        ) from exc
    return zstandard


def _write_jsonl_zst(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    raw = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
        + b"\n"
        for row in rows
    )
    compressed = _zstandard().ZstdCompressor(level=6).compress(raw)
    _atomic_write(path, compressed)


def _write_json_zst(path: Path, value: Mapping[str, Any]) -> None:
    compressed = _zstandard().ZstdCompressor(level=6).compress(_json_bytes(value))
    _atomic_write(path, compressed)


def _decode_zst(path: Path) -> bytes:
    try:
        return _zstandard().ZstdDecompressor().decompress(path.read_bytes())
    except Exception as exc:
        raise CampaignError(f"cannot decompress {path}: {exc}") from exc


_INTEGER_RE = re.compile(r"^[+-]?(?:0|[1-9][0-9]*)$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:(?:[0-9]+\.[0-9]*)|(?:[0-9]*\.[0-9]+)|(?:[0-9]+[eE][+-]?[0-9]+)|(?:[0-9]+\.[0-9]*[eE][+-]?[0-9]+))$"
)


def _coerce_text(value: str) -> Any:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if _INTEGER_RE.fullmatch(stripped):
        try:
            return int(stripped)
        except ValueError:
            return stripped
    if _FLOAT_RE.fullmatch(stripped):
        try:
            number = float(stripped)
            return number if math.isfinite(number) else stripped
        except ValueError:
            return stripped
    if stripped[:1] in {"[", "{"}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def _extract_rows(value: Any, *, label: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        _require(all(isinstance(row, dict) for row in value), f"{label}: rows must be objects")
        return [dict(row) for row in value]
    if isinstance(value, dict):
        for key in (
            "rows",
            "source_wait_events",
            "g4irsf17_source_wait_blockers",
            "source_wait_telemetry",
            "events",
            "pairs",
            "records",
            "targets",
            "data",
        ):
            candidate = value.get(key)
            if isinstance(candidate, (list, dict)):
                try:
                    return _extract_rows(candidate, label=f"{label}.{key}")
                except CampaignError:
                    pass
        # A single pair/event object is a useful one-row fixture.
        return [dict(value)]
    raise CampaignError(f"{label}: expected row list or object payload")


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Read CSV, JSON, JSONL, or their zstd variants into dictionaries."""

    if not path.is_file():
        raise CampaignError(f"input does not exist: {path}")
    suffixes = [suffix.lower() for suffix in path.suffixes]
    payload = _decode_zst(path) if suffixes[-1:] == [".zst"] else path.read_bytes()
    name_without_zst = path.name[:-4] if path.name.lower().endswith(".zst") else path.name
    if name_without_zst.lower().endswith(".csv"):
        text = payload.decode("utf-8-sig")
        return [
            {key: _coerce_text(value) for key, value in row.items()}
            for row in csv.DictReader(io.StringIO(text))
        ]
    text = payload.decode("utf-8-sig").strip()
    if not text:
        return []
    try:
        return _extract_rows(json.loads(text), label=str(path))
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CampaignError(f"{path}:{line_number}: invalid JSONL") from exc
            _require(isinstance(row, dict), f"{path}:{line_number}: row is not an object")
            rows.append(row)
        return rows


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


@dataclass
class CampaignJournal:
    """Small append/update journal; scientific results, not hashes, are state."""

    root: Path
    manifest_path: Path = CAMPAIGN_MANIFEST_PATH
    log_path: Path = CAMPAIGN_LOG_PATH

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.manifest_path = self.root / self.manifest_path
        self.log_path = self.root / self.log_path
        if self.manifest_path.is_file():
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            _require(
                value.get("schema") in {SCHEMA_MANIFEST, LEGACY_SCHEMA_MANIFEST},
                "G17 manifest schema mismatch",
            )
            self.value = value
            self.value.setdefault("stages", {})
        else:
            self.value = {
                "schema": SCHEMA_MANIFEST,
                "status": "IN_PROGRESS",
                "created_at_utc": _now(),
                "updated_at_utc": _now(),
                "code_revision": _git_revision(self.root),
                "delta_convention": "treatment_minus_baseline; negative_time_is_better",
                "stages": {},
            }
            self._save()
        if not self.log_path.is_file():
            _atomic_write(
                self.log_path,
                (
                    "# G4IRSF17 campaign log\n\n"
                    "This log tracks executable evidence stages and pivots; artifact hashes are intentionally not the campaign objective.\n"
                ).encode("utf-8"),
            )

    def _save(self) -> None:
        self.value["updated_at_utc"] = _now()
        _write_json(self.manifest_path, self.value)

    def _log(self, stage: str, status: str, detail: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(f"\n## {_now()} — {stage}: {status}\n\n{detail.strip()}\n")

    @staticmethod
    def _phase_for_stage(stage: str) -> str | None:
        if stage == "source_wait_diagnosis":
            return "A"
        if stage.startswith("i1_") or stage in {"state_aliasing", "model_reporting"}:
            return "B-D"
        return None

    def _phase_row(self, stage: str) -> dict[str, Any] | None:
        phase_name = self._phase_for_stage(stage)
        phases = self.value.get("phases")
        if phase_name is None or not isinstance(phases, list):
            return None
        return next(
            (
                row
                for row in phases
                if isinstance(row, dict) and str(row.get("phase")) == phase_name
            ),
            None,
        )

    def resumable(self, stage: str, outputs: Sequence[Path]) -> bool:
        value = self.value.get("stages", {}).get(stage, {})
        return value.get("status") == "COMPLETE" and all(
            (self.root / output).is_file() for output in outputs
        )

    def begin(
        self,
        stage: str,
        *,
        command: Sequence[str] | None = None,
        inputs: Sequence[Path] = (),
    ) -> None:
        prior = self.value["stages"].get(stage, {})
        attempt = int(prior.get("attempt", 0)) + 1
        self.value["stages"][stage] = {
            **prior,
            "status": "RUNNING",
            "attempt": attempt,
            "started_at_utc": _now(),
            "code_revision": _git_revision(self.root),
            "command": list(command or ()),
            "inputs": [_relative(path, self.root) for path in inputs],
            "error": None,
        }
        phase = self._phase_row(stage)
        if phase is not None:
            phase["status"] = "IN_PROGRESS"
            commands = phase.setdefault("commands", [])
            rendered = " ".join(str(value) for value in (command or ()))
            if rendered and rendered not in commands:
                commands.append(rendered)
        self._save()
        self._log(stage, "RUNNING", f"Attempt {attempt} started.")

    def checkpoint(self, stage: str, progress: Mapping[str, Any]) -> None:
        value = self.value["stages"].setdefault(stage, {})
        value["status"] = "RUNNING"
        value["progress"] = dict(progress)
        value["checkpoint_at_utc"] = _now()
        self._save()

    def complete(
        self,
        stage: str,
        *,
        outputs: Sequence[Path],
        summary: Mapping[str, Any],
        decision: str,
        next_action: str,
    ) -> None:
        value = self.value["stages"].setdefault(stage, {})
        value.update(
            {
                "status": "COMPLETE",
                "finished_at_utc": _now(),
                "outputs": [_relative(path, self.root) for path in outputs],
                "summary": dict(summary),
                "decision": decision,
                "next_action": next_action,
                "error": None,
            }
        )
        phase = self._phase_row(stage)
        if phase is not None:
            # Model reporting is one B-D checkpoint, not completion of the
            # whole causal/model phase.  Phase A, however, is exactly this
            # diagnosis stage.
            phase["status"] = (
                "COMPLETE" if stage == "source_wait_diagnosis" else "IN_PROGRESS"
            )
            result_paths = phase.setdefault("result_paths", [])
            for path in outputs:
                rendered = _relative(path, self.root)
                if rendered not in result_paths:
                    result_paths.append(rendered)
            phase["decision"] = decision
            phase["next_action"] = next_action
        self._save()
        self._log(
            stage,
            "COMPLETE",
            f"Decision: `{decision}`\n\nNext: {next_action}",
        )

    def fail(self, stage: str, error: BaseException) -> None:
        value = self.value["stages"].setdefault(stage, {})
        value.update(
            {
                "status": "FAILED_RESUMABLE",
                "finished_at_utc": _now(),
                "error": f"{type(error).__name__}: {error}",
            }
        )
        phase = self._phase_row(stage)
        if phase is not None:
            phase["status"] = "FAILED_RESUMABLE"
            phase["decision"] = "RESUME_FROM_LAST_CHECKPOINT"
            phase["next_action"] = str(error)
        self._save()
        self._log(stage, "FAILED_RESUMABLE", str(error))


def _bag_identity(row: Mapping[str, Any]) -> str:
    value = _pick(
        row,
        "raw_bag_id",
        "task_id",
        "selected_task_id",
        "bag_id",
        "runtime_bag_id",
        "selected_runtime_bag_id",
    )
    if value in (None, ""):
        raise CampaignError("bag row lacks raw_bag_id/task_id/bag_id/runtime_bag_id")
    return str(value)


def _normalise_bag_metrics(row: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    source_wait = _number(
        _pick(
            row,
            "source_wait_seconds",
            "observed_source_wait_seconds",
            "source_queue_wait_seconds",
        ),
        f"{label}.source_wait_seconds",
    )
    network = _number(
        _pick(
            row,
            "network_time_seconds",
            "observed_network_time_seconds",
            "network_seconds",
        ),
        f"{label}.network_time_seconds",
    )
    tth_value = _pick(
        row,
        "total_system_time_seconds",
        "original_entry_time_tth_seconds",
        "observed_original_entry_seconds",
        "tth_seconds",
        "completion_seconds",
    )
    tth = _number(tth_value, f"{label}.tth_seconds")
    return {
        "bag_key": _bag_identity(row),
        "task_id": _pick(row, "task_id", "raw_bag_id", "bag_id"),
        "source_wait_seconds": source_wait,
        "network_time_seconds": network,
        "tth_seconds": tth,
        "deadline_miss": _boolean(_pick(row, "deadline_miss", "missed_deadline"), default=False),
        "complete": _boolean(_pick(row, "complete", "completed"), default=True),
    }


def _normalise_arm(value: Any, *, default: str) -> str:
    if value in (None, ""):
        return default
    text = str(value).strip().lower()
    if text in {"h5", "candidate", "treatment", "closed_loop", "on"}:
        return "h5"
    if text in {"off", "baseline", "control", "e4_off", "f2"}:
        return "off"
    raise CampaignError(f"unknown telemetry arm {value!r}")


def _reason_class(reason: str) -> str:
    if reason in SOURCE_LOCAL_REASONS:
        return "SOURCE_LOCAL_ORDERABLE"
    if reason in DOWNSTREAM_REASONS:
        return "DOWNSTREAM_BACKPRESSURE"
    if reason in FAULT_RECOVERY_REASONS:
        return "FAULT_OR_RECOVERY"
    return "OTHER_EXPLICIT"


def _leg_type(row: Mapping[str, Any]) -> str:
    direct = _pick(row, "leg_type", "bag_class", "leg")
    if direct not in (None, ""):
        return str(direct)
    segment = str(_pick(row, "segment_id", "selected_segment_id", default="unknown"))
    if ":" in segment:
        return segment.rsplit(":", 1)[-1]
    return "unknown"


def _normalise_wait_event(
    row: Mapping[str, Any],
    *,
    index: int,
    default_arm: str,
) -> dict[str, Any]:
    raw_reason = _pick(row, "reason", "wait_reason", "source_wait_reason", "block_reason")
    if raw_reason in (None, ""):
        raise CampaignError(
            f"telemetry row {index} lacks an explicit source-wait reason; blocked=true is not attribution"
        )
    reason = str(raw_reason).strip().upper().replace("-", "_").replace(" ", "_")
    reason = WAIT_REASON_ALIASES.get(reason, reason)
    if reason not in CANONICAL_WAIT_REASONS:
        raise CampaignError(f"telemetry row {index} has unknown explicit reason {raw_reason!r}")
    start = _pick(row, "wait_start_time", "start_time", "blocked_since")
    end = _pick(row, "wait_end_time", "end_time", "unblocked_at")
    # Native interval telemetry exposes both wall-clock interval seconds and
    # queue-population-weighted bag seconds.  Attribution must use bag seconds
    # so it reconciles to raw-bag source wait.
    duration_value = _pick(
        row,
        "wait_bag_seconds",
        "wait_seconds",
        "duration_seconds",
        "source_wait_seconds",
    )
    if duration_value in (None, ""):
        _require(start not in (None, "") and end not in (None, ""), f"telemetry row {index} lacks wait duration")
        duration = _number(end, f"telemetry[{index}].wait_end") - _number(start, f"telemetry[{index}].wait_start")
    else:
        duration = _number(duration_value, f"telemetry[{index}].wait_seconds")
    if duration < -EPSILON:
        raise CampaignError(f"telemetry row {index} has negative wait duration")
    duration = max(0.0, duration)
    event_time = _number(
        _pick(row, "event_time", "wait_start_time", "start_time", default=0.0),
        f"telemetry[{index}].event_time",
    )
    hour = _pick(row, "time_bucket", "event_hour_floor", "hour")
    time_bucket = str(hour if hour not in (None, "") else int(event_time // 3600.0))
    bag_key = _bag_identity(row)
    return {
        "arm": _normalise_arm(_pick(row, "arm", "policy", "variant", "branch", "mode"), default=default_arm),
        "bag_key": bag_key,
        "runtime_bag_id": _pick(row, "runtime_bag_id", "selected_runtime_bag_id"),
        "task_id": _pick(row, "task_id", "selected_task_id", "raw_bag_id", "bag_id"),
        "segment_id": _pick(row, "segment_id", "selected_segment_id"),
        "reason": reason,
        "cause_class": _reason_class(reason),
        "source_node": str(_pick(row, "source_node", "source", "node", default="unknown")),
        "blocker_node": str(_pick(row, "blocker_node", "destination_node", "target_node", default="unknown")),
        "blocker_resource": str(_pick(row, "blocker_resource", "resource", "edge", default="unknown")),
        "source_queue_generation": _pick(
            row,
            "source_queue_generation",
            "source_generation",
            "queue_generation",
            "generation",
        ),
        "blocker_generation": _pick(row, "blocker_generation"),
        "affected_bag_count": _integer(
            _pick(row, "affected_bag_count", default=1),
            f"telemetry[{index}].affected_bag_count",
            default=1,
        ),
        "aggregate_interval": "wait_bag_seconds" in row,
        "interval_wait_seconds": _number(
            _pick(row, "wait_seconds", "duration_seconds", default=duration),
            f"telemetry[{index}].interval_wait_seconds",
            default=duration,
        ),
        "wait_start_time": start,
        "wait_end_time": end,
        "event_time": event_time,
        "time_bucket": time_bucket,
        "leg_type": _leg_type(row),
        "wait_seconds": duration,
        "admitted": _boolean(_pick(row, "admitted"), default=False),
        "held": _boolean(_pick(row, "held"), default=True),
    }


def _topology_rows(ledger: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dimensions = {
        "CAUSE": ("reason", "cause_class"),
        "SOURCE": ("source_node",),
        "BLOCKER": ("blocker_node", "blocker_resource"),
        "SOURCE_BLOCKER_TIME_LEG": (
            "source_node",
            "blocker_node",
            "time_bucket",
            "leg_type",
            "reason",
        ),
    }
    total_positive = sum(float(row["attributed_positive_additional_wait_seconds"]) for row in ledger)
    result: list[dict[str, Any]] = []
    for aggregation, fields in dimensions.items():
        grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
        for row in ledger:
            grouped[tuple(str(row.get(field, "")) for field in fields)].append(row)
        ranked: list[dict[str, Any]] = []
        for key, rows in grouped.items():
            positive = sum(float(row["attributed_positive_additional_wait_seconds"]) for row in rows)
            attribution_scopes = {
                str(row.get("attribution_scope", "matched_bag")) for row in rows
            }
            aggregate_native_cells = attribution_scopes == {
                "aggregate_native_cell"
            }
            ranked.append(
                {
                    "aggregation": aggregation,
                    **{field: value for field, value in zip(fields, key, strict=True)},
                    # Aggregate native intervals are queue-population-weighted
                    # cells, not per-bag observations.  Their selected bag
                    # identity is trace context only, so a bag count would
                    # incorrectly imply finer causal attribution.
                    "matched_bag_count": (
                        None
                        if aggregate_native_cells
                        else len({str(row["bag_key"]) for row in rows})
                    ),
                    "attribution_scope": (
                        "aggregate_native_cell"
                        if aggregate_native_cells
                        else "matched_bag"
                    ),
                    "h5_native_wait_seconds": sum(float(row["h5_native_wait_seconds"]) for row in rows),
                    "off_native_wait_seconds": sum(float(row["off_native_wait_seconds"]) for row in rows),
                    "native_reason_wait_delta_seconds": sum(float(row["native_reason_wait_delta_seconds"]) for row in rows),
                    "attributed_positive_additional_wait_seconds": positive,
                    "positive_additional_wait_share": positive / total_positive if total_positive > EPSILON else 0.0,
                }
            )
        ranked.sort(
            key=lambda row: (
                -float(row["attributed_positive_additional_wait_seconds"]),
                json.dumps(row, sort_keys=True, default=str),
            )
        )
        for rank, row in enumerate(ranked, start=1):
            row["rank_within_aggregation"] = rank
            result.append(row)
    return result


def diagnose_source_wait(
    telemetry_rows: Sequence[Mapping[str, Any]],
    h5_bag_rows: Sequence[Mapping[str, Any]],
    off_bag_rows: Sequence[Mapping[str, Any]],
    *,
    off_telemetry_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Attribute matched H5-minus-off source wait to native explicit reasons."""

    h5 = {_bag_identity(row): _normalise_bag_metrics(row, label="h5") for row in h5_bag_rows}
    off = {_bag_identity(row): _normalise_bag_metrics(row, label="off") for row in off_bag_rows}
    matched = sorted(set(h5) & set(off), key=lambda value: (len(value), value))
    _require(matched, "no matched H5/off bags")
    events = [
        _normalise_wait_event(row, index=index, default_arm="h5")
        for index, row in enumerate(telemetry_rows)
    ]
    events.extend(
        _normalise_wait_event(row, index=index, default_arm="off")
        for index, row in enumerate(off_telemetry_rows)
    )

    aggregate: dict[tuple[str, str, str, str, str, str, str], dict[str, float]] = defaultdict(
        lambda: {"h5": 0.0, "off": 0.0}
    )
    event_meta: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
    for event in events:
        if event["bag_key"] not in set(matched):
            continue
        key = (
            event["bag_key"],
            event["reason"],
            event["source_node"],
            event["blocker_node"],
            event["blocker_resource"],
            event["time_bucket"],
            event["leg_type"],
        )
        aggregate[key][event["arm"]] += float(event["wait_seconds"])
        event_meta[key] = event

    by_bag_keys: dict[str, list[tuple[str, str, str, str, str, str, str]]] = defaultdict(list)
    for key in aggregate:
        by_bag_keys[key[0]].append(key)

    ledger: list[dict[str, Any]] = []
    covered_positive_seconds = 0.0
    positive_source_wait_total = 0.0
    for bag_key in matched:
        left, right = off[bag_key], h5[bag_key]
        source_delta = right["source_wait_seconds"] - left["source_wait_seconds"]
        network_delta = right["network_time_seconds"] - left["network_time_seconds"]
        tth_delta = right["tth_seconds"] - left["tth_seconds"]
        positive_delta = max(0.0, source_delta)
        positive_source_wait_total += positive_delta
        keys = by_bag_keys.get(bag_key, [])
        native_deltas = {
            key: aggregate[key]["h5"] - aggregate[key]["off"] for key in keys
        }
        positive_native = {key: max(0.0, value) for key, value in native_deltas.items()}
        weight_total = sum(positive_native.values())
        if positive_delta > EPSILON and weight_total > EPSILON:
            covered_positive_seconds += positive_delta
        if not keys and positive_delta > EPSILON:
            synthetic_key = (
                bag_key,
                "OTHER_EXPLICIT_REASON",
                "unknown",
                "unknown",
                "UNATTRIBUTED_NATIVE_COVERAGE_GAP",
                "unknown",
                "unknown",
            )
            keys = [synthetic_key]
            aggregate[synthetic_key] = {"h5": 0.0, "off": 0.0}
            native_deltas[synthetic_key] = 0.0
            positive_native[synthetic_key] = 0.0
            event_meta[synthetic_key] = {
                "cause_class": "OTHER_EXPLICIT",
                "source_queue_generation": None,
            }
        for key in keys:
            _, reason, source, blocker, resource, time_bucket, leg_type = key
            attributed = (
                positive_delta * positive_native.get(key, 0.0) / weight_total
                if weight_total > EPSILON
                else 0.0
            )
            meta = event_meta[key]
            ledger.append(
                {
                    "bag_key": bag_key,
                    "task_id": right["task_id"],
                    "reason": reason,
                    "cause_class": meta.get("cause_class", _reason_class(reason)),
                    "source_node": source,
                    "blocker_node": blocker,
                    "blocker_resource": resource,
                    "time_bucket": time_bucket,
                    "leg_type": leg_type,
                    "source_queue_generation": meta.get("source_queue_generation"),
                    "h5_native_wait_seconds": aggregate[key]["h5"],
                    "off_native_wait_seconds": aggregate[key]["off"],
                    "native_reason_wait_delta_seconds": native_deltas.get(key, 0.0),
                    "attributed_positive_additional_wait_seconds": attributed,
                    "telemetry_attributed": weight_total > EPSILON,
                    "bag_source_wait_delta_seconds": source_delta,
                    "bag_network_time_delta_seconds": network_delta,
                    "bag_tth_delta_seconds": tth_delta,
                    "same_bag_network_improvement_source_regression": source_delta > EPSILON and network_delta < -EPSILON,
                    "attribution_scope": "matched_bag",
                }
            )

    aggregate_interval_attribution = any(
        event["aggregate_interval"] for event in events
    )
    if aggregate_interval_attribution:
        # The native G17 binding reports bounded blocker intervals with
        # ``affected_bag_count`` and queue-population-weighted
        # ``wait_bag_seconds``.  A selected bag is diagnostic context, not an
        # assertion that all interval bag-seconds belong to it.  Attribute at
        # interval/topology level and reconcile the global positive bag delta.
        interval_totals: dict[tuple[str, str, str, str, str, str], dict[str, float]] = defaultdict(
            lambda: {"h5": 0.0, "off": 0.0}
        )
        interval_meta: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
        for event in events:
            key = (
                event["reason"],
                event["source_node"],
                event["blocker_node"],
                event["blocker_resource"],
                event["time_bucket"],
                event["leg_type"],
            )
            interval_totals[key][event["arm"]] += float(event["wait_seconds"])
            interval_meta[key] = event
        interval_deltas = {
            key: value["h5"] - value["off"]
            for key, value in interval_totals.items()
        }
        positive_interval_total = sum(max(0.0, value) for value in interval_deltas.values())
        covered_positive_seconds = min(
            positive_source_wait_total,
            positive_interval_total,
        )
        ledger = []
        for key in sorted(interval_totals):
            reason, source, blocker, resource, time_bucket, leg_type = key
            meta = interval_meta[key]
            attributed = (
                positive_source_wait_total
                * max(0.0, interval_deltas[key])
                / positive_interval_total
                if positive_interval_total > EPSILON
                else 0.0
            )
            ledger.append(
                {
                    "bag_key": "AGGREGATE_NATIVE_INTERVALS",
                    "task_id": meta.get("task_id"),
                    "reason": reason,
                    "cause_class": meta["cause_class"],
                    "source_node": source,
                    "blocker_node": blocker,
                    "blocker_resource": resource,
                    "time_bucket": time_bucket,
                    "leg_type": leg_type,
                    "source_queue_generation": meta.get("source_queue_generation"),
                    "blocker_generation": meta.get("blocker_generation"),
                    "affected_bag_count": meta.get("affected_bag_count"),
                    "h5_native_wait_seconds": interval_totals[key]["h5"],
                    "off_native_wait_seconds": interval_totals[key]["off"],
                    "native_reason_wait_delta_seconds": interval_deltas[key],
                    "attributed_positive_additional_wait_seconds": attributed,
                    "telemetry_attributed": positive_interval_total > EPSILON,
                    "bag_source_wait_delta_seconds": None,
                    "bag_network_time_delta_seconds": None,
                    "bag_tth_delta_seconds": None,
                    "same_bag_network_improvement_source_regression": None,
                    "attribution_scope": "aggregate_native_cell",
                }
            )

    telemetry_coverage = (
        covered_positive_seconds / positive_source_wait_total
        if positive_source_wait_total > EPSILON
        else 1.0
    )
    topology = _topology_rows(ledger)
    reason_positive: Counter[str] = Counter()
    class_positive: Counter[str] = Counter()
    for row in ledger:
        contribution = float(row["attributed_positive_additional_wait_seconds"])
        reason_positive[str(row["reason"])] += contribution
        class_positive[str(row["cause_class"])] += contribution
    denominator = sum(reason_positive.values())
    source_share = class_positive["SOURCE_LOCAL_ORDERABLE"] / denominator if denominator > EPSILON else 0.0
    downstream_share = class_positive["DOWNSTREAM_BACKPRESSURE"] / denominator if denominator > EPSILON else 0.0
    other_share = 1.0 - source_share - downstream_share if denominator > EPSILON else 0.0
    if not events or telemetry_coverage < SOURCE_WAIT_TELEMETRY_MIN_COVERAGE:
        pivot = "TELEMETRY_INSUFFICIENT_ADD_MINIMAL_NATIVE_REASONS"
        next_action = "Complete native reason coverage before training or a G2 pivot."
    elif downstream_share >= 0.50:
        pivot = "I1_BOUNDED_PILOT_AND_START_G2"
        next_action = "Run the bounded I1 pilot, while allocating the next causal budget to destination merge/service-token G2."
    elif source_share >= 0.50:
        pivot = "CONTINUE_I1_SOURCE_ORDERING"
        next_action = "Run and expand real competitive I1 top-2 pairs."
    else:
        pivot = "I1_BOUNDED_PILOT_MIXED_ATTRIBUTION"
        next_action = "Run bounded I1 and retain explicit mixed-cause stratification."

    bag_deltas = [
        {
            "bag_key": bag_key,
            "source": h5[bag_key]["source_wait_seconds"] - off[bag_key]["source_wait_seconds"],
            "network": h5[bag_key]["network_time_seconds"] - off[bag_key]["network_time_seconds"],
            "tth": h5[bag_key]["tth_seconds"] - off[bag_key]["tth_seconds"],
        }
        for bag_key in matched
    ]
    tradeoff_count = sum(
        row["source"] > EPSILON and row["network"] < -EPSILON for row in bag_deltas
    )
    network_improved = {row["bag_key"] for row in bag_deltas if row["network"] < -EPSILON}
    source_regressed = {row["bag_key"] for row in bag_deltas if row["source"] > EPSILON}
    top_joint = [
        row
        for row in topology
        if row["aggregation"] == "SOURCE_BLOCKER_TIME_LEG"
    ][:10]
    summary = {
        "matched_bag_count": len(matched),
        "source_wait_delta_total_seconds": sum(row["source"] for row in bag_deltas),
        "source_wait_delta_mean_seconds_per_raw_bag": sum(row["source"] for row in bag_deltas) / len(matched),
        "network_time_delta_total_seconds": sum(row["network"] for row in bag_deltas),
        "network_time_delta_mean_seconds_per_raw_bag": sum(row["network"] for row in bag_deltas) / len(matched),
        "tth_delta_total_seconds": sum(row["tth"] for row in bag_deltas),
        "tth_delta_mean_seconds_per_raw_bag": sum(row["tth"] for row in bag_deltas) / len(matched),
        "positive_additional_source_wait_seconds": positive_source_wait_total,
        "native_telemetry_event_count": len(events),
        "telemetry_attribution_scope": (
            "aggregate_native_cell_positive_delta_reconciliation"
            if aggregate_interval_attribution
            else "matched_bag_positive_delta_reconciliation"
        ),
        "telemetry_positive_wait_coverage": telemetry_coverage,
        "source_local_orderable_share": source_share,
        "downstream_backpressure_share": downstream_share,
        "fault_recovery_or_other_share": max(0.0, other_share),
        "reason_positive_additional_seconds": dict(sorted(reason_positive.items())),
        "network_improved_bag_count": len(network_improved),
        "source_wait_regressed_bag_count": len(source_regressed),
        "same_bag_network_improvement_source_regression_count": tradeoff_count,
        "same_bag_tradeoff_share_of_source_regressions": tradeoff_count / len(source_regressed) if source_regressed else 0.0,
        "additional_wait_affected_bag_count": len(source_regressed),
        "pivot_decision": pivot,
        "next_action": next_action,
        "topology_top10": top_joint,
    }
    return {"ledger": ledger, "topology": topology, "summary": summary}


def _source_wait_report(summary: Mapping[str, Any]) -> str:
    reasons = summary["reason_positive_additional_seconds"]
    reason_lines = "\n".join(
        f"| {reason} | {seconds:.6f} |"
        for reason, seconds in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    ) or "| no attributed native reason | 0.000000 |"
    top_lines = "\n".join(
        "| {source_node} | {blocker_node} | {time_bucket} | {leg_type} | {reason} | {seconds:.6f} | {share:.2%} |".format(
            **row,
            seconds=float(row["attributed_positive_additional_wait_seconds"]),
            share=float(row["positive_additional_wait_share"]),
        )
        for row in summary.get("topology_top10", [])
    ) or "| — | — | — | — | — | 0.000000 | 0.00% |"
    if summary.get("telemetry_attribution_scope") == (
        "aggregate_native_cell_positive_delta_reconciliation"
    ):
        reconciliation_text = (
            "Native rows are queue-population-weighted aggregate intervals. "
            "The table reconciles the matched cohort's global positive "
            "H5-minus-off source-wait delta across aggregate native cells in "
            "proportion to each cell's positive H5-minus-off bag-seconds "
            "delta. Selected bag identities are trace context only; this is "
            "not per-bag causal attribution."
        )
    else:
        reconciliation_text = (
            "The table distributes each bag's measured positive H5-minus-off "
            "source-wait delta in proportion to that bag's positive native "
            "reason-duration deltas."
        )
    return f"""# G4IRSF17 source-wait diagnosis

## Result

Matched raw bags: **{summary['matched_bag_count']}**.  H5 minus matched E4/off mean source wait is **{summary['source_wait_delta_mean_seconds_per_raw_bag']:+.6f} s/raw bag**; network time is **{summary['network_time_delta_mean_seconds_per_raw_bag']:+.6f} s/raw bag** and total TTH is **{summary['tth_delta_mean_seconds_per_raw_bag']:+.6f} s/raw bag**.

All deltas are `H5 - E4/off`; negative time is better.  Native explicit-reason telemetry reconciles **{summary['telemetry_positive_wait_coverage']:.2%}** of the matched cohort's positive additional source wait.

The orderable local-source share is **{summary['source_local_orderable_share']:.2%}** and downstream credit/capacity/merge backpressure is **{summary['downstream_backpressure_share']:.2%}**.  The directional 50% gate therefore yields **`{summary['pivot_decision']}`**.

{summary['next_action']}

## Native reason contribution

{reconciliation_text}  Raw native durations remain in the ledger, so this reconciliation is visible rather than guessed.

| Reason | Attributed positive additional seconds |
|---|---:|
{reason_lines}

## Top source / blocker / time / leg cells

| Source | Blocker | Hour bucket | Leg | Reason | Seconds | Share |
|---|---|---|---|---|---:|---:|
{top_lines}

## Same-bag versus transferred waiting

Network time improved for **{summary['network_improved_bag_count']}** bags, source wait regressed for **{summary['source_wait_regressed_bag_count']}**, and both happened on the same bag for **{summary['same_bag_network_improvement_source_regression_count']}** bags.  Positive source-wait regression touched **{summary['additional_wait_affected_bag_count']}** matched raw bags; this count is reported as propagation/transfer breadth, not as proof that every affected bag was causally downstream of the same intervention.

## Publication boundary

Raw `*.source_wait.json`, `*.raw_bag_timings.csv`, and `outputs/runstate/**` files are local resumable telemetry and are intentionally excluded from the repository release.  The committed compact evidence for this diagnosis is `outputs/tables/g4irsf17_source_wait_cause_ledger.csv`, `outputs/tables/g4irsf17_source_wait_topology_attribution.csv`, and this report.

## Gate definitions

* `CONTINUE_I1_SOURCE_ORDERING`: at least 50% of attributed positive added wait is `SOURCE_SERVICE_NOT_READY` or `SUPERVISOR_HOLD`.
* `I1_BOUNDED_PILOT_AND_START_G2`: at least 50% is first-edge credit, destination capacity, or destination merge-token backpressure.
* telemetry coverage below {SOURCE_WAIT_TELEMETRY_MIN_COVERAGE:.0%} blocks either scientific pivot; a generic `blocked=true` is never converted into a reason offline.
"""


def run_source_wait_diagnosis(
    *,
    root: Path,
    telemetry_rows: Sequence[Mapping[str, Any]],
    h5_bag_rows: Sequence[Mapping[str, Any]],
    off_bag_rows: Sequence[Mapping[str, Any]],
    off_telemetry_rows: Sequence[Mapping[str, Any]] = (),
    journal: CampaignJournal | None = None,
) -> dict[str, Any]:
    result = diagnose_source_wait(
        telemetry_rows,
        h5_bag_rows,
        off_bag_rows,
        off_telemetry_rows=off_telemetry_rows,
    )
    ledger_path = root / SOURCE_WAIT_LEDGER_PATH
    topology_path = root / SOURCE_WAIT_TOPOLOGY_PATH
    report_path = root / SOURCE_WAIT_REPORT_PATH
    _write_csv(ledger_path, result["ledger"])
    _write_csv(topology_path, result["topology"])
    _atomic_write(report_path, _source_wait_report(result["summary"]).encode("utf-8"))
    if journal is not None:
        journal.complete(
            "source_wait_diagnosis",
            outputs=(ledger_path, topology_path, report_path),
            summary=result["summary"],
            decision=result["summary"]["pivot_decision"],
            next_action=result["summary"]["next_action"],
        )
    return result


def _queue_bucket(queue_length: int) -> str:
    if queue_length <= 2:
        return "q2"
    if queue_length <= 4:
        return "q3_4"
    if queue_length <= 8:
        return "q5_8"
    if queue_length <= 16:
        return "q9_16"
    if queue_length <= 32:
        return "q17_32"
    return "q33_plus"


def _target_strata(row: Mapping[str, Any]) -> dict[str, str]:
    offline = row.get("offline_sampling_metadata")
    offline = offline if isinstance(offline, dict) else {}
    source = _pick(offline, "source_node", "source_label", default=_pick(row, "source_node", "node", "source", default="unknown"))
    event_time = _number(_pick(row, "event_time", default=0.0), "target.event_time")
    time_bucket = _pick(row, "event_hour_floor", default=int(event_time // 3600.0))
    queue_length = _integer(
        _pick(row, "queued_bag_count", "source_queue_length", default=len(row.get("source_ready_order", []))),
        "target.queue_length",
        default=0,
    )
    slack = _pick(offline, "deadline_slack_bucket")
    if slack in (None, ""):
        deadline = _number(_pick(row, "deadline", default=-1.0), "target.deadline")
        remaining = deadline - event_time if deadline >= 0.0 else math.inf
        slack = "tight" if remaining <= 300.0 else "medium" if remaining <= 900.0 else "ample"
    leg = _pick(offline, "bag_class", default=_leg_type(row))
    return {
        "source": str(source),
        "time": str(time_bucket),
        "queue": _queue_bucket(queue_length),
        "slack": str(slack),
        "leg": str(leg),
    }


def is_real_competitive_i1(row: Mapping[str, Any]) -> bool:
    if row.get("kind") != "I1":
        return False
    ready = row.get("source_ready_order")
    if not isinstance(ready, list) or len(ready) < 2:
        return False
    try:
        baseline = _integer(row.get("runtime_bag_id"), "target.runtime_bag_id")
        peer = _integer(row.get("peer_runtime_bag_id"), "target.peer_runtime_bag_id")
        first = _integer(ready[0], "target.source_ready_order[0]")
        second = _integer(ready[1], "target.source_ready_order[1]")
        alternatives = _integer(
            _pick(
                row,
                "candidate_action_count",
                "alternative_action_count",
                default=len(ready) - 1,
            ),
            "target.candidate_action_count",
            default=0,
        )
    except CampaignError:
        return False
    return baseline == first and peer == second and baseline != peer and alternatives >= 1


def _diverse_select(
    rows: Sequence[Mapping[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    _require(count >= 0, "selection count must be non-negative")
    _require(count <= len(rows), f"requested {count} targets from only {len(rows)} eligible rows")
    available = [dict(row) for row in rows]
    available.sort(key=lambda row: (int(row.get("event_ordinal", 0)), str(row.get("descriptor_id", ""))))
    dimension_counts: dict[str, Counter[str]] = {
        name: Counter() for name in ("source", "time", "queue", "slack", "leg")
    }
    joint_counts: Counter[tuple[str, ...]] = Counter()
    selected: list[dict[str, Any]] = []
    weights = {"source": 3.0, "time": 2.0, "queue": 2.0, "slack": 1.5, "leg": 1.5}
    while len(selected) < count:
        best_index = 0
        best_score: tuple[float, float, int, str] | None = None
        for index, row in enumerate(available):
            strata = _target_strata(row)
            joint = tuple(strata[name] for name in ("source", "time", "queue", "slack", "leg"))
            diversity = sum(
                weights[name] / (1.0 + dimension_counts[name][value])
                for name, value in strata.items()
            )
            diversity += 2.0 / (1.0 + joint_counts[joint])
            queue_length = float(_pick(row, "queued_bag_count", default=2))
            score = (
                diversity,
                min(queue_length, 64.0) / 64.0,
                -int(row.get("event_ordinal", 0)),
                str(row.get("descriptor_id", "")),
            )
            if best_score is None or score > best_score:
                best_score = score
                best_index = index
        chosen = available.pop(best_index)
        strata = _target_strata(chosen)
        joint = tuple(strata[name] for name in ("source", "time", "queue", "slack", "leg"))
        for name, value in strata.items():
            dimension_counts[name][value] += 1
        joint_counts[joint] += 1
        chosen["g4irsf17_strata"] = strata
        chosen["g4irsf17_selection_rank"] = len(selected) + 1
        selected.append(chosen)
    return selected


def _with_horizon(row: Mapping[str, Any], horizon: str) -> dict[str, Any]:
    _require(horizon in {"H_bag", "H_system"}, f"unsupported horizon {horizon}")
    result = dict(row)
    result["horizon"] = horizon
    for field in ("target_address_sha256", "intervention_sha256"):
        variants = result.get(f"{field}_by_horizon")
        if isinstance(variants, dict) and horizon in variants:
            result[field] = variants[horizon]
    descriptor = _pick(result, "descriptor_id", "target_address_id", "skeleton_id")
    _require(descriptor not in (None, ""), "I1 target lacks descriptor identity")
    result["target_key"] = f"{descriptor}:{horizon}"
    result["g4irsf17_native_seam"] = "g4irsf15_run_causal_target_pairs_from_records"
    return result


def select_i1_pilot_targets(
    rows: Sequence[Mapping[str, Any]],
    *,
    h_bag_count: int = 128,
    h_system_count: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select diverse real I1 top-2 opportunities and bounded H_system copies."""

    # Counts below 64 are accepted for fixture/dry-run analysis only.  The
    # selection summary makes that non-publication scale explicit; the real
    # pilot gate remains 64 opportunities.
    _require(1 <= h_bag_count <= 1_024, "I1 H_bag selection must contain 1..1024 opportunities")
    _require(0 <= h_system_count <= MAX_H_SYSTEM_SAMPLES, f"H_system sample count exceeds {MAX_H_SYSTEM_SAMPLES}")
    _require(h_system_count <= h_bag_count, "H_system samples must be a subset of H_bag opportunities")
    competitive = [row for row in rows if is_real_competitive_i1(row)]
    _require(len(competitive) >= h_bag_count, f"only {len(competitive)} real competitive I1 opportunities")
    h_bag_rows = _diverse_select(competitive, h_bag_count)
    h_system_rows = _diverse_select(h_bag_rows, h_system_count) if h_system_count else []
    targets = [_with_horizon(row, "H_bag") for row in h_bag_rows]
    targets.extend(_with_horizon(row, "H_system") for row in h_system_rows)
    targets.sort(key=lambda row: (int(row.get("event_ordinal", 0)), 0 if row["horizon"] == "H_bag" else 1, row["target_key"]))
    coverage = {
        name: sorted({row["g4irsf17_strata"][name] for row in h_bag_rows})
        for name in ("source", "time", "queue", "slack", "leg")
    }
    coverage_gate_pass = (
        len(coverage["source"]) >= 3
        and len(coverage["time"]) >= 3
        and len(coverage["queue"]) >= 2
        and len(coverage["slack"]) >= 2
        and len(coverage["leg"]) >= 2
    )
    summary = {
        "source_frame_row_count": len(rows),
        "real_competitive_i1_count": len(competitive),
        "h_bag_opportunity_count": h_bag_count,
        "pilot_scale_gate_pass": h_bag_count >= 64,
        "h_system_sample_count": h_system_count,
        "total_target_count": len(targets),
        "coverage": coverage,
        "coverage_gate_pass": coverage_gate_pass,
        "coverage_gate": {
            "min_sources": 3,
            "min_time_buckets": 3,
            "min_queue_buckets": 2,
            "min_slack_buckets": 2,
            "min_leg_types": 2,
        },
        "top2_contract": "baseline=source_ready_order[0]; treatment=source_ready_order[1]",
    }
    return targets, summary


def create_i1_plan(
    rows: Sequence[Mapping[str, Any]],
    *,
    h_bag_count: int = 128,
    h_system_count: int = 8,
) -> dict[str, Any]:
    targets, summary = select_i1_pilot_targets(
        rows,
        h_bag_count=h_bag_count,
        h_system_count=h_system_count,
    )
    return {
        "schema": SCHEMA_I1_PLAN,
        "status": (
            "READY_FOR_PILOT"
            if summary["pilot_scale_gate_pass"] and summary["coverage_gate_pass"]
            else "TARGET_COVERAGE_GAP"
            if summary["pilot_scale_gate_pass"]
            else "FIXTURE_OR_DRY_RUN_SCALE"
        ),
        "created_at_utc": _now(),
        "delta_convention": "I1_second_ready_minus_native_baseline_winner",
        "native_reuse": {
            "target_source": G15_TARGET_FRAME_PATH.as_posix(),
            "pair_binding": "g4irsf15_run_causal_target_pairs_from_records",
            "replay_semantics": "G15 exact native same-state target-pair replay",
        },
        "selection": summary,
        "targets": targets,
    }


def _target_key(row: Mapping[str, Any]) -> str:
    key = row.get("target_key")
    if key not in (None, ""):
        return str(key)
    descriptor = _pick(row, "descriptor_id", "target_address_id", "skeleton_id")
    horizon = _pick(row, "horizon", default="H_bag")
    return f"{descriptor}:{horizon}"


def _unwrap_pair(row: Mapping[str, Any]) -> dict[str, Any]:
    pair = row.get("pair")
    return dict(pair) if isinstance(pair, dict) else dict(row)


def _pairs_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, tuple) and payload:
        payload = payload[0]
    if isinstance(payload, dict) and isinstance(payload.get("pairs"), list):
        return [dict(row) for row in payload["pairs"]]
    return [_unwrap_pair(row) for row in _extract_rows(payload, label="pair payload")]


def _native_pair_executor(root: Path, binary: Path) -> Callable[[Sequence[Mapping[str, Any]]], list[dict[str, Any]]]:
    try:
        from scripts.eval import g4irsf15_causal_campaign as g15
    except ImportError as exc:  # pragma: no cover - repository always contains it
        raise CampaignError("cannot import G15 causal runner") from exc

    def execute(targets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        native_args, _, _ = g15._native_arguments(root)  # noqa: SLF001 - explicit reuse seam
        payload, _binary_identity = g15._call_exact_binary(  # noqa: SLF001
            root=root,
            binary=binary,
            function_name="g4irsf15_run_causal_target_pairs_from_records",
            arguments=[*native_args, list(targets)],
        )
        return _pairs_from_payload(payload)

    return execute


def _fixture_pair_executor(
    rows: Sequence[Mapping[str, Any]],
) -> Callable[[Sequence[Mapping[str, Any]]], list[dict[str, Any]]]:
    pairs = [_unwrap_pair(row) for row in rows]
    by_key = {_target_key(pair): pair for pair in pairs if _pick(pair, "target_key", "descriptor_id") not in (None, "")}

    def execute(targets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for target in targets:
            key = _target_key(target)
            pair = by_key.get(key)
            if pair is None:
                # A fixture may omit target_key but preserve plan order.
                index = next(
                    (i for i, candidate in enumerate(pairs) if _target_key(candidate) == key),
                    -1,
                )
                if index >= 0:
                    pair = pairs[index]
            if pair is None:
                raise CampaignError(f"fixture lacks pair {key}")
            selected.append(dict(pair))
        return selected

    return execute


def _validate_pair_alignment(
    targets: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
) -> None:
    _require(len(targets) == len(pairs), "native pair count does not match target count")
    for index, (target, pair) in enumerate(zip(targets, pairs, strict=True)):
        expected = _target_key(target)
        actual = _target_key(pair)
        if actual != expected:
            raise CampaignError(f"pair {index} identity mismatch: {actual} != {expected}")


def _metric(row: Mapping[str, Any], field: str, *, default: float = 0.0) -> float:
    aliases = {
        "completion_seconds": ("completion_seconds", "tth_seconds"),
        "source_wait_seconds": ("source_wait_seconds", "source_queue_wait_seconds"),
        "network_time_seconds": ("network_time_seconds", "network_seconds"),
        "finish_time": ("finish_time", "completed_at"),
        "deadline": ("deadline",),
    }
    value = _pick(row, *aliases.get(field, (field,)), default=default)
    if field == "network_time_seconds" and value == default and not any(name in row for name in aliases[field]):
        completion = _number(_pick(row, "completion_seconds", "tth_seconds", default=0.0), "outcome.completion", default=0.0)
        source = _number(_pick(row, "source_wait_seconds", default=0.0), "outcome.source_wait", default=0.0)
        return completion - source
    return _number(value, f"outcome.{field}", default=default)


def _outcomes_by_id(branch: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    rows = branch.get("affected_bag_outcomes")
    if not isinstance(rows, list):
        return {}
    result: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("runtime_bag_id") not in (None, ""):
            result[_integer(row["runtime_bag_id"], "outcome.runtime_bag_id")] = row
    return result


def _direct_deltas(pair: Mapping[str, Any]) -> list[dict[str, Any]]:
    baseline = pair.get("baseline")
    treatment = pair.get("treatment")
    if not isinstance(baseline, dict) or not isinstance(treatment, dict):
        return []
    left = _outcomes_by_id(baseline)
    right = _outcomes_by_id(treatment)
    direct_ids = pair.get("direct_affected_runtime_bag_ids", pair.get("affected_runtime_bag_ids", []))
    if not isinstance(direct_ids, list):
        return []
    result: list[dict[str, Any]] = []
    for value in direct_ids:
        runtime_id = _integer(value, "direct_runtime_bag_id")
        if runtime_id not in left or runtime_id not in right:
            continue
        before, after = left[runtime_id], right[runtime_id]
        completion = _metric(after, "completion_seconds") - _metric(before, "completion_seconds")
        source_wait = _metric(after, "source_wait_seconds") - _metric(before, "source_wait_seconds")
        network = _metric(after, "network_time_seconds") - _metric(before, "network_time_seconds")
        deadline_before = _metric(before, "deadline", default=-1.0)
        deadline_after = _metric(after, "deadline", default=deadline_before)
        miss_before = deadline_before >= 0.0 and _metric(before, "finish_time") > deadline_before
        miss_after = deadline_after >= 0.0 and _metric(after, "finish_time") > deadline_after
        result.append(
            {
                "runtime_bag_id": runtime_id,
                "task_id": _pick(after, "task_id", default=_pick(before, "task_id")),
                "segment_id": _pick(after, "segment_id", default=_pick(before, "segment_id")),
                "completion_delta_seconds": completion,
                "source_wait_delta_seconds": source_wait,
                "network_time_delta_seconds": network,
                "deadline_miss_delta": int(miss_after) - int(miss_before),
            }
        )
    return result


def _realized_delta(row: Mapping[str, Any]) -> float:
    direct = _pick(
        row,
        "completion_delta_seconds",
        "delta_completion_seconds",
        "finish_time_delta_seconds",
        "delta_finish_time",
    )
    if direct not in (None, ""):
        return _number(direct, "realized.completion_delta")
    baseline = row.get("baseline")
    treatment = row.get("treatment")
    if isinstance(baseline, dict) and isinstance(treatment, dict):
        return _metric(treatment, "completion_seconds") - _metric(baseline, "completion_seconds")
    raise CampaignError("realized outcome row lacks a completion delta")


def cvar95_harm(values: Sequence[float]) -> float:
    """Mean of the worst ceil(5%) non-negative losses, including zero fill."""

    if not values:
        return 0.0
    losses = sorted((max(0.0, float(value)) for value in values), reverse=True)
    tail_count = max(1, int(math.ceil(0.05 * len(losses))))
    return sum(losses[:tail_count]) / tail_count


_SAFETY_COUNTERS = (
    "unsafe_entry_count",
    "reservation_conflict_count",
    "runtime_full_astar_call_count",
    "runtime_global_scan_count",
    "runtime_future_route_read_count",
    "runtime_future_schedule_read_count",
    "teacher_input_count",
    "two_step_reservation_count",
    "unresolved_deadlock_count",
)


def _pair_gate(pair: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if pair.get("action_changed") is not True:
        blockers.append("ACTION_NOT_CHANGED_OR_FALSE_POSITIVE")
    if pair.get("same_state_start") is not True:
        blockers.append("NOT_SAME_STATE_START")
    if pair.get("horizon_complete") is not True or pair.get("pair_complete") is not True:
        blockers.append("PAIR_OR_HORIZON_INCOMPLETE")
    if pair.get("hard_gate_pass") is False:
        blockers.append("NATIVE_HARD_GATE_FAILED")
    for branch_name in ("baseline", "treatment"):
        branch = pair.get(branch_name)
        if not isinstance(branch, dict):
            blockers.append(f"{branch_name.upper()}_EVIDENCE_MISSING")
            continue
        invariants = branch.get("invariants")
        if not isinstance(invariants, dict):
            blockers.append(f"{branch_name.upper()}_INVARIANTS_MISSING")
            continue
        if invariants.get("live_safety_pass") is False:
            blockers.append(f"{branch_name.upper()}_LIVE_SAFETY_FAILED")
        for counter in _SAFETY_COUNTERS:
            if _integer(invariants.get(counter, 0), f"{branch_name}.{counter}", default=0) != 0:
                blockers.append(f"{branch_name.upper()}_{counter.upper()}")
        if invariants.get("event_limit_reached") is True:
            blockers.append(f"{branch_name.upper()}_EVENT_LIMIT")
        if invariants.get("time_limit_reached") is True:
            blockers.append(f"{branch_name.upper()}_TIME_LIMIT")
    return not blockers, blockers


def _raw_metric_delta_seconds(
    baseline: Mapping[str, Any],
    treatment: Mapping[str, Any],
    field: str,
) -> float | None:
    left = baseline.get("raw_bag_cohort_metrics")
    right = treatment.get("raw_bag_cohort_metrics")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    if field not in left or field not in right:
        return None
    delta = _number(right[field], f"treatment.raw.{field}") - _number(left[field], f"baseline.raw.{field}")
    return 60.0 * delta if field.endswith("_minutes") else delta


def _optional_delta(
    baseline: Mapping[str, Any],
    treatment: Mapping[str, Any],
    aliases: Sequence[str],
) -> float | None:
    for name in aliases:
        if name in baseline and name in treatment:
            return _number(treatment[name], f"treatment.{name}") - _number(baseline[name], f"baseline.{name}")
    return None


def _observation_fields(pair: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    sources: list[Mapping[str, Any]] = [target]
    for container in (target, pair, pair.get("resolved_execution_descriptor", {})):
        if not isinstance(container, dict):
            continue
        for name in ("runtime_local_features", "local_observation", "observation", "features"):
            value = container.get(name)
            if isinstance(value, dict):
                sources.append(value)
    for source in sources:
        for name, value in source.items():
            if isinstance(value, bool):
                result.setdefault(name, float(value))
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                result.setdefault(name, float(value))
    return result


def _validated_i1_observation_pair(value: Any) -> dict[str, Any]:
    """Validate and normalize the native pre-action local observation pair.

    The pair is accepted only from the native causal result.  Trace identities
    remain on the outer descriptor/pair and are deliberately absent here.
    """

    if not isinstance(value, Mapping):
        raise CampaignError("observation_pair: expected native object")
    expected_fields = {
        "schema",
        "feature_names",
        "pairwise_feature_names",
        "candidate_observations",
        "canonical_candidate_observations",
        "baseline_observation",
        "treatment_observation",
        "baseline_candidate_index",
        "treatment_candidate_index",
        "pairwise_features",
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "runtime_full_astar_call_count",
        "identity_fields_are_trace_only",
    }
    missing = sorted(expected_fields.difference(value))
    extra = sorted(set(value).difference(expected_fields))
    if missing:
        raise CampaignError(
            "observation_pair: missing native fields " + ",".join(missing)
        )
    if extra:
        raise CampaignError(
            "observation_pair: unexpected fields " + ",".join(extra)
        )
    if value["schema"] != "czr005.g4irsf17.i1_pre_action_observation_pair.v1":
        raise CampaignError("observation_pair: unsupported schema")

    def names(raw: Any, expected: Sequence[str], label: str) -> list[str]:
        if (
            not isinstance(raw, Sequence)
            or isinstance(raw, (str, bytes, bytearray))
            or any(not isinstance(item, str) for item in raw)
        ):
            raise CampaignError(f"observation_pair.{label}: expected name list")
        result = list(raw)
        if result != list(expected):
            raise CampaignError(f"observation_pair.{label}: feature order mismatch")
        return result

    def finite_number(raw: Any, label: str) -> float:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise CampaignError(f"observation_pair.{label}: expected finite number")
        result = float(raw)
        if not math.isfinite(result):
            raise CampaignError(f"observation_pair.{label}: expected finite number")
        return result

    def vector(raw: Any, expected_size: int, label: str) -> list[float]:
        if (
            not isinstance(raw, Sequence)
            or isinstance(raw, (str, bytes, bytearray))
            or len(raw) != expected_size
        ):
            raise CampaignError(
                f"observation_pair.{label}: expected {expected_size}-value vector"
            )
        return [finite_number(item, f"{label}[{index}]") for index, item in enumerate(raw)]

    def observation(raw: Any, label: str) -> dict[str, float]:
        if not isinstance(raw, Mapping):
            raise CampaignError(f"observation_pair.{label}: expected feature object")
        missing_names = [name for name in CANONICAL_OBSERVATION_FEATURES if name not in raw]
        extra_names = [name for name in raw if name not in CANONICAL_OBSERVATION_FEATURES]
        if missing_names or extra_names:
            detail = "missing=" + ",".join(missing_names)
            if extra_names:
                detail += ";extra=" + ",".join(map(str, extra_names))
            raise CampaignError(f"observation_pair.{label}: {detail}")
        result = {
            name: finite_number(raw[name], f"{label}.{name}")
            for name in CANONICAL_OBSERVATION_FEATURES
        }
        try:
            canonical_feature_vector(result)
        except (TypeError, ValueError) as exc:
            raise CampaignError(f"observation_pair.{label}: {exc}") from exc
        return result

    feature_names = names(
        value["feature_names"],
        CANONICAL_OBSERVATION_FEATURES,
        "feature_names",
    )
    pairwise_names = names(
        value["pairwise_feature_names"],
        PAIRWISE_FEATURES,
        "pairwise_feature_names",
    )
    raw_candidates = value["candidate_observations"]
    if (
        not isinstance(raw_candidates, Sequence)
        or isinstance(raw_candidates, (str, bytes, bytearray))
        or len(raw_candidates) != 2
    ):
        raise CampaignError(
            "observation_pair.candidate_observations: expected exactly two candidates"
        )
    candidates = [
        observation(raw, f"candidate_observations[{index}]")
        for index, raw in enumerate(raw_candidates)
    ]
    baseline = observation(value["baseline_observation"], "baseline_observation")
    treatment = observation(value["treatment_observation"], "treatment_observation")
    if baseline != candidates[0] or treatment != candidates[1]:
        raise CampaignError(
            "observation_pair: baseline/treatment mappings disagree with candidate order"
        )

    raw_canonical = value["canonical_candidate_observations"]
    if (
        not isinstance(raw_canonical, Sequence)
        or isinstance(raw_canonical, (str, bytes, bytearray))
        or len(raw_canonical) != 2
    ):
        raise CampaignError(
            "observation_pair.canonical_candidate_observations: expected 2x39 matrix"
        )
    canonical = [
        vector(raw, len(CANONICAL_OBSERVATION_FEATURES), f"canonical_candidate_observations[{index}]")
        for index, raw in enumerate(raw_canonical)
    ]
    for index, (actual, mapped) in enumerate(zip(canonical, candidates, strict=True)):
        expected = [mapped[name] for name in CANONICAL_OBSERVATION_FEATURES]
        if any(
            not math.isclose(left, right, rel_tol=0.0, abs_tol=EPSILON)
            for left, right in zip(actual, expected, strict=True)
        ):
            raise CampaignError(
                "observation_pair.canonical_candidate_observations"
                f"[{index}]: vector/mapping mismatch"
            )

    for name in CONTEXT_FEATURES:
        if not math.isclose(
            baseline[name], treatment[name], rel_tol=0.0, abs_tol=EPSILON
        ):
            raise CampaignError(
                f"observation_pair: candidate context is not shared for {name}"
            )
    expected_pairwise = pairwise_feature_vector(
        {name: treatment[name] for name in CANDIDATE_FEATURES},
        {name: baseline[name] for name in CANDIDATE_FEATURES},
        {name: baseline[name] for name in CONTEXT_FEATURES},
    ).tolist()
    pairwise = vector(value["pairwise_features"], len(PAIRWISE_FEATURES), "pairwise_features")
    if any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=EPSILON)
        for left, right in zip(pairwise, expected_pairwise, strict=True)
    ):
        raise CampaignError("observation_pair.pairwise_features: treatment-baseline mismatch")

    for label, expected in (
        ("baseline_candidate_index", 0),
        ("treatment_candidate_index", 1),
    ):
        raw = value[label]
        if isinstance(raw, bool) or not isinstance(raw, int) or raw != expected:
            raise CampaignError(f"observation_pair.{label}: expected {expected}")
    for label in (
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "runtime_full_astar_call_count",
    ):
        raw = value[label]
        if isinstance(raw, bool) or not isinstance(raw, int) or raw != 0:
            raise CampaignError(f"observation_pair.{label}: expected zero")
    if value["identity_fields_are_trace_only"] is not True:
        raise CampaignError(
            "observation_pair.identity_fields_are_trace_only: expected true"
        )

    return {
        "schema": value["schema"],
        "feature_names": feature_names,
        "pairwise_feature_names": pairwise_names,
        "candidate_observations": candidates,
        "canonical_candidate_observations": canonical,
        "baseline_observation": baseline,
        "treatment_observation": treatment,
        "baseline_candidate_index": 0,
        "treatment_candidate_index": 1,
        "pairwise_features": pairwise,
        "runtime_global_scan_count": 0,
        "runtime_future_route_read_count": 0,
        "runtime_future_schedule_read_count": 0,
        "runtime_full_astar_call_count": 0,
        "identity_fields_are_trace_only": True,
    }


def _analyse_pair(pair: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    horizon = str(_pick(pair, "horizon", default=_pick(target, "horizon", default="H_bag")))
    gate_pass, blockers = _pair_gate(pair)
    direct = _direct_deltas(pair)
    target_runtime_id = _integer(_pick(target, "runtime_bag_id", default=-1), "target.runtime_bag_id", default=-1)
    peer_runtime_id = _integer(_pick(target, "peer_runtime_bag_id", default=-1), "target.peer_runtime_bag_id", default=-1)
    by_id = {row["runtime_bag_id"]: row for row in direct}
    own = by_id.get(target_runtime_id)
    peer = by_id.get(peer_runtime_id)
    direct_sum = sum(float(row["completion_delta_seconds"]) for row in direct)
    direct_source = sum(float(row["source_wait_delta_seconds"]) for row in direct)
    direct_network = sum(float(row["network_time_delta_seconds"]) for row in direct)
    deadline_delta = sum(int(row["deadline_miss_delta"]) for row in direct)

    direct_ids = set(by_id)
    realized = pair.get("realized_outcome_deltas")
    other_deltas: list[float] = []
    if horizon == "H_system" and isinstance(realized, list):
        for row in realized:
            if not isinstance(row, dict):
                continue
            runtime_id = _integer(_pick(row, "runtime_bag_id", default=-1), "realized.runtime_bag_id", default=-1)
            if runtime_id not in direct_ids:
                other_deltas.append(_realized_delta(row))
    externality_observed = horizon == "H_system" and isinstance(realized, list)
    other_sum = sum(other_deltas) if externality_observed else None
    other_max = max((max(0.0, value) for value in other_deltas), default=0.0) if externality_observed else None
    other_cvar = cvar95_harm(other_deltas) if externality_observed else None

    baseline = pair.get("baseline") if isinstance(pair.get("baseline"), dict) else {}
    treatment = pair.get("treatment") if isinstance(pair.get("treatment"), dict) else {}
    raw_tth_delta = _raw_metric_delta_seconds(baseline, treatment, "original_entry_mean_minutes")
    raw_source_delta = _raw_metric_delta_seconds(baseline, treatment, "source_wait_mean_minutes")
    raw_network_delta = _raw_metric_delta_seconds(baseline, treatment, "network_time_mean_minutes")
    p95_delta = _raw_metric_delta_seconds(baseline, treatment, "original_entry_p95_seconds")
    p99_delta = _raw_metric_delta_seconds(baseline, treatment, "original_entry_p99_seconds")
    makespan_delta = _optional_delta(
        baseline,
        treatment,
        ("system_makespan_seconds", "makespan_seconds", "finish_time_max_seconds"),
    )
    drain_delta = _optional_delta(
        baseline,
        treatment,
        ("local_queue_drain_time_seconds", "queue_drain_time_seconds", "drain_time_seconds"),
    )

    external_cost = float(other_sum or 0.0)
    tail_penalty = float(other_cvar or 0.0)
    deadline_penalty = DEADLINE_MISS_PENALTY_SECONDS * max(0, deadline_delta)
    system_cost = direct_sum + external_cost + tail_penalty + deadline_penalty
    utility = -system_cost
    if not gate_pass or not direct:
        label = "EXCLUDED"
    elif system_cost < -EPSILON:
        label = "BENEFICIAL"
    elif system_cost > EPSILON:
        label = "HARMFUL"
    else:
        label = "NEUTRAL"
    strata = target.get("g4irsf17_strata")
    strata = strata if isinstance(strata, dict) else _target_strata(target)
    result: dict[str, Any] = {
        "target_key": _target_key(target),
        "descriptor_id": _pick(target, "descriptor_id", "target_address_id", "skeleton_id"),
        "horizon": horizon,
        "event_ordinal": _pick(target, "event_ordinal", default=_pick(pair, "event_ordinal")),
        "source": strata["source"],
        "time_bucket": strata["time"],
        "queue_bucket": strata["queue"],
        "slack_bucket": strata["slack"],
        "leg_type": strata["leg"],
        "runtime_bag_id": target_runtime_id,
        "peer_runtime_bag_id": peer_runtime_id,
        "action_changed": pair.get("action_changed") is True,
        "eligible_causal_effect": gate_pass and bool(direct),
        "hard_gate_pass": gate_pass,
        "hard_gate_blockers": blockers,
        "effect_label": label,
        "utility_scope": "SYSTEM_REALIZED_AFFECTED" if externality_observed else "DIRECT_ONLY_H_BAG",
        "own_bag_tth_delta_seconds": own["completion_delta_seconds"] if own else None,
        "peer_bag_tth_delta_seconds": peer["completion_delta_seconds"] if peer else None,
        "direct_bag_count": len(direct),
        "direct_bag_tth_sum_delta_seconds": direct_sum if direct else None,
        "direct_bag_tth_mean_delta_seconds": direct_sum / len(direct) if direct else None,
        "direct_source_wait_sum_delta_seconds": direct_source if direct else None,
        "direct_network_time_sum_delta_seconds": direct_network if direct else None,
        "other_bag_count": len(other_deltas) if externality_observed else None,
        "other_bag_sum_delta_seconds": other_sum,
        "other_bag_max_harm_seconds": other_max,
        "other_bag_cvar95_harm_seconds": other_cvar,
        "deadline_miss_delta": deadline_delta if direct else None,
        "raw_bag_mean_tth_delta_seconds": raw_tth_delta,
        "raw_bag_mean_source_wait_delta_seconds": raw_source_delta,
        "raw_bag_mean_network_time_delta_seconds": raw_network_delta,
        "raw_bag_p95_tth_delta_seconds": p95_delta,
        "raw_bag_p99_tth_delta_seconds": p99_delta,
        "local_queue_drain_time_delta_seconds": drain_delta,
        "system_makespan_delta_seconds": makespan_delta,
        "system_cost_delta_seconds": system_cost if direct else None,
        "system_utility": utility if direct else None,
    }
    for name, value in _observation_fields(pair, target).items():
        result.setdefault(name, value)
    native_observation_pair = pair.get("observation_pair")
    if native_observation_pair is not None:
        result["observation_pair"] = _validated_i1_observation_pair(
            native_observation_pair
        )
    return result


def _assign_diagnostic_splits(effects: list[dict[str, Any]]) -> None:
    eligible = sorted(
        (row for row in effects if row["horizon"] == "H_bag" and row["eligible_causal_effect"]),
        key=lambda row: (int(row.get("event_ordinal") or 0), str(row["descriptor_id"])),
    )
    # A diagnostic 70/15/15 blocked-order split.  Formal model code can replace
    # this with source/time/task-group held-out splits; no ID is a feature.
    for index, row in enumerate(eligible):
        slot = index % 20
        row["diagnostic_split"] = "train" if slot < 14 else "calibration" if slot < 17 else "validation"
    for row in effects:
        row.setdefault("diagnostic_split", "not_trainable")


def analyse_i1_pairs(
    pair_records: Sequence[Mapping[str, Any]],
    *,
    targets: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    target_by_key = {_target_key(row): dict(row) for row in targets}
    effects: list[dict[str, Any]] = []
    for record in pair_records:
        pair = _unwrap_pair(record)
        target_value = record.get("target") if isinstance(record.get("target"), dict) else None
        target = dict(target_value) if target_value is not None else target_by_key.get(_target_key(pair), dict(pair))
        effects.append(_analyse_pair(pair, target))
    _assign_diagnostic_splits(effects)
    h_bag = [row for row in effects if row["horizon"] == "H_bag"]
    eligible = [row for row in h_bag if row["eligible_causal_effect"]]
    beneficial = [row for row in eligible if row["effect_label"] == "BENEFICIAL"]
    harmful = [row for row in eligible if row["effect_label"] == "HARMFUL"]
    split_counts = Counter(str(row["diagnostic_split"]) for row in beneficial)
    sources = {str(row["source"]) for row in beneficial}
    times = {str(row["time_bucket"]) for row in beneficial}
    legs = {str(row["leg_type"]) for row in beneficial}
    attempted_sources = {str(row["source"]) for row in h_bag}
    attempted_times = {str(row["time_bucket"]) for row in h_bag}
    attempted_legs = {str(row["leg_type"]) for row in h_bag}
    attempted_coverage_ready = (
        len(attempted_sources) >= MIN_BENEFICIAL_SOURCES
        and len(attempted_times) >= MIN_BENEFICIAL_TIME_BUCKETS
        and len(attempted_legs) >= MIN_BENEFICIAL_LEG_TYPES
    )
    support_ready = (
        all(split_counts[name] >= minimum for name, minimum in BENEFICIAL_SUPPORT.items())
        and len(sources) >= MIN_BENEFICIAL_SOURCES
        and len(times) >= MIN_BENEFICIAL_TIME_BUCKETS
        and len(legs) >= MIN_BENEFICIAL_LEG_TYPES
    )
    attempted = len(h_bag)
    changed = sum(row["action_changed"] for row in h_bag)
    if support_ready:
        pivot = "I1_SUPPORT_READY_FOR_STATE_AND_MODEL_AUDIT"
        next_action = "Run state aliasing, rule/linear/tiny-MLP comparisons, and conservative authorization."
    elif attempted >= 512 and not attempted_coverage_ready:
        pivot = "PIVOT_TO_G2_I1_FRAME_COVERAGE_NO_GO"
        next_action = (
            "The current real I1 frame cannot satisfy the source/leg coverage gate; "
            "move the primary causal budget to bounded destination merge/service-token G2."
        )
    elif changed >= 512:
        pivot = "PIVOT_TO_G2_I1_SUPPORT_NO_GO"
        next_action = "Move the primary causal budget to bounded destination merge/service-token G2."
    elif attempted >= 512:
        pivot = "EXPAND_COMPETITIVE_I1_TO_1024_FOR_LIVE_SUPPORT"
        next_action = "Use the optional 1,024-address cap to reach 512 live changed pairs."
    elif attempted >= 128 and changed == 0:
        pivot = "REFRESH_REAL_COMPETITIVE_I1_TARGET_SCAN"
        next_action = "The frame did not resolve to live competition; refresh the minimal target scan before a scientific no-go."
    elif attempted >= 128:
        pivot = "EXPAND_COMPETITIVE_I1_TO_512"
        next_action = "Sample targeted under-covered I1 strata up to 512 competitive pairs."
    else:
        pivot = "EXPAND_COMPETITIVE_I1_TO_128"
        next_action = "Complete the 64-128 opportunity pilot before judging support."
    h_system = [row for row in effects if row["horizon"] == "H_system"]
    summary = {
        "attempted_h_bag_opportunity_count": attempted,
        "action_changed_h_bag_count": changed,
        "eligible_h_bag_effect_count": len(eligible),
        "beneficial_h_bag_count": len(beneficial),
        "harmful_h_bag_count": len(harmful),
        "neutral_h_bag_count": sum(row["effect_label"] == "NEUTRAL" for row in eligible),
        "excluded_h_bag_count": attempted - len(eligible),
        "beneficial_split_counts": {name: split_counts[name] for name in BENEFICIAL_SUPPORT},
        "beneficial_source_count": len(sources),
        "beneficial_time_bucket_count": len(times),
        "beneficial_leg_type_count": len(legs),
        "attempted_source_count": len(attempted_sources),
        "attempted_time_bucket_count": len(attempted_times),
        "attempted_leg_type_count": len(attempted_legs),
        "attempted_coverage_ready": attempted_coverage_ready,
        "support_ready": support_ready,
        "h_system_attempt_count": len(h_system),
        "h_system_eligible_count": sum(row["eligible_causal_effect"] for row in h_system),
        "h_system_harmful_count": sum(row["effect_label"] == "HARMFUL" for row in h_system),
        "h_system_max_other_bag_cvar95_harm_seconds": max(
            (float(row["other_bag_cvar95_harm_seconds"]) for row in h_system if row["other_bag_cvar95_harm_seconds"] is not None),
            default=None,
        ),
        "pivot_decision": pivot,
        "next_action": next_action,
    }
    return {"effects": effects, "summary": summary}


def _i1_support_report(summary: Mapping[str, Any]) -> str:
    split = summary["beneficial_split_counts"]
    return f"""# G4IRSF17 I1 causal support

## Decision

**`{summary['pivot_decision']}`** — {summary['next_action']}

The pilot attempted **{summary['attempted_h_bag_opportunity_count']}** real-address H_bag opportunities; **{summary['action_changed_h_bag_count']}** changed the native winner and **{summary['eligible_h_bag_effect_count']}** passed the same-state and hard-safety gates.  Eligible effects were {summary['beneficial_h_bag_count']} beneficial, {summary['harmful_h_bag_count']} harmful, and {summary['neutral_h_bag_count']} neutral.

## Exact effect convention

Every delta is `I1 second-ready treatment - native F2/Q0 baseline winner`; negative TTH, source-wait, network, drain, makespan, P95, and P99 deltas are improvements.  H_bag utility is `-(sum direct TTH delta + deadline penalty)` and is explicitly direct-only.  H_system utility additionally includes realized other-bag sum and CVaR95 tail harm.  Each new deadline miss adds a {DEADLINE_MISS_PENALTY_SECONDS:.0f}-second risk penalty.

Other-bag externality excludes both reordered runtime bags.  `CVaR95 harm` is the mean of the worst `max(1, ceil(0.05*n))` values after replacing improvements by zero; it is unavailable, not zero, at H_bag.

## Support gate

Beneficial diagnostic split counts are train/calibration/validation = **{split['train']}/{split['calibration']}/{split['validation']}**, against {BENEFICIAL_SUPPORT['train']}/{BENEFICIAL_SUPPORT['calibration']}/{BENEFICIAL_SUPPORT['validation']}.  Beneficial coverage spans **{summary['beneficial_source_count']}** sources, **{summary['beneficial_time_bucket_count']}** time buckets, and **{summary['beneficial_leg_type_count']}** leg types, against {MIN_BENEFICIAL_SOURCES}/{MIN_BENEFICIAL_TIME_BUCKETS}/{MIN_BENEFICIAL_LEG_TYPES}.  Support ready: **{summary['support_ready']}**.

## Pivot gates

* sufficient 32/8/8 beneficial support plus 3 sources, 3 time buckets, and 2 leg types -> state/model audit;
* incomplete support after 128 attempted real addresses -> target 512 addresses;
* a structurally under-covered frame at 512 addresses -> frame-scoped I1 no-go and G2 pivot;
* adequate strata but fewer than 512 live changes at 512 addresses -> optional 1,024-address cap;
* incomplete support after 512 live changed pairs -> I1 support no-go and G2 pivot;
* 128 addresses with zero live action changes -> refresh competitive target telemetry, not a scientific no-go.

H_system was deliberately bounded to **{summary['h_system_attempt_count']}** sampled opportunities (hard maximum {MAX_H_SYSTEM_SAMPLES}); {summary['h_system_harmful_count']} were harmful and the maximum observed other-bag CVaR95 harm was **{summary['h_system_max_other_bag_cvar95_harm_seconds']}** seconds.
"""


def write_i1_analysis(
    *,
    root: Path,
    pair_records: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    result = analyse_i1_pairs(pair_records, targets=targets)
    _write_csv(root / I1_EFFECTS_PATH, result["effects"])
    _atomic_write(
        root / I1_SUPPORT_REPORT_PATH,
        _i1_support_report(result["summary"]).encode("utf-8"),
    )
    return result


def _compact_pair_for_publication(pair: Mapping[str, Any]) -> dict[str, Any]:
    """Omit dense cohort rows already represented by realized deltas and aggregates."""

    compact = dict(pair)
    difference_sidecar = compact.get("cohort_difference_sidecar")
    if isinstance(difference_sidecar, dict) and isinstance(difference_sidecar.get("rows"), list):
        metadata = dict(difference_sidecar)
        metadata.pop("rows")
        metadata["dense_rows_omitted"] = True
        compact["cohort_difference_sidecar"] = metadata
        compact["cohort_difference_sidecar_serialized"] = False
    for branch_name in ("baseline", "treatment"):
        branch = compact.get(branch_name)
        if not isinstance(branch, dict):
            continue
        branch_copy = dict(branch)
        sidecar = branch_copy.get("raw_bag_sufficient_statistics_sidecar")
        if isinstance(sidecar, dict) and isinstance(sidecar.get("rows"), list):
            metadata = dict(sidecar)
            metadata.pop("rows")
            metadata["dense_rows_omitted"] = True
            branch_copy["raw_bag_sufficient_statistics_sidecar"] = metadata
            branch_copy["raw_bag_sufficient_statistics_serialized"] = False
            compact[branch_name] = branch_copy
    return compact


def execute_i1_pilot(
    *,
    root: Path,
    plan: Mapping[str, Any],
    binary: Path | None = None,
    pair_executor: Callable[[Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]] | None = None,
    chunk_size: int = 16,
    chunk_indices: set[int] | None = None,
    journal: CampaignJournal | None = None,
    force: bool = False,
) -> dict[str, Any]:
    _require(plan.get("schema") == SCHEMA_I1_PLAN, "I1 plan schema mismatch")
    targets = plan.get("targets")
    _require(isinstance(targets, list) and targets, "I1 plan has no targets")
    _require(chunk_size > 0, "chunk size must be positive")
    if pair_executor is None:
        _require(binary is not None, "native execution requires --binary or a fixture executor")
        pair_executor = _native_pair_executor(root, binary.resolve())
    runstate = root / I1_RUNSTATE_ROOT
    runstate.mkdir(parents=True, exist_ok=True)
    chunks = [targets[index : index + chunk_size] for index in range(0, len(targets), chunk_size)]
    if chunk_indices is not None:
        invalid = sorted(index for index in chunk_indices if index < 0 or index >= len(chunks))
        _require(not invalid, f"I1 chunk indices out of range: {invalid}")
        _require(bool(chunk_indices), "I1 selected chunk set cannot be empty")
    cached_pairs: dict[str, dict[str, Any]] = {}
    dataset_path = root / I1_DATASET_PATH
    if dataset_path.is_file() and not force:
        for record in read_rows(dataset_path):
            target = record.get("target")
            pair = record.get("pair")
            if (
                record.get("schema") != SCHEMA_I1_RECORD
                or not isinstance(target, dict)
                or not isinstance(pair, dict)
            ):
                continue
            key = _target_key(target)
            if _target_key(pair) == key:
                cached_pairs[key] = dict(pair)
    all_records: list[dict[str, Any]] = []
    reused = 0
    reused_pairs = 0
    executed_pairs = 0
    completed_chunk_indices: list[int] = []
    for chunk_index, chunk_targets in enumerate(chunks):
        if chunk_indices is not None and chunk_index not in chunk_indices:
            continue
        checkpoint = runstate / f"chunk-{chunk_index:05d}.json.zst"
        chunk_value: dict[str, Any] | None = None
        if checkpoint.is_file() and not force:
            decoded = json.loads(_decode_zst(checkpoint))
            if (
                decoded.get("schema") == SCHEMA_I1_CHUNK
                and decoded.get("status") == "COMPLETE"
                and decoded.get("target_keys") == [_target_key(row) for row in chunk_targets]
            ):
                chunk_value = decoded
                reused += 1
        if chunk_value is None:
            pairs_by_key: dict[str, dict[str, Any]] = {}
            missing_targets: list[Mapping[str, Any]] = []
            for target in chunk_targets:
                key = _target_key(target)
                pair = cached_pairs.get(key)
                if pair is None:
                    missing_targets.append(target)
                else:
                    pairs_by_key[key] = dict(pair)
                    reused_pairs += 1
            if missing_targets:
                executed = [dict(row) for row in pair_executor(missing_targets)]
                _validate_pair_alignment(missing_targets, executed)
                executed_pairs += len(executed)
                pairs_by_key.update((_target_key(pair), pair) for pair in executed)
            pairs = [pairs_by_key[_target_key(target)] for target in chunk_targets]
            _validate_pair_alignment(chunk_targets, pairs)
            chunk_value = {
                "schema": SCHEMA_I1_CHUNK,
                "status": "COMPLETE",
                "completed_at_utc": _now(),
                "chunk_index": chunk_index,
                "target_keys": [_target_key(row) for row in chunk_targets],
                "pairs": pairs,
            }
            _write_json_zst(checkpoint, chunk_value)
        pairs = chunk_value.get("pairs")
        _require(isinstance(pairs, list), f"chunk {chunk_index} lacks pairs")
        _validate_pair_alignment(chunk_targets, pairs)
        completed_chunk_indices.append(chunk_index)
        all_records.extend(
            {
                "schema": SCHEMA_I1_RECORD,
                "target": dict(target),
                "pair": dict(pair),
            }
            for target, pair in zip(chunk_targets, pairs, strict=True)
        )
        if journal is not None:
            journal.checkpoint(
                "i1_paired_execution",
                {
                    "completed_chunks": chunk_index + 1,
                    "total_chunks": len(chunks),
                    "completed_pairs": len(all_records),
                    "target_pairs": len(targets),
                },
            )
    if chunk_indices is not None:
        return {
            "records": all_records,
            "analysis": None,
            "summary": {
                "status": "SELECTED_CHUNKS_COMPLETE",
                "completed_chunk_indices": completed_chunk_indices,
                "completed_pair_count": len(all_records),
                "total_chunk_count": len(chunks),
                "reused_chunk_count": reused,
                "reused_pair_count": reused_pairs,
                "executed_pair_count": executed_pairs,
            },
        }
    publication_records = [
        {**record, "pair": _compact_pair_for_publication(record["pair"])}
        for record in all_records
    ]
    _write_jsonl_zst(root / I1_DATASET_PATH, publication_records)
    analysis = write_i1_analysis(root=root, pair_records=all_records, targets=targets)
    result = {
        "record_count": len(all_records),
        "chunk_count": len(chunks),
        "reused_chunk_count": reused,
        "reused_pair_count": reused_pairs,
        "executed_pair_count": executed_pairs,
        **analysis["summary"],
    }
    if journal is not None:
        journal.complete(
            "i1_paired_execution",
            outputs=(root / I1_DATASET_PATH, root / I1_EFFECTS_PATH, root / I1_SUPPORT_REPORT_PATH),
            summary=result,
            decision=analysis["summary"]["pivot_decision"],
            next_action=analysis["summary"]["next_action"],
        )
    return {"records": all_records, "analysis": analysis, "summary": result}


def _import_g17_package() -> Any | None:
    try:
        return importlib.import_module("czr005.g4irsf17")
    except ImportError:
        return None


def _call_supported(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(function)
    accepts_arbitrary_keywords = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    accepted = kwargs if accepts_arbitrary_keywords else {
        name: value for name, value in kwargs.items() if name in signature.parameters
    }
    return function(*args, **accepted)


def call_state_aliasing_hooks(
    rows: Sequence[Mapping[str, Any]],
    *,
    package: Any | None = None,
) -> dict[str, Any]:
    prepared_rows: list[dict[str, Any]] = []
    for row in rows:
        horizon = row.get("horizon")
        if horizon not in (None, "", "H_bag"):
            continue
        eligible = row.get("eligible_causal_effect")
        if eligible is not None and not _boolean(eligible, default=False):
            continue
        prepared = dict(row)
        observation_pair = prepared.get("observation_pair")
        if isinstance(observation_pair, Mapping):
            treatment = observation_pair.get("treatment_observation")
            if isinstance(treatment, Mapping):
                prepared["features"] = dict(treatment)
        prepared_rows.append(prepared)
    package = package if package is not None else _import_g17_package()
    if package is None:
        return {
            "status": "PACKAGE_HOOK_UNAVAILABLE",
            "audit": None,
            "feature_ablation": [],
            "input_row_count": len(rows),
            "eligible_feature_row_count": len(prepared_rows),
        }
    function = getattr(package, "run_state_aliasing_audit", None)
    if not callable(function):
        return {
            "status": "ALIASING_HOOK_UNAVAILABLE",
            "audit": None,
            "feature_ablation": [],
            "input_row_count": len(rows),
            "eligible_feature_row_count": len(prepared_rows),
        }
    _require(bool(prepared_rows), "state aliasing has no eligible causal feature rows")
    def feature_available(row: Mapping[str, Any], name: str) -> bool:
        nested = row.get("features")
        return name in row or (isinstance(nested, Mapping) and name in nested)

    kwargs: dict[str, Any] = {"outcome_key": "system_utility"}
    legacy_names = tuple(getattr(package, "LEGACY_29_FEATURES", ()))
    augmented_names = tuple(getattr(package, "AUGMENTED_WITH_LEGACY_FEATURES", ()))
    canonical_names = tuple(getattr(package, "CANONICAL_OBSERVATION_FEATURES", ()))
    legacy_available = bool(legacy_names) and all(
        all(feature_available(row, name) for name in legacy_names)
        for row in prepared_rows
    )
    canonical_available = bool(canonical_names) and all(
        all(feature_available(row, name) for name in canonical_names)
        for row in prepared_rows
    )
    comparison_scope = "EXACT_LEGACY_29_VS_AUGMENTED"
    status = "COMPLETE"
    ablation_kwargs: dict[str, Any] = {"outcome_key": "system_utility"}
    if legacy_available and augmented_names:
        kwargs["legacy_feature_names"] = legacy_names
        kwargs["augmented_feature_names"] = augmented_names
    elif canonical_available:
        static_local_baseline = tuple(CANDIDATE_FEATURES) + (
            "source_queue_length",
            "source_queue_capacity",
            "source_queue_utilization",
            "first_edge_credit_slack_seconds",
            "target_queue_length",
            "target_queue_capacity",
            "target_queue_utilization",
            "target_scheduled_incoming",
        )
        kwargs["legacy_feature_names"] = static_local_baseline
        kwargs["augmented_feature_names"] = canonical_names
        ablation_kwargs["feature_names"] = canonical_names
        comparison_scope = "CANONICAL_STATIC_LOCAL_VS_FULL_39_ABLATION"
        status = "CANONICAL_ABLATION_COMPLETE_LEGACY_29_UNAVAILABLE"
    else:
        if legacy_names:
            kwargs["legacy_feature_names"] = legacy_names
        if augmented_names:
            kwargs["augmented_feature_names"] = augmented_names
    audit = _call_supported(function, prepared_rows, **kwargs)
    ablation_function = getattr(package, "feature_ablation", None)
    ablation = (
        _call_supported(ablation_function, prepared_rows, **ablation_kwargs)
        if callable(ablation_function)
        else []
    )
    return {
        "status": status,
        "comparison_scope": comparison_scope,
        "legacy_29_snapshot_available": legacy_available,
        "audit": audit,
        "feature_ablation": list(ablation or []),
        "input_row_count": len(rows),
        "eligible_feature_row_count": len(prepared_rows),
        "causal_scope": "H_bag",
    }


def write_state_aliasing_report(
    *,
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    package: Any | None = None,
) -> dict[str, Any]:
    result = call_state_aliasing_hooks(rows, package=package)
    _write_csv(root / FEATURE_ABLATION_PATH, result["feature_ablation"])
    audit_json = json.dumps(result.get("audit"), ensure_ascii=False, sort_keys=True, indent=2)
    report = f"""# G4IRSF17 state aliasing audit

Status: **`{result['status']}`**

Input effect rows: **{result.get('input_row_count', len(rows))}**; eligible native causal feature rows: **{result.get('eligible_feature_row_count', len(rows))}**.

Causal scope: **`{result.get('causal_scope', 'H_bag')}`**. H_system rows use a different externality utility and are not mixed into the H_bag nearest-neighbor labels.

Comparison scope: **`{result.get('comparison_scope', 'UNAVAILABLE')}`**. Exact legacy-29 snapshot available: **{result.get('legacy_29_snapshot_available', False)}**.

When the exact G16 29D vector is absent at the I1 source-order boundary, the report does not synthesize a proxy or claim legacy-vs-39D superiority. It instead records a real native 39D static-local versus full temporal/pressure/merge ablation; model authorization remains governed by causal support and externality gates.

The campaign passed I1 effect rows to `czr005.g4irsf17.run_state_aliasing_audit` when that package hook was available, using `system_utility` as the outcome.  Feature ablation was called through the package's canonical implementation as well; the campaign runner does not duplicate model semantics.

```json
{audit_json}
```
"""
    _atomic_write(root / ALIASING_REPORT_PATH, report.encode("utf-8"))
    return result


def call_model_reporting_hooks(
    rows: Sequence[Mapping[str, Any]],
    *,
    package: Any | None = None,
    evaluation_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    package = package if package is not None else _import_g17_package()
    if package is None:
        return {"status": "PACKAGE_HOOK_UNAVAILABLE", "evaluation": None, "available_components": []}
    components = [
        name
        for name in (
            "PairwiseLinearRanker",
            "TinyMLPListwiseRanker",
            "ConservativeSelectiveOverride",
            "make_diagnostic_splits",
            "evaluate_policy",
            "ranking_metrics",
        )
        if hasattr(package, name)
    ]
    split_function = getattr(package, "make_diagnostic_splits", None)
    splits = None
    if callable(split_function) and rows:
        split_value = _call_supported(
            split_function,
            [row.get("source", "unknown") for row in rows],
            [float(row.get("event_time", row.get("event_ordinal", 0.0))) for row in rows],
            [row.get("task_group", row.get("task_id", row.get("descriptor_id", index))) for index, row in enumerate(rows)],
        )
        splits = split_value.to_dict() if hasattr(split_value, "to_dict") else split_value
    evaluation = None
    status = "HOOK_READY_INPUT_REQUIRED"
    if evaluation_payload is not None:
        evaluate = getattr(package, "evaluate_policy", None)
        _require(callable(evaluate), "g4irsf17 package lacks evaluate_policy")
        candidate_sets = evaluation_payload.get("candidate_sets")
        chosen_indices = evaluation_payload.get("chosen_indices")
        _require(isinstance(candidate_sets, list) and isinstance(chosen_indices, list), "model evaluation payload requires candidate_sets and chosen_indices")
        evaluation = _call_supported(
            evaluate,
            candidate_sets,
            chosen_indices,
            baseline_indices=evaluation_payload.get("baseline_indices"),
            legal_masks=evaluation_payload.get("legal_masks"),
        )
        status = "COMPLETE"
    return {
        "status": status,
        "evaluation": evaluation,
        "diagnostic_splits": splits,
        "available_components": components,
    }


def write_model_report(
    *,
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    package: Any | None = None,
    evaluation_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = call_model_reporting_hooks(
        rows,
        package=package,
        evaluation_payload=evaluation_payload,
    )
    beneficial = sum(str(row.get("effect_label")) == "BENEFICIAL" for row in rows)
    harmful = sum(str(row.get("effect_label")) == "HARMFUL" for row in rows)
    report = f"""# G4IRSF17 I1 model decision hook

Status: **`{result['status']}`**

Input effects contain **{beneficial} beneficial** and **{harmful} harmful** rows.  Available canonical package components: `{', '.join(result['available_components']) or 'none'}`.

The campaign runner only reports package evaluations; it does not manufacture activation thresholds or train a substitute model.  `HOOK_READY_INPUT_REQUIRED` means the model package is present but no explicit candidate-set/chosen-index evaluation payload was supplied.

```json
{json.dumps(result.get('evaluation'), ensure_ascii=False, sort_keys=True, indent=2, default=_json_default)}
```
"""
    _atomic_write(root / MODEL_REPORT_PATH, report.encode("utf-8"))
    return result


def _load_effect_rows(path: Path) -> list[dict[str, Any]]:
    return read_rows(path)


def _resolve_binary_from_manifest(path: Path) -> Path:
    value = json.loads(path.read_text(encoding="utf-8"))
    binary = value.get("binary")
    _require(isinstance(binary, dict) and binary.get("path"), f"{path} lacks binary.path")
    return Path(str(binary["path"]))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="create/resume the lightweight campaign journal")

    diagnose = subparsers.add_parser("diagnose-source-wait")
    diagnose.add_argument("--telemetry", type=Path, required=True)
    diagnose.add_argument("--off-telemetry", type=Path)
    diagnose.add_argument("--h5-bags", type=Path, required=True)
    diagnose.add_argument("--off-bags", type=Path, required=True)
    diagnose.add_argument("--force", action="store_true")

    plan = subparsers.add_parser("plan-i1")
    plan.add_argument("--targets", type=Path, default=G15_TARGET_FRAME_PATH)
    plan.add_argument("--h-bag-count", type=int, default=128)
    plan.add_argument("--h-system-count", type=int, default=8)
    plan.add_argument("--output", type=Path, default=I1_PLAN_PATH)
    plan.add_argument("--dry-run", action="store_true")
    plan.add_argument("--force", action="store_true")

    run = subparsers.add_parser("run-i1")
    run.add_argument("--plan", type=Path, default=I1_PLAN_PATH)
    run.add_argument("--binary", type=Path)
    run.add_argument("--build-manifest", type=Path)
    run.add_argument("--pairs-fixture", type=Path)
    run.add_argument("--chunk-size", type=int, default=16)
    run.add_argument(
        "--chunk-index",
        type=int,
        action="append",
        help="execute only this zero-based checkpoint chunk; repeat for multiple chunks",
    )
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--force", action="store_true")

    analyse = subparsers.add_parser("analyse-i1")
    analyse.add_argument("--pairs", type=Path, default=I1_DATASET_PATH)
    analyse.add_argument("--plan", type=Path, default=I1_PLAN_PATH)

    alias = subparsers.add_parser("aliasing-report")
    alias.add_argument("--effects", type=Path, default=I1_EFFECTS_PATH)

    model = subparsers.add_parser("model-report")
    model.add_argument("--effects", type=Path, default=I1_EFFECTS_PATH)
    model.add_argument("--evaluation", type=Path)

    subparsers.add_parser("status", help="print the resumable campaign manifest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.root.resolve()
    journal = CampaignJournal(root)
    command = arguments.command
    try:
        if command == "init":
            print(journal.manifest_path)
            return 0
        if command == "status":
            print(json.dumps(journal.value, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if command == "diagnose-source-wait":
            outputs = (SOURCE_WAIT_LEDGER_PATH, SOURCE_WAIT_TOPOLOGY_PATH, SOURCE_WAIT_REPORT_PATH)
            if not arguments.force and journal.resumable("source_wait_diagnosis", outputs):
                print("source_wait_diagnosis already complete; use --force to recompute")
                return 0
            paths = [arguments.telemetry, arguments.h5_bags, arguments.off_bags]
            if arguments.off_telemetry:
                paths.append(arguments.off_telemetry)
            resolved = [path if path.is_absolute() else root / path for path in paths]
            journal.begin("source_wait_diagnosis", command=sys.argv, inputs=resolved)
            result = run_source_wait_diagnosis(
                root=root,
                telemetry_rows=read_rows(resolved[0]),
                h5_bag_rows=read_rows(resolved[1]),
                off_bag_rows=read_rows(resolved[2]),
                off_telemetry_rows=read_rows(resolved[3]) if len(resolved) == 4 else (),
                journal=journal,
            )
            print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if command == "plan-i1":
            target_path = arguments.targets if arguments.targets.is_absolute() else root / arguments.targets
            output_path = arguments.output if arguments.output.is_absolute() else root / arguments.output
            rows = read_rows(target_path)
            plan = create_i1_plan(
                rows,
                h_bag_count=arguments.h_bag_count,
                h_system_count=arguments.h_system_count,
            )
            if arguments.dry_run:
                print(json.dumps(plan["selection"], ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            if output_path.is_file() and not arguments.force:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
                _require(existing.get("schema") == SCHEMA_I1_PLAN, "existing I1 plan schema mismatch")
                print(f"reusing existing plan {output_path}; use --force to replace")
                return 0
            journal.begin("i1_plan", command=sys.argv, inputs=(target_path,))
            _write_json(output_path, plan)
            journal.complete(
                "i1_plan",
                outputs=(output_path,),
                summary=plan["selection"],
                decision="REAL_COMPETITIVE_I1_PANEL_PLANNED",
                next_action="Execute matched H_bag pairs and the bounded H_system subset.",
            )
            print(output_path)
            return 0
        if command == "run-i1":
            plan_path = arguments.plan if arguments.plan.is_absolute() else root / arguments.plan
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if arguments.dry_run:
                print(
                    json.dumps(
                        {
                            "status": "DRY_RUN",
                            "target_count": len(plan.get("targets", [])),
                            "chunk_size": arguments.chunk_size,
                            "chunk_count": math.ceil(len(plan.get("targets", [])) / arguments.chunk_size),
                            "selected_chunk_indices": arguments.chunk_index,
                            "native_binding": "g4irsf15_run_causal_target_pairs_from_records",
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            selected_chunks = set(arguments.chunk_index) if arguments.chunk_index else None
            if selected_chunks is None:
                journal.begin("i1_paired_execution", command=sys.argv, inputs=(plan_path,))
            executor = None
            binary = arguments.binary
            if arguments.pairs_fixture:
                fixture = arguments.pairs_fixture if arguments.pairs_fixture.is_absolute() else root / arguments.pairs_fixture
                executor = _fixture_pair_executor(read_rows(fixture))
            elif binary is None and arguments.build_manifest is not None:
                manifest = arguments.build_manifest if arguments.build_manifest.is_absolute() else root / arguments.build_manifest
                binary = _resolve_binary_from_manifest(manifest)
            if binary is not None and not binary.is_absolute():
                binary = root / binary
            result = execute_i1_pilot(
                root=root,
                plan=plan,
                binary=binary,
                pair_executor=executor,
                chunk_size=arguments.chunk_size,
                chunk_indices=selected_chunks,
                journal=journal if selected_chunks is None else None,
                force=arguments.force,
            )
            print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if command == "analyse-i1":
            pairs_path = arguments.pairs if arguments.pairs.is_absolute() else root / arguments.pairs
            plan_path = arguments.plan if arguments.plan.is_absolute() else root / arguments.plan
            targets: list[dict[str, Any]] = []
            if plan_path.is_file():
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                targets = list(plan.get("targets", []))
            journal.begin("i1_analysis", command=sys.argv, inputs=(pairs_path,))
            result = write_i1_analysis(root=root, pair_records=read_rows(pairs_path), targets=targets)
            journal.complete(
                "i1_analysis",
                outputs=(root / I1_EFFECTS_PATH, root / I1_SUPPORT_REPORT_PATH),
                summary=result["summary"],
                decision=result["summary"]["pivot_decision"],
                next_action=result["summary"]["next_action"],
            )
            print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if command == "aliasing-report":
            effects = arguments.effects if arguments.effects.is_absolute() else root / arguments.effects
            journal.begin("state_aliasing", command=sys.argv, inputs=(effects,))
            result = write_state_aliasing_report(root=root, rows=_load_effect_rows(effects))
            journal.complete(
                "state_aliasing",
                outputs=(root / ALIASING_REPORT_PATH, root / FEATURE_ABLATION_PATH),
                summary={"status": result["status"], "ablation_row_count": len(result["feature_ablation"])},
                decision=result["status"],
                next_action="Retain only runtime-realizable features that reduce sign disagreement.",
            )
            print(result["status"])
            return 0
        if command == "model-report":
            effects = arguments.effects if arguments.effects.is_absolute() else root / arguments.effects
            evaluation = None
            inputs = [effects]
            if arguments.evaluation:
                evaluation_path = arguments.evaluation if arguments.evaluation.is_absolute() else root / arguments.evaluation
                evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
                inputs.append(evaluation_path)
            journal.begin("model_reporting", command=sys.argv, inputs=inputs)
            result = write_model_report(root=root, rows=_load_effect_rows(effects), evaluation_payload=evaluation)
            journal.complete(
                "model_reporting",
                outputs=(root / MODEL_REPORT_PATH,),
                summary={"status": result["status"], "available_components": result["available_components"]},
                decision=result["status"],
                next_action="Compare localized rule, linear pairwise, tiny MLP/listwise, and conservative selective override after support gates.",
            )
            print(result["status"])
            return 0
        raise CampaignError(f"unknown command {command}")
    except Exception as exc:
        stage_by_command = {
            "diagnose-source-wait": "source_wait_diagnosis",
            "plan-i1": "i1_plan",
            "run-i1": "i1_paired_execution",
            "analyse-i1": "i1_analysis",
            "aliasing-report": "state_aliasing",
            "model-report": "model_reporting",
        }
        stage = stage_by_command.get(command)
        if stage is not None:
            journal.fail(stage, exc)
        print(f"G4IRSF17 campaign error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
