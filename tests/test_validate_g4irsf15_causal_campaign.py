from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import validate_g4irsf15_causal_campaign as validator
from scripts import run_g4irsf15_campaign_shards as orchestrator
from scripts.eval import g4irsf15_causal_campaign as campaign


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_real_protected_input_schema_reconstructs_native_record_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / campaign.TASK_PATH).open(
        "r", encoding="utf-8"
    ) as handle:
        first_row = json.loads(handle.readline())
    assert "deadline" not in first_row
    assert "source" not in first_row
    assert first_row["std"] == 22_200.0

    prefix = campaign.g12.load_input_prefix(
        campaign.FULL_SEGMENT_COUNT, root=root
    )
    native_records = campaign.g12.binding_bag_records(prefix)
    native_workload_fields: list[tuple[str, str, object]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.input_runtime_cohort_order.v1",
        ),
        ("request_count", "u", len(native_records)),
    ]
    for runtime_bag_id, record in enumerate(native_records):
        segment_id, task_id, release, deadline, start, goal, source = record
        native_workload_fields.append(
            (
                "request",
                "s",
                validator.canonical_fields_payload(
                    [
                        ("runtime_bag_id", "u", runtime_bag_id),
                        ("task_id", "i", task_id),
                        ("segment_id", "s", segment_id),
                        ("start", "i", start),
                        ("goal", "i", goal),
                        ("release_time", "d", release),
                        ("deadline", "d", deadline),
                        ("source", "s", source),
                    ]
                ),
            )
        )
    native_workload_sha256 = validator.canonical_fields_sha256(
        native_workload_fields
    )

    produced = campaign._protected_inputs(root)
    independently_reconstructed = validator.protected_inputs(root)

    assert produced["task"]["segment_count"] == campaign.FULL_SEGMENT_COUNT
    assert produced["task"]["raw_bag_count"] == campaign.FULL_RAW_BAG_COUNT
    assert (
        produced["task"]["input_runtime_cohort_sha256"]
        == native_workload_sha256
        == "7f3a01c58ae4e703297320f2fa8d8020564f32cb1c3661e2f97c7fd8967fea60"
    )
    assert independently_reconstructed == {
        "segment_count": produced["task"]["segment_count"],
        "raw_bag_count": produced["task"]["raw_bag_count"],
        "input_runtime_cohort_sha256": produced["task"][
            "input_runtime_cohort_sha256"
        ],
        "runtime_segment_mapping_sha256": produced["task"][
            "runtime_segment_mapping_sha256"
        ],
        "raw_bag_mapping_sha256": produced["task"][
            "raw_bag_mapping_sha256"
        ],
        "raw_bag_original_entry_mapping_sha256": produced["task"][
            "raw_bag_original_entry_mapping_sha256"
        ],
    }


def _sampling() -> dict[str, object]:
    return {
        "sampling_stratum_id": "I1|TAIL|NO_DIVERGENCE|LOW",
        "N_h": 10,
        "n_h": 2,
        "sealed_pool_n_h": 5,
        "stage2_frame_n_h": 4,
        "attempt_n_h": 2,
        "pool_pi_h": 0.5,
        "post_exclusion_survival_pi_h": 0.8,
        "stage2_pi_h": 0.5,
        "pi_h": 0.2,
        "analysis_weight": 5.0,
        "cluster_id": _sha("clone"),
        "cluster_bootstrap_unit": "clone_group_id",
    }


def _eligible_label() -> dict[str, object]:
    row: dict[str, object] = {
        "schema": validator.LABEL_SCHEMA,
        "target_key": f"{_sha('descriptor')}:H_system",
        "descriptor_id": _sha("descriptor"),
        "event_ordinal": 17,
        "kind": "I1",
        "clone_group_id": _sha("clone"),
        "horizon": "H_system",
        "eligible_causal_label": True,
        "exclusion_reason": "",
        "action_changed": True,
        "same_state_start": True,
        "certificate_valid": True,
        "hard_gate_pass": True,
        "safety_hard_gate_pass": True,
        "horizon_complete": True,
        "evidence_complete": True,
        "signed_label": "HARMFUL",
        "h_system_cohort_size": validator.FULL_SEGMENT_COUNT,
        "h_system_cohort_is_all_input_runtime_ids": True,
        "h_system_cohort_mapping_sha256": _sha("runtime-mapping"),
        "raw_bag_mapping_sha256": _sha("raw-mapping"),
        "pair_evidence_sha256": _sha("pair-evidence"),
        "realized_outcome_deltas_sha256": _sha(
            "realized-outcome-deltas"
        ),
        "realized_outcome_deltas_binding": {
            "row_count": 3,
            "content_sha256": _sha("realized-outcome-deltas"),
        },
        "committed_action_certificate_sha256": _sha(
            "committed-action-certificate"
        ),
        "direct_affected_runtime_bag_ids": [1, 2],
        "realized_affected_runtime_bag_ids": [1, 2, 9],
        "externality_runtime_bag_ids": [9],
        "realized_affected_set_observable": True,
        "offline_sampling_metadata": {
            "must_not_enter_policy_features": True
        },
        "sampling": _sampling(),
        "baseline_affected_bag_outcomes": [{"runtime_bag_id": 1}],
        "treatment_affected_bag_outcomes": [{"runtime_bag_id": 1}],
        "affected_bag_deltas": [{"runtime_bag_id": 1}],
    }
    row["label_sha256"] = validator.canonical_sha256(row)
    return row


def _compact_outcome(
    runtime_id: int, *, completion_seconds: float
) -> dict[str, object]:
    return {
        "runtime_bag_id": runtime_id,
        "task_id": runtime_id,
        "segment_id": f"{runtime_id}:segment",
        "start": 0,
        "goal": 1,
        "current_node": 1,
        "known": True,
        "completed": True,
        "failed": False,
        "status": "completed",
        "failure_reason": "",
        "release_time": 0.0,
        "deadline": 100.0,
        "admitted_time": 0.0,
        "finish_time": completion_seconds,
        "source_wait_seconds": 1.0,
        "total_local_wait_seconds": 2.0,
        "junction_wait_seconds": 1.0,
        "merge_wait_seconds": 0.0,
        "edge_travel_seconds": 4.0,
        "node_service_seconds": 3.0,
        "loop_extra_seconds": 0.0,
        "completion_seconds": completion_seconds,
        "decision_count": 2,
        "retry_count": 0,
        "loop_count": 0,
    }


def _compact_raw_sidecar(
    *,
    mapping_sha: str,
    raw_mapping_sha: str,
    original_entry_mapping_sha: str,
    changed: bool,
) -> dict[str, object]:
    rows = [
        {
            "task_id": 0,
            "runtime_bag_ids": [0, 1],
            "runtime_id_mapping_sha256": _sha("raw-row-map:0"),
            "row_sha256": _sha(
                "raw-row:0:treatment"
                if changed
                else "raw-row:0:baseline"
            ),
        },
        {
            "task_id": 1,
            "runtime_bag_ids": [2],
            "runtime_id_mapping_sha256": _sha("raw-row-map:1"),
            "row_sha256": _sha("raw-row:1:baseline"),
        },
    ]
    sidecar: dict[str, object] = {
        "schema": (
            "czr005.g4irsf15.raw_bag_sufficient_statistics.v1"
        ),
        "row_count": 2,
        "expected_raw_bag_count": 2,
        "selected_segment_count": 3,
        "complete_coverage": True,
        "task_id_order": "STRICT_ASCENDING_NUMERIC",
        "runtime_segment_mapping_sha256": mapping_sha,
        "raw_bag_mapping_sha256": raw_mapping_sha,
        "raw_bag_original_entry_mapping_sha256": (
            original_entry_mapping_sha
        ),
        "rows": rows,
    }
    sidecar["content_sha256"] = (
        campaign._raw_bag_sidecar_logical_content_sha256(sidecar)
    )
    return sidecar


