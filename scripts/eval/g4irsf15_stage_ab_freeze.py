#!/usr/bin/env python3
"""Generate the deterministic G4IRSF15 Stage 15A/15B evidence freeze.

This is an evidence-only generator.  It reads the sealed G4IRSF13/14
artifacts, audits the request/lifecycle rows that were actually retained, and
publishes a content-addressed Stage 15A/15B bundle.  It does not run a new
simulation, alter a predecessor artifact, infer an unavailable original-1x
destination breakdown, or turn screening support into causal labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

REPOSITORY_SLUG = "czr5454112-glitch/jichang_origin"
REQUIRED_BASE_COMMIT = "966a063573f0419df1324708db75211c521d59db"
UPSTREAM_REF = "origin/codex/czr005-rewrite"
ALLOWED_BRANCHES = (
    "codex/czr005-rewrite",
    "codex/g4irsf15-execution",
)

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
G13_PER_BAG = Path("outputs/tables/g4irsf13_per_bag_delta.csv")
G14_BASELINE = Path("artifacts/gates/g4irsf14_baseline_registry.json")
G14_F2 = Path("artifacts/policies/g4irsf14_f2_frozen_control.json")
G14_CLONE = Path("artifacts/datasets/g4irsf14_clone_manifest.json")
G14_CENSUS = Path("outputs/tables/g4irsf14_opportunity_census.json")
G14_MERGE_CONFIG = Path(
    "artifacts/configs/g4irsf14_merge_grant_protocol.json"
)
G14_MERGE_RULE = Path("outputs/tables/g4irsf14_merge_rule_ab.csv")
G14_LIFECYCLE = Path("outputs/tables/g4irsf14_merge_grant_lifecycle.csv")
G14_EVENT_TABLE = Path("outputs/tables/g4irsf14_event_microphase_ab.csv")
G14_EVENT_REPORT = Path("outputs/reports/g4irsf14_event_microphase_ab.md")

START_REPORT = Path("outputs/reports/g4irsf15_start_state.md")
POSTMORTEM_REPORT = Path("outputs/reports/g4irsf15_g4irsf14_postmortem.md")
CHURN_REPORT = Path(
    "outputs/reports/g4irsf15_merge_request_churn_postmortem.md"
)
CHURN_TABLE = Path("outputs/tables/g4irsf15_merge_request_churn.csv")
HOTSPOT_TABLE = Path(
    "outputs/tables/g4irsf15_merge_destination_hotspots.csv"
)
SCREENING_TABLE = Path(
    "outputs/tables/g4irsf15_screening_false_positive_estimate.csv"
)
BASELINE_REGISTRY = Path("artifacts/gates/g4irsf15_baseline_registry.json")
F2_CONTROL = Path("artifacts/policies/g4irsf15_f2_frozen_control.json")
E4_CONTROL = Path(
    "artifacts/policies/g4irsf15_e4_frozen_mechanism_control.json"
)
CAMPAIGN_MANIFEST = Path(
    "artifacts/datasets/g4irsf15_campaign_source_manifest.json"
)

OUTPUT_PATHS = (
    START_REPORT,
    POSTMORTEM_REPORT,
    CHURN_REPORT,
    CHURN_TABLE,
    HOTSPOT_TABLE,
    SCREENING_TABLE,
    BASELINE_REGISTRY,
    F2_CONTROL,
    E4_CONTROL,
    CAMPAIGN_MANIFEST,
)

MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
TASK_SEMANTIC_SHA256 = TASK_RAW_SHA256
FULL_SEGMENT_COUNT = 43_603
FULL_RAW_BAG_COUNT = 28_506

EXPECTED_SEMANTIC_SHA256: Mapping[Path, str] = {
    G13_PER_BAG: (
        "fc3dde5aa958d23be4a186e0727702db6895980847d1473b21c5134d002ca551"
    ),
    G14_BASELINE: (
        "331338197366eb51e604d4f18296d6c41a54a6a426eee5963648223ae9f24e46"
    ),
    G14_F2: (
        "2e2c66244ceb4ff1b514da211487d8c5223f7a29304548309856824297eccfaf"
    ),
    G14_CLONE: (
        "f5b8c2629f627728aa774bf1117f8a6f1eef90ad6be2417a35ed962ad2e0fa0f"
    ),
    G14_CENSUS: (
        "365d2a8f860944616f5e7199be2c3c86b3d07dc743ba793b978b0fedf4586de3"
    ),
    G14_MERGE_CONFIG: (
        "e36e81bcc4aafa1b3d222fdd0d634dae687fa337d706c7af28c38141585298e4"
    ),
    G14_MERGE_RULE: (
        "8808a79443a20bf2bfdee35ead5789b52d76a0ea386153ffd267a78020dc31c1"
    ),
    G14_LIFECYCLE: (
        "138f8af81d844cb2aa021f7b0667c0c1aa1133db29fb7b640e0f6fa6eec9920f"
    ),
    G14_EVENT_TABLE: (
        "86344c5f48cba6a378855129509ad5267b8300485f8609f2976aed53db15c3ce"
    ),
    G14_EVENT_REPORT: (
        "c2cd7a80f7cd5b318891e7e9393ed9c80f7c4c25263007fc85b8bac86c77720f"
    ),
}

BINARY_SHA256: Mapping[str, str] = {
    "f2_frozen_control": (
        "814b233016a51a755d6f568604fcb04ca81d781222416075cf2648ec087f1de7"
    ),
    "e4_original_1x_screening": (
        "11b957890666a4ac4dd056fca4828cecb6b3f3ff29fdc590d05c4cff875ebc71"
    ),
    "e4_stage_d_mechanism": (
        "0d82141e8e650d682f812fe18582661ba6feb6dd08c88731c343d3caf07d6a38"
    ),
    "event_microphase_instrumented": (
        "e10da3f5fcf49d3522eb51e70523b2b8d2d2a747cee07d3991d9f74de1efb233"
    ),
}

CHURN_FIELDS = (
    "schema",
    "evidence_scope",
    "selection",
    "dimension",
    "dimension_value",
    "completed_movement_count",
    "unique_requesting_segment_count",
    "request_count",
    "active_grant_rejection_count",
    "arbitration_count",
    "lifecycle_transition_count",
    "lifecycle_dropped_count",
    "requests_per_completed_movement",
    "rejections_per_completed_movement",
    "arbitrations_per_completed_movement",
    "event_count",
    "events_per_completed_movement",
    "protocol_mean_grant_wait_seconds",
    "mean_successful_fifo_wait_seconds",
    "peak_pending_request_count",
    "multi_request_live_boundary_count",
    "queue_capacity_block_count",
    "exact_slot_busy_count",
    "stale_generation_count",
    "fault_count",
    "breakdown_available",
    "extrapolation_allowed",
    "source_limitation",
    "row_sha256",
)

HOTSPOT_FIELDS = (
    "schema",
    "evidence_scope",
    "rank",
    "destination_node",
    "request_count",
    "request_share",
    "active_grant_rejection_count",
    "rejection_share",
    "unique_requesting_segment_count",
    "successful_issue_count",
    "mean_successful_fifo_wait_seconds",
    "breakdown_available",
    "extrapolation_allowed",
    "source_limitation",
    "row_sha256",
)

SCREENING_FIELDS = (
    "schema",
    "intervention_kind",
    "support_semantics",
    "screening_support_count",
    "prefilter_count",
    "committed_target_descriptor_count",
    "formal_attempt_count",
    "action_changed_count",
    "complete_h_bag_count",
    "complete_h_system_count",
    "screening_false_positive_rate_estimate",
    "estimate_status",
    "campaign_source_status",
    "source_screening_manifest_sha256",
    "blocker",
    "row_sha256",
)

UNAVAILABLE_FULL_BREAKDOWNS = (
    "destination",
    "upstream",
    "hour",
    "source",
    "goal",
    "storage_direct",
    "entry_time_band",
    "deadline_slack_bucket",
    "retry_count",
    "active_grant",
    "queue_capacity",
    "stale_generation",
    "exact_slot_busy",
    "fault",
)


class StageABError(RuntimeError):
    """Raised when a Stage 15A/15B invariant is not satisfied."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_sha256(path: Path) -> str:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StageABError(f"NON_UTF8_BOUND_ARTIFACT:{path}") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise StageABError(
            f"GIT_COMMAND_FAILED:{' '.join(arguments)}:{detail}"
        )
    return result.stdout.strip()


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise StageABError(
            f"GIT_ANCESTRY_CHECK_FAILED:{ancestor}:{descendant}"
        )
    return result.returncode == 0


