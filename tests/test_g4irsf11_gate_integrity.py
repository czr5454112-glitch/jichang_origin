from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
import sys
import tempfile

import pytest

from scripts.eval import g4irsf11_gate_integrity as gate


SHA_A = "a" * 40
SHA_B = "b" * 40
HASH_A = "1" * 64


@pytest.fixture
def workspace_tmp() -> Iterator[Path]:
    root = Path(".pytest_cache") / "g4irsf11_gate_integrity_tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        yield Path(directory)


def _provenance_commands() -> tuple[gate.CommandRecord, ...]:
    argv = (
        ("git", "rev-parse", "HEAD"),
        ("git", "branch", "--show-current"),
        ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        ("git", "rev-parse", "@{u}"),
        ("git", "merge-base", "--is-ancestor", SHA_A, "HEAD"),
        ("git", "merge-base", "--is-ancestor", "HEAD", "@{u}"),
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "legacy",
        ),
        ("git", "diff", "--name-only", f"{SHA_A}..HEAD", "--", "legacy"),
    )
    return tuple(gate.CommandRecord(item, ".", 0, "", "") for item in argv)


def _provenance(**overrides: object) -> gate.GitProvenance:
    values: dict[str, object] = {
        "head": SHA_A,
        "base_head": SHA_A,
        "branch": "codex/czr005-rewrite",
        "upstream": "origin/codex/czr005-rewrite",
        "remote_head": SHA_A,
        "base_is_ancestor_of_head": True,
        "head_is_ancestor_of_remote": True,
        "worktree_status": "",
        "protected_worktree_status": "",
        "protected_committed_diff": "",
        "commands": _provenance_commands(),
    }
    values.update(overrides)
    return gate.GitProvenance(**values)  # type: ignore[arg-type]


def test_unrelated_nonempty_remote_head_never_passes() -> None:
    result = gate.audit_git_provenance(
        _provenance(remote_head=SHA_B, head_is_ancestor_of_remote=False)
    )

    assert result.status == gate.FAIL
    assert any("unrelated" in detail for detail in result.details)


def test_related_clean_remote_state_passes() -> None:
    assert gate.audit_git_provenance(_provenance()).status == gate.PASS


def test_provenance_command_failure_is_not_silently_ignored() -> None:
    commands = list(_provenance_commands())
    failed = commands[-1]
    commands[-1] = gate.CommandRecord(
        failed.argv, failed.cwd, 128, failed.stdout, "bad revision"
    )

    result = gate.audit_git_provenance(_provenance(commands=tuple(commands)))

    assert result.status == gate.FAIL
    assert "returned 128" in " ".join(result.details)


def test_warn_cannot_be_aggregated_into_state_clean_pass() -> None:
    result = gate.audit_state_rows(
        [
            {"audit_item": "remote", "status": "PASS"},
            {"audit_item": "protected", "status": "WARN"},
        ],
        required_items={"remote", "protected"},
    )

    assert result.status == gate.FAIL
    assert "only PASS is clean" in " ".join(result.details)


def _paper_rows(names: set[str]) -> list[dict[str, object]]:
    return [
        {
            "scenario": name,
            "task_path_sha256": HASH_A,
            "execution_status": gate.EXECUTED,
            "executable_command": f"python run.py --scenario {name}",
            "return_code": 0,
        }
        for name in sorted(names)
    ]


def test_paper_gate_requires_exact_set_hash_and_status() -> None:
    names = {"paper_a", "paper_b"}
    spec = gate.PaperScenarioSpec.single_hash(HASH_A, scenarios=names)

    result = gate.audit_paper_scenarios(_paper_rows(names), spec)

    assert result.status == gate.PASS
    assert result.metrics["command_evidence"]["paper_a"]["return_code"] == 0


@pytest.mark.parametrize("mutation", ["missing", "extra", "hash", "status", "command"])
def test_paper_gate_fails_closed_for_any_matrix_mismatch(mutation: str) -> None:
    names = {"paper_a", "paper_b"}
    spec = gate.PaperScenarioSpec.single_hash(HASH_A, scenarios=names)
    rows = _paper_rows(names)
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(
            {
                "scenario": "paper_extra",
                "task_path_sha256": HASH_A,
                "execution_status": gate.EXECUTED,
            }
        )
    elif mutation == "hash":
        rows[0]["task_path_sha256"] = "2" * 64
    elif mutation == "status":
        rows[0]["execution_status"] = "WARN"
    else:
        rows[0]["executable_command"] = ""

    assert gate.audit_paper_scenarios(rows, spec).status == gate.FAIL