def _compact_fixture() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    descriptor_id = _sha("compact-target")
    mapping_sha = _sha("h-system-mapping")
    raw_mapping_sha = _sha("raw-bag-mapping")
    original_entry_mapping_sha = _sha(
        "raw-bag-original-entry-mapping"
    )
    baseline_raw = _compact_raw_sidecar(
        mapping_sha=mapping_sha,
        raw_mapping_sha=raw_mapping_sha,
        original_entry_mapping_sha=original_entry_mapping_sha,
        changed=False,
    )
    treatment_raw = _compact_raw_sidecar(
        mapping_sha=mapping_sha,
        raw_mapping_sha=raw_mapping_sha,
        original_entry_mapping_sha=original_entry_mapping_sha,
        changed=True,
    )
    cohort_rows: list[dict[str, object]] = []
    realized_rows: list[dict[str, object]] = []
    digest_fields: list[tuple[str, str, object]] = [
        (
            "schema",
            "s",
            "czr005.g4irsf15.full_cohort_outcome_difference.v1",
        ),
        ("row_count", "u", 3),
    ]
    for runtime_id in range(3):
        baseline_outcome = _compact_outcome(
            runtime_id, completion_seconds=10.0 + runtime_id
        )
        treatment_outcome = copy.deepcopy(baseline_outcome)
        if runtime_id == 1:
            treatment_outcome["completion_seconds"] = 12.0
            treatment_outcome["finish_time"] = 12.0
            realized_rows.append(
                {
                    "runtime_bag_id": runtime_id,
                    "baseline": baseline_outcome,
                    "treatment": treatment_outcome,
                }
            )
        baseline_sha = hashlib.sha256(
            campaign._causal_outcome_payload(baseline_outcome)
        ).hexdigest()
        treatment_sha = hashlib.sha256(
            campaign._causal_outcome_payload(treatment_outcome)
        ).hexdigest()
        changed = baseline_sha != treatment_sha
        row_sha = campaign._canonical_fields_sha256(
            [
                ("runtime_bag_id", "i", runtime_id),
                ("baseline_outcome_sha256", "s", baseline_sha),
                ("treatment_outcome_sha256", "s", treatment_sha),
                ("outcome_changed", "b", changed),
            ]
        )
        cohort_rows.append(
            {
                "runtime_bag_id": runtime_id,
                "baseline_outcome_sha256": baseline_sha,
                "treatment_outcome_sha256": treatment_sha,
                "outcome_changed": changed,
                "row_sha256": row_sha,
            }
        )
        digest_fields.append(("row_sha256", "s", row_sha))
    digest_fields.append(("changed_count", "i", 1))
    cohort_sidecar = {
        "schema": (
            "czr005.g4irsf15.full_cohort_outcome_difference.v1"
        ),
        "row_count": 3,
        "changed_count": 1,
        "complete_coverage": True,
        "runtime_id_order": "CONTIGUOUS_ZERO_BASED_INPUT_ORDER",
        "rows": cohort_rows,
        "content_sha256": campaign._canonical_fields_sha256(
            digest_fields
        ),
    }
    pair: dict[str, object] = {
        "descriptor_id": descriptor_id,
        "kind": "I3",
        "event_ordinal": 17,
        "horizon": "H_system",
        "protected_full_1x_shape": True,
        "action_changed": True,
        "pair_complete": True,
        "formal_hard_gate_pass": True,
        "h_system_cohort_mapping_sha256": mapping_sha,
        "raw_bag_mapping_sha256": raw_mapping_sha,
        "raw_bag_original_entry_mapping_sha256": (
            original_entry_mapping_sha
        ),
        "baseline": {
            "terminal_state_sha256": _sha("baseline-terminal"),
            "cohort_outcome_sha256": _sha("baseline-cohort"),
            "cohort_metrics": {"completion_mean_seconds": 11.0},
            "raw_bag_cohort_metrics": {
                "original_entry_mean_minutes": 1.0
            },
            "raw_bag_sufficient_statistics_sidecar": baseline_raw,
        },
        "treatment": {
            "terminal_state_sha256": _sha("treatment-terminal"),
            "cohort_outcome_sha256": _sha("treatment-cohort"),
            "cohort_metrics": {"completion_mean_seconds": 11.5},
            "raw_bag_cohort_metrics": {
                "original_entry_mean_minutes": 1.1
            },
            "raw_bag_sufficient_statistics_sidecar": treatment_raw,
        },
        "realized_outcome_deltas": realized_rows,
        "realized_outcome_deltas_sha256": _sha(
            "realized-outcome-sidecar"
        ),
        "cohort_difference_sidecar": cohort_sidecar,
    }
    target = {"target_key": f"{descriptor_id}:H_system"}
    plan = {
        "self_sha256": _sha("compact-plan"),
        "source_bundle_sha256": _sha("compact-source"),
        "protected_inputs": {
            "task": {
                "input_runtime_cohort_sha256": _sha(
                    "compact-input-cohort"
                )
            }
        },
    }
    compact, reference = campaign._compact_pair_for_publication(
        pair,
        target,
        None,
        plan=plan,
        binary_sha256=_sha("compact-binary"),
    )
    assert reference is not None
    return pair, compact, reference