def audit_repository(root: Path) -> dict[str, Any]:
    top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root.resolve():
        raise StageABError(f"WRONG_REPOSITORY_ROOT:{top}")
    if "czr004" in str(top).lower():
        raise StageABError(f"FORBIDDEN_CZR004_PATH:{top}")

    remote = _git(root, "remote", "get-url", "origin")
    canonical_remote = remote.lower().removesuffix(".git")
    if REPOSITORY_SLUG.lower() not in canonical_remote:
        raise StageABError(f"WRONG_ORIGIN:{remote}")

    branch = _git(root, "branch", "--show-current")
    if branch not in ALLOWED_BRANCHES:
        raise StageABError(f"WRONG_BRANCH:{branch}")
    head = _git(root, "rev-parse", "HEAD")
    upstream_head = _git(root, "rev-parse", UPSTREAM_REF)
    if not _is_ancestor(root, REQUIRED_BASE_COMMIT, head):
        raise StageABError(f"HEAD_NOT_DESCENDANT_OF_BASE:{head}")
    if not _is_ancestor(root, REQUIRED_BASE_COMMIT, upstream_head):
        raise StageABError(
            f"UPSTREAM_NOT_DESCENDANT_OF_BASE:{upstream_head}"
        )
    merge_base = _git(root, "merge-base", head, upstream_head)
    if not _is_ancestor(root, REQUIRED_BASE_COMMIT, merge_base):
        raise StageABError(f"INVALID_HEAD_UPSTREAM_MERGE_BASE:{merge_base}")

    protected = (
        MAP_PATH,
        TASK_PATH,
        *EXPECTED_SEMANTIC_SHA256.keys(),
    )
    drift = _git(
        root,
        "status",
        "--porcelain=v1",
        "--",
        *(path.as_posix() for path in protected),
    )
    if drift:
        raise StageABError(f"PROTECTED_OR_SEALED_PATH_DRIFT:{drift}")

    return {
        "repository": REPOSITORY_SLUG,
        "origin_canonical": (
            "https://github.com/czr5454112-glitch/jichang_origin"
        ),
        "branch": branch,
        "head_at_generation": head,
        "required_base_commit": REQUIRED_BASE_COMMIT,
        "head_is_base_or_descendant": True,
        "upstream_ref": UPSTREAM_REF,
        "upstream_head_at_generation": upstream_head,
        "upstream_is_base_or_descendant": True,
        "head_upstream_merge_base": merge_base,
        "protected_and_sealed_inputs_clean": True,
    }


def verify_inputs(root: Path) -> dict[str, dict[str, Any]]:
    map_path = root / MAP_PATH
    task_path = root / TASK_PATH
    if file_sha256(map_path) != MAP_RAW_SHA256:
        raise StageABError("PROTECTED_MAP_RAW_SHA256_MISMATCH")
    if semantic_sha256(map_path) != MAP_SEMANTIC_SHA256:
        raise StageABError("PROTECTED_MAP_SEMANTIC_SHA256_MISMATCH")
    if file_sha256(task_path) != TASK_RAW_SHA256:
        raise StageABError("PROTECTED_TASK_RAW_SHA256_MISMATCH")
    if semantic_sha256(task_path) != TASK_SEMANTIC_SHA256:
        raise StageABError("PROTECTED_TASK_SEMANTIC_SHA256_MISMATCH")

    segment_count = 0
    raw_bag_ids: set[int] = set()
    with task_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            segment_count += 1
            raw_bag_ids.add(int(row["task_id"]))
    if segment_count != FULL_SEGMENT_COUNT:
        raise StageABError(f"TASK_SEGMENT_COUNT_MISMATCH:{segment_count}")
    if len(raw_bag_ids) != FULL_RAW_BAG_COUNT:
        raise StageABError(f"TASK_RAW_BAG_COUNT_MISMATCH:{len(raw_bag_ids)}")

    bindings: dict[str, dict[str, Any]] = {
        MAP_PATH.as_posix(): {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": MAP_RAW_SHA256,
            "semantic_sha256": MAP_SEMANTIC_SHA256,
            "byte_count": map_path.stat().st_size,
            "access": "READ_ONLY_PROTECTED",
        },
        TASK_PATH.as_posix(): {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": TASK_RAW_SHA256,
            "semantic_sha256": TASK_SEMANTIC_SHA256,
            "byte_count": task_path.stat().st_size,
            "segment_count": segment_count,
            "raw_bag_count": len(raw_bag_ids),
            "access": "READ_ONLY_PROTECTED",
        },
    }
    for relative, expected in EXPECTED_SEMANTIC_SHA256.items():
        path = root / relative
        if not path.is_file():
            raise StageABError(f"MISSING_SEALED_INPUT:{relative.as_posix()}")
        actual = semantic_sha256(path)
        if actual != expected:
            raise StageABError(
                f"SEALED_INPUT_CONTENT_DRIFT:{relative.as_posix()}:{actual}"
            )
        bindings[relative.as_posix()] = {
            "path": relative.as_posix(),
            "semantic_sha256": actual,
            "byte_count": path.stat().st_size,
            "hash_mode": "sha256_utf8_after_crlf_cr_to_lf",
            "access": "READ_ONLY_SEALED_EVIDENCE",
        }
    return bindings


