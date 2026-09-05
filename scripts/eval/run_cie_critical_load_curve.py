#!/usr/bin/env python3
"""Run the frozen map2 critical-load curve for HCA, paper-environment DH, and G31.

This module is orchestration and normalization only.  It reuses the registered
whole-flight, schedule-preserving workload builders and the native baseline
runners; it does not modify any routing algorithm.  All methods see one exact
raw-bag population at each load and the common absolute horizon 98,259 s.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from czr005.io.legacy_tasks import (  # noqa: E402
    expand_tasks,
    parse_legacy_tasks,
    write_task_jsonl,
)
from scripts.eval import g4irsf11_capacity_metrics as capacity  # noqa: E402
from scripts.eval import run_cie_component_activation as activation  # noqa: E402
from scripts.eval import run_cie_external_baseline_robustness as external  # noqa: E402
from scripts.eval import run_g4irsf29_workload as g29  # noqa: E402


SCHEMA = "czr005.cie_critical_load_curve.v2"
IDENTITY_SCHEMA = "czr005.cie_external_baseline_workload.v1"
LOAD_FACTORS = (1.0, 1.25, 1.5, 1.75, 2.0)
METHODS = (
    "FENG_NATIVE_HCA",
    "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION",
    "G31_S4_NATIVE_SYSTEM",
)
EXPECTED_POPULATIONS = {
    1.0: (28_506, 43_603),
    1.25: (35_659, 54_559),
    1.5: (42_932, 65_679),
    1.75: (49_765, 76_108),
    2.0: (57_012, 87_206),
}
FIXED_HORIZON_SECONDS = 98_259.0
HCA_START_EPOCH = 8_260
HCA_MAX_EPOCHS = 90_000

DEFAULT_MAP = ROOT / "legacy/jichang_origin_readonly/map2.txt"
DEFAULT_SOURCE_RAW = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
DEFAULT_SOURCE_CANONICAL = ROOT / "data/processed/tasks/inputdata.jsonl"
DEFAULT_WORKLOAD_ROOT = ROOT / "data/processed/workloads/cie_critical_load_curve"
DEFAULT_RUNTIME_ROOT = ROOT / "outputs/runtime/cie_critical_load_curve"
DEFAULT_G31_ROOT = ROOT / "outputs/runtime/cie_component_activation"
DEFAULT_FORMAL_G31_1X_REFERENCE = (
    ROOT / "outputs/runtime/cie_ablations/same_hca/a4_full/map2_1x.json"
)
DEFAULT_G31_BINARY = (
    ROOT
    / "build/nanning_ablation_gate_f_pybind/python/Release/"
    "czr005_cpp.cp311-win_amd64.pyd"
)
EXPECTED_FINAL_G31_SHA256 = (
    "b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5"
)
FORMAL_G31_RELEASE_PROTOCOL = "EXACT_NATIVE_HCA_RUN_01_SEGMENT_RELEASE"
G31_ALIGNMENT_SCHEMA = "czr005.cie_critical_load_curve.g31_release_alignment.v1"
FORMAL_G31_1X_MEAN_TOLERANCE_SECONDS = 1.0e-6
EXPECTED_FINAL_DH_SOURCE_SHA256 = (
    "99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8"
)
EXPECTED_FINAL_DH_CLASS_SHA256 = (
    "d611967f0433dfc08f67d92c89e9b13dcb5b8ac5ace3d3abec9c098dba360286"
)
DEFAULT_HCA_1X_REUSE = ROOT / "outputs/raw/feng_paper_env_hca_rerun"
DEFAULT_TABLE = ROOT / "outputs/tables/cie_critical_load_curve_v2.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/cie_critical_load_curve_v2.md"
DEFAULT_FIGURE = ROOT / "outputs/figures/cie_critical_load_curve_v2.png"
DEFAULT_JAVA_CLASSES = ROOT / "build/cie_critical_load_hca_java"
DEFAULT_DH_CLASSES = ROOT / "build/feng_cie_dh_java"


class CriticalLoadError(RuntimeError):
    """Raised when workload or native evidence identity is inconsistent."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _label(factor: float) -> str:
    return f"{factor:.2f}"


def _tag(factor: float) -> str:
    return _label(factor).replace(".", "p")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                   allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise CriticalLoadError("cannot write an empty critical-load table")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _cell_root(runtime_root: Path, factor: float) -> Path:
    return runtime_root / f"map2_{_tag(factor)}x"


def _workload_root(workload_root: Path, factor: float) -> Path:
    return workload_root / f"map2_{_tag(factor)}x"


def _identity_path(runtime_root: Path, factor: float) -> Path:
    return _cell_root(runtime_root, factor) / "workload_identity.json"


def _read_identity(runtime_root: Path, factor: float) -> dict[str, Any]:
    path = _identity_path(runtime_root, factor).resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != IDENTITY_SCHEMA:
        raise CriticalLoadError(f"identity schema mismatch: {path}")
    if not math.isclose(float(value.get("load_factor", math.nan)), factor):
        raise CriticalLoadError(f"identity load mismatch: {path}")
    raw = Path(str(value.get("raw_path", ""))).resolve(strict=True)
    canonical = Path(str(value.get("canonical_path", ""))).resolve(strict=True)
    map_path = Path(str(value.get("map_path", ""))).resolve(strict=True)
    if map_path != DEFAULT_MAP.resolve(strict=True):
        raise CriticalLoadError(f"registered map path mismatch: {path}")
    if value.get("map_sha256") != _sha256(map_path):
        raise CriticalLoadError(f"registered map hash mismatch: {path}")
    if (
        int(value.get("storage_in_goal", -1)) != 47
        or int(value.get("storage_out_start", -1)) != 52
    ):
        raise CriticalLoadError(f"registered map role mismatch: {path}")
    if _sha256(raw) != value.get("raw_sha256"):
        raise CriticalLoadError(f"raw workload hash mismatch: {path}")
    if _sha256(canonical) != value.get("canonical_sha256"):
        raise CriticalLoadError(f"canonical workload hash mismatch: {path}")
    expected_raw, expected_segments = EXPECTED_POPULATIONS[factor]
    if (
        int(value.get("raw_bag_count", -1)) != expected_raw
        or int(value.get("segment_count", -1)) != expected_segments
    ):
        raise CriticalLoadError(f"registered population mismatch: {path}")
    return value