def _reseal(value: dict[str, object]) -> None:
    value.pop("self_sha256", None)
    value["self_sha256"] = campaign._canonical_sha256(value)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def _orchestrator_profile_set_fixture(
    tmp_path: Path,
    *,
    subsets: list[list[int]] | None = None,
    external_binary: bool = False,
) -> tuple[
    Path,
    dict[str, object],
    dict[str, object],
    list[Path],
    dict[str, object],
]:
    subsets = subsets or [[0], [1]]
    shard_count = max(index for subset in subsets for index in subset) + 1
    root = tmp_path / "profile_repo"
    root.mkdir()
    worker = root / validator.GENERATOR_PATH
    worker.parent.mkdir(parents=True)
    worker.write_text("# publication worker\n", encoding="utf-8")
    orchestrator_script = root / validator.ORCHESTRATOR_PATH
    orchestrator_script.parent.mkdir(parents=True, exist_ok=True)
    orchestrator_script.write_text(
        "# publication orchestrator\n", encoding="utf-8"
    )
    binary = (
        tmp_path / "external/fake_binary.pyd"
        if external_binary
        else root / "build/fake_binary.pyd"
    )
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"exact binary")
    build_manifest_path = root / "outputs/manifests/build.json"
    build_manifest = {
        "binary": {
            "path": (
                str(binary.resolve())
                if external_binary
                else binary.relative_to(root).as_posix()
            ),
            "sha256": validator.file_sha256(binary),
            "byte_count": binary.stat().st_size,
        }
    }
    _write_json(build_manifest_path, build_manifest)
    build_binding: dict[str, object] = {
        "path": build_manifest_path.relative_to(root).as_posix(),
        "file_sha256": validator.file_sha256(build_manifest_path),
        "self_sha256": _sha("build-self"),
        "binary_sha256": validator.file_sha256(binary),
        "binary_path": (
            None
            if external_binary
            else binary.relative_to(root).as_posix()
        ),
        "binary_path_scope": (
            "CONTENT_HASH_ONLY_EXTERNAL_GENERATION_ARTIFACT"
            if external_binary
            else "REPOSITORY_RELATIVE_GENERATION_ARTIFACT"
        ),
    }
    shards: list[dict[str, object]] = []
    for index in range(shard_count):
        shard: dict[str, object] = {
            "shard_index": index,
            "targets": [],
            "target_keys": [],
        }
        shard["shard_sha256"] = validator.canonical_sha256(shard)
        shards.append(shard)
    plan: dict[str, object] = {
        "campaign": "pilot",
        "pilot_round": 1,
        "shards": shards,
    }
    _reseal(plan)
    plan_path = root / validator.PILOT_PLAN_PATH
    _write_json(plan_path, plan)
    declared_inputs = (
        {
            "binary": {
                "path": str(binary.resolve()),
                "file_sha256": validator.file_sha256(binary),
                "byte_count": binary.stat().st_size,
            }
        }
        if external_binary
        else None
    )
    inputs = validator.expected_orchestrator_input_bindings(
        root,
        plan_path=plan_path,
        build_binding=build_binding,
        declared_inputs=declared_inputs,
    )
    inventory = [
        {
            "shard_index": index,
            "shard_sha256": shard["shard_sha256"],
        }
        for index, shard in enumerate(shards)
    ]
    plan_binding = {
        **inputs["plan"],
        "self_sha256": plan["self_sha256"],
        "shard_count": shard_count,
        "available_shard_indices": list(range(shard_count)),
        "shard_inventory": inventory,
        "shard_inventory_sha256": validator.canonical_sha256(
            inventory
        ),
    }
    profile_paths: list[Path] = []
    for profile_index, requested in enumerate(subsets):
        profile_path = (
            root
            / validator.ORCHESTRATOR_PROFILE_ROOT
            / f"profile_{profile_index}.json"
        )
        heartbeat_path = profile_path.with_name(
            f"{profile_path.name}.heartbeat.json"
        )
        timestamps = [
            f"2026-01-01T00:00:00.{offset:06d}Z"
            for offset in (profile_index, 20_000 + profile_index, 40_000 + profile_index)
        ]
        cap_bytes = 64 * 1024 * 1024
        group_peak = 1_000 * min(2, len(requested))
        heartbeat: dict[str, object] = {
            "schema": validator.ORCHESTRATOR_HEARTBEAT_SCHEMA,
            "status": "COMPLETE",
            "formal_pass_claimed": False,
            "campaign": "pilot",
            "pilot_round": 1,
            "input_artifact_bindings": inputs,
            "ending_input_artifact_bindings": inputs,
            "input_artifact_drift": [],
            "available_shard_indices": list(range(shard_count)),
            "execution_mode": "PRODUCTION_NATIVE_PROCESS_TREE_RSS",
            "started_utc": timestamps[0],
            "heartbeat_utc": timestamps[-1],
            "heartbeat_sequence": 3,
            "requested_shard_indices": requested,
            "scheduled_shard_indices": requested,
            "pending_shard_indices": [],
            "active_shard_indices": [],
            "completed_shard_indices": requested,
            "failure_observed": False,
            "max_process_rss_bytes": cap_bytes,
            "rss_sampling_interval_seconds": 0.005,
            "heartbeat_interval_seconds": 0.02,
            "termination_grace_seconds": 5.0,
            "kill_reap_timeout_seconds": 5.0,
            "rss_cap_exceeded_shard_indices": [],
            "rss_cap_unattestable_shard_indices": [],
            "process_group_peak_resident_bytes": group_peak,
            "active_memory_samples": [],
        }
        _reseal(heartbeat)
        _write_json(heartbeat_path, heartbeat)
        python_executable = root / "python.exe"
        rows: list[dict[str, object]] = []
        for index in requested:
            argv = orchestrator._worker_argv(
                python_executable=python_executable,
                worker_script=worker,
                root=root,
                campaign="pilot",
                pilot_round=1,
                shard_index=index,
                binary=binary,
                build_manifest=build_manifest_path,
            )
            assert len(argv) == 15
            rows.append(
                {
                    "shard_index": index,
                    "argv": argv,
                    "pid": 1000 + index,
                    "started_utc": timestamps[0],
                    "finished_utc": timestamps[-1],
                    "elapsed_wall_seconds": 0.05,
                    "return_code": 0,
                    "launch_error": None,
                    "orchestration_failure_reason": None,
                    "stdout": {
                        "sha256": _sha(f"stdout-{index}"),
                        "byte_count": 10,
                    },
                    "stderr": {
                        "sha256": _sha(f"stderr-{index}"),
                        "byte_count": 0,
                    },
                    "peak_resident_bytes": 1_000,
                    "rss_sample_method": (
                        "WINDOWS_TOOLHELP32_PROCESS_TREE_"
                        "GETPROCESSMEMORYINFO"
                    ),
                    "rss_sample_count": 5,
                    "rss_successful_sample_count": 5,
                    "memory_sampling_supported": True,
                    "termination_requested": False,
                    "forced_kill": False,
                }
            )
        profile: dict[str, object] = {
            "schema": validator.ORCHESTRATOR_PROFILE_SCHEMA,
            "status": "COMPLETE",
            "formal_pass_claimed": False,
            "campaign": "pilot",
            "pilot_round": 1,
            "execution_mode": "PRODUCTION_NATIVE_PROCESS_TREE_RSS",
            "resume_policy": (
                "DELEGATED_TO_IDEMPOTENT_RUN_SHARD_VALIDATION"
            ),
            "worker_process_policy": (
                "ONE_FRESH_SUBPROCESS_PER_SHARD_SHELL_FALSE"
            ),
            "failure_policy": (
                "STOP_SCHEDULING_ON_FIRST_OBSERVED_FAILURE_THEN_REAP_ALL"
            ),
            "termination_policy": (
                "TERM_THEN_BOUNDED_GRACE_THEN_KILL_THEN_BOUNDED_REAP"
            ),
            "termination_grace_seconds": 5.0,
            "kill_reap_timeout_seconds": 5.0,
            "publication_execution_contract": {
                "max_allowed_process_rss_mib": 65_536.0,
                "max_allowed_heartbeat_interval_seconds": 60.0,
                "required_memory_scope": (
                    "PER_SHARD_WORKER_PROCESS_TREE_RESIDENT_BYTES"
                ),
                "production_rss_sample_methods": sorted(
                    validator.PRODUCTION_RSS_METHODS
                ),
            },
            "input_artifact_bindings": inputs,
            "ending_input_artifact_bindings": inputs,
            "input_artifact_drift": [],
            "plan": plan_binding,
            "binary_sha256": validator.file_sha256(binary),
            "build_manifest_sha256": validator.file_sha256(
                build_manifest_path
            ),
            "python_executable": str(python_executable),
            "worker_script": str(worker),
            "worker_count_requested": 2,
            "worker_count_effective": min(2, len(requested)),
            "requested_shard_indices": requested,
            "launch_attempted_shard_indices": requested,
            "scheduled_shard_indices": requested,
            "unscheduled_shard_indices": [],
            "completed_result_count": len(requested),
            "successful_shard_count": len(requested),
            "failed_shard_count": 0,
            "first_failure_shard_index": None,
            "launch_error": None,
            "started_utc": timestamps[0],
            "finished_utc": timestamps[-1],
            "elapsed_wall_seconds": 0.05,
            "throughput": {
                "completed_shards_per_wall_second": (
                    len(requested) / 0.05
                ),
                "successful_shards_per_wall_second": (
                    len(requested) / 0.05
                ),
            },
            "process_group_peak_resident_bytes": group_peak,
            "process_group_rss_scope": (
                "SUM_OF_CONCURRENT_SHARD_WORKER_PROCESS_TREE_RSS_SAMPLES"
            ),
            "rss_sampling_interval_seconds": 0.005,
            "memory_sampling": {
                "execution_mode": (
                    "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
                ),
                "production_native_sampler": True,
                "injected_sampler": False,
                "required_complete_profile_methods": sorted(
                    validator.PRODUCTION_RSS_METHODS
                ),
                "fail_closed_on_unavailable_process_or_child": True,
            },
            "process_rss_cap": {
                "configured": True,
                "required_for_publication_execution": True,
                "max_process_rss_mib": 64.0,
                "max_process_rss_bytes": cap_bytes,
                "policy": (
                    "FAIL_CLOSED_STOP_SCHEDULING_TERMINATE_ONLY_"
                    "OFFENDING_WORKER;UNAVAILABLE_SAMPLE_IS_FAILURE"
                ),
                "cap_scope": (
                    "PER_SHARD_WORKER_PROCESS_TREE_RESIDENT_BYTES"
                ),
                "exceeded_shard_indices": [],
                "unattestable_shard_indices": [],
            },
            "liveness": {
                "heartbeat_path": heartbeat_path.relative_to(
                    root
                ).as_posix(),
                "heartbeat_file_sha256": validator.file_sha256(
                    heartbeat_path
                ),
                "heartbeat_self_sha256": heartbeat["self_sha256"],
                "heartbeat_interval_seconds": 0.02,
                "poll_interval_seconds": 0.005,
                "rss_sampling_interval_seconds": 0.005,
                "heartbeat_count": 3,
                "heartbeat_timestamps_utc": timestamps,
                "final_heartbeat_status": "COMPLETE",
                "final_heartbeat_sequence": 3,
            },
            "publication_execution_attestation": {
                "profile_status_complete": True,
                "input_artifacts_stable": True,
                "rss_cap_configured": True,
                "production_native_memory_sampling": True,
                "all_successful_shards_have_peak_rss": True,
                "final_heartbeat_complete": True,
                "final_heartbeat_self_hash_bound": True,
            },
            "shards": rows,
        }
        _reseal(profile)
        _write_json(profile_path, profile)
        profile_paths.append(profile_path)
    profile_set = campaign._validate_orchestrator_profile_set(
        root=root,
        profile_paths=list(reversed(profile_paths)),
        campaign="pilot",
        pilot_round=1,
        plan=plan,
        plan_path=plan_path,
        binary=binary,
        build_manifest=build_manifest_path,
        build_binding=build_binding,
    )
    return root, plan, build_binding, profile_paths, profile_set