def _read_json(root: Path, relative: Path) -> dict[str, Any]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StageABError(f"JSON_ROOT_NOT_OBJECT:{relative.as_posix()}")
    return value


def _read_csv(root: Path, relative: Path) -> list[dict[str, str]]:
    with (root / relative).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise StageABError("NON_FINITE_NUMBER")
    return format(value, ".17g")


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _row_with_hash(
    fields: Sequence[str], values: Mapping[str, Any]
) -> dict[str, str]:
    row = {field: str(values.get(field, "")) for field in fields}
    row.pop("row_sha256", None)
    row["row_sha256"] = canonical_sha256(row)
    return row


def _csv_bytes(
    fields: Sequence[str], rows: Iterable[Mapping[str, str]]
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _signed_json(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("self_sha256", None)
    result["self_sha256"] = canonical_sha256(result)
    return result


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _output_binding(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    return {
        "path": relative.as_posix(),
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size,
        "hash_mode": "sha256_exact_bytes",
    }


def _verify_binary_arguments(
    specifications: Sequence[str],
) -> tuple[str, ...]:
    seen: set[str] = set()
    for specification in specifications:
        if "=" not in specification:
            raise StageABError(
                "BINARY_SPEC_MUST_BE_ROLE_EQUALS_PATH:" + specification
            )
        role, raw_path = specification.split("=", 1)
        if role not in BINARY_SHA256:
            raise StageABError(f"UNKNOWN_BINARY_ROLE:{role}")
        if role in seen:
            raise StageABError(f"DUPLICATE_BINARY_ROLE:{role}")
        path = Path(raw_path)
        if not path.is_file():
            raise StageABError(f"EXACT_BINARY_MISSING:{role}:{path}")
        actual = file_sha256(path)
        expected = BINARY_SHA256[role]
        if actual != expected:
            raise StageABError(
                f"EXACT_BINARY_SHA256_MISMATCH:{role}:{actual}:{expected}"
            )
        seen.add(role)
    missing = set(BINARY_SHA256) - seen
    if missing:
        raise StageABError(
            "EXACT_BINARY_VERIFICATION_REQUIRED:"
            + ",".join(sorted(missing))
        )
    return tuple(sorted(seen))


def _load_context(root: Path) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    for row in _read_csv(root, G13_PER_BAG):
        task_id = int(row["task_id"])
        result[task_id] = {
            "hour": row["hour"],
            "source": row["source"],
            "goal": row["goal"],
            "bag_class": row["bag_class"],
            "storage_direct": (
                "storage"
                if row["bag_class"].startswith("storage")
                else "direct"
            ),
            "entry_time_band": row["entry_time_band"],
            "deadline_slack_bucket": row["deadline_slack_bucket"],
        }
    if len(result) != FULL_RAW_BAG_COUNT:
        raise StageABError(f"PER_BAG_CONTEXT_COUNT_MISMATCH:{len(result)}")
    return result


def _m0_lifecycle(
    root: Path,
) -> tuple[
    list[dict[str, str]],
    dict[int, dict[str, str]],
    set[int],
    set[int],
    dict[int, float],
    dict[int, list[dict[str, str]]],
]:
    rows = [
        row
        for row in _read_csv(root, G14_LIFECYCLE)
        if row["rule"] == "M0"
    ]
    if len(rows) != 2_658:
        raise StageABError(f"M0_LIFECYCLE_COUNT_MISMATCH:{len(rows)}")
    requests: dict[int, dict[str, str]] = {}
    rejected: set[int] = set()
    issued: set[int] = set()
    fifo_wait: dict[int, float] = {}
    transitions: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        request_id = int(row["request_id"])
        transitions[request_id].append(row)
        if row["state"] == "REQUESTED":
            if request_id in requests:
                raise StageABError(f"DUPLICATE_M0_REQUEST:{request_id}")
            requests[request_id] = row
        elif row["state"] == "ROLLED_BACK":
            if row["reason"] != "active_unconsumed_grant_exists":
                raise StageABError(
                    f"UNEXPECTED_M0_ROLLBACK_REASON:{row['reason']}"
                )
            rejected.add(request_id)
        elif row["state"] == "ISSUED":
            issued.add(request_id)
            fifo_wait[request_id] = max(
                0.0,
                float(row["issue_time"]) - float(row["fifo_request_time"]),
            )
    if len(requests) != 666 or len(rejected) != 224 or len(issued) != 442:
        raise StageABError(
            "M0_LIFECYCLE_COUNTER_MISMATCH:"
            f"{len(requests)}:{len(rejected)}:{len(issued)}"
        )
    if rejected & issued:
        raise StageABError("M0_REQUEST_BOTH_REJECTED_AND_ISSUED")
    if set(requests) != rejected | issued:
        raise StageABError("M0_REQUEST_TERMINAL_PARTITION_MISMATCH")
    return rows, requests, rejected, issued, fifo_wait, transitions


def _request_dimensions(
    request: Mapping[str, str],
    context: Mapping[int, Mapping[str, str]],
) -> dict[str, str]:
    task_id = int(request["task_id"])
    bag = context.get(task_id)
    if bag is None:
        raise StageABError(f"MISSING_TASK_CONTEXT:{task_id}")
    return {
        "destination": request["destination_node"],
        "upstream": request["upstream_node"],
        "hour": bag["hour"],
        "source": bag["source"],
        "goal": bag["goal"],
        "bag_class": bag["bag_class"],
        "storage_direct": bag["storage_direct"],
        "entry_time_band": bag["entry_time_band"],
        "deadline_slack_bucket": bag["deadline_slack_bucket"],
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_churn_rows(
    census: Mapping[str, Any],
    merge_summary: Mapping[str, Any],
    context: Mapping[int, Mapping[str, str]],
    lifecycle_rows: Sequence[Mapping[str, str]],
    requests: Mapping[int, Mapping[str, str]],
    rejected: set[int],
    issued: set[int],
    fifo_wait: Mapping[int, float],
    transitions: Mapping[int, Sequence[Mapping[str, str]]],
) -> list[dict[str, str]]:
    counters = census["i2_raw_counters"]
    hard = census["raw_hard_gates"]["decision_run"]
    rows: list[dict[str, str]] = []
    full_requests = int(counters["merge_grant_request_count"])
    full_rejections = int(
        counters["merge_grant_active_grant_rejection_count"]
    )
    full_arbitrations = int(
        counters["destination_merge_arbitration_event_count"]
    )
    full_events = int(hard["event_count"])
    full_drops = int(hard["merge_grant_lifecycle_dropped_count"])
    common_full = {
        "schema": "czr005.g4irsf15.merge_request_churn.v1",
        "evidence_scope": "G4IRSF14_ORIGINAL_1X_E4_SCREENING",
        "selection": "map2_inputdata_original_1x",
        "completed_movement_count": FULL_SEGMENT_COUNT,
        "unique_requesting_segment_count": "",
        "lifecycle_transition_count": "",
        "lifecycle_dropped_count": full_drops,
        "protocol_mean_grant_wait_seconds": "",
        "mean_successful_fifo_wait_seconds": "",
        "peak_pending_request_count": counters[
            "merge_grant_peak_pending_requests"
        ],
        "multi_request_live_boundary_count": counters[
            "g4irsf14_i2_live_eligible_multi_request_boundary_count"
        ],
        "queue_capacity_block_count": counters[
            "merge_grant_queue_capacity_block_count"
        ],
        "exact_slot_busy_count": counters[
            "merge_grant_exact_slot_busy_count"
        ],
        "stale_generation_count": counters[
            "merge_grant_stale_arbitration_count"
        ],
        "fault_count": 0,
        "extrapolation_allowed": "false",
    }
    rows.append(
        _row_with_hash(
            CHURN_FIELDS,
            {
                **common_full,
                "dimension": "all",
                "dimension_value": "all",
                "request_count": full_requests,
                "active_grant_rejection_count": full_rejections,
                "arbitration_count": full_arbitrations,
                "requests_per_completed_movement": _number(
                    full_requests / FULL_SEGMENT_COUNT
                ),
                "rejections_per_completed_movement": _number(
                    full_rejections / FULL_SEGMENT_COUNT
                ),
                "arbitrations_per_completed_movement": _number(
                    full_arbitrations / FULL_SEGMENT_COUNT
                ),
                "event_count": full_events,
                "events_per_completed_movement": _number(
                    full_events / FULL_SEGMENT_COUNT
                ),
                "breakdown_available": "true",
                "source_limitation": (
                    "aggregate counters only; lifecycle rows were truncated"
                ),
            },
        )
    )
    for dimension in UNAVAILABLE_FULL_BREAKDOWNS:
        rows.append(
            _row_with_hash(
                CHURN_FIELDS,
                {
                    **common_full,
                    "dimension": dimension,
                    "dimension_value": "NOT_RETAINED",
                    "completed_movement_count": "",
                    "request_count": "",
                    "active_grant_rejection_count": "",
                    "arbitration_count": "",
                    "lifecycle_dropped_count": full_drops,
                    "peak_pending_request_count": "",
                    "multi_request_live_boundary_count": "",
                    "queue_capacity_block_count": "",
                    "exact_slot_busy_count": "",
                    "stale_generation_count": "",
                    "fault_count": "",
                    "breakdown_available": "false",
                    "source_limitation": (
                        "original-1x per-request rows are not present in the "
                        "committed evidence; no destination/hour/class value "
                        "is inferred from the 144-segment mechanism run"
                    ),
                },
            )
        )

    m0_wait = _mean(list(fifo_wait.values()))
    rows.append(
        _row_with_hash(
            CHURN_FIELDS,
            {
                "schema": "czr005.g4irsf15.merge_request_churn.v1",
                "evidence_scope": "G4IRSF14_STAGE_D_M0_144_DIAGNOSTIC",
                "selection": "canonical_first_144_segments",
                "dimension": "all",
                "dimension_value": "all",
                "completed_movement_count": 144,
                "unique_requesting_segment_count": len(
                    {row["segment_id"] for row in requests.values()}
                ),
                "request_count": len(requests),
                "active_grant_rejection_count": len(rejected),
                "arbitration_count": merge_summary[
                    "destination_merge_arbitration_event_count"
                ],
                "lifecycle_transition_count": len(lifecycle_rows),
                "lifecycle_dropped_count": merge_summary[
                    "merge_grant_lifecycle_dropped_count"
                ],
                "requests_per_completed_movement": _number(
                    len(requests) / 144
                ),
                "rejections_per_completed_movement": _number(
                    len(rejected) / 144
                ),
                "arbitrations_per_completed_movement": _number(
                    int(
                        merge_summary[
                            "destination_merge_arbitration_event_count"
                        ]
                    )
                    / 144
                ),
                "event_count": "",
                "events_per_completed_movement": "",
                "protocol_mean_grant_wait_seconds": _number(
                    float(merge_summary["mean_grant_wait_seconds"])
                ),
                "mean_successful_fifo_wait_seconds": _number(m0_wait),
                "peak_pending_request_count": merge_summary[
                    "merge_grant_peak_pending_requests"
                ],
                "multi_request_live_boundary_count": 0,
                "queue_capacity_block_count": merge_summary[
                    "merge_grant_queue_capacity_block_count"
                ],
                "exact_slot_busy_count": merge_summary[
                    "merge_grant_exact_slot_busy_count"
                ],
                "stale_generation_count": merge_summary[
                    "merge_grant_stale_arbitration_count"
                ],
                "fault_count": merge_summary["fault_event_count"],
                "breakdown_available": "true",
                "extrapolation_allowed": "false",
                "source_limitation": (
                    "complete Stage-D M0 lifecycle for 144 segments; "
                    "diagnostic only and not an original-1x distribution"
                ),
            },
        )
    )

    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for request_id, request in requests.items():
        for dimension, value in _request_dimensions(
            request, context
        ).items():
            grouped[(dimension, value)].append(request_id)
    for (dimension, value), request_ids in sorted(grouped.items()):
        request_set = set(request_ids)
        waits = [
            fifo_wait[request_id]
            for request_id in request_ids
            if request_id in issued
        ]
        rows.append(
            _row_with_hash(
                CHURN_FIELDS,
                {
                    "schema": "czr005.g4irsf15.merge_request_churn.v1",
                    "evidence_scope": (
                        "G4IRSF14_STAGE_D_M0_144_DIAGNOSTIC"
                    ),
                    "selection": "canonical_first_144_segments",
                    "dimension": dimension,
                    "dimension_value": value,
                    "completed_movement_count": "",
                    "unique_requesting_segment_count": len(
                        {
                            requests[request_id]["segment_id"]
                            for request_id in request_ids
                        }
                    ),
                    "request_count": len(request_ids),
                    "active_grant_rejection_count": len(
                        request_set & rejected
                    ),
                    "arbitration_count": len(request_ids),
                    "lifecycle_transition_count": sum(
                        len(transitions[request_id])
                        for request_id in request_ids
                    ),
                    "lifecycle_dropped_count": 0,
                    "protocol_mean_grant_wait_seconds": "",
                    "mean_successful_fifo_wait_seconds": _number(
                        _mean(waits)
                    ),
                    "breakdown_available": "true",
                    "extrapolation_allowed": "false",
                    "source_limitation": (
                        "Stage-D M0 144-segment diagnostic cohort only; "
                        "rates per completed movement are intentionally blank"
                    ),
                },
            )
        )
    return rows


def build_hotspot_rows(
    requests: Mapping[int, Mapping[str, str]],
    rejected: set[int],
    issued: set[int],
    fifo_wait: Mapping[int, float],
) -> list[dict[str, str]]:
    rows = [
        _row_with_hash(
            HOTSPOT_FIELDS,
            {
                "schema": "czr005.g4irsf15.merge_destination_hotspots.v1",
                "evidence_scope": "G4IRSF14_ORIGINAL_1X_E4_SCREENING",
                "rank": 0,
                "destination_node": "NOT_RETAINED",
                "request_count": 335_770,
                "request_share": 1,
                "active_grant_rejection_count": 178_263,
                "rejection_share": 1,
                "breakdown_available": "false",
                "extrapolation_allowed": "false",
                "source_limitation": (
                    "only the all-destination aggregate survives; a ranked "
                    "original-1x destination list cannot be reconstructed"
                ),
            },
        )
    ]
    by_destination: dict[str, list[int]] = defaultdict(list)
    for request_id, request in requests.items():
        by_destination[request["destination_node"]].append(request_id)
    ranked = sorted(
        by_destination.items(),
        key=lambda item: (
            -len(set(item[1]) & rejected),
            -len(item[1]),
            int(item[0]),
        ),
    )
    for rank, (destination, request_ids) in enumerate(ranked, start=1):
        request_set = set(request_ids)
        waits = [
            fifo_wait[request_id]
            for request_id in request_ids
            if request_id in issued
        ]
        rows.append(
            _row_with_hash(
                HOTSPOT_FIELDS,
                {
                    "schema": (
                        "czr005.g4irsf15.merge_destination_hotspots.v1"
                    ),
                    "evidence_scope": (
                        "G4IRSF14_STAGE_D_M0_144_DIAGNOSTIC"
                    ),
                    "rank": rank,
                    "destination_node": destination,
                    "request_count": len(request_ids),
                    "request_share": _number(len(request_ids) / 666),
                    "active_grant_rejection_count": len(
                        request_set & rejected
                    ),
                    "rejection_share": _number(
                        len(request_set & rejected) / 224
                    ),
                    "unique_requesting_segment_count": len(
                        {
                            requests[request_id]["segment_id"]
                            for request_id in request_ids
                        }
                    ),
                    "successful_issue_count": len(request_set & issued),
                    "mean_successful_fifo_wait_seconds": _number(
                        _mean(waits)
                    ),
                    "breakdown_available": "true",
                    "extrapolation_allowed": "false",
                    "source_limitation": (
                        "rank is valid only inside the Stage-D M0 "
                        "144-segment mechanism cohort"
                    ),
                },
            )
        )
    return rows


def build_screening_rows(
    census: Mapping[str, Any],
) -> list[dict[str, str]]:
    support = census["support"]
    specifications = (
        (
            "I1_SOURCE_ORDER_SWAP",
            "exact complete source boundary count",
            support["I1_source_order_swap"]["multi_ready_boundary_count"],
            "",
            support["I1_source_order_swap"][
                "screening_manifest_sha256"
            ],
            "SOURCE_FAMILY_SUPPORTED_TARGETS_REQUIRE_REMATERIALIZATION",
            "no committed target descriptors and no action-changing trial",
        ),
        (
            "I2_MERGE_ORDER_SWAP",
            "exact live eligible multi-request boundary count",
            support["I2_merge_request_order_swap"][
                "eligible_live_multi_request_boundary_count"
            ],
            "",
            "",
            "BLOCKED_INSUFFICIENT_PRIMARY_SUPPORT",
            "only one live multi-request boundary",
        ),
        (
            "I3_NEXT_EDGE",
            "conservative safe-alternative boundary lower bound",
            support["I3_next_edge"][
                "safe_alternative_boundary_lower_bound"
            ],
            "",
            support["I3_next_edge"]["screening_manifest_sha256"],
            "SOURCE_FAMILY_SUPPORTED_TARGETS_REQUIRE_REMATERIALIZATION",
            "lower bound only; no action-changing trial",
        ),
        (
            "I4_HOLD_RELEASE",
            "conservative release-to-hold boundary lower bound",
            support["I4_hold_release"][
                "release_to_hold_boundary_lower_bound"
            ],
            "",
            support["I4_hold_release"]["screening_manifest_sha256"],
            "SOURCE_FAMILY_SUPPORTED_TARGETS_REQUIRE_REMATERIALIZATION",
            "one-local-opportunity hold horizon not executed",
        ),
        (
            "I5_PIBT_TRIGGER",
            "strict applicable ready-slice boundary count",
            support["I5_pibt_trigger"][
                "applicable_ready_slice_boundary_count"
            ],
            support["I5_pibt_trigger"]["prefilter_candidate_count"],
            "",
            "BLOCKED_ZERO_STRICT_APPLICABLE_SUPPORT",
            "1337 queue-capacity prefilters are not PIBT applicability",
        ),
    )
    return [
        _row_with_hash(
            SCREENING_FIELDS,
            {
                "schema": (
                    "czr005.g4irsf15.screening_false_positive_estimate.v1"
                ),
                "intervention_kind": kind,
                "support_semantics": semantics,
                "screening_support_count": count,
                "prefilter_count": prefilter,
                "committed_target_descriptor_count": 0,
                "formal_attempt_count": 0,
                "action_changed_count": 0,
                "complete_h_bag_count": 0,
                "complete_h_system_count": 0,
                "screening_false_positive_rate_estimate": "",
                "estimate_status": (
                    "NOT_ESTIMABLE_ZERO_ACTION_CHANGING_TRIALS"
                ),
                "campaign_source_status": source_status,
                "source_screening_manifest_sha256": manifest,
                "blocker": blocker,
            },
        )
        for (
            kind,
            semantics,
            count,
            prefilter,
            manifest,
            source_status,
            blocker,
        ) in specifications
    ]


def _binary_ledger() -> dict[str, dict[str, Any]]:
    return {
        role: {
            "sha256": digest,
            "binding_type": "CONTENT_ADDRESS_FROM_SEALED_G4IRSF14_ARTIFACT",
            "physical_generation_path_is_not_a_portability_requirement": True,
        }
        for role, digest in sorted(BINARY_SHA256.items())
    }


def _start_report(
    repository: Mapping[str, Any],
    census: Mapping[str, Any],
) -> str:
    counters = census["i2_raw_counters"]
    return f"""# G4IRSF15 Stage 15A start state

## Repository and protected inputs

- Repository: `{REPOSITORY_SLUG}`
- Stage base: `{REQUIRED_BASE_COMMIT}`
- Generation branch: `{repository["branch"]}`
- Generation HEAD: `{repository["head_at_generation"]}`
- Upstream: `{UPSTREAM_REF}` at `{repository["upstream_head_at_generation"]}`
- The base commit is an ancestor of both HEAD and upstream.
- Protected map: `{MAP_PATH.as_posix()}` raw `{MAP_RAW_SHA256}`, semantic `{MAP_SEMANTIC_SHA256}`.
- Protected tasks: `{TASK_PATH.as_posix()}` raw `{TASK_RAW_SHA256}`, {FULL_SEGMENT_COUNT:,} segments and {FULL_RAW_BAG_COUNT:,} raw bags.
- No G4IRSF12--14 artifact is rewritten. Stage 15 copies only selected values and binds predecessor content.

## Frozen controls

| Role | Exact binary SHA-256 |
|---|---|
| Final F2 control | `{BINARY_SHA256["f2_frozen_control"]}` |
| Original-1x E4 screening | `{BINARY_SHA256["e4_original_1x_screening"]}` |
| Stage-D E4 mechanism | `{BINARY_SHA256["e4_stage_d_mechanism"]}` |
| Event-microphase instrumented runtime | `{BINARY_SHA256["event_microphase_instrumented"]}` |

F2 remains `R3/S1/P2/C0/Q0`, reservation depth 1. Its original-entry mean is `41.514218717973414` minutes, versus frozen v2-safe `41.49530698780892` minutes and corrected historical HCA `43.13593828041816` minutes. The gap to v2-safe remains `+1.1347038098698192` seconds per bag.

## G4IRSF14 handoff

- Prior decision: `PARTIAL_WITH_EXPLICIT_BLOCKER`.
- Formal complete causal labels: `0`; H_system pairs: `0`.
- E4 original-1x requests/arbitrations: `{int(counters["merge_grant_request_count"]):,}` / `{int(counters["destination_merge_arbitration_event_count"]):,}`.
- Active-grant rejections: `{int(counters["merge_grant_active_grant_rejection_count"]):,}`.
- Live multi-request boundaries: `{int(counters["g4irsf14_i2_live_eligible_multi_request_boundary_count"]):,}`; peak pending: `{int(counters["merge_grant_peak_pending_requests"])}`.
- Lifecycle rows dropped by the bounded passive trace: `1,011,439`.

This freeze does not authorize training, closed-loop evaluation, scaling, or a performance claim. Stage 15C must first rematerialize exact target descriptors and execute action-changing same-state pairs.

## GitHub Actions boundary

No G4IRSF15 workflow run exists at generation time. A run URL, run ID, job ID, and artifact hash must be appended by the publishing task after push; this bundle does not claim an unobserved CI result.
"""


def _postmortem_report(census: Mapping[str, Any]) -> str:
    support = census["support"]
    return f"""# G4IRSF15 / G4IRSF14 mechanism postmortem

## Finding

G4IRSF14 proved that exact-state clone/no-op fidelity and the destination-owned exact-slot capability were implementable. It did **not** produce an action-changing causal label. E4 behaved primarily as request -> immediate exact-slot arbitration -> issue or active-grant rejection -> later request, rather than as a retained pending set competing for the next local service opportunity.

## Answers to the Stage 15B audit questions

1. **Why {335_770:,} requests but one multi-request boundary?** Requests and arbitration events are exactly equal (`335,770`). There were `178,263` active-grant rejections, peak pending was `2`, and only `1` live eligible multi-request boundary was counted. Together these counters support the immediate-arbitration/retry explanation; they do not support a persistent multi-request queue.
2. **Where did the active-grant rejections occur?** The original-1x evidence retained only aggregate counters. Destination, hour, source, goal, storage/direct, timing band, slack, and bag-class breakdowns are **NOT AVAILABLE**. The destination table contains a single explicit unavailable aggregate plus a separately labeled 144-segment diagnostic; it never extrapolates the diagnostic ranking.
3. **Did immediate issue/reject prevent a pending set?** The counter relationship strongly supports that mechanism diagnosis. It is an inference from exact aggregate counters, not a claim based on missing per-request rows.
4. **Why were 1,011,439 lifecycle rows dropped?** The passive original-1x trace used a bounded lifecycle retention limit of `8,192`. The evidence records truncation and the aggregate dropped count, but not a per-row drop-reason distribution. Increasing memory without a retention protocol is not accepted as the repair.
5. **Why did same-timestamp batching not help?** Twenty motif/144/512/2048/8192 cases executed and passed hard gates. No full mode launched. At 8192, E1 failed `NO_REQUIRED_MECHANISM_CHANGE`; E2/E3 were rejected because p95 loss was `3.0033815000006143` seconds, above the 2-second gate. Standalone batching is frozen as negative evidence.
6. **What is the screening false-positive rate?** It is **not estimable**. Formal action-changing attempts are zero, so neither `0%` nor `100%` is a valid estimate. Screening support remains candidate support only.
7. **What can enter the campaign?** I1 (`{int(support["I1_source_order_swap"]["multi_ready_boundary_count"]):,}` exact source boundaries), I3 (`{int(support["I3_next_edge"]["safe_alternative_boundary_lower_bound"]):,}` conservative lower bound), and I4 (`{int(support["I4_hold_release"]["release_to_hold_boundary_lower_bound"]):,}` conservative lower bound) are supported source families. Their exact target descriptors are not committed and must be rematerialized with the exact screening binary. I2 has only one live boundary; I5 has zero strict applicable boundaries, while its `1,337` prefilters are not PIBT applicability.

## Mechanism boundary

E4 remains a frozen exact-slot safety/capability control. It is not promoted as an effective merge scheduler. The next scheduler design must retain losers as pending destination-owned requests and arbitrate at the next natural local service opportunity without reserving a second edge or reading a future route.
"""


def _churn_report(
    census: Mapping[str, Any],
    merge_summary: Mapping[str, Any],
) -> str:
    counters = census["i2_raw_counters"]
    hard = census["raw_hard_gates"]["decision_run"]
    request_rate = int(counters["merge_grant_request_count"]) / FULL_SEGMENT_COUNT
    reject_rate = (
        int(counters["merge_grant_active_grant_rejection_count"])
        / FULL_SEGMENT_COUNT
    )
    event_rate = int(hard["event_count"]) / FULL_SEGMENT_COUNT
    return f"""# G4IRSF15 merge-request churn postmortem

## Original 1x aggregate

| Metric | Value |
|---|---:|
| Completed movements (segments) | {FULL_SEGMENT_COUNT:,} |
| Merge requests | {int(counters["merge_grant_request_count"]):,} |
| Arbitration events | {int(counters["destination_merge_arbitration_event_count"]):,} |
| Active-grant rejections | {int(counters["merge_grant_active_grant_rejection_count"]):,} |
| Requests per completed movement | {request_rate:.9f} |
| Rejections per completed movement | {reject_rate:.9f} |
| Runtime events per completed movement | {event_rate:.9f} |
| Queue-capacity blocks | {int(counters["merge_grant_queue_capacity_block_count"]):,} |
| Live multi-request boundaries | {int(counters["g4irsf14_i2_live_eligible_multi_request_boundary_count"]):,} |
| Lifecycle rows dropped | {int(hard["merge_grant_lifecycle_dropped_count"]):,} |

The equality of requests and arbitrations, high active-grant rejection count, and almost absent multi-request live boundary are consistent with churn caused by immediate arbitration against an already active grant.

## Evidence availability

The original-1x destination/hour/source/goal/storage/timing/slack/retry breakdown is **NOT AVAILABLE** because the bounded passive lifecycle trace dropped rows and the committed census retained aggregate counters only. `g4irsf15_merge_request_churn.csv` contains one row per unavailable dimension to make this limitation machine-readable.

The complete Stage-D M0 144-segment lifecycle is audited separately: `{int(merge_summary["merge_grant_request_count"])}` requests, `{int(merge_summary["merge_grant_active_grant_rejection_count"])}` active-grant rejections, `{int(merge_summary["destination_merge_arbitration_event_count"])}` arbitrations, and zero dropped lifecycle rows. Its cohort contains only early, tight-slack, storage-in/out bags from hours 2--3, so it cannot estimate original-1x hotspots.

## Required campaign retention

Every selected intervention and its local lifecycle must be retained with dropped count zero. Non-target runs may retain aggregates plus deterministic min-hash samples. Shards must be streamed, compressed, atomically closed, and content-bound by a manifest. This solves evidence completeness without an unbounded in-memory trace.
"""


def generate(
    root: Path = ROOT,
    *,
    verify_binary_specs: Sequence[str] = (),
) -> dict[str, Any]:
    repository = audit_repository(root)
    input_bindings = verify_inputs(root)
    verified_roles = _verify_binary_arguments(verify_binary_specs)

    baseline = _read_json(root, G14_BASELINE)
    f2 = _read_json(root, G14_F2)
    census = _read_json(root, G14_CENSUS)
    merge_config = _read_json(root, G14_MERGE_CONFIG)
    if census["binary"]["sha256"] != BINARY_SHA256[
        "e4_original_1x_screening"
    ]:
        raise StageABError("CENSUS_BINARY_IDENTITY_MISMATCH")
    if merge_config["binary"]["sha256"] != BINARY_SHA256[
        "e4_stage_d_mechanism"
    ]:
        raise StageABError("MERGE_CONFIG_BINARY_IDENTITY_MISMATCH")
    if f2["final_runtime_identity"]["binary"]["file_sha256"] != BINARY_SHA256[
        "f2_frozen_control"
    ]:
        raise StageABError("F2_BINARY_IDENTITY_MISMATCH")

    merge_summary = merge_config["runs"]["M0"]["summary_projection"]
    merge_summary = {
        **merge_summary,
        **merge_config["runs"]["M0"]["metrics"],
    }
    context = _load_context(root)
    (
        lifecycle_rows,
        requests,
        rejected,
        issued,
        fifo_wait,
        transitions,
    ) = _m0_lifecycle(root)

    churn_rows = build_churn_rows(
        census,
        merge_summary,
        context,
        lifecycle_rows,
        requests,
        rejected,
        issued,
        fifo_wait,
        transitions,
    )
    hotspot_rows = build_hotspot_rows(requests, rejected, issued, fifo_wait)
    screening_rows = build_screening_rows(census)

    reports = {
        START_REPORT: _start_report(repository, census),
        POSTMORTEM_REPORT: _postmortem_report(census),
        CHURN_REPORT: _churn_report(census, merge_summary),
    }
    for relative, text in reports.items():
        _atomic_write(root / relative, text.encode("utf-8"))
    _atomic_write(root / CHURN_TABLE, _csv_bytes(CHURN_FIELDS, churn_rows))
    _atomic_write(
        root / HOTSPOT_TABLE,
        _csv_bytes(HOTSPOT_FIELDS, hotspot_rows),
    )
    _atomic_write(
        root / SCREENING_TABLE,
        _csv_bytes(SCREENING_FIELDS, screening_rows),
    )

    f2_control = _signed_json(
        {
            "schema": "czr005.g4irsf15.f2_frozen_control.v1",
            "status": "PASS_FROZEN_BY_CONTENT_BINDING",
            "candidate_id": "G4IRSF15_F2_FROZEN_CONTROL",
            "copy_semantics": (
                "selected immutable projection plus predecessor content "
                "binding; predecessor file is not rewritten"
            ),
            "predecessor": input_bindings[G14_F2.as_posix()],
            "binary": _binary_ledger()["f2_frozen_control"],
            "configuration": f2["configuration"],
            "comparators": f2["comparators"],
            "hard_gates": f2["hard_gates"],
            "protected_inputs": {
                "map": input_bindings[MAP_PATH.as_posix()],
                "task": input_bindings[TASK_PATH.as_posix()],
            },
            "claim_boundary": f2["claim_boundary"],
        }
    )
    _atomic_write(root / F2_CONTROL, _json_bytes(f2_control))

    e4_control = _signed_json(
        {
            "schema": "czr005.g4irsf15.e4_frozen_mechanism_control.v1",
            "status": "FROZEN_CAPABILITY_CONTROL_WITH_NEGATIVE_EVIDENCE",
            "mechanism_id": "G4IRSF14_E4_EXACT_SLOT_MERGE_GRANT_V1",
            "copy_semantics": (
                "selected immutable projection plus predecessor content "
                "bindings; no G4IRSF14 file is rewritten"
            ),
            "binary_ledger": _binary_ledger(),
            "frozen_controls": census["frozen_controls"],
            "original_1x_counters": {
                **census["i2_raw_counters"],
                "event_count": census["raw_hard_gates"]["decision_run"][
                    "event_count"
                ],
                "merge_grant_lifecycle_dropped_count": census[
                    "raw_hard_gates"
                ]["decision_run"]["merge_grant_lifecycle_dropped_count"],
            },
            "stage_d_m0_counters": {
                "completed_segment_count": 144,
                "merge_grant_request_count": len(requests),
                "merge_grant_active_grant_rejection_count": len(rejected),
                "destination_merge_arbitration_event_count": int(
                    merge_summary[
                        "destination_merge_arbitration_event_count"
                    ]
                ),
                "merge_grant_lifecycle_transition_count": len(
                    lifecycle_rows
                ),
                "merge_grant_lifecycle_dropped_count": int(
                    merge_summary["merge_grant_lifecycle_dropped_count"]
                ),
                "merge_grant_peak_pending_requests": int(
                    merge_summary["merge_grant_peak_pending_requests"]
                ),
            },
            "screening": {
                "formal_complete_causal_labels": 0,
                "h_system_pairs": 0,
                "i1_source_order_support": census["support"][
                    "I1_source_order_swap"
                ]["multi_ready_boundary_count"],
                "i2_live_multi_request_support": census["support"][
                    "I2_merge_request_order_swap"
                ]["eligible_live_multi_request_boundary_count"],
                "i3_next_edge_lower_bound": census["support"][
                    "I3_next_edge"
                ]["safe_alternative_boundary_lower_bound"],
                "i4_hold_release_lower_bound": census["support"][
                    "I4_hold_release"
                ]["release_to_hold_boundary_lower_bound"],
                "i5_prefilter_count": census["support"][
                    "I5_pibt_trigger"
                ]["prefilter_candidate_count"],
                "i5_strict_applicable_count": census["support"][
                    "I5_pibt_trigger"
                ]["applicable_ready_slice_boundary_count"],
            },
            "negative_evidence": {
                "request_equals_arbitration_count": True,
                "persistent_pending_queue_supported": False,
                "event_microphase_executed_case_count": 20,
                "event_microphase_full_mode_launched": False,
                "best_8192_batched_mode": None,
                "blockers": (
                    "NO_REQUIRED_MECHANISM_CHANGE",
                    "P95_LOSS_GT_2S",
                ),
                "screening_false_positive_rate_estimate": None,
                "screening_false_positive_estimate_status": (
                    "NOT_ESTIMABLE_ZERO_ACTION_CHANGING_TRIALS"
                ),
            },
            "input_bindings": {
                path: input_bindings[path]
                for path in (
                    G14_CLONE.as_posix(),
                    G14_CENSUS.as_posix(),
                    G14_MERGE_CONFIG.as_posix(),
                    G14_MERGE_RULE.as_posix(),
                    G14_LIFECYCLE.as_posix(),
                    G14_EVENT_TABLE.as_posix(),
                    G14_EVENT_REPORT.as_posix(),
                )
            },
            "output_bindings": {
                path.as_posix(): _output_binding(root, path)
                for path in (
                    POSTMORTEM_REPORT,
                    CHURN_REPORT,
                    CHURN_TABLE,
                    HOTSPOT_TABLE,
                    SCREENING_TABLE,
                )
            },
            "claim_boundary": (
                "exact-slot safety/capability control only; not an effective "
                "merge scheduler and not causal-label evidence"
            ),
        }
    )
    _atomic_write(root / E4_CONTROL, _json_bytes(e4_control))

    baseline_registry = _signed_json(
        {
            "schema": "czr005.g4irsf15.baseline_registry.v1",
            "status": "PASS_STAGE_15AB_EVIDENCE_FREEZE",
            "phase": "G4IRSF15-A/B",
            "repository": repository,
            "protected_inputs": {
                "map": input_bindings[MAP_PATH.as_posix()],
                "task": input_bindings[TASK_PATH.as_posix()],
            },
            "predecessor_registry": input_bindings[
                G14_BASELINE.as_posix()
            ],
            "controls": {
                F2_CONTROL.as_posix(): _output_binding(root, F2_CONTROL),
                E4_CONTROL.as_posix(): _output_binding(root, E4_CONTROL),
            },
            "reports": {
                path.as_posix(): _output_binding(root, path)
                for path in (START_REPORT, POSTMORTEM_REPORT, CHURN_REPORT)
            },
            "frozen_outcome": {
                "g4irsf14_decision": "PARTIAL_WITH_EXPLICIT_BLOCKER",
                "formal_complete_causal_label_count": 0,
                "h_system_pair_count": 0,
                "training_authorized": False,
                "scale_execution_count": 0,
            },
            "governance": {
                "namespace": "g4irsf15_",
                "sealed_g4irsf12_to_g4irsf14_artifacts_rewritten": False,
                "protected_map_or_task_rewritten": False,
                "binary_binding": "sha256_content_address",
                "github_actions_status": (
                    "NOT_BOUND_AT_GENERATION_REQUIRES_POST_PUSH_EVIDENCE"
                ),
            },
        }
    )
    _atomic_write(root / BASELINE_REGISTRY, _json_bytes(baseline_registry))

    source_rows = {
        row["intervention_kind"]: row for row in screening_rows
    }
    manifest = _signed_json(
        {
            "schema": "czr005.g4irsf15.campaign_source_manifest.v1",
            "status": (
                "SOURCE_FAMILIES_AUDITED_TARGET_DESCRIPTORS_NOT_MATERIALIZED"
            ),
            "formal_campaign_authorized": False,
            "target_descriptor_count": 0,
            "causal_label_count": 0,
            "complete_h_bag_count": 0,
            "complete_h_system_count": 0,
            "exact_binary_requirement": _binary_ledger()[
                "e4_original_1x_screening"
            ],
            "source_families": {
                kind: {
                    "screening_support_count": int(
                        row["screening_support_count"]
                    ),
                    "prefilter_count": (
                        int(row["prefilter_count"])
                        if row["prefilter_count"]
                        else 0
                    ),
                    "status": row["campaign_source_status"],
                    "source_screening_manifest_sha256": row[
                        "source_screening_manifest_sha256"
                    ],
                    "blocker": row["blocker"],
                }
                for kind, row in sorted(source_rows.items())
            },
            "retention_contract": {
                "selected_target_local_lifecycle": "FULL",
                "selected_target_dropped_count_required": 0,
                "non_target_retention": (
                    "AGGREGATES_PLUS_DETERMINISTIC_MINHASH_SAMPLE"
                ),
                "shard_write": "STREAM_COMPRESS_ATOMIC_CLOSE",
                "manifest_binding": "SHA256_EXACT_BYTES",
                "unbounded_in_memory_trace_allowed": False,
            },
            "evidence_limitations": {
                "original_1x_request_breakdown_available": False,
                "missing_dimensions": list(UNAVAILABLE_FULL_BREAKDOWNS),
                "committed_exact_target_rows_available": False,
                "screening_false_positive_rate_estimable": False,
                "stage_d_144_extrapolation_to_original_1x_allowed": False,
                "required_next_action": (
                    "rematerialize exact I1/I3/I4 target descriptors with "
                    "the exact screening binary, then execute same-state "
                    "action-changing H_bag/H_system pairs"
                ),
            },
            "input_bindings": input_bindings,
            "output_bindings": {
                path.as_posix(): _output_binding(root, path)
                for path in OUTPUT_PATHS
                if path != CAMPAIGN_MANIFEST
            },
            "generation_binary_verification": {
                "verification_is_log_only_not_a_portability_dependency": True,
                "roles_verified_in_this_invocation": list(verified_roles),
            },
        }
    )
    _atomic_write(root / CAMPAIGN_MANIFEST, _json_bytes(manifest))
    return {
        "status": "PASS_STAGE_15AB_GENERATED",
        "output_count": len(OUTPUT_PATHS),
        "verified_binary_roles": list(verified_roles),
        "manifest_self_sha256": manifest["self_sha256"],
    }


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="run the independent validator without publishing",
    )
    parser.add_argument(
        "--verify-binary",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help=(
            "verify exact external binary bytes; required once for each of "
            + ", ".join(sorted(BINARY_SHA256))
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    root = arguments.root.resolve()
    try:
        if arguments.validate_only:
            if arguments.verify_binary:
                raise StageABError(
                    "--verify-binary is invalid with --validate-only"
                )
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from scripts import (  # noqa: PLC0415
                validate_g4irsf15_stage_ab_freeze as validator,
            )

            result = validator.validate_stage_ab(root)
        else:
            result = generate(
                root,
                verify_binary_specs=arguments.verify_binary,
            )
    except (OSError, ValueError, KeyError, StageABError) as exc:
        print(f"G4IRSF15 Stage 15A/15B: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