def _write_workload(
    *,
    header: str,
    raw_tasks: Sequence[Any],
    raw_path: Path,
    canonical_path: Path,
) -> tuple[int, int]:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    g29.write_raw_tasks(header, raw_tasks, raw_path)
    _header, reparsed = parse_legacy_tasks(raw_path)
    segments = expand_tasks(reparsed)
    write_task_jsonl(segments, canonical_path)
    if len({int(row.task_id) for row in reparsed}) != len(reparsed):
        raise CriticalLoadError("generated raw task IDs are not unique")
    if {int(row.task_id) for row in segments} != {
        int(row.task_id) for row in reparsed
    }:
        raise CriticalLoadError("canonical expansion lost a raw bag")
    return len(reparsed), len(segments)


def generate_workloads(
    *,
    workload_root: Path = DEFAULT_WORKLOAD_ROOT,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
) -> dict[str, Any]:
    """Materialize the exact unjittered five-load map2 ladder."""

    source_raw = DEFAULT_SOURCE_RAW.resolve(strict=True)
    source_canonical = DEFAULT_SOURCE_CANONICAL.resolve(strict=True)
    header, source_tasks = parse_legacy_tasks(source_raw)
    if len(source_tasks) != EXPECTED_POPULATIONS[1.0][0]:
        raise CriticalLoadError("the protected 1x source population changed")

    manifest_cells: list[dict[str, Any]] = []
    for factor in LOAD_FACTORS:
        selection: Mapping[str, Any]
        if factor == 1.0:
            raw_path = source_raw
            canonical_path = source_canonical
            selection = {
                "method": "ORIGINAL_UNJITTERED_TIMETABLE",
                "whole_flight_manifest_invariant": True,
            }
        else:
            target = _workload_root(workload_root, factor)
            raw_path = target / "inputdata.txt"
            canonical_path = target / "canonical.jsonl"
            if factor == 2.0:
                generated, _flight_rows, generation = g29.densify_flight_timetable(
                    source_tasks
                )
                selection = {
                    **generation,
                    "method": "G29_SCHEDULE_PRESERVING_WHOLE_FLIGHT_2X",
                    "whole_flight_manifest_invariant": True,
                }
            else:
                generated, selection_value, _offset = activation.build_factor_raw_tasks(
                    source_tasks, factor
                )
                selection = selection_value
            _write_workload(
                header=header,
                raw_tasks=generated,
                raw_path=raw_path,
                canonical_path=canonical_path,
            )

        _header, raw_rows = parse_legacy_tasks(raw_path)
        canonical_rows = activation._read_jsonl(canonical_path)
        raw_count = len(raw_rows)
        segment_count = len(canonical_rows)
        expected = EXPECTED_POPULATIONS[factor]
        if (raw_count, segment_count) != expected:
            raise CriticalLoadError(
                f"{factor:.2f}x population {(raw_count, segment_count)} != {expected}"
            )
        raw_ids = {int(row.task_id) for row in raw_rows}
        canonical_ids = {int(row["task_id"]) for row in canonical_rows}
        if raw_ids != canonical_ids:
            raise CriticalLoadError(f"{factor:.2f}x raw/canonical bag identity differs")

        identity = {
            "schema": IDENTITY_SCHEMA,
            "status": "COMPLETE",
            "map": "map2",
            "map_path": str(DEFAULT_MAP.resolve(strict=True)),
            "map_sha256": _sha256(DEFAULT_MAP),
            "storage_in_goal": 47,
            "storage_out_start": 52,
            "load_factor": factor,
            "seed": 0,
            "arrival_jitter_seconds": 0,
            "raw_path": str(raw_path.resolve()),
            "canonical_path": str(canonical_path.resolve()),
            "raw_sha256": _sha256(raw_path),
            "canonical_sha256": _sha256(canonical_path),
            "raw_bag_count": raw_count,
            "segment_count": segment_count,
            "fixed_horizon_seconds": FIXED_HORIZON_SECONDS,
            "generation": dict(selection),
            "protocol": {
                "unjittered": True,
                "whole_flights_only": True,
                "schedule_preserving": True,
                "expanded_segment_sampling_or_duplication": False,
                "same_raw_for_hca_and_dh": True,
                "canonical_is_deterministic_expansion_of_raw": True,
            },
        }
        identity_path = _identity_path(runtime_root, factor)
        _atomic_json(identity_path, identity)
        manifest_cells.append(
            {
                "load_factor": factor,
                "identity_path": str(identity_path.resolve()),
                "identity_sha256": _sha256(identity_path),
                "raw_path": str(raw_path.resolve()),
                "raw_sha256": identity["raw_sha256"],
                "canonical_path": str(canonical_path.resolve()),
                "canonical_sha256": identity["canonical_sha256"],
                "raw_bag_count": raw_count,
                "segment_count": segment_count,
            }
        )

    manifest = {
        "schema": SCHEMA,
        "status": "WORKLOADS_COMPLETE",
        "generated_at": _utc_now(),
        "fixed_horizon_seconds": FIXED_HORIZON_SECONDS,
        "loads": manifest_cells,
        "invariants": {
            "load_factors": list(LOAD_FACTORS),
            "unjittered": True,
            "whole_flight_schedule_preserving": True,
            "same_exact_raw_for_hca_and_dh_per_load": True,
        },
    }
    _atomic_json(runtime_root / "workload_manifest.json", manifest)
    return manifest


def _copy_hca_evidence(source: Path, destination: Path) -> None:
    campaign = json.loads((source / "fresh_hca_summary.json").read_text(encoding="utf-8"))
    runs = campaign.get("runs", [])
    if len(runs) != 1 or runs[0].get("run_id") != "run_01":
        raise CriticalLoadError("the 1x HCA reuse campaign is not one complete run")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "fresh_hca_summary.json", destination / "fresh_hca_summary.json")
    for optional in ("fresh_hca_runs.csv",):
        if (source / optional).is_file():
            shutil.copy2(source / optional, destination / optional)
    target_run = destination / "run_01"
    target_run.mkdir(parents=True, exist_ok=True)
    for name in (
        "run_status.json",
        "metrics.json",
        "segment_lifecycle.csv",
        "raw_bag_timings.csv",
        "release.csv",
        "routes.csv",
        "summary.csv",
    ):
        shutil.copy2(source / "run_01" / name, target_run / name)


def _g31_aligned_canonical_path(runtime_root: Path, factor: float) -> Path:
    return _cell_root(runtime_root, factor) / "g31_same_hca_release_canonical.jsonl"


def _g31_alignment_path(runtime_root: Path, factor: float) -> Path:
    return _cell_root(runtime_root, factor) / "g31_release_alignment.json"


def _atomic_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n"
            )
    os.replace(temporary, path)


