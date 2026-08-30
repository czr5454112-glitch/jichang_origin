#!/usr/bin/env python3
"""Run the V3R12 Nanning P0 outcome-informed engineering canary.

This module deliberately does not describe its cohort as outcome-blind.  The
62-row slice is a diagnostic canary selected after inspecting the terminal
V3R11 non-overlap result.  It may establish that the real G32 path can be
exercised safely, but it is not a replacement estimand or a new formal sample.

V3R7 control and V3R11 synthetic artifacts remain immutable historical inputs.
The active V3R12 control revision is therefore kept distinct from the V3R7
historical revision recorded by the already-passing V3R11 prerequisite.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_workload as workload31  # noqa: E402
from scripts.eval import run_g4irsf32_v3r3_nanning_p0_selection as historical  # noqa: E402


SCHEMA = "czr005.g4irsf32.nanning_p0_engineering_canary_control.v3r12"
SHADOW_GATE_SCHEMA = (
    "czr005.g4irsf32.nanning_p0_engineering_canary_shadow_gate.v3r12"
)
PROTOCOL_ID = "G4IRSF32_V3R12_ARRIVAL_COVERED_NANNING_P0_ADDENDUM_20260829"
CONTROL_REVISION_ID = (
    "G4IRSF32_V3R12_OUTCOME_INFORMED_ENGINEERING_CANARY_CONTROL_20260829"
)
CAMPAIGN_REVISION_ID = (
    "G4IRSF32_V3R12_OUTCOME_INFORMED_ENGINEERING_CANARY_SHADOW_20260829"
)
HISTORICAL_CONTROL_REVISION_ID = historical.CONTROL_REVISION_ID
PREREQUISITE_SYNTHETIC_REVISION_ID = historical.SYNTHETIC_REVISION_ID
PREREQUISITE_CAMPAIGN_REVISION_ID = historical.CAMPAIGN_REVISION_ID

PASS = "PASS_V3R12_NANNING_P0_ENGINEERING_CANARY_CONTROL"
NO_EVENT = "NO_GO_V3R12_NANNING_P0_ENGINEERING_CANARY_CONTROL_NO_EVENT"
NO_GO = "NO_GO_V3R12_NANNING_P0_ENGINEERING_CANARY_CONTROL_AUDIT_FAILED"
SHADOW_PASS = "PASS_V3R12_NANNING_P0_ENGINEERING_CANARY_SHADOW"
SHADOW_NO_EVENT = "NO_GO_V3R12_NANNING_P0_ENGINEERING_CANARY_NOT_OBSERVED"
SHADOW_NO_GO = "NO_GO_V3R12_NANNING_P0_ENGINEERING_CANARY_SHADOW_GATE"

SELECTOR_ALGORITHM_ID = "FIXED_V3R11_DIAGNOSTIC_CANARY_68400_RANK60_V1"
SELECTION_BASIS = "outcome_informed_engineering_canary"
SELECTION_ROLE = "ENGINEERING_EXISTENCE_CANARY_NOT_EFFECT_ESTIMATE"
DIAGNOSTIC_ORIGIN = "V3R11_TERMINAL_NON_OVERLAP_BOUNDED_DIAGNOSTIC_REPLAY"
SELECTOR_RULE = (
    "from each validated frozen workload, canonically order the external "
    "start-53 storage_out burst at pass_time=68400 by "
    "(pass_time,segment_id,task_id) and take its first 61 rows; compute the "
    "first external arrival as 68400+0.001+60.1 and the rank-60 commit as "
    "68400+0.001+60; among local start-49 rows strictly inside "
    "(first_arrival-1,rank60_commit), take the canonical earliest row and "
    "require it to be 25195:direct; this is an outcome-informed engineering "
    "canary and is not eligible as an outcome-blind formal cohort"
)

EXTERNAL_RELEASE = 68_400.0
EXTERNAL_PREFIX_COUNT = 61
EXTERNAL_COMMIT_RANK = 60
EXTERNAL_RELEASE_MULTIPLICITY = 155
LOCAL_SEGMENT_ID = "25195:direct"
LOCAL_TASK_ID = 25_195
FIRST_EXTERNAL_ARRIVAL = (
    EXTERNAL_RELEASE
    + historical.EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
    + historical.EXTERNAL_53_TO_49_TRAVEL_SECONDS
)
RANK60_COMMIT = (
    EXTERNAL_RELEASE
    + historical.EXTERNAL_FIRST_ENTRY_OFFSET_SECONDS
    + EXTERNAL_COMMIT_RANK * historical.NODE49_SERVICE_SECONDS
)
LOCAL_WINDOW_OPEN = FIRST_EXTERNAL_ARRIVAL - historical.NODE49_SERVICE_SECONDS
LOCAL_WINDOW_CLOSE = RANK60_COMMIT
EXPECTED_SELECTED_COUNT = EXTERNAL_PREFIX_COUNT + 1

EXPECTED_EXTERNAL_SEGMENT_IDS = (
    "19934:storage_out",
    "20091:storage_out",
    "20174:storage_out",
    "20261:storage_out",
    "20468:storage_out",
    "20539:storage_out",
    "20649:storage_out",
    "20672:storage_out",
    "20868:storage_out",
    "21038:storage_out",
    "21079:storage_out",
    "21317:storage_out",
    "21337:storage_out",
    "21628:storage_out",
    "21740:storage_out",
    "21858:storage_out",
    "21895:storage_out",
    "21998:storage_out",
    "22098:storage_out",
    "22143:storage_out",
    "22190:storage_out",
    "22191:storage_out",
    "22192:storage_out",
    "22193:storage_out",
    "22196:storage_out",
    "22197:storage_out",
    "22198:storage_out",
    "22199:storage_out",
    "22206:storage_out",
    "22221:storage_out",
    "22225:storage_out",
    "22233:storage_out",
    "22277:storage_out",
    "22291:storage_out",
    "22324:storage_out",
    "22367:storage_out",
    "22463:storage_out",
    "22494:storage_out",
    "22506:storage_out",
    "22509:storage_out",
    "22648:storage_out",
    "22699:storage_out",
    "22717:storage_out",
    "22722:storage_out",
    "22727:storage_out",
    "22732:storage_out",
    "22787:storage_out",
    "22846:storage_out",
    "22847:storage_out",
    "22851:storage_out",
    "22895:storage_out",
    "22910:storage_out",
    "22913:storage_out",
    "22943:storage_out",
    "23032:storage_out",
    "23040:storage_out",
    "23051:storage_out",
    "23057:storage_out",
    "23058:storage_out",
    "23075:storage_out",
    "23076:storage_out",
)
EXPECTED_SELECTED_SEGMENT_IDS = (*EXPECTED_EXTERNAL_SEGMENT_IDS, LOCAL_SEGMENT_ID)

PROFILE_PATH = historical.PROFILE_PATH
SOURCE_TIMETABLE_PATH = historical.SOURCE_TIMETABLE_PATH
MANIFEST_DIR = historical.MANIFEST_DIR
G31_BINARY = historical.G31_BINARY
OUTPUT_PATH = (
    ROOT / "outputs/tables/g4irsf32_v3r12_nanning_p0_control_selection.json"
)

Executor = Callable[..., Mapping[str, Any]]
SelectionError = historical.SelectionError


def _canonical_row_key(row: Mapping[str, Any]) -> tuple[float, str, int]:
    return (
        historical._finite(row.get("pass_time"), "row.pass_time"),
        str(row.get("segment_id", "")),
        historical._integer(row.get("task_id"), "row.task_id"),
    )


def _selected_identity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": str(row.get("segment_id", "")),
            "task_id": historical._integer(row.get("task_id"), "row.task_id"),
        }
        for row in rows
    ]


def select_engineering_canary(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select the fixed diagnostic slice without claiming outcome blindness."""

    external_burst = sorted(
        (
            row
            for row in rows
            if row.get("start") == historical.EXTERNAL_START
            and row.get("leg") == "storage_out"
            and str(row.get("segment_id", "")).endswith(":storage_out")
            and historical._finite(row.get("pass_time"), "external.pass_time")
            == EXTERNAL_RELEASE
        ),
        key=_canonical_row_key,
    )
    if len(external_burst) < EXTERNAL_PREFIX_COUNT:
        raise SelectionError("68400 external burst has fewer than 61 rows")
    if len({str(row.get("segment_id")) for row in external_burst}) != len(
        external_burst
    ):
        raise SelectionError("68400 external burst identities are not unique")

    window_locals = sorted(
        (
            row
            for row in rows
            if row.get("start") == historical.LOCAL_START
            and LOCAL_WINDOW_OPEN
            < historical._finite(row.get("pass_time"), "local.pass_time")
            < LOCAL_WINDOW_CLOSE
        ),
        key=_canonical_row_key,
    )
    if not window_locals:
        raise SelectionError("rank-60 arrival/commit window has no local row")
    local = window_locals[0]
    if (
        local.get("segment_id") != LOCAL_SEGMENT_ID
        or local.get("task_id") != LOCAL_TASK_ID
    ):
        raise SelectionError(
            "canonical earliest local row in the diagnostic window is not "
            f"{LOCAL_SEGMENT_ID}"
        )

    selected = sorted(
        (dict(row) for row in [*external_burst[:EXTERNAL_PREFIX_COUNT], local]),
        key=_canonical_row_key,
    )
    segment_ids = [str(row.get("segment_id")) for row in selected]
    if len(selected) != EXPECTED_SELECTED_COUNT or len(set(segment_ids)) != len(
        segment_ids
    ):
        raise SelectionError("engineering canary selection identity is invalid")
    return (
        {
            "selector_algorithm_id": SELECTOR_ALGORITHM_ID,
            "rule": SELECTOR_RULE,
            "selection_basis": SELECTION_BASIS,
            "selection_role": SELECTION_ROLE,
            "diagnostic_origin": DIAGNOSTIC_ORIGIN,
            "selection_outcome_blind": False,
            "formal_inference_eligible": False,
            "engineering_canary_only": True,
            "external_release": EXTERNAL_RELEASE,
            "external_release_multiplicity": len(external_burst),
            "external_prefix_count": EXTERNAL_PREFIX_COUNT,
            "external_commit_rank": EXTERNAL_COMMIT_RANK,
            "rank60_commit_time": RANK60_COMMIT,
            "first_external_arrival_time": FIRST_EXTERNAL_ARRIVAL,
            "local_window_open": LOCAL_WINDOW_OPEN,
            "local_window_close": LOCAL_WINDOW_CLOSE,
            "local_window_candidate_count": len(window_locals),
            "local_segment_id": LOCAL_SEGMENT_ID,
            "local_task_id": LOCAL_TASK_ID,
            "local_release": historical._finite(
                local.get("pass_time"), "local.pass_time"
            ),
            "external_selected_count": EXTERNAL_PREFIX_COUNT,
            "local_selected_count": 1,
            "selected_segment_count": EXPECTED_SELECTED_COUNT,
            "selected_identity": _selected_identity(selected),
        },
        selected,
    )