def test_default_paper_scenario_set_is_exactly_37() -> None:
    assert len(gate.DEFAULT_PAPER_SCENARIOS) == 37


def test_optional_gate_accepts_executed_or_reproducible_blocker() -> None:
    rows = [
        {
            "scenario": "16x_full",
            "execution_status": gate.EXECUTED,
            "artifact_sha256": HASH_A,
            "executable_command": "python run.py --scale 16",
            "return_code": 0,
        },
        {
            "scenario": "32x_full",
            "execution_status": gate.PARTIAL_WITH_EXPLICIT_BLOCKER,
            "blocker_reason": "process exceeded the measured memory budget",
            "executable_command": "python run.py --scale 32",
            "return_code": 137,
        },
    ]

    result = gate.audit_optional_scenarios(rows, {"16x_full", "32x_full"})

    assert result.status == gate.PASS
    assert result.metrics["command_evidence"]["32x_full"]["return_code"] == 137


def test_optional_not_run_or_unconditional_pass_is_not_evidence() -> None:
    for status in ("NOT_RUN", "PASS"):
        result = gate.audit_optional_scenarios(
            [{"scenario": "32x_full", "execution_status": status}], {"32x_full"}
        )
        assert result.status == gate.FAIL


def _hard_row(
    scenario: str,
    task_id: int,
    *,
    reasons: list[str],
    scale: str = "1x",
    fault: bool = False,
) -> dict[str, object]:
    return {
        "scenario": scenario,
        "scale": scale,
        "task_id": task_id,
        "segment_id": f"{task_id}:direct",
        "decision_time": float(task_id),
        "current_node": task_id,
        "goal_node": 99,
        "true_outgoing_candidates": [task_id + 1, task_id + 2],
        "candidate_records": [
            {
                "next_node": task_id + 1,
                "features": {"pressure": 0.0},
                "model_score": 0.0,
            },
            {
                "next_node": task_id + 2,
                "features": {"pressure": 1.0},
                "model_score": 0.5,
            },
        ],
        "selected_next_node": task_id + 1,
        "model_prediction": task_id + 1,
        "model_margin": 0.5,
        "model_score_semantics": "lower_is_better_cost",
        "fallback_selected_next": task_id + 2,
        "model_fallback_disagreement": True,
        "full_astar_used": False,
        "hard_reasons": reasons,
        "fault_active": fault,
        "candidate_validity": True,
    }


def _hard_adjacency(rows: list[dict[str, object]]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    for row in rows:
        current = int(row.get("current_node", row.get("junction_node")))
        candidates = row.get("true_outgoing_candidates", row.get("candidate_next_nodes"))
        result[current] = [int(node) for node in candidates]  # type: ignore[union-attr]
    return result


def test_hard_case_gate_covers_high_flow_fault_tail_and_valid_candidates() -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
        _hard_row("ordinary_hard", 4, reasons=["model_fallback_disagreement"]),
    ]

    result = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert result.status == gate.PASS
    assert result.metrics["invalid_candidate_count"] == 0


def test_hard_case_gate_does_not_count_fault_scenario_without_active_local_evidence() -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row(
            "temporal_fault",
            2,
            reasons=["fault_scenario_inactive_here"],
            fault=False,
        ),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
        _hard_row("ordinary_hard", 4, reasons=["model_fallback_disagreement"]),
    ]
    rows[1]["fault_bucket"] = "fault_scenario_inactive_here"

    inactive = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert inactive.status == gate.FAIL
    assert inactive.metrics["fault_count"] == 0

    rows[1]["fault_bucket"] = "fault_local_active"
    rows[1]["hard_reasons"] = ["local_fault_state"]
    active = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))
    assert active.status == gate.PASS
    assert active.metrics["fault_count"] == 1