def _reseal_orchestrator_profile_chain(
    root: Path,
    profile_set: dict[str, object],
    *,
    mutate_profile: object | None = None,
    mutate_heartbeat: object | None = None,
) -> None:
    binding = profile_set["profiles"][0]
    assert isinstance(binding, dict)
    profile_path = root / str(binding["path"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    heartbeat_binding = binding["heartbeat"]
    assert isinstance(heartbeat_binding, dict)
    heartbeat_path = root / str(heartbeat_binding["path"])
    heartbeat = json.loads(
        heartbeat_path.read_text(encoding="utf-8")
    )
    if callable(mutate_heartbeat):
        mutate_heartbeat(heartbeat)
        _reseal(heartbeat)
        _write_json(heartbeat_path, heartbeat)
        profile["liveness"]["heartbeat_file_sha256"] = (
            validator.file_sha256(heartbeat_path)
        )
        profile["liveness"]["heartbeat_self_sha256"] = heartbeat[
            "self_sha256"
        ]
    if callable(mutate_profile):
        mutate_profile(profile)
    _reseal(profile)
    _write_json(profile_path, profile)
    binding["sha256"] = validator.file_sha256(profile_path)
    binding["byte_count"] = profile_path.stat().st_size
    binding["self_sha256"] = profile["self_sha256"]
    binding["heartbeat"] = {
        "path": heartbeat_path.relative_to(root).as_posix(),
        "sha256": validator.file_sha256(heartbeat_path),
        "byte_count": heartbeat_path.stat().st_size,
        "self_sha256": heartbeat["self_sha256"],
    }
    _reseal(profile_set)


def _compact_target() -> dict[str, object]:
    descriptor_id = _sha("compact-target")
    return {
        "target_key": f"{descriptor_id}:H_system",
        "descriptor_id": descriptor_id,
        "kind": "I3",
        "event_ordinal": 17,
        "horizon": "H_system",
    }


def test_profile_set_uses_real_orchestrator_argv_and_validates_portably(
    tmp_path: Path,
) -> None:
    root, plan, build_binding, profile_paths, profile_set = (
        _orchestrator_profile_set_fixture(tmp_path)
    )
    assert [
        row["requested_shard_indices"]
        for row in profile_set["profiles"]
    ] == [[0], [1]]
    first_profile = json.loads(
        profile_paths[0].read_text(encoding="utf-8")
    )
    assert first_profile["shards"][0]["argv"] == (
        orchestrator._worker_argv(
            python_executable=root / "python.exe",
            worker_script=root / validator.GENERATOR_PATH,
            root=root,
            campaign="pilot",
            pilot_round=1,
            shard_index=0,
            binary=root / "build/fake_binary.pyd",
            build_manifest=root / "outputs/manifests/build.json",
        )
    )
    validated = validator.validate_orchestrator_profile_set(
        root,
        binding=profile_set,
        campaign="pilot",
        pilot_round=1,
        plan=plan,
        plan_path=root / validator.PILOT_PLAN_PATH,
        build_binding=build_binding,
    )
    assert validated == profile_set


def test_real_orchestrator_profile_flows_through_finalize_and_portable_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "real_profile_repo"
    root.mkdir()
    copied_orchestrator = root / validator.ORCHESTRATOR_PATH
    copied_orchestrator.parent.mkdir(parents=True)
    copied_orchestrator.write_text(
        Path(orchestrator.__file__).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    worker = root / validator.GENERATOR_PATH
    worker.parent.mkdir(parents=True)
    worker.write_text(
        """
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
commands = parser.add_subparsers(dest="command", required=True)
run = commands.add_parser("run-shard")
run.add_argument("--campaign", required=True)
run.add_argument("--shard-index", required=True)
run.add_argument("--binary", required=True)
run.add_argument("--build-manifest", required=True)
run.add_argument("--round", required=True)
parser.parse_args()
time.sleep(0.25)
""".lstrip(),
        encoding="utf-8",
    )
    binary = root / "build/fake_binary.pyd"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"real-profile-binary")
    build_manifest_path = root / "outputs/manifests/build.json"
    build_manifest = {
        "binary": {
            "path": binary.relative_to(root).as_posix(),
            "sha256": validator.file_sha256(binary),
            "byte_count": binary.stat().st_size,
        }
    }
    _write_json(build_manifest_path, build_manifest)
    build_binding = {
        "path": build_manifest_path.relative_to(root).as_posix(),
        "file_sha256": validator.file_sha256(build_manifest_path),
        "self_sha256": _sha("real-build-self"),
        "binary_sha256": validator.file_sha256(binary),
        "binary_path": binary.relative_to(root).as_posix(),
        "binary_path_scope": (
            "REPOSITORY_RELATIVE_GENERATION_ARTIFACT"
        ),
    }
    shard: dict[str, object] = {
        "shard_index": 0,
        "event_ordinal_start": 0,
        "event_ordinal_end": 0,
        "target_count": 0,
        "h_system_target_count": 0,
        "targets": [],
        "target_keys": [],
    }
    shard["shard_sha256"] = validator.canonical_sha256(shard)
    plan: dict[str, object] = {
        "schema": campaign.CAMPAIGN_PLAN_SCHEMA,
        "campaign": "pilot",
        "pilot_round": 1,
        "source_bundle_sha256": _sha("real-source"),
        "binary": {
            "sha256_before": validator.file_sha256(binary)
        },
        "exact_binary_build_manifest": build_binding,
        "attempt_budget": 0,
        "shards": [shard],
    }
    _reseal(plan)
    plan_path = root / validator.PILOT_PLAN_PATH
    _write_json(plan_path, plan)
    profile_path = (
        root / validator.ORCHESTRATOR_PROFILE_ROOT / "real.json"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(copied_orchestrator),
            "--root",
            str(root),
            "--campaign",
            "pilot",
            "--binary",
            str(binary),
            "--build-manifest",
            str(build_manifest_path),
            "--workers",
            "1",
            "--shards",
            "all",
            "--profile-output",
            str(profile_path),
            "--max-process-rss-mib",
            "512",
            "--heartbeat-interval-seconds",
            "0.02",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    real_profile = json.loads(
        profile_path.read_text(encoding="utf-8")
    )
    assert real_profile["execution_mode"] == (
        "PRODUCTION_NATIVE_PROCESS_TREE_RSS"
    )
    monkeypatch.setattr(
        campaign, "_assert_repository_safety", lambda _root: {}
    )
    monkeypatch.setattr(
        campaign, "_protected_inputs", lambda _root: {}
    )
    monkeypatch.setattr(
        campaign,
        "_source_identity",
        lambda _root: {
            "source_bundle_sha256": plan["source_bundle_sha256"]
        },
    )
    monkeypatch.setattr(
        campaign,
        "_validate_build_manifest",
        lambda **_kwargs: build_binding,
    )
    monkeypatch.setattr(
        campaign,
        "_collect_shards",
        lambda *_args, **_kwargs: (
            [],
            [],
            [{"shard_index": 0}],
            None,
        ),
    )
    result = campaign.finalize_campaign(
        root=root,
        campaign="pilot",
        binary=binary,
        build_manifest=build_manifest_path,
        orchestrator_profiles=[profile_path],
        pilot_round=1,
    )
    assert result["campaign_shard_execution"]["profile_count"] == 1
    assert validator.validate_orchestrator_profile_set(
        root,
        binding=result["campaign_shard_execution"],
        campaign="pilot",
        pilot_round=1,
        plan=plan,
        plan_path=plan_path,
        build_binding=build_binding,
    ) == result["campaign_shard_execution"]


def test_portable_profile_validation_needs_no_external_host_binary(
    tmp_path: Path,
) -> None:
    root, plan, build_binding, _, profile_set = (
        _orchestrator_profile_set_fixture(
            tmp_path, external_binary=True
        )
    )
    first_binding = profile_set["profiles"][0]
    first_profile = json.loads(
        (root / str(first_binding["path"])).read_text(
            encoding="utf-8"
        )
    )
    external_path = Path(
        first_profile["input_artifact_bindings"]["binary"]["path"]
    )
    exact_manifest = json.loads(
        (
            root / str(build_binding["path"])
        ).read_text(encoding="utf-8")
    )
    assert Path(exact_manifest["binary"]["path"]).is_absolute()
    clone = tmp_path / "portable_clone"
    shutil.copytree(root, clone)
    external_path.unlink()
    assert not external_path.exists()
    assert validator.validate_orchestrator_profile_set(
        clone,
        binding=profile_set,
        campaign="pilot",
        pilot_round=1,
        plan=plan,
        plan_path=clone / validator.PILOT_PLAN_PATH,
        build_binding=build_binding,
    ) == profile_set


def test_windows_producer_paths_are_classified_without_host_pathlib(
    tmp_path: Path,
) -> None:
    producer_root = r"C:\work\czr005"
    external_binary = r"C:\tmp\exact\czr005_cpp.pyd"
    cmake = r"C:\Program Files\CMake\bin\cmake.exe"
    assert validator.producer_path_is_absolute(external_binary)
    assert validator.producer_path_basename(cmake) == "cmake.exe"
    _host_path, publication_path = validator.portable_binary_location(
        tmp_path, external_binary
    )
    assert publication_path is None
    assert validator.producer_binary_argv_path(
        producer_root,
        external_binary,
        repository_relative=False,
    ) == external_binary
    assert validator.producer_binary_argv_path(
        producer_root,
        "build/czr005_cpp.pyd",
        repository_relative=True,
    ) == r"C:\work\czr005\build\czr005_cpp.pyd"
    assert validator.producer_resolve_path(
        producer_root, external_binary
    ) == external_binary


@pytest.mark.parametrize(
    ("subsets", "message"),
    [
        ([[0, 1], [1, 2]], "ORCHESTRATOR_PROFILE_SHARD_OVERLAP"),
        ([[0], [2]], "DOES_NOT_EXACTLY_COVER_PLAN"),
    ],
)
def test_producer_rejects_overlapping_or_incomplete_profile_coverage(
    tmp_path: Path,
    subsets: list[list[int]],
    message: str,
) -> None:
    with pytest.raises(campaign.CampaignError, match=message):
        _orchestrator_profile_set_fixture(
            tmp_path, subsets=subsets
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("cap", "ORCHESTRATOR_RSS_CAP_CONTRACT_DRIFT"),
        ("sampler", "ORCHESTRATOR_SHARD_RESULT_FAILURE"),
        ("argv", "ORCHESTRATOR_SHARD_ARGV"),
        ("inventory", "ORCHESTRATOR_PROFILE_INPUT_BINDING_DRIFT"),
        ("time", "ORCHESTRATOR_SHARD_TIME_WINDOW_DRIFT"),
    ],
)
def test_portable_profile_validator_rejects_resealed_tamper(
    tmp_path: Path,
    field: str,
    message: str,
) -> None:
    root, plan, build_binding, _, profile_set = (
        _orchestrator_profile_set_fixture(tmp_path)
    )

    def mutate(profile: dict[str, object]) -> None:
        if field == "cap":
            profile["process_rss_cap"]["configured"] = False
        elif field == "sampler":
            profile["shards"][0]["rss_sample_method"] = "FAKE_RSS"
        elif field == "argv":
            profile["shards"][0]["argv"].append("--forged")
        elif field == "inventory":
            profile["plan"]["shard_inventory"][0][
                "shard_sha256"
            ] = _sha("forged-shard")
        elif field == "time":
            profile["shards"][0][
                "finished_utc"
            ] = "2025-12-31T23:59:59Z"
        else:  # pragma: no cover
            raise AssertionError(field)

    _reseal_orchestrator_profile_chain(
        root, profile_set, mutate_profile=mutate
    )
    with pytest.raises(validator.ValidationError, match=message):
        validator.validate_orchestrator_profile_set(
            root,
            binding=profile_set,
            campaign="pilot",
            pilot_round=1,
            plan=plan,
            plan_path=root / validator.PILOT_PLAN_PATH,
            build_binding=build_binding,
        )


def test_portable_profile_validator_rejects_resealed_terminal_heartbeat(
    tmp_path: Path,
) -> None:
    root, plan, build_binding, _, profile_set = (
        _orchestrator_profile_set_fixture(tmp_path)
    )

    def mutate(heartbeat: dict[str, object]) -> None:
        heartbeat["status"] = "RUNNING"
        heartbeat["active_shard_indices"] = [0]

    _reseal_orchestrator_profile_chain(
        root, profile_set, mutate_heartbeat=mutate
    )
    with pytest.raises(
        validator.ValidationError,
        match="ORCHESTRATOR_FINAL_HEARTBEAT_CONTENT_DRIFT",
    ):
        validator.validate_orchestrator_profile_set(
            root,
            binding=profile_set,
            campaign="pilot",
            pilot_round=1,
            plan=plan,
            plan_path=root / validator.PILOT_PLAN_PATH,
            build_binding=build_binding,
        )


def test_portable_profile_validator_rejects_orchestrator_source_drift(
    tmp_path: Path,
) -> None:
    root, plan, build_binding, _, profile_set = (
        _orchestrator_profile_set_fixture(tmp_path)
    )
    (root / validator.ORCHESTRATOR_PATH).write_text(
        "# tampered orchestrator\n", encoding="utf-8"
    )
    with pytest.raises(
        validator.ValidationError,
        match="ORCHESTRATOR_PROFILE_INPUT_BINDING_DRIFT",
    ):
        validator.validate_orchestrator_profile_set(
            root,
            binding=profile_set,
            campaign="pilot",
            pilot_round=1,
            plan=plan,
            plan_path=root / validator.PILOT_PLAN_PATH,
            build_binding=build_binding,
        )


def test_portable_profile_validator_rejects_noncanonical_profile_order(
    tmp_path: Path,
) -> None:
    root, plan, build_binding, _, profile_set = (
        _orchestrator_profile_set_fixture(tmp_path)
    )
    profile_set["profiles"].reverse()
    _reseal(profile_set)
    with pytest.raises(
        validator.ValidationError,
        match="ORCHESTRATOR_PROFILE_SET_COVERAGE_OR_ORDER_DRIFT",
    ):
        validator.validate_orchestrator_profile_set(
            root,
            binding=profile_set,
            campaign="pilot",
            pilot_round=1,
            plan=plan,
            plan_path=root / validator.PILOT_PLAN_PATH,
            build_binding=build_binding,
        )


def test_portable_profile_validator_rejects_profile_path_escape(
    tmp_path: Path,
) -> None:
    root, plan, build_binding, _, profile_set = (
        _orchestrator_profile_set_fixture(tmp_path)
    )
    profile_set["profiles"][0]["path"] = "../escaped.json"
    _reseal(profile_set)
    with pytest.raises(
        validator.ValidationError,
        match="ORCHESTRATOR_PROFILE_PATH",
    ):
        validator.validate_orchestrator_profile_set(
            root,
            binding=profile_set,
            campaign="pilot",
            pilot_round=1,
            plan=plan,
            plan_path=root / validator.PILOT_PLAN_PATH,
            build_binding=build_binding,
        )


@pytest.mark.parametrize(
    "relative",
    [
        "outputs/runstate/ignored_profile.json",
        ".git/forged_profile.json",
    ],
)
def test_profile_publication_path_rejects_ignored_or_internal_roots(
    tmp_path: Path,
    relative: str,
) -> None:
    root = tmp_path / "path_repo"
    root.mkdir()
    path = root / relative
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        campaign.CampaignError,
        match="OUTSIDE_PUBLICATION_PROFILE_ROOT",
    ):
        campaign._repository_publication_file(
            root, path, "ORCHESTRATOR_PROFILE"
        )
    with pytest.raises(
        validator.ValidationError,
        match="OUTSIDE_PUBLICATION_PROFILE_ROOT",
    ):
        validator.repository_publication_file(
            root, relative, "ORCHESTRATOR_PROFILE"
        )


def _compact_native_attestation_fixture(
    pair: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    native = {
        "schema": campaign.PAIR_RUN_SCHEMA,
        "evidence_scope": (
            "EXACT_NATIVE_SAME_STATE_ONE_SHOT_MATCHED_PAIRS"
        ),
        "formal_pass_claimed": False,
        "protected_full_1x_shape": True,
        "h_system_cohort_policy": (
            "ALL_INPUT_RUNTIME_IDS_IN_INPUT_ORDER"
        ),
        "input_request_count": campaign.FULL_SEGMENT_COUNT,
        "raw_bag_count": campaign.FULL_RAW_BAG_COUNT,
        "input_runtime_cohort_sha256": _sha(
            "compact-input-cohort"
        ),
        "h_system_cohort_mapping_sha256": pair[
            "h_system_cohort_mapping_sha256"
        ],
        "raw_bag_mapping_sha256": pair["raw_bag_mapping_sha256"],
        "raw_bag_original_entry_mapping_sha256": pair[
            "raw_bag_original_entry_mapping_sha256"
        ],
        "frozen_controls": dict(campaign.FROZEN_CONTROLS),
        "target_count": 1,
        "action_changing_pair_count": 1,
        "applied_action_changing_pair_count": 1,
        "false_positive_pair_count": 0,
        "complete_action_changing_h_bag_count": 0,
        "applied_action_changing_h_system_count": 1,
        "complete_h_system_hard_gate_pass_count": 1,
        "h_system_pair_count": 1,
    }
    attestation = campaign._compact_native_payload_attestation(
        native
    )
    plan = {
        "protected_inputs": {
            "task": {
                "input_runtime_cohort_sha256": native[
                    "input_runtime_cohort_sha256"
                ],
                "runtime_segment_mapping_sha256": native[
                    "h_system_cohort_mapping_sha256"
                ],
                "raw_bag_mapping_sha256": native[
                    "raw_bag_mapping_sha256"
                ],
                "raw_bag_original_entry_mapping_sha256": native[
                    "raw_bag_original_entry_mapping_sha256"
                ],
            }
        }
    }
    shard = {"target_count": 1}
    return attestation, plan, shard


def test_validator_accepts_signed_h_system_and_checks_externality() -> None:
    row = _eligible_label()
    validator.validate_label(row)

    row["externality_runtime_bag_ids"] = []
    row.pop("label_sha256")
    with pytest.raises(validator.ValidationError, match="EXTERNALITY"):
        validator.validate_label(row)


def test_validator_rejects_sampling_probability_tamper() -> None:
    row = _eligible_label()
    row.pop("label_sha256")
    row["sampling"]["pi_h"] = 0.3
    with pytest.raises(validator.ValidationError, match="PI_H"):
        validator.validate_label(row)


def test_self_hash_tamper_fails_closed() -> None:
    value = {"schema": "test", "count": 1}
    value["self_sha256"] = validator.canonical_sha256(value)
    validator.validate_self_hash(value, "fixture")
    value["count"] = 2
    with pytest.raises(validator.ValidationError, match="SELF_SHA256_DRIFT"):
        validator.validate_self_hash(value, "fixture")


def test_dense_pair_compacts_and_independently_hydrates_losslessly() -> None:
    pair, compact, reference = _compact_fixture()
    target_key = str(compact["target_key"])

    assert campaign._hydrate_compact_pair(
        compact,
        reference,
        expected_target_key=target_key,
    ) == pair
    assert validator.hydrate_compact_pair(
        compact,
        reference,
        expected_target_key=target_key,
    ) == pair
    validator.validate_compact_storage_semantics(compact, pair)


def test_compact_target_key_and_preregistered_identity_are_bound() -> None:
    pair, compact, reference = _compact_fixture()
    target = _compact_target()
    validator.validate_compact_pair_target_identity(pair, target)

    wrong_key = copy.deepcopy(compact)
    wrong_key["target_key"] = _sha("wrong-target-key")
    with pytest.raises(
        campaign.CampaignError,
        match="COMPACT_PAIR_TARGET_KEY_DRIFT",
    ):
        campaign._hydrate_compact_pair(
            wrong_key,
            reference,
            expected_target_key=str(target["target_key"]),
        )
    with pytest.raises(
        validator.ValidationError,
        match="COMPACT_PAIR_TARGET_KEY_DRIFT",
    ):
        validator.hydrate_compact_pair(
            wrong_key,
            reference,
            expected_target_key=str(target["target_key"]),
        )

    wrong_identity = copy.deepcopy(pair)
    wrong_identity["descriptor_id"] = _sha("wrong-descriptor")
    with pytest.raises(
        validator.ValidationError,
        match="PREREGISTERED_TARGET_IDENTITY",
    ):
        validator.validate_compact_pair_target_identity(
            wrong_identity,
            target,
        )
    wrong_horizon = dict(target)
    wrong_horizon["horizon"] = "H_bag"
    with pytest.raises(
        validator.ValidationError,
        match="PREREGISTERED_TARGET_IDENTITY",
    ):
        validator.validate_compact_pair_target_identity(
            pair,
            wrong_horizon,
        )


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("terminal_state_sha256", _sha("tampered-terminal")),
        ("cohort_outcome_sha256", _sha("tampered-cohort-root")),
        (
            "cohort_metrics",
            {"completion_mean_seconds": 999.0},
        ),
        (
            "raw_bag_cohort_metrics",
            {"original_entry_mean_minutes": 999.0},
        ),
    ],
)
def test_inline_baseline_drift_is_rejected_against_global_reference(
    field: str,
    tampered_value: object,
) -> None:
    _, compact, reference = _compact_fixture()
    compact["baseline"][field] = tampered_value
    key = str(compact["target_key"])
    with pytest.raises(
        campaign.CampaignError,
        match="INLINE_BASELINE_REFERENCE_DRIFT",
    ):
        campaign._hydrate_compact_pair(
            compact,
            reference,
            expected_target_key=key,
        )
    with pytest.raises(
        validator.ValidationError,
        match="INLINE_BASELINE_REFERENCE_DRIFT",
    ):
        validator.hydrate_compact_pair(
            compact,
            reference,
            expected_target_key=key,
        )


