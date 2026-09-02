#!/usr/bin/env python3
"""Create transparent fixed-horizon backlog-area corrections for CIE artifacts.

The original artifacts are immutable evidence.  This module builds a separate
view which retains their last-event integral and, when the last event can be
reconstructed exactly, adds the missing constant-backlog tail through the
registered observation horizon.  Ambiguous legacy tails are ``N/M`` rather
than silently reused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from scripts.eval import g4irsf11_capacity_metrics as capacity


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "czr005.cie_backlog_area_correction.v1"
CANONICAL_LAST_RAW_ARRIVAL_BY_LOAD = {
    1.0: 81_503.72582,
    2.0: 82_403.72582,
}
GROUPS = (
    "raw_bag_total",
    "raw_bag_source_until_all_segments_admitted",
    "raw_bag_network_after_all_segments_admitted",
)


class BacklogAreaCorrectionError(RuntimeError):
    """Raised when an allegedly exact correction cannot be established."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0.0 or not number.is_integer():
        return None
    return int(number)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_value(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def business_payload(artifact: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the detailed fixed-denominator payload from every CIE run shape."""

    paper = artifact.get("paper_subjects")
    if isinstance(paper, Mapping):
        value = paper.get("fixed_denominator_business")
        if isinstance(value, Mapping):
            return value
    outer = artifact.get("fixed_denominator_business")
    if isinstance(outer, Mapping):
        detailed = outer.get("detailed")
        return detailed if isinstance(detailed, Mapping) else outer
    return {}


def _unavailable(
    *,
    group: str,
    status: str,
    metric: Mapping[str, Any],
    legacy_area: float | None,
    legacy_method: str,
    raw_last_arrival: float,
    horizon: float,
) -> dict[str, Any]:
    return {
        "group": group,
        "status": status,
        "reportable": False,
        "legacy_area_seconds": legacy_area,
        "legacy_method": legacy_method,
        "corrected_area_seconds": None,
        "correction_seconds": None,
        "reported_method": None,
        "raw_last_arrival_seconds": raw_last_arrival,
        "derived_last_event_seconds": None,
        "observation_end_seconds": horizon,
        "end_backlog": metric.get("end_backlog"),
    }


def correction_view(
    business: Mapping[str, Any],
    *,
    raw_last_arrival: float,
) -> dict[str, Any]:
    """Return exact corrected areas, or explicit N/M, without mutating input."""

    horizon = _number(business.get("fixed_horizon_seconds"))
    raw_last_arrival = _number(raw_last_arrival)
    if horizon is None or raw_last_arrival is None:
        raise BacklogAreaCorrectionError(
            "fixed horizon and raw last arrival must be finite"
        )
    if raw_last_arrival > horizon:
        raise BacklogAreaCorrectionError(
            "raw last arrival lies after the fixed observation horizon"
        )
    backlog = business.get("backlog")
    if not isinstance(backlog, Mapping):
        raise BacklogAreaCorrectionError("business payload lacks backlog metrics")

    metrics: dict[str, Mapping[str, Any]] = {}
    for group in GROUPS:
        value = backlog.get(group)
        metrics[group] = value if isinstance(value, Mapping) else {}

    def recovered_drain(metric: Mapping[str, Any]) -> float | None:
        departures = _integer(metric.get("departure_count"))
        if departures == 0:
            return 0.0
        value = _number(metric.get("drain_time_seconds"))
        return value if value is not None and value >= 0.0 else None

    total_drain = recovered_drain(metrics[GROUPS[0]])
    source_drain = recovered_drain(metrics[GROUPS[1]])

    corrected: dict[str, Any] = {}
    for group, metric in metrics.items():
        legacy_area = _number(metric.get("backlog_area_seconds"))
        end = _integer(metric.get("end_backlog"))
        arrivals = _integer(metric.get("arrival_count"))
        departures = _integer(metric.get("departure_count"))
        legacy_method = str(
            metric.get(
                "backlog_area_method",
                capacity.BACKLOG_AREA_METHOD_LAST_EVENT_V1,
            )
        )
        if (
            legacy_area is None
            or end is None
            or arrivals is None
            or departures is None
            or arrivals < departures
            or end != arrivals - departures
        ):
            corrected[group] = _unavailable(
                group=group,
                status="N_M_INVALID_OR_INCONSISTENT_LEGACY_COUNTERS",
                metric=metric,
                legacy_area=legacy_area,
                legacy_method=legacy_method,
                raw_last_arrival=raw_last_arrival,
                horizon=horizon,
            )
            continue

        metric_observation_end = _number(metric.get("observation_end_seconds"))
        if legacy_method == capacity.BACKLOG_AREA_METHOD_OBSERVATION_END_V2:
            metric_last_event = _number(metric.get("last_event_time_seconds"))
            if (
                metric_observation_end != horizon
                or metric.get("area_includes_residual_to_observation_end")
                is not True
                or (end > 0 and metric_last_event is None)
                or (
                    metric_last_event is not None
                    and metric_last_event > horizon
                )
            ):
                corrected[group] = _unavailable(
                    group=group,
                    status="N_M_OBSERVATION_END_IDENTITY_MISMATCH",
                    metric=metric,
                    legacy_area=legacy_area,
                    legacy_method=legacy_method,
                    raw_last_arrival=raw_last_arrival,
                    horizon=horizon,
                )
                continue
            corrected[group] = {
                "group": group,
                "status": "EXACT_NATIVE_OBSERVATION_END_V2",
                "reportable": True,
                "legacy_area_seconds": None,
                "legacy_method": None,
                "corrected_area_seconds": legacy_area,
                "correction_seconds": 0.0,
                "reported_method": legacy_method,
                "raw_last_arrival_seconds": raw_last_arrival,
                "derived_last_event_seconds": _number(
                    metric.get("last_event_time_seconds")
                ),
                "observation_end_seconds": horizon,
                "end_backlog": end,
            }
            continue

        # A zero tail makes the legacy last-event area numerically exact even
        # though it predates the explicit observation-end method marker.
        if end == 0:
            corrected[group] = {
                "group": group,
                "status": "EXACT_LEGACY_ZERO_END_BACKLOG",
                "reportable": True,
                "legacy_area_seconds": legacy_area,
                "legacy_method": legacy_method,
                "corrected_area_seconds": legacy_area,
                "correction_seconds": 0.0,
                "reported_method": (
                    "LEGACY_LAST_EVENT_EQUIVALENT_AT_ZERO_END_BACKLOG"
                ),
                "raw_last_arrival_seconds": raw_last_arrival,
                "derived_last_event_seconds": None,
                "observation_end_seconds": horizon,
                "end_backlog": end,
            }
            continue

        if group == GROUPS[0]:
            last_event = (
                raw_last_arrival + total_drain
                if total_drain is not None
                else None
            )
        elif group == GROUPS[1]:
            last_event = (
                raw_last_arrival + source_drain
                if source_drain is not None
                else None
            )
        else:
            if (
                total_drain is None
                or source_drain is None
                or max(total_drain, source_drain) == 0.0
            ):
                last_event = None
            else:
                last_event = raw_last_arrival + max(total_drain, source_drain)

        if last_event is None:
            corrected[group] = _unavailable(
                group=group,
                status="N_M_LEGACY_LAST_EVENT_NOT_EXACTLY_RECOVERABLE",
                metric=metric,
                legacy_area=legacy_area,
                legacy_method=legacy_method,
                raw_last_arrival=raw_last_arrival,
                horizon=horizon,
            )
            continue
        if last_event > horizon:
            corrected[group] = _unavailable(
                group=group,
                status="N_M_DERIVED_LAST_EVENT_AFTER_HORIZON",
                metric=metric,
                legacy_area=legacy_area,
                legacy_method=legacy_method,
                raw_last_arrival=raw_last_arrival,
                horizon=horizon,
            )
            continue
        tail = float(end) * (horizon - last_event)
        corrected[group] = {
            "group": group,
            "status": "EXACT_LEGACY_TAIL_CORRECTED_V1",
            "reportable": True,
            "legacy_area_seconds": legacy_area,
            "legacy_method": legacy_method,
            "corrected_area_seconds": legacy_area + tail,
            "correction_seconds": tail,
            "reported_method": "LEGACY_PLUS_EXACT_FIXED_HORIZON_TAIL_V1",
            "raw_last_arrival_seconds": raw_last_arrival,
            "derived_last_event_seconds": last_event,
            "observation_end_seconds": horizon,
            "end_backlog": end,
        }

    segment_views: dict[str, Any] = {}
    for group in ("segment_source", "segment_network"):
        metric = backlog.get(group)
        metric = metric if isinstance(metric, Mapping) else {}
        method = metric.get("backlog_area_method")
        area = _number(metric.get("backlog_area_seconds"))
        end = _integer(metric.get("end_backlog"))
        observation_end = _number(metric.get("observation_end_seconds"))
        if (
            method == capacity.BACKLOG_AREA_METHOD_OBSERVATION_END_V2
            and metric.get("area_includes_residual_to_observation_end") is True
            and observation_end == horizon
            and area is not None
        ):
            segment_views[group] = {
                "status": "EXACT_NATIVE_OBSERVATION_END_V2",
                "reportable": True,
                "legacy_area_seconds": None,
                "corrected_area_seconds": area,
                "reported_method": method,
                "end_backlog": end,
            }
        else:
            segment_views[group] = {
                "status": "N_M_LEGACY_SEGMENT_EVENTS_NOT_REPLAYED",
                "reportable": False,
                "legacy_area_seconds": area,
                "corrected_area_seconds": None,
                "reported_method": None,
                "end_backlog": end,
            }

    return {
        "schema": SCHEMA,
        "status": (
            "COMPLETE"
            if all(value["reportable"] for value in corrected.values())
            else "PARTIAL_WITH_EXPLICIT_N_M"
        ),
        "raw_last_arrival_seconds": raw_last_arrival,
        "observation_end_seconds": horizon,
        "groups": corrected,
        "non_aggregated_segment_groups": segment_views,
        "source_artifact_mutated": False,
    }


def canonical_last_raw_arrival(artifact: Mapping[str, Any]) -> float:
    load = _number(artifact.get("scale"))
    if load is None:
        load = _number(artifact.get("nominal_load_factor"))
    if load not in CANONICAL_LAST_RAW_ARRIVAL_BY_LOAD:
        raise BacklogAreaCorrectionError(
            f"no registered canonical last arrival for load {load!r}"
        )
    return CANONICAL_LAST_RAW_ARRIVAL_BY_LOAD[load]


def requires_legacy_tail_reconstruction(artifact: Mapping[str, Any]) -> bool:
    """Whether any raw-bag area has an incomplete unversioned tail."""

    business = business_payload(artifact)
    backlog = business.get("backlog")
    if not isinstance(backlog, Mapping):
        return False
    for group in GROUPS:
        metric = backlog.get(group)
        if not isinstance(metric, Mapping):
            continue
        if (
            metric.get("backlog_area_method")
            != capacity.BACKLOG_AREA_METHOD_OBSERVATION_END_V2
            and _integer(metric.get("end_backlog")) not in (None, 0)
        ):
            return True
    return False


def embedded_or_zero_tail_last_arrival(artifact: Mapping[str, Any]) -> float:
    """Use embedded v2 identity, or a neutral value when every tail is zero."""

    business = business_payload(artifact)
    total = business.get("backlog")
    total = total.get("raw_bag_total") if isinstance(total, Mapping) else None
    if isinstance(total, Mapping):
        embedded = _number(total.get("last_arrival_time_seconds"))
        if embedded is not None:
            return embedded
    if not requires_legacy_tail_reconstruction(artifact):
        # Last arrival cancels out when every legacy end backlog is zero.
        return 0.0
    raise BacklogAreaCorrectionError(
        "incomplete legacy backlog requires exact last-arrival reconstruction"
    )


def _random_args(artifact: Mapping[str, Any], manifest: Path) -> SimpleNamespace:
    from scripts.eval import run_cie_random_robustness as random_runner

    provenance = artifact.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    release = artifact.get("release_protocol")
    release = release if isinstance(release, Mapping) else {}
    release_evidence = release.get("evidence")
    release_evidence = (
        release_evidence if isinstance(release_evidence, Mapping) else {}
    )
    release_source = release_evidence.get("source_root")
    release_source = (
        Path(release_source) if isinstance(release_source, str) else None
    )
    load_factor = _number(artifact.get("load_factor"))
    if load_factor == 1.0:
        release_gates = {
            "base_release_mode": (
                release.get("base_release_mode_before_random_jitter")
                == "same_hca"
            ),
            "base_release_pass": (
                release.get("base_same_hca_release_trace_pass") is True
            ),
            "evidence_pass": release_evidence.get("pass") is True,
            "evidence_status": (
                release_evidence.get("status")
                == "ELIGIBLE_EXACT_HCA_RELEASE_TRACE"
            ),
            "source_root_recorded": release_source is not None,
        }
        if not all(release_gates.values()):
            raise BacklogAreaCorrectionError(
                "random 1x correction requires its recorded, eligible "
                f"same-HCA release root: {release_gates}"
            )
        try:
            release_source = release_source.resolve(strict=True)
        except OSError as exc:
            raise BacklogAreaCorrectionError(
                "recorded same-HCA release root is unavailable"
            ) from exc
        if not release_source.is_dir():
            raise BacklogAreaCorrectionError(
                "recorded same-HCA release root is not a directory"
            )
    value = provenance.get("workload_path")
    provenance_workload = Path(value) if isinstance(value, str) else None
    canonical_workload = (
        provenance_workload if load_factor not in (1.0, 2.0) else None
    )
    return SimpleNamespace(
        map=artifact.get("map"),
        load_factor=load_factor,
        arm=artifact.get("arm"),
        seed=artifact.get("seed"),
        binary=Path(str(provenance.get("binary_path"))),
        output=Path("backlog-correction-does-not-run-native.json"),
        revision_manifest=manifest,
        canonical_workload=canonical_workload,
        load_manifest=random_runner.activation.DEFAULT_LOAD_MANIFEST,
        nanning_task_dir=(
            provenance_workload.parent
            if artifact.get("map") == "nanning"
            and load_factor in (1.0, 2.0)
            and provenance_workload is not None
            else random_runner.factorial.g35.nanning_native.DEFAULT_TASK_DIR
        ),
        nanning_map_profile=random_runner.factorial.g35.nanning_native.DEFAULT_MAP_PROFILE,
        nanning_hca_root=(
            release_source
            if artifact.get("map") == "nanning" and load_factor == 1.0
            else random_runner.factorial.g35.nanning_paired.DEFAULT_HCA_ROOT
        ),
        map2_workload_1x=(
            provenance_workload
            if artifact.get("map") == "map2" and load_factor == 1.0
            else random_runner.factorial.g35.map2_native.DEFAULT_WORKLOAD_1X
        ),
        map2_workload_2x=(
            provenance_workload
            if artifact.get("map") == "map2" and load_factor == 2.0
            else random_runner.factorial.g35.map2_native.DEFAULT_WORKLOAD_2X
        ),
        map2_hca_case_root=(
            release_source
            if artifact.get("map") == "map2" and load_factor == 1.0
            else None
        ),
        dry_run=True,
        force=False,
    )


def regenerate_random_last_raw_arrival(
    artifact: Mapping[str, Any],
    *,
    manifest_path: Path,
) -> tuple[float, dict[str, Any]]:
    """Rebuild one frozen jitter realization and verify all stored identities."""

    from scripts.eval import run_cie_random_robustness as random_runner

    manifest = manifest_path.resolve(strict=True)
    contract = random_runner.load_random_contract(manifest)
    stored_contract = artifact.get("random_contract")
    stored_contract = stored_contract if isinstance(stored_contract, Mapping) else {}
    provenance = artifact.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    perturbation = artifact.get("perturbation")
    perturbation = perturbation if isinstance(perturbation, Mapping) else {}
    stored_arrival = perturbation.get("arrival_jitter_seconds")
    stored_arrival = stored_arrival if isinstance(stored_arrival, Mapping) else {}

    args = _random_args(artifact, manifest)
    _case, workload, _request, _release, prepared = (
        random_runner.prepare_randomized_cell(args, contract)
    )
    rebuilt = prepared.get("perturbation")
    rebuilt = rebuilt if isinstance(rebuilt, Mapping) else {}
    rebuilt_arrival = rebuilt.get("arrival_jitter_seconds")
    rebuilt_arrival = rebuilt_arrival if isinstance(rebuilt_arrival, Mapping) else {}
    source = Path(workload.source_path).resolve(strict=True)
    rows = tuple(workload.rows)
    arrivals_by_task: dict[int, list[float]] = {}
    for row in rows:
        arrivals_by_task.setdefault(int(row["task_id"]), []).append(
            float(row.get("original_entry_time", row["pass_time"]))
        )
    raw_arrivals = [min(values) for values in arrivals_by_task.values()]
    if not raw_arrivals:
        raise BacklogAreaCorrectionError("random workload has no raw arrivals")

    gates = {
        "manifest_sha256": (
            stored_contract.get("manifest_sha256") == contract.manifest_sha256
            and _sha256_file(manifest) == contract.manifest_sha256
        ),
        "workload_sha256": (
            provenance.get("workload_sha256") == _sha256_file(source)
        ),
        "arrival_realization_sha256": (
            stored_arrival.get("realization_sha256")
            == rebuilt_arrival.get("realization_sha256")
        ),
        "base_arrival_schedule_sha256": (
            perturbation.get("base_arrival_schedule_sha256")
            == rebuilt.get("base_arrival_schedule_sha256")
        ),
        "randomized_arrival_schedule_sha256": (
            perturbation.get("randomized_arrival_schedule_sha256")
            == rebuilt.get("randomized_arrival_schedule_sha256")
        ),
        "combined_realization_sha256": (
            perturbation.get("combined_realization_sha256")
            == rebuilt.get("combined_realization_sha256")
        ),
        "pairing_key": perturbation.get("pairing_key")
        == rebuilt.get("pairing_key"),
        "same_realization_required_for_both_arms": (
            perturbation.get("same_realization_required_for_both_arms") is True
        ),
        "arm_used_to_generate_randomness": (
            perturbation.get("arm_used_to_generate_randomness") is False
        ),
    }
    if not all(gates.values()):
        raise BacklogAreaCorrectionError(
            f"random jitter identity could not be reproduced exactly: {gates}"
        )
    return max(raw_arrivals), {
        "method": "FROZEN_MANIFEST_SEED_JITTER_REGENERATION_V1",
        "gates": gates,
        "pass": True,
    }


def artifact_correction(
    artifact: Mapping[str, Any],
    *,
    source_path: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    schema = str(artifact.get("schema", ""))
    if schema == "czr005.cie_random_robustness.single_cell.v1":
        if manifest_path is None:
            raise BacklogAreaCorrectionError(
                "random artifact correction requires the frozen manifest"
            )
        last_arrival, arrival_identity = regenerate_random_last_raw_arrival(
            artifact, manifest_path=manifest_path
        )
    else:
        last_arrival = canonical_last_raw_arrival(artifact)
        arrival_identity = {
            "method": "REGISTERED_CANONICAL_LAST_RAW_ARRIVAL_V1",
            "pass": True,
        }
    view = correction_view(
        business_payload(artifact), raw_last_arrival=last_arrival
    )
    source_sha = _sha256_file(source_path) if source_path is not None else None
    return {
        **view,
        "source": {
            "path": str(source_path.resolve()) if source_path is not None else None,
            "sha256": source_sha,
            "artifact_schema": schema,
            "artifact_status": artifact.get("status"),
        },
        "arrival_identity": arrival_identity,
    }


def _pair_random_supplements(
    supplements: list[dict[str, Any]], artifacts: Sequence[Mapping[str, Any]]
) -> None:
    groups: dict[tuple[Any, Any, Any], list[int]] = {}
    for index, artifact in enumerate(artifacts):
        if artifact.get("schema") != "czr005.cie_random_robustness.single_cell.v1":
            continue
        key = (artifact.get("map"), artifact.get("load_factor"), artifact.get("seed"))
        groups.setdefault(key, []).append(index)
    for indexes in groups.values():
        arms = {artifacts[index].get("arm") for index in indexes}
        identities = {
            _sha256_value(artifacts[index].get("perturbation")) for index in indexes
        }
        pair_pass = arms == {"P0D0", "P1D1"} and len(identities) == 1
        for index in indexes:
            supplements[index]["arrival_identity"]["paired_arms_present"] = sorted(
                str(value) for value in arms
            )
            supplements[index]["arrival_identity"][
                "paired_artifact_realization_identity_pass"
            ] = pair_pass
            supplements[index]["arrival_identity"]["pass"] = bool(
                supplements[index]["arrival_identity"].get("pass") and pair_pass
            )
            if not pair_pass:
                supplements[index]["status"] = (
                    "PARTIAL_RANDOM_PAIR_IDENTITY_NOT_ESTABLISHED"
                )
                groups = supplements[index].get("groups")
                if isinstance(groups, Mapping):
                    for value in groups.values():
                        if not isinstance(value, dict):
                            continue
                        value["provisional_corrected_area_seconds"] = value.get(
                            "corrected_area_seconds"
                        )
                        value["corrected_area_seconds"] = None
                        value["reportable"] = False
                        value["status"] = "N_M_RANDOM_PAIR_IDENTITY_NOT_ESTABLISHED"


def write_supplements(
    paths: Sequence[Path],
    *,
    output_dir: Path,
    manifest_path: Path | None = None,
) -> list[Path]:
    artifacts: list[Mapping[str, Any]] = []
    resolved_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve(strict=True)
        value = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise BacklogAreaCorrectionError(f"artifact is not an object: {resolved}")
        artifacts.append(value)
        resolved_paths.append(resolved)
    supplements = [
        artifact_correction(
            artifact,
            source_path=path,
            manifest_path=manifest_path,
        )
        for path, artifact in zip(resolved_paths, artifacts)
    ]
    _pair_random_supplements(supplements, artifacts)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path, supplement in zip(resolved_paths, supplements):
        target = output_dir / f"{path.stem}.backlog_area_correction.json"
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(supplement, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, target)
        written.append(target)
    return written


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--revision-manifest", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    written = write_supplements(
        args.artifact,
        output_dir=args.output_dir,
        manifest_path=args.revision_manifest,
    )
    print(json.dumps({"status": "COMPLETE", "written": [str(p) for p in written]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BacklogAreaCorrectionError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CIE backlog-area correction failed: {exc}")
        raise SystemExit(2)