def test_hard_case_gate_requires_graph_adjacency_evidence() -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
    ]

    result = gate.audit_hard_case_coverage(rows)

    assert result.status == gate.FAIL
    assert result.metrics["graph_adjacency_supplied"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_rows": 2},
        {"minimum_per_required_category": 0},
        {"max_duplicate_fraction": 0.21},
        {"max_single_scenario_family_fraction": 0.61},
        {"require_graph_adjacency": False},
    ],
)
def test_hard_case_policy_cannot_be_configured_weaker(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        gate.HardCasePolicy(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("missing_category", ["high_flow", "fault", "tail"])
def test_hard_case_gate_requires_each_coverage_category(missing_category: str) -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
        _hard_row("ordinary_hard", 4, reasons=["model_fallback_disagreement"]),
    ]
    if missing_category == "high_flow":
        rows.pop(0)
    elif missing_category == "fault":
        rows.pop(1)
    else:
        rows.pop(2)

    result = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert result.status == gate.FAIL
    assert result.metrics[f"{missing_category}_count"] == 0


def test_hard_case_gate_rejects_path_suffix_as_candidates() -> None:
    row = _hard_row("high_flow_fault_tail", 1, reasons=["fault_p99_tail"], scale="2x")
    row.pop("true_outgoing_candidates")
    row["candidate_next_nodes"] = [2, 3, 4]

    rows = [row, {**row, "task_id": 2}, {**row, "task_id": 3}]
    result = gate.audit_hard_case_coverage(rows, adjacency={1: [2, 3]})

    assert result.status == gate.FAIL
    assert result.metrics["invalid_candidate_count"] == 3


def test_candidate_next_nodes_requires_and_passes_exact_graph_validation() -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
    ]
    adjacency: dict[int, list[int]] = {}
    for row in rows:
        candidates = row.pop("true_outgoing_candidates")
        current = int(row.pop("current_node"))
        row["junction_node"] = current
        row["candidate_next_nodes"] = candidates
        row["candidate_records"] = [
            {"next_node": node, "features": {"pressure": float(index)}, "model_score": index * 0.5}
            for index, node in enumerate(candidates)  # type: ignore[union-attr]
        ]
        row["selected_next"] = row.pop("selected_next_node")
        adjacency[current] = list(candidates)  # type: ignore[arg-type]

    assert gate.audit_hard_case_coverage(rows, adjacency=adjacency).status == gate.PASS
    adjacency[1] = [2, 3, 999]
    assert gate.audit_hard_case_coverage(rows, adjacency=adjacency).status == gate.FAIL


def test_hard_case_gate_rejects_selection_outside_true_candidates() -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
    ]
    rows[0]["selected_next_node"] = 999

    result = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert result.status == gate.FAIL
    assert result.metrics["invalid_candidate_count"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_fallback_disagreement", False),
        ("model_margin", float("nan")),
        ("model_margin", 0.6),
        ("model_score_semantics", "higher_is_better_score"),
        ("full_astar_used", True),
    ],
)
def test_hard_case_gate_rejects_false_disagreement_or_runtime_leakage(
    field: str, value: object
) -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
    ]
    rows[0][field] = value

    result = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert result.status == gate.FAIL
    assert result.metrics["invalid_decision_semantics_count"] == 1


def test_hard_case_gate_enforces_lower_cost_prediction_contract() -> None:
    rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
    ]
    records = rows[0]["candidate_records"]
    records[1]["model_score"] = -1.0  # type: ignore[index]

    result = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert result.status == gate.FAIL
    assert result.metrics["invalid_decision_semantics_count"] == 1


def test_hard_case_gate_rejects_deterministic_repeat_bias() -> None:
    base = _hard_row(
        "paper_main_repeat_1",
        1,
        reasons=["fault_p99_tail"],
        scale="2x",
        fault=True,
    )
    rows = [{**base, "scenario": f"paper_main_repeat_{index}"} for index in range(1, 6)]

    result = gate.audit_hard_case_coverage(rows, adjacency=_hard_adjacency(rows))

    assert result.status == gate.FAIL
    assert result.metrics["duplicate_fraction"] > 0.20


def test_lineage_accepts_complete_decision_time_derivation() -> None:
    lineage = {
        "candidate_pressure": {
            "role": "derived_runtime",
            "availability": "decision_time",
            "sources": ["local_queue", "candidate_capacity"],
        },
        "local_queue": {"role": "raw_runtime", "origin": "junction_controller"},
        "candidate_capacity": {"role": "static_graph", "origin": "map"},
        "current_node": {"role": "raw_runtime", "origin": "bag_agent"},
    }

    result = gate.audit_runtime_feature_lineage(
        ["candidate_pressure"], lineage, runtime_state_fields=["current_node"]
    )

    assert result.status == gate.PASS


@pytest.mark.parametrize("forbidden", ["path_history", "future_route", "future_schedule"])
def test_path_history_and_future_route_are_forbidden_runtime_features(
    forbidden: str,
) -> None:
    result = gate.audit_runtime_feature_lineage(
        [forbidden],
        {forbidden: {"role": "raw_runtime", "origin": "bag_agent"}},
    )

    assert result.status == gate.FAIL
    assert "forbidden" in " ".join(result.details)