def test_omitted_changed_segment_is_rejected() -> None:
    _, compact, reference = _compact_fixture()
    tampered = copy.deepcopy(compact)
    tampered["realized_outcome_deltas"] = []
    overlay = tampered["cohort_difference_sidecar"]
    overlay["changed_runtime_bag_ids"] = []
    overlay["changed_count"] = 0
    _reseal(overlay)
    key = str(tampered["target_key"])

    with pytest.raises(
        campaign.CampaignError,
        match="COMPACT_COHORT_LOGICAL_CONTENT_DRIFT",
    ):
        campaign._hydrate_compact_pair(
            tampered,
            reference,
            expected_target_key=key,
        )
    with pytest.raises(
        validator.ValidationError,
        match="COMPACT_COHORT_LOGICAL_CONTENT_DRIFT",
    ):
        validator.hydrate_compact_pair(
            tampered,
            reference,
            expected_target_key=key,
        )


def test_omitted_changed_raw_row_is_rejected() -> None:
    _, compact, reference = _compact_fixture()
    tampered = copy.deepcopy(compact)
    overlay = tampered["treatment"][
        "raw_bag_sufficient_statistics_sidecar"
    ]
    overlay["rows"] = []
    overlay["changed_task_ids"] = []
    overlay["changed_row_count"] = 0
    _reseal(overlay)
    key = str(tampered["target_key"])

    with pytest.raises(
        campaign.CampaignError,
        match="RAW_OVERLAY_LOGICAL_CONTENT_DRIFT",
    ):
        campaign._hydrate_compact_pair(
            tampered,
            reference,
            expected_target_key=key,
        )
    with pytest.raises(
        validator.ValidationError,
        match="RAW_OVERLAY_LOGICAL_CONTENT_DRIFT",
    ):
        validator.hydrate_compact_pair(
            tampered,
            reference,
            expected_target_key=key,
        )