def regenerate_and_select(
    temporary_root: Path,
    *,
    source_raw_path: Path = SOURCE_TIMETABLE_PATH,
    map_profile_path: Path = PROFILE_PATH,
    manifest_dir: Path = MANIFEST_DIR,
) -> dict[int, dict[str, Any]]:
    """Regenerate both frozen workloads and extract the same identity slice."""

    result: dict[int, dict[str, Any]] = {}
    identities: dict[int, list[dict[str, Any]]] = {}
    for scale in (1, 2):
        output_dir = temporary_root / f"{scale}x"
        generated = workload31.build_workload(
            scale=scale,
            source_raw_path=source_raw_path,
            map_profile_path=map_profile_path,
            output_dir=output_dir,
        )
        generated_manifest_path = output_dir / f"nanning_{scale}x_manifest.json"
        generated_manifest = historical._mapping(
            historical.read_strict_json(generated_manifest_path),
            "generated manifest",
        )
        if generated_manifest != generated:
            raise SelectionError("returned and written regenerated manifests differ")
        frozen_manifest_path = manifest_dir / f"nanning_{scale}x_manifest.json"
        frozen_manifest = historical._mapping(
            historical.read_strict_json(frozen_manifest_path), "frozen manifest"
        )
        canonical_path = output_dir / f"nanning_{scale}x_canonical.jsonl"
        raw_path = output_dir / f"nanning_{scale}x_raw.txt"
        rows = historical._read_jsonl(canonical_path)
        validation = historical.validate_regenerated_workload(
            scale, generated_manifest, rows, frozen_manifest
        )
        cohort, original_rows = select_engineering_canary(rows)
        selected_rows, projection_identity = historical.project_selected_rows(
            original_rows
        )
        identities[scale] = _selected_identity(original_rows)
        result[scale] = {
            "scale": scale,
            "workload": {
                "validation": validation,
                "frozen_manifest_sha256": historical.file_sha256(
                    frozen_manifest_path
                ),
                "regenerated_manifest_sha256": historical.file_sha256(
                    generated_manifest_path
                ),
                "regenerated_manifest_semantics_sha256": (
                    historical.canonical_sha256(
                        historical._manifest_semantics(generated_manifest)
                    )
                ),
                "regenerated_raw_sha256": historical.file_sha256(raw_path),
                "regenerated_canonical_jsonl_sha256": historical.file_sha256(
                    canonical_path
                ),
                "regenerated_ordered_rows_sha256": historical.canonical_sha256(
                    rows
                ),
            },
            "selection": {
                **cohort,
                "original_selected_rows": original_rows,
                "selected_rows": selected_rows,
                "projection_identity": projection_identity,
            },
        }
    if identities[1] != identities[2]:
        raise SelectionError("1x/2x selected segment/task identities differ")
    return result