def test_derived_feature_cannot_hide_post_hoc_or_path_lineage() -> None:
    lineage = {
        "innocent_pressure_score": {
            "role": "derived_runtime",
            "availability": "decision_time",
            "sources": ["queue_depth", "route_finish_time"],
        },
        "queue_depth": {"role": "raw_runtime", "origin": "junction_controller"},
        "route_finish_time": {
            "role": "offline_outcome",
            "availability": "after_route",
            "origin": "completed_task",
        },
    }

    result = gate.audit_runtime_feature_lineage(["innocent_pressure_score"], lineage)

    assert result.status == gate.FAIL
    assert "route_finish_time" in " ".join(result.details)


def test_recorded_command_preserves_executable_and_nonzero_return_code(
    workspace_tmp: Path,
) -> None:
    record = gate.run_recorded_command(
        [sys.executable, "-c", "raise SystemExit(7)"], cwd=workspace_tmp
    )

    assert record.return_code == 7
    assert sys.executable in record.executable_command
    assert record.argv[-1] == "raise SystemExit(7)"


def test_integrity_report_contains_commands_and_overall_status(workspace_tmp: Path) -> None:
    command = gate.CommandRecord(("python", "check.py"), str(workspace_tmp), 0, "ok", "")
    output = workspace_tmp / "gate.json"
    gate.write_integrity_report(
        output,
        [gate.GateCheck("component", gate.PASS)],
        [command],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["overall_status"] == gate.PASS
    assert payload["commands"][0]["return_code"] == 0
    assert payload["commands"][0]["executable_command"] == "python check.py"


def _write_test_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def test_full_integrity_config_exercises_all_required_sections(
    workspace_tmp: Path,
) -> None:
    paper_path = workspace_tmp / "paper.csv"
    _write_test_csv(
        paper_path,
        [
            {
                "scenario": scenario,
                "task_path_sha256": gate.G4IRSF10_PAPER_TASK_SHA256,
                "execution_status": gate.EXECUTED,
                "executable_command": f"python paper.py --scenario {scenario}",
                "return_code": 0,
            }
            for scenario in sorted(gate.DEFAULT_PAPER_SCENARIOS)
        ],
    )

    optional_path = workspace_tmp / "optional.csv"
    _write_test_csv(
        optional_path,
        [
            {
                "scenario": scenario,
                "execution_status": gate.EXECUTED,
                "artifact_sha256": HASH_A,
                "executable_command": f"python optional.py --scenario {scenario}",
                "return_code": 0,
            }
            for scenario in sorted(gate.DEFAULT_OPTIONAL_SCENARIOS)
        ],
    )

    hard_rows = [
        _hard_row("high_flow_2x", 1, reasons=["pressure"], scale="2x"),
        _hard_row("temporal_fault", 2, reasons=["fault_reroute"], fault=True),
        _hard_row("latency_tail", 3, reasons=["p99_delay_tail"]),
    ]
    hard_path = workspace_tmp / "hard.csv"
    _write_test_csv(hard_path, hard_rows)
    adjacency_path = workspace_tmp / "adjacency.json"
    adjacency_path.write_text(
        json.dumps(_hard_adjacency(hard_rows), sort_keys=True), encoding="utf-8"
    )

    lineage_path = workspace_tmp / "lineage.csv"
    _write_test_csv(
        lineage_path,
        [
            {
                "field_path": "candidate_pressure",
                "lineage": "runtime",
                "role": "derived_runtime",
                "origin": "feature_builder",
                "availability": "decision_time",
                "sources": ["queue_depth"],
                "model_input_allowed": True,
                "storage_boundary": "decision_trace",
            },
            {
                "field_path": "queue_depth",
                "lineage": "runtime",
                "role": "raw_runtime",
                "origin": "junction_controller",
                "availability": "decision_time",
                "sources": [],
                "model_input_allowed": False,
                "storage_boundary": "lineage_dependency",
            },
        ],
    )

    checks = gate.evaluate_integrity_config(
        gate.ROOT,
        {
            "paper": {
                "csv": str(paper_path),
                "expected_scenarios": sorted(gate.DEFAULT_PAPER_SCENARIOS),
                "expected_sha256": gate.G4IRSF10_PAPER_TASK_SHA256,
            },
            "optional": {
                "csv": str(optional_path),
                "expected_scenarios": sorted(gate.DEFAULT_OPTIONAL_SCENARIOS),
            },
            "hard_cases": {
                "csv": str(hard_path),
                "adjacency_json": str(adjacency_path),
            },
            "lineage": {"csv": str(lineage_path)},
        },
    )

    assert len(checks) == 4
    assert all(check.status == gate.PASS for check in checks)