def test_forged_cohort_content_root_is_rejected() -> None:
    _, compact, reference = _compact_fixture()
    tampered = copy.deepcopy(compact)
    overlay = tampered["cohort_difference_sidecar"]
    overlay["logical_content_sha256"] = _sha(
        "forged-cohort-content-root"
    )
    _reseal(overlay)
    key = str(tampered["target_key"])

    with pytest.raises(
        campaign.CampaignError,
        match="COMPACT_COHORT_LOGICAL_CONTENT_DRIFT",
    ):
        campaign._hydrate_compact_pair(
            tampered,
            reference,
            expected_target_key=key,
        )
    with pytest.raises(
        validator.ValidationError,
        match="COMPACT_COHORT_LOGICAL_CONTENT_DRIFT",
    ):
        validator.hydrate_compact_pair(
            tampered,
            reference,
            expected_target_key=key,
        )


def test_dense_storage_mode_cannot_be_downgraded_to_inline() -> None:
    pair, compact, _ = _compact_fixture()
    inline = copy.deepcopy(pair)
    inline["target_key"] = compact["target_key"]
    inline["compact_storage"] = "INLINE_NATIVE_SMALL_EVIDENCE"
    with pytest.raises(
        validator.ValidationError,
        match="COMPACT_STORAGE_MODE_SEMANTIC_DRIFT",
    ):
        validator.validate_compact_storage_semantics(inline, pair)