def _scenario(scale: int) -> str:
    if scale not in (1, 2):
        raise SelectionError("canary request scale must be 1 or 2")
    return f"g4irsf32_v3r12_nanning_p0_canary_{scale}x"


def build_g31_control_request(
    scale: int,
    selected_rows: Sequence[Mapping[str, Any]],
    *,
    binary: Path = G31_BINARY,
    map_profile_path: Path = PROFILE_PATH,
    auditor: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an exact omitted/default-off request for the 62-row canary."""

    if len(selected_rows) != EXPECTED_SELECTED_COUNT:
        raise SelectionError("canary control request requires exactly 62 rows")
    selected_auditor = auditor or historical._v3_auditor()
    profile = map_adapter.load_map_profile(
        map_profile_path, storage_source_nodes=[historical.EXTERNAL_START]
    )
    request, potential = map_adapter.build_s4_request(
        profile,
        selected_rows,
        binary=binary,
        scenario=_scenario(scale),
        max_events=2_000_000,
        max_simulation_time=-1.0,
        trace_limit=historical.TRACE_LIMIT,
        event_trace_limit=historical.TRACE_LIMIT,
        summary_only=False,
        edge_speed_mps=historical.SPEED_MPS,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    request.update(fault_windows=[])
    ordinary_projection = {
        key: value
        for key, value in selected_auditor.REQUEST_PROJECTION.items()
        if key != "source_aware_destination_service_trace_limit"
    }
    mismatches = {
        key: {"expected": value, "actual": request.get(key)}
        for key, value in ordinary_projection.items()
        if request.get(key) != value
    }
    if mismatches:
        raise SelectionError(f"G31 canary request projection drift: {mismatches}")
    expected_keys = (
        set(ordinary_projection)
        | (
            set(selected_auditor.REQUEST_DATA_KEYS)
            - {"source_aware_destination_service_mode"}
        )
        | set(selected_auditor.REQUEST_BINARY_LOCATOR_KEYS)
    )
    if set(request) != expected_keys:
        raise SelectionError("G31 canary request is not exact omitted/default-off")
    if any(str(key).startswith(selected_auditor.NS) for key in request):
        raise SelectionError("G31 canary request contains G32 keys")
    if request.get("storage_source_nodes") != [historical.EXTERNAL_START]:
        raise SelectionError("G31 canary storage role must be exactly [53]")
    if request.get("scenario") != _scenario(scale):
        raise SelectionError("G31 canary scenario identity changed")
    if request.get("retry_interval") != historical.SOURCE_RETRY_INTERVAL_SECONDS:
        raise SelectionError("G31 canary retry interval changed")
    return request, potential


def audit_g31_control_payload(
    *,
    scale: int,
    selected_rows: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    payload: Mapping[str, Any],
    expected_binary_sha256: str = historical.FROZEN_SOURCE_HASHES[G31_BINARY],
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Reuse the strict G31 payload audit and translate only revision status."""

    result = dict(
        historical.audit_g31_control_payload(
            scale=scale,
            selected_rows=selected_rows,
            request=request,
            payload=payload,
            expected_binary_sha256=expected_binary_sha256,
            auditor=auditor,
        )
    )
    result["status"] = (
        PASS
        if result.get("pass") is True
        else NO_EVENT
        if result.get("status") == historical.NO_EVENT
        else NO_GO
    )
    return result


def _validate_selection_evidence(
    scale: int, value: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    expected_keys = {
        "selector_algorithm_id",
        "rule",
        "selection_basis",
        "selection_role",
        "diagnostic_origin",
        "selection_outcome_blind",
        "formal_inference_eligible",
        "engineering_canary_only",
        "external_release",
        "external_release_multiplicity",
        "external_prefix_count",
        "external_commit_rank",
        "rank60_commit_time",
        "first_external_arrival_time",
        "local_window_open",
        "local_window_close",
        "local_window_candidate_count",
        "local_segment_id",
        "local_task_id",
        "local_release",
        "external_selected_count",
        "local_selected_count",
        "selected_segment_count",
        "selected_identity",
        "original_selected_rows",
        "selected_rows",
        "projection_identity",
    }
    historical._exact_keys(value, expected_keys, f"{scale}x.selection")
    original = historical._rows(
        value.get("original_selected_rows"), f"{scale}x.original rows"
    )
    projected = historical._rows(
        value.get("selected_rows"), f"{scale}x.projected rows"
    )
    identity = historical._rows(
        value.get("projection_identity"), f"{scale}x.projection identity"
    )
    canonical = sorted((dict(row) for row in original), key=_canonical_row_key)
    selected_identity = _selected_identity(original)
    external = original[:EXTERNAL_PREFIX_COUNT]
    local = original[-1:]
    reprojection, reidentity = historical.project_selected_rows(original)
    semantics = (
        value.get("selector_algorithm_id") == SELECTOR_ALGORITHM_ID
        and value.get("rule") == SELECTOR_RULE
        and value.get("selection_basis") == SELECTION_BASIS
        and value.get("selection_role") == SELECTION_ROLE
        and value.get("diagnostic_origin") == DIAGNOSTIC_ORIGIN
        and value.get("selection_outcome_blind") is False
        and value.get("formal_inference_eligible") is False
        and value.get("engineering_canary_only") is True
        and value.get("external_release") == EXTERNAL_RELEASE
        and value.get("external_release_multiplicity")
        == EXTERNAL_RELEASE_MULTIPLICITY
        and value.get("external_prefix_count") == EXTERNAL_PREFIX_COUNT
        and value.get("external_commit_rank") == EXTERNAL_COMMIT_RANK
        and value.get("rank60_commit_time") == RANK60_COMMIT
        and value.get("first_external_arrival_time") == FIRST_EXTERNAL_ARRIVAL
        and value.get("local_window_open") == LOCAL_WINDOW_OPEN
        and value.get("local_window_close") == LOCAL_WINDOW_CLOSE
        and value.get("local_window_candidate_count") == 1
        and value.get("local_segment_id") == LOCAL_SEGMENT_ID
        and value.get("local_task_id") == LOCAL_TASK_ID
        and value.get("external_selected_count") == EXTERNAL_PREFIX_COUNT
        and value.get("local_selected_count") == 1
        and value.get("selected_segment_count") == EXPECTED_SELECTED_COUNT
        and value.get("selected_identity") == selected_identity
        and original == canonical
        and len(original) == EXPECTED_SELECTED_COUNT
        and len(projected) == EXPECTED_SELECTED_COUNT
        and len(identity) == EXPECTED_SELECTED_COUNT
        and tuple(row["segment_id"] for row in selected_identity)
        == EXPECTED_SELECTED_SEGMENT_IDS
        and all(
            row.get("start") == historical.EXTERNAL_START
            and row.get("leg") == "storage_out"
            and row.get("pass_time") == EXTERNAL_RELEASE
            for row in external
        )
        and len(local) == 1
        and local[0].get("start") == historical.LOCAL_START
        and local[0].get("segment_id") == LOCAL_SEGMENT_ID
        and local[0].get("task_id") == LOCAL_TASK_ID
        and value.get("local_release") == local[0].get("pass_time")
        and LOCAL_WINDOW_OPEN < value.get("local_release") < LOCAL_WINDOW_CLOSE
        and reprojection == projected
        and reidentity == identity
    )
    if not semantics:
        raise SelectionError(f"{scale}x engineering canary selection changed")
    return projected


def _validate_selections_for_execution(
    selections: Mapping[int, Mapping[str, Any]],
) -> None:
    if set(selections) != {1, 2}:
        raise SelectionError("regeneration must return exact 1x/2x selections")
    identities: dict[int, Any] = {}
    for scale in (1, 2):
        item = historical._mapping(selections[scale], f"{scale}x selection")
        historical._exact_keys(item, {"scale", "workload", "selection"}, f"{scale}x")
        if item.get("scale") != scale:
            raise SelectionError(f"{scale}x scale identity changed")
        historical._validate_workload_evidence(
            scale, historical._mapping(item.get("workload"), f"{scale}x.workload")
        )
        selected = historical._mapping(item.get("selection"), f"{scale}x.selection")
        _validate_selection_evidence(scale, selected)
        identities[scale] = selected.get("selected_identity")
    if identities[1] != identities[2]:
        raise SelectionError("1x/2x canary segment/task identities differ")


def run_control_selection(
    *,
    executor: Executor | None = None,
    binary: Path = G31_BINARY,
    map_profile_path: Path = PROFILE_PATH,
    source_raw_path: Path = SOURCE_TIMETABLE_PATH,
    manifest_dir: Path = MANIFEST_DIR,
) -> dict[str, Any]:
    """Regenerate, select, and execute the two exact-off G31 canaries."""

    binary = historical._validate_frozen_g31_binary_argument(binary)
    auditor = historical._v3_auditor()
    selected_executor = executor
    if selected_executor is None:
        from czr005.cpp_backend import g4irsf11_event_runtime_from_records

        selected_executor = g4irsf11_event_runtime_from_records
    with tempfile.TemporaryDirectory(prefix="g4irsf32_v3r12_canary_") as name:
        selections = regenerate_and_select(
            Path(name),
            source_raw_path=source_raw_path,
            map_profile_path=map_profile_path,
            manifest_dir=manifest_dir,
        )
        _validate_selections_for_execution(selections)
        scales: dict[str, Any] = {}
        for scale in (1, 2):
            item = selections[scale]
            rows = historical._rows(
                item["selection"]["selected_rows"], f"{scale}x selected rows"
            )
            try:
                request, potential = build_g31_control_request(
                    scale,
                    rows,
                    binary=binary,
                    map_profile_path=map_profile_path,
                    auditor=auditor,
                )
                payload = selected_executor(**request)
                if not isinstance(payload, Mapping):
                    raise SelectionError("G31 canary executor did not return an object")
                audit = audit_g31_control_payload(
                    scale=scale,
                    selected_rows=rows,
                    request=request,
                    payload=payload,
                    auditor=auditor,
                )
                scales[f"{scale}x"] = {
                    **item,
                    "request": historical._portable(request),
                    "request_sha256": auditor.request_sha256(request),
                    "ordinary_request_sha256": auditor.ordinary_request_sha256(
                        request
                    ),
                    "profile_sha256": auditor.profile_sha256(request),
                    "potential_sha256": historical.canonical_sha256(
                        request["heuristic_time"]
                    ),
                    "potential_contract": potential,
                    "control": historical._control_evidence(payload, audit, auditor),
                    "pass": audit["pass"],
                    "status": audit["status"],
                }
            except Exception as error:
                scales[f"{scale}x"] = {
                    **item,
                    "pass": False,
                    "status": NO_GO,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
                break
    attempted = set(scales) == {"1x", "2x"}
    passed = attempted and all(scales[name].get("pass") is True for name in scales)
    no_event_only = attempted and any(
        scales[name].get("status") == NO_EVENT for name in scales
    ) and all(scales[name].get("status") in {PASS, NO_EVENT} for name in scales)
    status = PASS if passed else NO_EVENT if no_event_only else NO_GO
    return historical.with_content_hash(
        {
            "schema": SCHEMA,
            "protocol_id": PROTOCOL_ID,
            "control_revision_id": CONTROL_REVISION_ID,
            "historical_control_revision_id": HISTORICAL_CONTROL_REVISION_ID,
            "status": status,
            "pass": passed,
            "g32_executed": False,
            "selection_basis": SELECTION_BASIS,
            "selection_role": SELECTION_ROLE,
            "diagnostic_origin": DIAGNOSTIC_ORIGIN,
            "selection_outcome_blind": False,
            "formal_inference_eligible": False,
            "scales": scales,
        }
    )


def _validate_control_artifact_mapping(
    value: Mapping[str, Any], *, auditor: Any | None = None
) -> dict[str, Any]:
    """Deeply rebuild the active control request and replay both G31 payloads."""

    loaded = deepcopy(dict(value))
    historical._exact_keys(
        loaded,
        {
            "schema",
            "protocol_id",
            "control_revision_id",
            "historical_control_revision_id",
            "status",
            "pass",
            "g32_executed",
            "selection_basis",
            "selection_role",
            "diagnostic_origin",
            "selection_outcome_blind",
            "formal_inference_eligible",
            "scales",
            "artifact_content_sha256",
        },
        "V3R12 control artifact",
    )
    historical.verify_content_hash(loaded)
    if (
        loaded.get("schema") != SCHEMA
        or loaded.get("protocol_id") != PROTOCOL_ID
        or loaded.get("control_revision_id") != CONTROL_REVISION_ID
        or loaded.get("historical_control_revision_id")
        != HISTORICAL_CONTROL_REVISION_ID
        or loaded.get("control_revision_id")
        == loaded.get("historical_control_revision_id")
        or loaded.get("status") != PASS
        or loaded.get("pass") is not True
        or loaded.get("g32_executed") is not False
        or loaded.get("selection_basis") != SELECTION_BASIS
        or loaded.get("selection_role") != SELECTION_ROLE
        or loaded.get("diagnostic_origin") != DIAGNOSTIC_ORIGIN
        or loaded.get("selection_outcome_blind") is not False
        or loaded.get("formal_inference_eligible") is not False
    ):
        raise SelectionError("V3R12 active/historical control binding is invalid")

    selected_auditor = auditor or historical._v3_auditor()
    scales = historical._mapping(loaded.get("scales"), "control.scales")
    if set(scales) != {"1x", "2x"}:
        raise SelectionError("V3R12 control must contain exact 1x/2x scales")
    identities: dict[int, Any] = {}
    for scale, name in ((1, "1x"), (2, "2x")):
        item = historical._mapping(scales[name], f"control.{name}")
        historical._exact_keys(
            item,
            {
                "scale",
                "workload",
                "selection",
                "request",
                "request_sha256",
                "ordinary_request_sha256",
                "profile_sha256",
                "potential_sha256",
                "potential_contract",
                "control",
                "pass",
                "status",
            },
            f"control.{name}",
        )
        if item.get("scale") != scale:
            raise SelectionError(f"control.{name} scale identity changed")
        historical._validate_workload_evidence(
            scale,
            historical._mapping(item.get("workload"), f"control.{name}.workload"),
        )
        selection = historical._mapping(
            item.get("selection"), f"control.{name}.selection"
        )
        rows = _validate_selection_evidence(scale, selection)
        identities[scale] = selection.get("selected_identity")
        request = historical._mapping(item.get("request"), f"control.{name}.request")
        rebuilt, potential = build_g31_control_request(
            scale,
            rows,
            binary=G31_BINARY,
            map_profile_path=PROFILE_PATH,
            auditor=selected_auditor,
        )
        request_evidence = {
            "request_sha256": selected_auditor.request_sha256(request),
            "ordinary_request_sha256": selected_auditor.ordinary_request_sha256(
                request
            ),
            "profile_sha256": selected_auditor.profile_sha256(request),
            "potential_sha256": historical.canonical_sha256(
                request.get("heuristic_time")
            ),
        }
        if (
            historical._portable(request) != historical._portable(rebuilt)
            or historical._portable(item.get("potential_contract"))
            != historical._portable(potential)
            or any(item.get(key) != digest for key, digest in request_evidence.items())
        ):
            raise SelectionError(f"control.{name} request evidence changed")

        control = historical._mapping(item.get("control"), f"control.{name}.control")
        historical._exact_keys(
            control,
            {
                "payload_sha256",
                "ordinary_payload_hashes",
                "events_sha256",
                "decisions_sha256",
                "service_episodes_sha256",
                "payload",
                "audit",
            },
            f"control.{name}.control",
        )
        payload = historical._mapping(
            control.get("payload"), f"control.{name}.payload"
        )
        recomputed_audit = audit_g31_control_payload(
            scale=scale,
            selected_rows=rows,
            request=request,
            payload=payload,
            auditor=selected_auditor,
        )
        recomputed = historical._control_evidence(
            payload, recomputed_audit, selected_auditor
        )
        if (
            recomputed_audit.get("pass") is not True
            or recomputed_audit.get("status") != PASS
            or historical._portable(control) != historical._portable(recomputed)
            or item.get("pass") is not True
            or item.get("status") != PASS
        ):
            raise SelectionError(f"control.{name} payload failed deep replay")
    if identities[1] != identities[2]:
        raise SelectionError("control 1x/2x selected identities differ")
    return loaded


def load_and_validate_control_artifact(
    value: Path,
    *,
    expected_file_sha256: str,
    auditor: Any | None = None,
) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Path):
        raise TypeError("V3R12 control artifact must be supplied as a Path")
    if value.resolve() != OUTPUT_PATH.resolve():
        raise SelectionError("V3R12 control artifact is not at its active path")
    loaded, file_sha = historical._load_bound_json(
        value, expected_file_sha256, label="V3R12 control artifact"
    )
    return _validate_control_artifact_mapping(loaded, auditor=auditor), file_sha


def _validate_prerequisite(
    value: Mapping[str, Any],
    *,
    expected_g32_binary_sha256: str,
) -> dict[str, Any]:
    """Bind a caller-validated V3R11 prerequisite without replaying 144 cases."""

    prerequisite = dict(value)
    auditor = historical._v3_auditor()
    if (
        prerequisite.get("synthetic_revision_id")
        != PREREQUISITE_SYNTHETIC_REVISION_ID
        or prerequisite.get("campaign_revision_id")
        != PREREQUISITE_CAMPAIGN_REVISION_ID
        or prerequisite.get("historical_control_revision_id")
        != HISTORICAL_CONTROL_REVISION_ID
        or prerequisite.get("historical_control_revision_id")
        == CONTROL_REVISION_ID
        or prerequisite.get("status") != auditor.SYNTHETIC_PASS
        or prerequisite.get("decision") != auditor.SYNTHETIC_PASS
        or prerequisite.get("synthetic_pass") is not True
        or prerequisite.get("g32_binary_sha256")
        != expected_g32_binary_sha256
        or not historical._sha256_text(
            prerequisite.get("artifact_content_sha256")
        )
    ):
        raise SelectionError("V3R11 prerequisite binding is invalid")
    head = prerequisite.get("implementation_head")
    if (
        not isinstance(head, str)
        or len(head) != 40
        or any(character not in "0123456789abcdef" for character in head.lower())
    ):
        raise SelectionError("V3R11 prerequisite implementation head is invalid")
    return prerequisite


class _CanaryAuditorProxy:
    """Keep historical helper logic while substituting active scenario labels."""

    def __init__(self, auditor: Any, name: str) -> None:
        self._auditor = auditor
        self._name = name
        self._scenario = _scenario(int(name[0]))
        self._case_id = f"g4irsf32_v3r12_nanning_p0_canary_shadow_{name}"

    def __getattr__(self, name: str) -> Any:
        return getattr(self._auditor, name)

    def assert_request_projection(
        self,
        request: Mapping[str, Any],
        mode: str,
        storage: list[int],
        _historical_scenario: str,
    ) -> None:
        if request.get("scenario") != self._scenario:
            raise SelectionError("active canary scenario binding changed")
        self._auditor.assert_request_projection(
            request, mode, storage, self._scenario
        )

    def extract_rows(self, payload: Mapping[str, Any], **kwargs: Any) -> Any:
        metadata = dict(kwargs.get("metadata", {}))
        metadata["flow_pattern"] = SELECTION_BASIS
        kwargs.update(case_id=self._case_id, metadata=metadata)
        return self._auditor.extract_rows(payload, **kwargs)

    def build_service_episodes(
        self,
        _historical_case_id: str,
        payload: Mapping[str, Any],
        observed: Sequence[Mapping[str, Any]],
        request: Mapping[str, Any],
    ) -> Any:
        return self._auditor.build_service_episodes(
            self._case_id, payload, observed, request
        )


def _shadow_status(results: Mapping[str, Mapping[str, Any]]) -> str:
    historical_status = historical._shadow_campaign_status(results)
    return {
        historical.SHADOW_PASS: SHADOW_PASS,
        historical.SHADOW_NO_EVENT: SHADOW_NO_EVENT,
        historical.SHADOW_NO_GO: SHADOW_NO_GO,
    }[historical_status]


def run_g32_shadow_gate(
    control_artifact: Path,
    g32_binary: Path,
    executor: Executor,
    *,
    expected_control_file_sha256: str,
    prerequisite: Mapping[str, Any],
    prerequisite_file_sha256: str,
    expected_g32_binary_sha256: str,
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Execute active shadow scales using a caller-validated V3R11 prerequisite."""

    selected_auditor = auditor or historical._v3_auditor()
    control, control_file_sha = load_and_validate_control_artifact(
        control_artifact,
        expected_file_sha256=expected_control_file_sha256,
        auditor=selected_auditor,
    )
    if not isinstance(g32_binary, Path) or g32_binary.is_symlink():
        raise SelectionError("G32 binary must be a non-symlink Path")
    binary = g32_binary.resolve(strict=True)
    binary_sha = historical.file_sha256(binary)
    if (
        not historical._sha256_text(expected_g32_binary_sha256)
        or binary_sha != expected_g32_binary_sha256
        or binary_sha == historical.FROZEN_SOURCE_HASHES[G31_BINARY]
    ):
        raise SelectionError("active G32 binary binding is invalid")
    if not historical._sha256_text(prerequisite_file_sha256):
        raise SelectionError("V3R11 prerequisite file binding is invalid")
    bound_prerequisite = _validate_prerequisite(
        prerequisite, expected_g32_binary_sha256=binary_sha
    )

    results: dict[str, Any] = {}
    for name in ("1x", "2x"):
        proxy = _CanaryAuditorProxy(selected_auditor, name)
        control_scale = historical._mapping(
            control["scales"][name], f"control.{name}"
        )
        context = historical._build_g32_shadow_scale_context(
            name=name,
            control_scale=control_scale,
            g32_binary=binary,
            auditor=proxy,
        )
        try:
            payload = executor(**context["shadow_request"])
            if not isinstance(payload, Mapping):
                raise SelectionError("G32 canary executor did not return an object")
            results[name] = historical._replay_g32_shadow_scale_evidence(
                context=context,
                shadow_payload=payload,
                g32_binary=binary,
                expected_g32_binary_sha256=binary_sha,
                auditor=proxy,
            )
        except Exception as error:
            results[name] = {
                "pass": False,
                "checks": {},
                "admitted_node49_upstream53_count": 0,
                "error_type": type(error).__name__,
                "error": str(error),
                "shadow_payload": None,
            }
            break
    status = _shadow_status(results)
    passed = status == SHADOW_PASS
    return historical.with_content_hash(
        {
            "schema": SHADOW_GATE_SCHEMA,
            "protocol_id": PROTOCOL_ID,
            "campaign_revision_id": CAMPAIGN_REVISION_ID,
            "active_control_revision_id": CONTROL_REVISION_ID,
            "historical_control_revision_id": HISTORICAL_CONTROL_REVISION_ID,
            "status": status,
            "pass": passed,
            "selection_basis": SELECTION_BASIS,
            "selection_role": SELECTION_ROLE,
            "diagnostic_origin": DIAGNOSTIC_ORIGIN,
            "formal_inference_eligible": False,
            "control_artifact_content_sha256": control[
                "artifact_content_sha256"
            ],
            "control_artifact_file_sha256": control_file_sha,
            "prerequisite_artifact_content_sha256": bound_prerequisite[
                "artifact_content_sha256"
            ],
            "prerequisite_artifact_file_sha256": prerequisite_file_sha256,
            "prerequisite_decision": bound_prerequisite["decision"],
            "prerequisite_implementation_head": bound_prerequisite[
                "implementation_head"
            ],
            "g32_binary_sha256": binary_sha,
            "scales": results,
        }
    )


def deep_validate_g32_shadow_result_mapping(
    value: Mapping[str, Any],
    *,
    expected_control_file_sha256: str,
    expected_prerequisite_file_sha256: str,
    expected_g32_binary_sha256: str,
    auditor: Any | None = None,
) -> dict[str, Any]:
    """Deeply replay both retained active canary scales.

    The prerequisite's 144-case validation intentionally remains the
    composer's job.  This validator binds the already-validated prerequisite
    file identity recorded by the shadow result, then independently rebuilds
    the active control tail and every retained shadow evidence field.
    """

    result = deepcopy(dict(value))
    historical._exact_keys(
        result,
        {
            "schema",
            "protocol_id",
            "campaign_revision_id",
            "active_control_revision_id",
            "historical_control_revision_id",
            "status",
            "pass",
            "selection_basis",
            "selection_role",
            "diagnostic_origin",
            "formal_inference_eligible",
            "control_artifact_content_sha256",
            "control_artifact_file_sha256",
            "prerequisite_artifact_content_sha256",
            "prerequisite_artifact_file_sha256",
            "prerequisite_decision",
            "prerequisite_implementation_head",
            "g32_binary_sha256",
            "scales",
            "artifact_content_sha256",
        },
        "V3R12 shadow artifact",
    )
    historical.verify_content_hash(result)
    if not historical._sha256_text(expected_prerequisite_file_sha256):
        raise SelectionError("expected prerequisite file binding is invalid")
    selected_auditor = auditor or historical._v3_auditor()
    control, control_file_sha = load_and_validate_control_artifact(
        OUTPUT_PATH,
        expected_file_sha256=expected_control_file_sha256,
        auditor=selected_auditor,
    )
    head = result.get("prerequisite_implementation_head")
    bindings = (
        result.get("schema") == SHADOW_GATE_SCHEMA
        and result.get("protocol_id") == PROTOCOL_ID
        and result.get("campaign_revision_id") == CAMPAIGN_REVISION_ID
        and result.get("active_control_revision_id") == CONTROL_REVISION_ID
        and result.get("historical_control_revision_id")
        == HISTORICAL_CONTROL_REVISION_ID
        and result.get("active_control_revision_id")
        != result.get("historical_control_revision_id")
        and result.get("selection_basis") == SELECTION_BASIS
        and result.get("selection_role") == SELECTION_ROLE
        and result.get("diagnostic_origin") == DIAGNOSTIC_ORIGIN
        and result.get("formal_inference_eligible") is False
        and result.get("control_artifact_content_sha256")
        == control.get("artifact_content_sha256")
        and result.get("control_artifact_file_sha256") == control_file_sha
        and result.get("prerequisite_artifact_file_sha256")
        == expected_prerequisite_file_sha256
        and historical._sha256_text(
            result.get("prerequisite_artifact_content_sha256")
        )
        and result.get("prerequisite_decision")
        == selected_auditor.SYNTHETIC_PASS
        and isinstance(head, str)
        and len(head) == 40
        and all(character in "0123456789abcdef" for character in head.lower())
        and result.get("g32_binary_sha256") == expected_g32_binary_sha256
    )
    if not bindings:
        raise SelectionError("V3R12 shadow top-level binding is invalid")

    scales = historical._mapping(result.get("scales"), "shadow.scales")
    if set(scales) != {"1x", "2x"}:
        raise SelectionError("V3R12 shadow must contain exact 1x/2x scales")
    first = historical._mapping(scales["1x"], "shadow.1x")
    loaded_path = first.get("loaded_cpp_binary_path")
    if not isinstance(loaded_path, str):
        raise SelectionError("V3R12 shadow does not record a loaded G32 path")
    recorded_binary = Path(loaded_path)
    if recorded_binary.is_symlink():
        raise SelectionError("V3R12 deep replay forbids a G32 binary symlink")
    binary = recorded_binary.resolve(strict=True)
    if (
        historical.file_sha256(binary) != expected_g32_binary_sha256
        or expected_g32_binary_sha256
        == historical.FROZEN_SOURCE_HASHES[G31_BINARY]
    ):
        raise SelectionError("V3R12 deep replay G32 binary binding is invalid")

    control_scales = historical._mapping(control.get("scales"), "control.scales")
    replayed: dict[str, Mapping[str, Any]] = {}
    for name in ("1x", "2x"):
        proxy = _CanaryAuditorProxy(selected_auditor, name)
        context = historical._build_g32_shadow_scale_context(
            name=name,
            control_scale=historical._mapping(
                control_scales[name], f"control.{name}"
            ),
            g32_binary=binary,
            auditor=proxy,
        )
        recorded = historical._mapping(scales[name], f"shadow.{name}")
        payload = historical._mapping(
            recorded.get("shadow_payload"), f"shadow.{name}.payload"
        )
        expected = historical._replay_g32_shadow_scale_evidence(
            context=context,
            shadow_payload=payload,
            g32_binary=binary,
            expected_g32_binary_sha256=expected_g32_binary_sha256,
            auditor=proxy,
        )
        if historical._portable(recorded) != historical._portable(expected):
            raise SelectionError(f"V3R12 shadow {name} differs on deep replay")
        replayed[name] = expected
    status = _shadow_status(replayed)
    if result.get("status") != status or result.get("pass") is not (
        status == SHADOW_PASS
    ):
        raise SelectionError("V3R12 shadow status/pass differs on deep replay")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--g31-binary", type=Path, default=G31_BINARY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_control_selection(binary=args.g31_binary)
    except Exception as error:
        result = historical.with_content_hash(
            {
                "schema": SCHEMA,
                "protocol_id": PROTOCOL_ID,
                "control_revision_id": CONTROL_REVISION_ID,
                "historical_control_revision_id": HISTORICAL_CONTROL_REVISION_ID,
                "status": NO_GO,
                "pass": False,
                "g32_executed": False,
                "selection_basis": SELECTION_BASIS,
                "selection_role": SELECTION_ROLE,
                "diagnostic_origin": DIAGNOSTIC_ORIGIN,
                "selection_outcome_blind": False,
                "formal_inference_eligible": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    historical.atomic_write_strict_json(args.output, result)
    print(result["status"])
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