def _hca_segment_releases(lifecycle_path: Path) -> dict[str, float]:
    releases: dict[str, float] = {}
    with lifecycle_path.resolve(strict=True).open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            segment_id = str(row.get("segment_id", ""))
            try:
                release = float(str(row.get("release_epoch", "")))
            except ValueError as exc:
                raise CriticalLoadError(
                    f"HCA lifecycle has invalid release_epoch: {lifecycle_path}"
                ) from exc
            if not segment_id or not math.isfinite(release):
                raise CriticalLoadError(
                    f"HCA lifecycle lacks finite segment release: {lifecycle_path}"
                )
            if segment_id in releases:
                raise CriticalLoadError(
                    f"HCA lifecycle has duplicate segment {segment_id}: "
                    f"{lifecycle_path}"
                )
            releases[segment_id] = release
    return releases


def _align_g31_rows(
    base_rows: Sequence[Mapping[str, Any]],
    releases: Mapping[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replace only canonical ``pass_time`` with the exact HCA release."""

    base_ids = [str(row.get("segment_id", "")) for row in base_rows]
    if any(not segment_id for segment_id in base_ids):
        raise CriticalLoadError("base canonical workload lacks a segment_id")
    if len(set(base_ids)) != len(base_ids):
        raise CriticalLoadError("base canonical workload has duplicate segments")
    if set(base_ids) != set(releases):
        missing = len(set(base_ids) - set(releases))
        foreign = len(set(releases) - set(base_ids))
        raise CriticalLoadError(
            "HCA release trace does not exactly cover canonical segments "
            f"(missing={missing}, foreign={foreign})"
        )

    aligned: list[dict[str, Any]] = []
    deltas: list[float] = []
    actual_changes = 0
    for source, segment_id in zip(base_rows, base_ids):
        if "pass_time" not in source:
            raise CriticalLoadError(
                f"canonical segment lacks pass_time: {segment_id}"
            )
        row = dict(source)
        base_pass = float(row["pass_time"])
        release = float(releases[segment_id])
        if not math.isfinite(base_pass) or not math.isfinite(release):
            raise CriticalLoadError(
                f"non-finite pass/release time for segment {segment_id}"
            )
        deltas.append(release - base_pass)
        if release != base_pass:
            actual_changes += 1
        row["pass_time"] = release
        if {
            key: value for key, value in row.items() if key != "pass_time"
        } != {
            key: value for key, value in source.items() if key != "pass_time"
        }:
            raise CriticalLoadError(
                f"G31 release alignment changed a non-pass_time field: {segment_id}"
            )
        aligned.append(row)
    return aligned, {
        "aligned_segment_count": len(aligned),
        "pass_time_value_change_count": actual_changes,
        "release_minus_canonical_pass_mean_seconds": statistics.fmean(deltas),
        "release_minus_canonical_pass_min_seconds": min(deltas),
        "release_minus_canonical_pass_max_seconds": max(deltas),
        "only_permitted_input_field": "pass_time",
        "non_pass_time_field_difference_count": 0,
        "algorithm_or_policy_modified": False,
    }


def _validate_g31_aligned_rows(
    base_rows: Sequence[Mapping[str, Any]],
    aligned_rows: Sequence[Mapping[str, Any]],
    releases: Mapping[str, float],
) -> dict[str, bool]:
    if len(base_rows) != len(aligned_rows):
        raise CriticalLoadError("aligned G31 canonical segment count changed")
    gates = {
        "same_segment_order": True,
        "exact_hca_release_by_segment": True,
        "only_pass_time_may_differ": True,
    }
    for base, aligned in zip(base_rows, aligned_rows):
        segment_id = str(base.get("segment_id", ""))
        gates["same_segment_order"] &= (
            segment_id == str(aligned.get("segment_id", ""))
        )
        gates["exact_hca_release_by_segment"] &= (
            float(aligned.get("pass_time", math.nan)) == releases.get(segment_id)
        )
        gates["only_pass_time_may_differ"] &= (
            {key: value for key, value in base.items() if key != "pass_time"}
            == {
                key: value for key, value in aligned.items() if key != "pass_time"
            }
        )
    if not all(gates.values()):
        raise CriticalLoadError(f"G31 release alignment gate failed: {gates}")
    return gates


def prepare_g31_release_alignment(
    *, factor: float, runtime_root: Path = DEFAULT_RUNTIME_ROOT
) -> dict[str, Any]:
    """Materialize the frozen original-paper same-HCA release input."""

    identity = _read_identity(runtime_root, factor)
    base_path = Path(str(identity["canonical_path"])).resolve(strict=True)
    lifecycle_path = (
        _cell_root(runtime_root, factor)
        / "hca_native/run_01/segment_lifecycle.csv"
    ).resolve(strict=True)
    aligned_path = _g31_aligned_canonical_path(runtime_root, factor)
    audit_path = _g31_alignment_path(runtime_root, factor)
    base_rows = activation._read_jsonl(base_path)
    releases = _hca_segment_releases(lifecycle_path)
    aligned_rows, details = _align_g31_rows(base_rows, releases)
    _atomic_jsonl(aligned_path, aligned_rows)
    written_rows = activation._read_jsonl(aligned_path)
    gates = _validate_g31_aligned_rows(base_rows, written_rows, releases)
    if len(written_rows) != int(identity["segment_count"]):
        raise CriticalLoadError(
            f"aligned G31 population differs at {factor:.2f}x"
        )

    reference = DEFAULT_FORMAL_G31_1X_REFERENCE.resolve(strict=True)
    audit = {
        "schema": G31_ALIGNMENT_SCHEMA,
        "status": "COMPLETE",
        "map": "map2",
        "load_factor": factor,
        "release_protocol": FORMAL_G31_RELEASE_PROTOCOL,
        "base_canonical_path": str(base_path),
        "base_canonical_sha256": identity["canonical_sha256"],
        "execution_canonical_path": str(aligned_path.resolve()),
        "execution_canonical_sha256": _sha256(aligned_path),
        "hca_release_lifecycle_path": str(lifecycle_path),
        "hca_release_lifecycle_sha256": _sha256(lifecycle_path),
        "formal_original_paper_reference_path": str(reference),
        "formal_original_paper_reference_sha256": _sha256(reference),
        "formal_reference_release_mode": "same_hca",
        "formal_reference_1x_network_mean_seconds": (
            210.55305735634744
        ),
        "gates": {
            "base_canonical_sha256_matches_identity": (
                _sha256(base_path) == identity["canonical_sha256"]
            ),
            "exact_segment_population": (
                len(written_rows) == int(identity["segment_count"])
            ),
            "exact_segment_identity": set(releases)
            == {str(row["segment_id"]) for row in base_rows},
            **gates,
        },
        "alignment": details,
    }
    if not all(audit["gates"].values()):
        raise CriticalLoadError(
            f"G31 formal release audit failed at {factor:.2f}x"
        )
    _atomic_json(audit_path, audit)
    return audit


def _read_g31_release_alignment(
    *, factor: float, runtime_root: Path = DEFAULT_RUNTIME_ROOT
) -> dict[str, Any]:
    identity = _read_identity(runtime_root, factor)
    audit_path = _g31_alignment_path(runtime_root, factor).resolve(strict=True)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (
        audit.get("schema") != G31_ALIGNMENT_SCHEMA
        or audit.get("status") != "COMPLETE"
        or audit.get("release_protocol") != FORMAL_G31_RELEASE_PROTOCOL
        or not all((audit.get("gates") or {}).values())
    ):
        raise CriticalLoadError(f"invalid G31 release audit: {audit_path}")
    if audit.get("base_canonical_sha256") != identity["canonical_sha256"]:
        raise CriticalLoadError(f"stale G31 base canonical audit: {audit_path}")
    execution_path = Path(
        str(audit.get("execution_canonical_path", ""))
    ).resolve(strict=True)
    lifecycle_path = Path(
        str(audit.get("hca_release_lifecycle_path", ""))
    ).resolve(strict=True)
    if _sha256(execution_path) != audit.get("execution_canonical_sha256"):
        raise CriticalLoadError(f"G31 aligned canonical hash mismatch: {audit_path}")
    if _sha256(lifecycle_path) != audit.get("hca_release_lifecycle_sha256"):
        raise CriticalLoadError(f"G31 HCA release trace hash mismatch: {audit_path}")
    _validate_g31_aligned_rows(
        activation._read_jsonl(Path(str(identity["canonical_path"]))),
        activation._read_jsonl(execution_path),
        _hca_segment_releases(lifecycle_path),
    )
    return audit


def _g31_normalization_identity(
    identity: Mapping[str, Any], alignment: Mapping[str, Any]
) -> dict[str, Any]:
    normalized = dict(identity)
    normalized["canonical_path"] = alignment["execution_canonical_path"]
    normalized["canonical_sha256"] = alignment["execution_canonical_sha256"]
    return normalized


def stage_g31(
    *, runtime_root: Path = DEFAULT_RUNTIME_ROOT, g31_root: Path = DEFAULT_G31_ROOT
) -> None:
    for factor in LOAD_FACTORS:
        alignment = prepare_g31_release_alignment(
            factor=factor, runtime_root=runtime_root
        )
        source = g31_root / f"map2_{_label(factor)}x.json"
        native = json.loads(source.read_text(encoding="utf-8"))
        provenance = native.get("provenance", {})
        if (
            provenance.get("canonical_sha256")
            != alignment["execution_canonical_sha256"]
            or provenance.get("release_protocol") != FORMAL_G31_RELEASE_PROTOCOL
        ):
            raise CriticalLoadError(
                f"G31 staged result is not formal same-HCA release at "
                f"{factor:.2f}x"
            )
        if float(native.get("request_contract", {}).get("fixed_end_epoch", math.nan)) != FIXED_HORIZON_SECONDS:
            raise CriticalLoadError(f"G31 horizon differs at {factor:.2f}x")
        destination = _cell_root(runtime_root, factor) / "g31_native.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def run_g31(
    *,
    factors: Sequence[float],
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    binary: Path = DEFAULT_G31_BINARY,
    force: bool = False,
) -> None:
    """Execute formal G31 with each HCA cell's exact segment release trace."""

    binary = binary.resolve(strict=True)
    if _sha256(binary) != EXPECTED_FINAL_G31_SHA256:
        raise CriticalLoadError(
            "G31 binary is not the frozen post-ablation-repair artifact"
        )
    runner = ROOT / "scripts/eval/run_cie_component_activation.py"
    for factor in factors:
        identity = _read_identity(runtime_root, factor)
        alignment = prepare_g31_release_alignment(
            factor=factor, runtime_root=runtime_root
        )
        execution_canonical = Path(
            str(alignment["execution_canonical_path"])
        ).resolve(strict=True)
        alignment_path = _g31_alignment_path(runtime_root, factor)
        destination = _cell_root(runtime_root, factor) / "g31_native.json"
        if not force and destination.is_file():
            existing = json.loads(destination.read_text(encoding="utf-8"))
            provenance = existing.get("provenance", {})
            if (
                existing.get("status") == "COMPLETE"
                and provenance.get("binary_sha256") == _sha256(binary)
                and provenance.get("canonical_sha256")
                == alignment["execution_canonical_sha256"]
                and provenance.get("base_canonical_sha256")
                == identity["canonical_sha256"]
                and provenance.get("release_protocol")
                == FORMAL_G31_RELEASE_PROTOCOL
                and provenance.get("release_alignment_sha256")
                == _sha256(alignment_path)
            ):
                continue
        command = [
            sys.executable,
            str(runner),
            "run",
            "--map",
            "map2",
            "--factor",
            str(factor),
            "--canonical",
            str(execution_canonical),
            "--binary",
            str(binary),
            "--output",
            str(destination),
            "--force",
        ]
        _run_checked(command)
        native = json.loads(destination.read_text(encoding="utf-8"))
        provenance = native.get("provenance")
        if not isinstance(provenance, dict):
            raise CriticalLoadError(
                f"G31 result lacks mutable provenance at {factor:.2f}x"
            )
        if (
            provenance.get("canonical_sha256")
            != alignment["execution_canonical_sha256"]
            or provenance.get("binary_sha256") != EXPECTED_FINAL_G31_SHA256
        ):
            raise CriticalLoadError(
                f"G31 execution identity differs at {factor:.2f}x"
            )
        provenance.update(
            {
                "release_protocol": FORMAL_G31_RELEASE_PROTOCOL,
                "base_canonical_path": identity["canonical_path"],
                "base_canonical_sha256": identity["canonical_sha256"],
                "release_alignment_path": str(alignment_path.resolve()),
                "release_alignment_sha256": _sha256(alignment_path),
                "hca_release_lifecycle_path": alignment[
                    "hca_release_lifecycle_path"
                ],
                "hca_release_lifecycle_sha256": alignment[
                    "hca_release_lifecycle_sha256"
                ],
            }
        )
        native["formal_g31_release_alignment"] = {
            "protocol": FORMAL_G31_RELEASE_PROTOCOL,
            "audit_path": str(alignment_path.resolve()),
            "audit_sha256": _sha256(alignment_path),
            "base_canonical_sha256": identity["canonical_sha256"],
            "execution_canonical_sha256": alignment[
                "execution_canonical_sha256"
            ],
            "only_modified_input_field": "pass_time",
            "algorithm_or_policy_modified": False,
        }
        _atomic_json(destination, native)


def _run_checked(command: Sequence[str]) -> None:
    completed = subprocess.run(list(command), cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise CriticalLoadError(
            f"native command failed ({completed.returncode}): "
            + subprocess.list2cmdline(list(command))
        )


def run_hca(
    *,
    factors: Sequence[float],
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    reuse_1x: Path = DEFAULT_HCA_1X_REUSE,
    classes_dir: Path = DEFAULT_JAVA_CLASSES,
    force: bool = False,
) -> None:
    runner = ROOT / "scripts/eval/run_g4irsf24_fresh_hca.py"
    _run_checked(
        [sys.executable, str(runner), "compile", "--classes-dir", str(classes_dir)]
    )
    for factor in factors:
        identity = _read_identity(runtime_root, factor)
        destination = _cell_root(runtime_root, factor) / "hca_native"
        if factor == 1.0 and reuse_1x.is_dir() and not force:
            _copy_hca_evidence(reuse_1x, destination)
            continue
        command = [
            sys.executable,
            str(runner),
            "run",
            "--profile",
            "full",
            "--map-path",
            str(DEFAULT_MAP),
            "--input-path",
            str(identity["raw_path"]),
            "--canonical-input",
            str(identity["canonical_path"]),
            "--classes-dir",
            str(classes_dir),
            "--output-root",
            str(destination),
            "--start-epoch",
            str(HCA_START_EPOCH),
            "--max-epochs",
            str(HCA_MAX_EPOCHS),
            "--max-new-tasks",
            "0",
            "--repeats",
            "1",
            "--timeout-seconds",
            "7200",
            "--speed-mps",
            "2.5",
            "--cleanup-epoch-files",
            "--skip-compile",
        ]
        if force:
            command.append("--force")
        _run_checked(command)


def run_dh(
    *,
    factors: Sequence[float],
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    classes_dir: Path = DEFAULT_DH_CLASSES,
    force: bool = False,
) -> None:
    runner = ROOT / "scripts/eval/run_feng_paper_env_cie_dh.py"
    _run_checked(
        [sys.executable, str(runner), "compile", "--classes-dir", str(classes_dir)]
    )
    for factor in factors:
        identity_path = _identity_path(runtime_root, factor)
        identity = _read_identity(runtime_root, factor)
        destination = _cell_root(runtime_root, factor) / "feng_env_dh"
        command = [
            sys.executable,
            str(runner),
            "run",
            "--map-path",
            str(DEFAULT_MAP),
            "--input-path",
            str(identity["raw_path"]),
            "--classes-dir",
            str(classes_dir),
            "--output-dir",
            str(destination),
            "--allow-external-workload",
            "--external-workload-identity",
            str(identity_path),
            "--seed",
            "0",
            "--horizon-seconds",
            str(FIXED_HORIZON_SECONDS),
            "--trace-sample-modulo",
            "0",
            "--timeout-seconds",
            "7200",
            "--skip-compile",
        ]
        if force:
            command.append("--force")
        _run_checked(command)


def _hca_lifecycle(identity: Mapping[str, Any], native_dir: Path) -> tuple[dict[int, float | None], dict[int, float | None]]:
    rows = external._read_csv_rows(native_dir / "run_01/segment_lifecycle.csv")
    return external._group_lifecycle(
        rows,
        identity,
        task_key="task_id",
        admission_key="processed_attempt_epoch",
        completion_key="finish_epoch",
        complete_key="complete",
        allow_missing=True,
        segment_key="segment_id",
    )


def _dh_lifecycle(identity: Mapping[str, Any], native_dir: Path) -> tuple[dict[int, float | None], dict[int, float | None]]:
    rows = external._read_csv_rows(native_dir / "segments.csv")
    return external._group_lifecycle(
        rows,
        identity,
        task_key="source_raw_bag_id",
        admission_key="admission_time_seconds",
        completion_key="completion_time_seconds",
        complete_key="status",
        complete_value="COMPLETED",
    )


def _backlog_shape(
    identity: Mapping[str, Any],
    completion: Mapping[int, float | None],
    admission: Mapping[int, float | None],
) -> dict[str, Any]:
    _header, tasks = parse_legacy_tasks(Path(str(identity["raw_path"])))
    arrivals = [float(task.entry_time) for task in tasks]
    finishes = [
        float(completion[int(task.task_id)])
        for task in tasks
        if completion[int(task.task_id)] is not None
    ]
    admissions = [
        float(admission[int(task.task_id)])
        for task in tasks
        if admission[int(task.task_id)] is not None
    ]
    source = vars(
        capacity.backlog_metrics(
            arrivals, admissions, observation_end=FIXED_HORIZON_SECONDS
        )
    )
    total = vars(
        capacity.backlog_metrics(
            arrivals, finishes, observation_end=FIXED_HORIZON_SECONDS
        )
    )
    return {"source": source, "total": total}


def _g31_backlog(native_path: Path) -> dict[str, Any]:
    native = json.loads(native_path.read_text(encoding="utf-8"))
    backlog = native["fixed_denominator_business"]["detailed"]["backlog"]
    return {
        "source": backlog["raw_bag_source_until_all_segments_admitted"],
        "total": backlog["raw_bag_total"],
    }


def _normalise_one(
    method: str, factor: float, runtime_root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    cell = _cell_root(runtime_root, factor)
    identity_path = _identity_path(runtime_root, factor)
    identity = _read_identity(runtime_root, factor)
    execution_canonical_sha256 = identity["canonical_sha256"]
    release_protocol = "SHARED_UNJITTERED_RAW_NATIVE_RELEASE"
    if method == "FENG_NATIVE_HCA":
        native = cell / "hca_native"
        metrics, full, _evidence, contract = external._normalize_hca(identity, native)
        completion, admission = _hca_lifecycle(identity, native)
        backlog = _backlog_shape(identity, completion, admission)
    elif method == "FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION":
        native = cell / "feng_env_dh"
        dh_status = json.loads(
            (native / "runner_status.json").read_text(encoding="utf-8")
        )
        dh_identity = dh_status.get("identity", {})
        if (
            dh_identity.get("reconstruction_java_source_aggregate_sha256")
            != EXPECTED_FINAL_DH_SOURCE_SHA256
            or dh_identity.get("compiled_java_class_aggregate_sha256")
            != EXPECTED_FINAL_DH_CLASS_SHA256
        ):
            raise CriticalLoadError(
                f"DH cell is not from the frozen service-time repair: {native}"
            )
        metrics, full, _evidence, contract = external._normalize_dh(
            identity_path, identity, native
        )
        completion, admission = _dh_lifecycle(identity, native)
        backlog = _backlog_shape(identity, completion, admission)
    elif method == "G31_S4_NATIVE_SYSTEM":
        native_path = cell / "g31_native.json"
        native_payload = json.loads(native_path.read_text(encoding="utf-8"))
        alignment = _read_g31_release_alignment(
            factor=factor, runtime_root=runtime_root
        )
        if (
            native_payload.get("provenance", {}).get("binary_sha256")
            != EXPECTED_FINAL_G31_SHA256
        ):
            raise CriticalLoadError(
                f"G31 cell is not from the final repaired binary: {native_path}"
            )
        provenance = native_payload.get("provenance", {})
        if (
            provenance.get("release_protocol") != FORMAL_G31_RELEASE_PROTOCOL
            or provenance.get("base_canonical_sha256")
            != identity["canonical_sha256"]
            or provenance.get("release_alignment_sha256")
            != _sha256(_g31_alignment_path(runtime_root, factor))
        ):
            raise CriticalLoadError(
                f"G31 cell is not from the formal same-HCA release protocol: "
                f"{native_path}"
            )
        g31_identity = _g31_normalization_identity(identity, alignment)
        metrics, full, _evidence, contract = external._normalize_g31(
            g31_identity, native_path
        )
        backlog = _g31_backlog(native_path)
        execution_canonical_sha256 = alignment["execution_canonical_sha256"]
        release_protocol = FORMAL_G31_RELEASE_PROTOCOL
        contract = {
            **contract,
            "release_protocol": FORMAL_G31_RELEASE_PROTOCOL,
            "base_canonical_sha256": identity["canonical_sha256"],
            "execution_canonical_sha256": execution_canonical_sha256,
            "release_alignment_sha256": _sha256(
                _g31_alignment_path(runtime_root, factor)
            ),
            "only_modified_input_field": "pass_time",
            "algorithm_or_policy_modified": False,
        }
    else:  # pragma: no cover - guarded by parser/constants
        raise CriticalLoadError(f"unknown method: {method}")

    source = backlog["source"]
    total = backlog["total"]
    completed = int(metrics["completed_raw_bag_count"])
    raw_count = int(identity["raw_bag_count"])
    timing_allowed = factor != 2.0 and full
    row = {
        "map": "map2",
        "method": method,
        "load_factor": _label(factor),
        "fixed_horizon_seconds": FIXED_HORIZON_SECONDS,
        "raw_bag_denominator": raw_count,
        "segment_count": int(identity["segment_count"]),
        "raw_sha256": identity["raw_sha256"],
        "canonical_sha256": identity["canonical_sha256"],
        "execution_canonical_sha256": execution_canonical_sha256,
        "release_protocol": release_protocol,
        "completed_raw_bag_count": completed,
        "completion_rate": metrics["completion_rate"],
        "on_time_raw_bag_count": int(metrics["on_time_raw_bag_count"]),
        "on_time_rate": metrics["on_time_rate"],
        "capacity_deficit_raw_bags": raw_count - completed,
        "source_backlog_end": int(source["end_backlog"]),
        "source_backlog_peak": int(source["peak_backlog"]),
        "source_backlog_auc_bag_seconds": float(
            metrics["source_backlog_area_seconds"]
        ),
        "network_backlog_auc_bag_seconds": float(
            metrics["network_backlog_area_seconds"]
        ),
        "total_backlog_end": int(total["end_backlog"]),
        "total_backlog_peak": int(total["peak_backlog"]),
        "total_backlog_auc_bag_seconds": float(
            metrics["total_backlog_area_seconds"]
        ),
        "time_to_95_percent_seconds": metrics["time_to_95_percent_seconds"],
        "time_to_99_percent_seconds": metrics["time_to_99_percent_seconds"],
        "time_to_95_status": (
            "REACHED" if metrics["time_to_95_percent_seconds"] is not None else "NOT_REACHED"
        ),
        "time_to_99_status": (
            "REACHED" if metrics["time_to_99_percent_seconds"] is not None else "NOT_REACHED"
        ),
        "full_population_timing_status": (
            "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
            if factor == 2.0
            else (
                "FULL_POPULATION_PROCESSED_ATTEMPT_TIMING"
                if timing_allowed
                else "NOT_MEASURED_FULL_POPULATION_INCOMPLETE"
            )
        ),
        "population_latency_mean_seconds": (
            metrics["population_latency_mean_seconds"] if timing_allowed else None
        ),
        "population_latency_p95_seconds": (
            metrics["population_latency_p95_seconds"] if timing_allowed else None
        ),
        "population_latency_p99_seconds": (
            metrics["population_latency_p99_seconds"] if timing_allowed else None
        ),
        "population_latency_max_seconds": (
            metrics["population_latency_max_seconds"] if timing_allowed else None
        ),
        "first_incomplete_load_factor": None,
        "completion_rate_curve_auc": None,
        "capacity_deficit_rate_curve_area": None,
        "capacity_deficit_raw_bag_curve_area": None,
        "workload_identity_status": (
            "EXACT_SHARED_UNJITTERED_RAW_AND_BASE_CANONICAL_"
            "FORMAL_G31_HCA_RELEASE_ALIGNED"
        ),
        "native_contract": json.dumps(contract, sort_keys=True, separators=(",", ":")),
    }
    return row, {"full": full, "contract": contract}


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _formal_g31_1x_network_mean_seconds(
    reference_path: Path = DEFAULT_FORMAL_G31_1X_REFERENCE,
) -> float:
    reference = json.loads(reference_path.resolve(strict=True).read_text(encoding="utf-8"))
    try:
        value = reference["paper_subjects"]["full_population_raw_bag_timing"][
            "metrics_seconds"
        ]["paper_network_from_admission"]["mean"]
        result = float(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise CriticalLoadError(
            f"formal G31 1x reference lacks network mean: {reference_path}"
        ) from exc
    if not math.isfinite(result):
        raise CriticalLoadError(
            f"formal G31 1x network mean is non-finite: {reference_path}"
        )
    return result


def _assert_formal_g31_1x_reproduction(
    rows: Sequence[Mapping[str, Any]],
    reference_path: Path = DEFAULT_FORMAL_G31_1X_REFERENCE,
) -> dict[str, Any]:
    row = next(
        (
            value
            for value in rows
            if value["method"] == "G31_S4_NATIVE_SYSTEM"
            and value["load_factor"] == "1.00"
        ),
        None,
    )
    if row is None or row.get("population_latency_mean_seconds") is None:
        raise CriticalLoadError("critical curve lacks formal G31 1x timing")
    expected = _formal_g31_1x_network_mean_seconds(reference_path)
    observed = float(row["population_latency_mean_seconds"])
    delta = observed - expected
    if abs(delta) > FORMAL_G31_1X_MEAN_TOLERANCE_SECONDS:
        raise CriticalLoadError(
            "G31 1x does not reproduce the frozen original-paper same-HCA "
            f"network mean: observed={observed}, expected={expected}, "
            f"delta={delta}"
        )
    return {
        "status": "PASS",
        "reference_path": str(reference_path.resolve()),
        "reference_sha256": _sha256(reference_path.resolve(strict=True)),
        "expected_mean_seconds": expected,
        "observed_mean_seconds": observed,
        "absolute_delta_seconds": abs(delta),
        "tolerance_seconds": FORMAL_G31_1X_MEAN_TOLERANCE_SECONDS,
    }


def _report(rows: Sequence[Mapping[str, Any]]) -> str:
    reproduction = _assert_formal_g31_1x_reproduction(rows)
    first_by_method = {
        method: next(
            (
                row["first_incomplete_load_factor"]
                for row in rows
                if row["method"] == method
            ),
            None,
        )
        for method in METHODS
    }
    lines = [
        "# CIE map2 critical-load curve v2",
        "",
        "All five cells are the unjittered, whole-flight, schedule-preserving map2 ladder. "
        "HCA and the Feng paper-environment DH reconstruction consume the same raw bytes; "
        "G31 preserves that raw population, topology, destinations and deadlines, while its "
        "canonical `pass_time` alone is aligned by segment ID to the corresponding native "
        "HCA run_01 release epoch. This is the frozen original-paper `same_hca` G31 timing "
        "protocol, not a policy or parameter change. Every result uses the absolute "
        "98,259 s horizon and the full raw-bag denominator.",
        f"The frozen formal 1x reference is "
        f"`{reproduction['reference_path']}` (SHA-256 "
        f"`{reproduction['reference_sha256']}`); the rerun reproduces its G31 network mean "
        f"at {_fmt(reproduction['observed_mean_seconds'], 9)} s versus "
        f"{_fmt(reproduction['expected_mean_seconds'], 9)} s "
        f"(absolute delta {_fmt(reproduction['absolute_delta_seconds'], 12)} s).",
        f"The G31 cells use final repaired native binary SHA-256 "
        f"`{EXPECTED_FINAL_G31_SHA256}`.",
        f"The DH cells use reconstruction source SHA-256 "
        f"`{EXPECTED_FINAL_DH_SOURCE_SHA256}` and compiled-class aggregate "
        f"`{EXPECTED_FINAL_DH_CLASS_SHA256}`.",
        "",
        "## Critical-load summary",
        "",
        "| Method | First incomplete load | Completion-rate AUC | Capacity-deficit-rate area | 2x completed / population | 2x on-time rate | 2x source backlog end / peak | 2x source AUC (bag-s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        row = next(
            row for row in rows if row["method"] == method and row["load_factor"] == "2.00"
        )
        lines.append(
            f"| {method} | {_fmt(first_by_method[method], 2)} | "
            f"{_fmt(row['completion_rate_curve_auc'], 6)} | "
            f"{_fmt(row['capacity_deficit_rate_curve_area'], 6)} | "
            f"{row['completed_raw_bag_count']} / {row['raw_bag_denominator']} | "
            f"{_fmt(row['on_time_rate'])} | {row['source_backlog_end']} / "
            f"{row['source_backlog_peak']} | "
            f"{_fmt(row['source_backlog_auc_bag_seconds'], 1)} |"
        )
    lines.extend(
        [
            "",
            "## Complete curve",
            "",
            "| Method | Load | Completion | On-time | Capacity deficit | Source backlog end / peak | Source / network / total backlog AUC | t95 (s) | t99 (s) | Timing status |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['load_factor']} | "
            f"{_fmt(row['completion_rate'])} | {_fmt(row['on_time_rate'])} | "
            f"{row['capacity_deficit_raw_bags']} | {row['source_backlog_end']} / "
            f"{row['source_backlog_peak']} | "
            f"{_fmt(row['source_backlog_auc_bag_seconds'], 1)} / "
            f"{_fmt(row['network_backlog_auc_bag_seconds'], 1)} / "
            f"{_fmt(row['total_backlog_auc_bag_seconds'], 1)} | "
            f"{_fmt(row['time_to_95_percent_seconds'], 1)} | "
            f"{_fmt(row['time_to_99_percent_seconds'], 1)} | "
            f"{row['full_population_timing_status']} |"
        )
    lines.extend(
        [
            "",
            "## Shared processed-attempt timing under the original-business protocol",
            "",
            "| Method | Load | Mean (s) | P95 (s) | P99 (s) | Max (s) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['load_factor']} | "
            f"{_fmt(row.get('population_latency_mean_seconds'))} | "
            f"{_fmt(row.get('population_latency_p95_seconds'))} | "
            f"{_fmt(row.get('population_latency_p99_seconds'))} | "
            f"{_fmt(row.get('population_latency_max_seconds'))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation contract",
            "",
            "- `capacity_deficit_raw_bags` is the frozen raw population minus completed raw bags at 98,259 s.",
            "- Completion-rate AUC is trapezoidal integration over the complete frozen 1.00–2.00 load ladder. Capacity-deficit-rate area integrates `1 - completion_rate` over that same interval; no cell is selected or omitted.",
            "- Source-backlog AUC integrates every not-yet-fully-admitted bag to its admission or the fixed horizon; incomplete tails are not dropped.",
            "- `t95`/`t99` are elapsed from the first raw arrival and are N/A when the full-denominator target is not reached.",
            "- 2x THT is always N/A. At lower loads THT is published only for a method whose entire raw population completed; no survivor or common-success cohort is used.",
            "- G31 `execution_canonical_sha256` identifies the audited same-HCA-release projection. Its `canonical_sha256` remains the shared base workload identity; the alignment audit proves every non-`pass_time` field is byte-value identical by segment.",
            "- DH remains the explicitly labelled paper-environment reconstruction with undisclosed original coefficients, not recovered source-exact Feng DH.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_figure(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - figure is optional
        return
    figure, axes = plt.subplots(1, 3, figsize=(13.8, 4.0), constrained_layout=True)
    minimum_completion = min(float(row["completion_rate"]) for row in rows)
    for method in METHODS:
        method_rows = [row for row in rows if row["method"] == method]
        x = [float(row["load_factor"]) for row in method_rows]
        axes[0].plot(x, [float(row["completion_rate"]) for row in method_rows], marker="o", label=method)
        axes[1].plot(x, [float(row["on_time_rate"]) for row in method_rows], marker="o", label=method)
        axes[2].plot(x, [float(row["source_backlog_auc_bag_seconds"]) for row in method_rows], marker="o", label=method)
    axes[0].set_ylabel("Raw-bag completion rate (zoomed)")
    axes[0].set_ylim(max(0.0, minimum_completion - 0.0004), 1.0002)
    axes[1].set_ylabel("On-time raw-bag rate")
    axes[1].set_ylim(max(0.0, min(float(row["on_time_rate"]) for row in rows) - 0.03), 1.01)
    axes[2].set_ylabel("Source backlog AUC (bag-s)")
    for axis in axes:
        axis.set_xlabel("Nominal load factor")
        axis.set_xticks(LOAD_FACTORS)
        axis.grid(alpha=0.25)
    axes[0].legend(fontsize=7)
    figure.suptitle("map2 fixed-horizon critical-load curve")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def aggregate(
    *,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    table_path: Path = DEFAULT_TABLE,
    report_path: Path = DEFAULT_REPORT,
    figure_path: Path = DEFAULT_FIGURE,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for method in METHODS:
        for factor in LOAD_FACTORS:
            row, _details = _normalise_one(method, factor, runtime_root)
            rows.append(row)
    for method in METHODS:
        first = next(
            (
                float(row["load_factor"])
                for row in rows
                if row["method"] == method and int(row["capacity_deficit_raw_bags"]) > 0
            ),
            None,
        )
        method_rows = [row for row in rows if row["method"] == method]
        completion_auc = 0.0
        deficit_rate_area = 0.0
        deficit_raw_area = 0.0
        for left, right in zip(method_rows, method_rows[1:]):
            width = float(right["load_factor"]) - float(left["load_factor"])
            left_rate = float(left["completion_rate"])
            right_rate = float(right["completion_rate"])
            completion_auc += width * (left_rate + right_rate) / 2.0
            deficit_rate_area += width * (
                (1.0 - left_rate) + (1.0 - right_rate)
            ) / 2.0
            deficit_raw_area += width * (
                int(left["capacity_deficit_raw_bags"])
                + int(right["capacity_deficit_raw_bags"])
            ) / 2.0
        for row in rows:
            if row["method"] == method:
                row["first_incomplete_load_factor"] = first
                row["completion_rate_curve_auc"] = completion_auc
                row["capacity_deficit_rate_curve_area"] = deficit_rate_area
                row["capacity_deficit_raw_bag_curve_area"] = deficit_raw_area
    reproduction = _assert_formal_g31_1x_reproduction(rows)
    _atomic_csv(table_path, rows)
    _atomic_text(report_path, _report(rows))
    _render_figure(rows, figure_path)
    _atomic_json(
        runtime_root / "aggregate_status.json",
        {
            "schema": SCHEMA,
            "status": "COMPLETE",
            "generated_at": _utc_now(),
            "fixed_horizon_seconds": FIXED_HORIZON_SECONDS,
            "row_count": len(rows),
            "formal_g31_1x_reproduction": reproduction,
            "table_path": str(table_path.resolve()),
            "table_sha256": _sha256(table_path),
            "report_path": str(report_path.resolve()),
            "report_sha256": _sha256(report_path),
        },
    )
    return rows


def _selected_factors(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(LOAD_FACTORS if not values else values)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--workload-root", type=Path, default=DEFAULT_WORKLOAD_ROOT)
    generate.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)

    stage = commands.add_parser("stage-g31")
    stage.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    stage.add_argument("--g31-root", type=Path, default=DEFAULT_G31_ROOT)

    run = commands.add_parser("run")
    run.add_argument("--method", choices=("hca", "dh", "g31", "all"), default="all")
    run.add_argument("--factor", type=float, choices=LOAD_FACTORS, action="append", default=[])
    run.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    run.add_argument("--g31-binary", type=Path, default=DEFAULT_G31_BINARY)
    run.add_argument("--force", action="store_true")

    campaign = commands.add_parser("campaign")
    campaign.add_argument("--workload-root", type=Path, default=DEFAULT_WORKLOAD_ROOT)
    campaign.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    campaign.add_argument("--g31-binary", type=Path, default=DEFAULT_G31_BINARY)
    campaign.add_argument("--force", action="store_true")

    aggregate_parser = commands.add_parser("aggregate")
    aggregate_parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    aggregate_parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    aggregate_parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    aggregate_parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        manifest = generate_workloads(
            workload_root=args.workload_root, runtime_root=args.runtime_root
        )
        print(json.dumps({"status": manifest["status"], "loads": len(manifest["loads"])}))
        return 0
    if args.command == "stage-g31":
        stage_g31(runtime_root=args.runtime_root, g31_root=args.g31_root)
        print(json.dumps({"status": "G31_STAGED", "loads": len(LOAD_FACTORS)}))
        return 0
    if args.command == "run":
        factors = _selected_factors(args.factor)
        if args.method in {"g31", "all"}:
            run_g31(
                factors=factors,
                runtime_root=args.runtime_root,
                binary=args.g31_binary,
                force=args.force,
            )
        if args.method in {"dh", "all"}:
            run_dh(factors=factors, runtime_root=args.runtime_root, force=args.force)
        if args.method in {"hca", "all"}:
            run_hca(factors=factors, runtime_root=args.runtime_root, force=args.force)
        print(json.dumps({"status": "RUNS_COMPLETE", "factors": factors}))
        return 0
    if args.command == "campaign":
        generate_workloads(
            workload_root=args.workload_root, runtime_root=args.runtime_root
        )
        run_g31(
            factors=LOAD_FACTORS,
            runtime_root=args.runtime_root,
            binary=args.g31_binary,
            force=args.force,
        )
        run_dh(factors=LOAD_FACTORS, runtime_root=args.runtime_root, force=args.force)
        run_hca(factors=LOAD_FACTORS, runtime_root=args.runtime_root, force=args.force)
        rows = aggregate(runtime_root=args.runtime_root)
        print(json.dumps({"status": "COMPLETE", "rows": len(rows)}))
        return 0
    rows = aggregate(
        runtime_root=args.runtime_root,
        table_path=args.table,
        report_path=args.report,
        figure_path=args.figure,
    )
    print(json.dumps({"status": "COMPLETE", "rows": len(rows)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CriticalLoadError, external.ExternalBaselineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