def test_dense_chunks_have_one_h_system_pair_and_reference_is_optional() -> None:
    _, dense, reference = _compact_fixture()
    assert reference is not None
    small_plan = {
        "self_sha256": _sha("small-plan"),
        "source_bundle_sha256": _sha("small-source"),
        "protected_inputs": {
            "task": {
                "input_runtime_cohort_sha256": _sha("small-input")
            }
        },
    }
    current_reference = None
    small_rows = []
    for index in range(2):
        small, current_reference = (
            campaign._compact_pair_for_publication(
                {"horizon": "H_bag", "ordinal": index},
                {"target_key": f"small:{index}"},
                current_reference,
                plan=small_plan,
                binary_sha256=_sha("small-binary"),
            )
        )
        small_rows.append(
            {"target_key": f"small:{index}", "pair": small}
        )
    assert current_reference is None

    chunks = campaign._partition_compact_evidence_rows(
        [
            small_rows[0],
            {"target_key": "dense:0", "pair": dense},
            {
                "target_key": "dense:1",
                "pair": copy.deepcopy(dense),
            },
            small_rows[1],
        ]
    )
    assert all(
        sum(
            row["pair"]["compact_storage"]
            == "GLOBAL_BASELINE_PLUS_SPARSE_TREATMENT_OVERLAYS"
            for row in chunk
        )
        <= 1
        for chunk in chunks
    )
    validator.validate_compact_baseline_reference_order(
        reference,
        [str(dense["target_key"])],
    )
    with pytest.raises(
        validator.ValidationError,
        match="REFERENCE_NOT_FIRST_DENSE_PAIR",
    ):
        validator.validate_compact_baseline_reference_order(
            reference,
            ["different:dense"],
        )
    order_plan = {
        "shards": [
            {"target_keys": ["small:0", str(dense["target_key"])]},
            {"target_keys": ["small:1"]},
        ]
    }
    validator.validate_compact_global_target_order(
        ["small:0", str(dense["target_key"]), "small:1"],
        order_plan,
    )
    with pytest.raises(
        validator.ValidationError,
        match="GLOBAL_TARGET_ORDER_DRIFT",
    ):
        validator.validate_compact_global_target_order(
            [str(dense["target_key"]), "small:0", "small:1"],
            order_plan,
        )


def test_native_attestation_controls_counts_and_run_state_are_bound() -> None:
    pair, _, _ = _compact_fixture()
    attestation, plan, shard = _compact_native_attestation_fixture(
        pair
    )
    normalized = (
        validator.validate_compact_native_payload_attestation(
            attestation,
            plan=plan,
            shard=shard,
        )
    )
    validator.validate_compact_native_summary_counts(
        normalized,
        [pair],
    )
    evidence = {
        "source_run_state_sha256": _sha("run-state-file"),
        "source_run_state_self_sha256": _sha("run-state-self"),
    }
    run_state = {
        "sha256": _sha("run-state-file"),
        "self_sha256": _sha("run-state-self"),
    }
    validator.validate_compact_source_run_state_binding(
        evidence,
        run_state,
    )

    bad_controls = copy.deepcopy(attestation)
    control_name = next(iter(validator.FROZEN_CONTROLS))
    bad_controls["frozen_controls"][control_name] = "tampered"
    _reseal(bad_controls)
    with pytest.raises(
        validator.ValidationError,
        match="ATTESTATION_CONTROL_DRIFT",
    ):
        validator.validate_compact_native_payload_attestation(
            bad_controls,
            plan=plan,
            shard=shard,
        )

    bad_counts = dict(normalized)
    bad_counts["action_changing_pair_count"] = 0
    with pytest.raises(
        validator.ValidationError,
        match="SUMMARY_COUNT_DRIFT",
    ):
        validator.validate_compact_native_summary_counts(
            bad_counts,
            [pair],
        )

    bad_run_state = dict(run_state)
    bad_run_state["sha256"] = _sha("other-run-state")
    with pytest.raises(
        validator.ValidationError,
        match="SOURCE_RUN_STATE_ATTESTATION_DRIFT",
    ):
        validator.validate_compact_source_run_state_binding(
            evidence,
            bad_run_state,
        )


def test_publishable_evidence_uses_strict_git_safety_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "compact-evidence.json.zst"
    artifact.write_bytes(b"xx")
    monkeypatch.setattr(
        campaign,
        "GITHUB_SAFE_ARTIFACT_MAX_BYTES",
        2,
    )
    monkeypatch.setattr(
        validator,
        "GITHUB_SAFE_ARTIFACT_MAX_BYTES",
        2,
    )
    with pytest.raises(
        campaign.CampaignError,
        match="GITHUB_100_MIB_LIMIT",
    ):
        campaign._publishable_byte_count(artifact, "compact")
    with pytest.raises(
        validator.ValidationError,
        match="GITHUB_100_MIB_LIMIT",
    ):
        validator.publishable_byte_count(artifact, "compact")


def test_independent_validator_does_not_import_generator() -> None:
    source = Path(validator.__file__).read_text(encoding="utf-8")
    assert "import g4irsf15_causal_campaign" not in source
    assert "from scripts.eval.g4irsf15_causal_campaign" not in source
    assert "import run_g4irsf15_campaign_shards" not in source
    assert "from scripts.run_g4irsf15_campaign_shards" not in source


def _analysis_label(index: int) -> dict[str, object]:
    sampling = _sampling()
    sampling["cluster_id"] = _sha(f"analysis-clone:{index}")
    row = {
        "target_key": _sha(f"analysis-target:{index}"),
        "descriptor_id": _sha(f"analysis-descriptor:{index}"),
        "kind": "I1",
        "clone_group_id": _sha(f"analysis-clone:{index}"),
        "horizon": "H_bag",
        "eligible_causal_label": True,
        "sampling": sampling,
        "delta_metrics": {
            metric: float(index + offset)
            for offset, metric in enumerate(
                validator.ANALYSIS_DELTA_METRICS
            )
        },
        "affected_bag_deltas": [
            {
                "runtime_bag_id": index,
                "delta_completion_seconds": float(index + 1),
            }
        ],
        "raw_bag_delta_metrics": None,
    }
    return row


def test_weighted_effect_analysis_matches_independent_recompute() -> None:
    labels = [_analysis_label(0), _analysis_label(1)]
    plan = {"self_sha256": _sha("plan"), "attempt_budget": 2}
    dataset = {
        "path": validator.LABEL_DATASET_PATH.as_posix(),
        "sha256": _sha("dataset"),
        "row_count": 2,
    }
    generated = campaign._weighted_effect_analysis(
        labels,
        plan=plan,
        label_dataset_binding=dataset,
        formal_gate_passed=True,
    )
    independently_recomputed = validator.expected_weighted_effect_analysis(
        labels,
        plan=plan,
        label_dataset_binding=dataset,
        formal_gate_passed=True,
    )
    assert generated == independently_recomputed
    mixed = [
        row
        for row in generated["estimates"]
        if row["group_type"] in {"overall", "kind"}
    ]
    assert mixed
    assert all(
        row["reference_design_hajek_mean"] is None for row in mixed
    )
    h_bag = [
        row
        for row in generated["estimates"]
        if row["group_type"] in {"horizon", "kind_horizon"}
    ]
    assert h_bag
    assert all(
        row["reference_design_hajek_mean"] is None
        for row in h_bag
    )
