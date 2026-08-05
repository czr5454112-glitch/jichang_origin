from __future__ import annotations

import csv
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess
from typing import Any, Callable

import pytest

from scripts.eval import g4irsf14_fail_closed_completion as generator
from scripts import validate_g4irsf14_fail_closed_completion as validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_SOURCE_COMMIT = "966a063573f0419df1324708db75211c521d59db"
HISTORICAL_REQUIRED_PATHS = {
    Path(".gitattributes"),
    Path("CMakeLists.txt"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("src/czr005/cpp_backend.py"),
}


@lru_cache(maxsize=None)
def _git_blob(commit: str, relative: Path) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative.as_posix()}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _copy_bundle(destination: Path) -> Path:
    for relative in validator.REQUIRED_BUNDLE_FILES:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative in HISTORICAL_REQUIRED_PATHS:
            target.write_bytes(_git_blob(PREDECESSOR_SOURCE_COMMIT, relative))
        else:
            source = REPOSITORY_ROOT / relative
            assert source.is_file(), relative.as_posix()
            shutil.copyfile(source, target)
    return destination


@pytest.fixture
def bundle_root(tmp_path: Path) -> Path:
    return _copy_bundle(tmp_path / "bundle")


def _read_json(root: Path, relative: Path) -> dict[str, Any]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(root: Path, relative: Path, value: dict[str, Any]) -> None:
    path = root / relative
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _resign_json(root: Path, relative: Path) -> dict[str, Any]:
    value = _read_json(root, relative)
    value.pop("self_sha256", None)
    value["self_sha256"] = validator.canonical_sha256(value)
    _write_json(root, relative, value)
    return value


def _mutate_json(
    root: Path,
    relative: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    value = _read_json(root, relative)
    mutate(value)
    value.pop("self_sha256", None)
    value["self_sha256"] = validator.canonical_sha256(value)
    _write_json(root, relative, value)


def _binding(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    return {
        "path": relative.as_posix(),
        "sha256": validator.file_sha256(path),
        "byte_count": path.stat().st_size,
    }


def _refresh_json_bindings(
    root: Path,
    relative: Path,
    bound_paths: tuple[Path, ...],
) -> None:
    value = _read_json(root, relative)
    assert set(value["output_bindings"]) == {
        path.as_posix() for path in bound_paths
    }
    value["output_bindings"] = {
        path.as_posix(): _binding(root, path) for path in bound_paths
    }
    value.pop("self_sha256", None)
    value["self_sha256"] = validator.canonical_sha256(value)
    _write_json(root, relative, value)


def _rebind_complete_chain(root: Path) -> None:
    # Children are resigned before every parent that physically binds them.
    _refresh_json_bindings(
        root,
        validator.RULE_GATE,
        (validator.RULE_REPORT, validator.RULE_TABLE),
    )
    _refresh_json_bindings(
        root,
        validator.LEARNING_GATE,
        (
            validator.LEARNING_DATA_REPORT,
            validator.OFFLINE_REPORT,
            validator.ROUTE_OFFLINE_TABLE,
            validator.MERGE_OFFLINE_TABLE,
            validator.ADMISSION_OFFLINE_TABLE,
        ),
    )
    _refresh_json_bindings(
        root,
        validator.CLOSED_LOOP_GATE,
        (
            validator.CLOSED_LOOP_REPORT,
            validator.CLOSED_LOOP_TABLE,
            validator.LEARNING_GATE,
        ),
    )
    _refresh_json_bindings(
        root,
        validator.FINAL_BUNDLE,
        validator.FINAL_BOUND_PATHS,
    )
    _refresh_json_bindings(
        root,
        validator.SCALE_GATE,
        (
            validator.FINAL_REPORT,
            validator.FINAL_TABLE,
            validator.FINAL_BUNDLE,
        ),
    )
    _refresh_json_bindings(
        root,
        validator.DOWNSTREAM_GATE,
        tuple(
            path
            for path in validator.OUTPUT_PATHS
            if path != validator.DOWNSTREAM_GATE
        ),
    )


def _mutate_csv(
    root: Path,
    relative: Path,
    mutate: Callable[[list[dict[str, str]]], None],
) -> None:
    path = root / relative
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = list(reader)
    assert fields and fields[-1] == "row_sha256"
    mutate(rows)
    for row in rows:
        projection = dict(row)
        projection.pop("row_sha256", None)
        row["row_sha256"] = validator.canonical_sha256(projection)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_valid_bundle_is_portable_and_does_not_resolve_recorded_binary(
    bundle_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    census = _read_json(bundle_root, validator.UPSTREAM_CENSUS)
    recorded_binary_text = str(census["binary"]["path"])
    assert PureWindowsPath(recorded_binary_text).is_absolute()
    assert not PurePosixPath(recorded_binary_text).is_absolute()
    recorded_binary = Path(recorded_binary_text)
    original_is_file = Path.is_file

    def guarded_is_file(path: Path) -> bool:
        if path == recorded_binary:
            raise AssertionError("validator touched generation-host binary")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", guarded_is_file)
    result = validator.validate_fail_closed_completion(bundle_root)
    assert result["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER_VALID"
    assert result["output_count"] == 24
    assert result["selected_candidate_id"] is None
    assert result["scale_execution_count"] == 0


def test_stage_e_recorded_source_checkout_drift_is_rejected(
    bundle_root: Path,
) -> None:
    path = bundle_root / Path("cpp/ics_core/runtime/bounded_local_pibt.hpp")
    path.write_text(
        path.read_text(encoding="utf-8") + "\n// forged drift\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(
        validator.CompletionValidationError,
        match="STAGE_E_SOURCE_CHECKOUT_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_generator_validate_only_rejects_stale_input_identity(
    bundle_root: Path,
) -> None:
    gate = _read_json(bundle_root, validator.DOWNSTREAM_GATE)
    expected_identity = dict(gate["input_identity"])
    expected_identity["census_self_sha256"] = "0" * 64

    with pytest.raises(
        generator.FailClosedCompletionError,
        match="DOWNSTREAM_INPUT_IDENTITY_DRIFT",
    ):
        generator._validate_published_bundle(
            bundle_root,
            expected_identity=expected_identity,
        )


def test_inherited_registry_artifact_drift_is_rejected(
    bundle_root: Path,
) -> None:
    path = bundle_root / Path(
        "outputs/reports/g4irsf13_fault_recovery_results.md"
    )
    path.write_text(
        path.read_text(encoding="utf-8") + "\nforged drift\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(
        validator.CompletionValidationError,
        match="BASELINE_REGISTRY_INHERITED_BINDING_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_pass_status_is_rejected(bundle_root: Path) -> None:
    _mutate_json(
        bundle_root,
        validator.RULE_GATE,
        lambda value: value.__setitem__("status", "PASS"),
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="RULE_GATE",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_metric_on_not_run_row_is_rejected(
    bundle_root: Path,
) -> None:
    def inject_metric(rows: list[dict[str, str]]) -> None:
        target = next(row for row in rows if row["candidate_id"] == "J3")
        assert target["execution_status"] == "NOT_RUN"
        target["original_entry_mean_minutes"] = "40.0"

    _mutate_csv(bundle_root, validator.CLOSED_LOOP_TABLE, inject_metric)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="CLOSED_LOOP",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_rule_result_label_inventory_is_rejected(
    bundle_root: Path,
) -> None:
    def remove_label(value: dict[str, Any]) -> None:
        value["result_label_inventory"].pop()

    _mutate_json(bundle_root, validator.RULE_GATE, remove_label)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="RULE_GATE_PROMOTION_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_learning_obligation_inventory_is_rejected(
    bundle_root: Path,
) -> None:
    def remove_negative_cohort(value: dict[str, Any]) -> None:
        value["planned_negative_cohorts"].pop()

    _mutate_json(
        bundle_root,
        validator.LEARNING_GATE,
        remove_negative_cohort,
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="LEARNING_GATE_ACTIVATION_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


@pytest.mark.parametrize(
    ("relative", "expected_error"),
    (
        (validator.RULE_TABLE, "RULE_GATE_ROW_INVENTORY_DRIFT"),
        (validator.CLOSED_LOOP_TABLE, "CLOSED_LOOP_CANDIDATE_SET_DRIFT"),
        (validator.FINAL_TABLE, "FINAL_CANDIDATE_ROW_SET_DRIFT"),
    ),
)
def test_rehashed_required_row_inventory_is_rejected(
    bundle_root: Path,
    relative: Path,
    expected_error: str,
) -> None:
    _mutate_csv(bundle_root, relative, lambda rows: rows.pop())
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match=expected_error,
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_sixteen_reason_taxonomy_is_rejected(
    bundle_root: Path,
) -> None:
    def remove_reason(rows: list[dict[str, str]]) -> None:
        assert len(rows) == 17
        rows.pop()

    _mutate_csv(bundle_root, validator.PIBT_REASONS_TABLE, remove_reason)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="PIBT_REASON",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_selected_candidate_is_rejected(bundle_root: Path) -> None:
    def select_candidate(value: dict[str, Any]) -> None:
        value["selected_candidate_id"] = "M1_RULE"
        value["candidate_selection_status"] = "SELECTED"
        value["new_candidate_execution_count"] = 1

    _mutate_json(bundle_root, validator.FINAL_BUNDLE, select_candidate)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="FINAL_BUNDLE",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_root_child_blocker_drift_is_rejected(
    bundle_root: Path,
) -> None:
    def remove_child_blocker(value: dict[str, Any]) -> None:
        value["single_blocker"]["child_blockers"].pop()

    _mutate_json(
        bundle_root,
        validator.DOWNSTREAM_GATE,
        remove_child_blocker,
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="DOWNSTREAM_SINGLE_BLOCKER_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_scale_condition_unlock_is_rejected(
    bundle_root: Path,
) -> None:
    def unlock_condition(value: dict[str, Any]) -> None:
        condition = value["conditions"]["strict_v2_safe_win"]
        condition["evaluation_status"] = "PASS"
        condition["satisfied"] = True

    _mutate_json(bundle_root, validator.SCALE_GATE, unlock_condition)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="SCALE_GATE_UNLOCK_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


@pytest.mark.parametrize(
    "field",
    (
        "strict_win_vs_v2_safe",
        "fault_regression_pass",
        "tail_gate_pass",
    ),
)
def test_rehashed_not_evaluated_null_to_false_is_rejected(
    bundle_root: Path,
    field: str,
) -> None:
    def forge_evaluated_false(value: dict[str, Any]) -> None:
        assert value[field] is None
        value[field] = False

    _mutate_json(bundle_root, validator.FINAL_BUNDLE, forge_evaluated_false)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="FINAL_BUNDLE",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_prefilter_count_as_attempt_is_rejected(
    bundle_root: Path,
) -> None:
    def conflate_csv(rows: list[dict[str, str]]) -> None:
        assert len(rows) == 1
        rows[0]["attempt_count"] = "1337"

    def conflate_gate(value: dict[str, Any]) -> None:
        value["pibt_measurement"]["attempt_count"] = 1_337

    _mutate_csv(bundle_root, validator.PIBT_COMMIT_TABLE, conflate_csv)
    _mutate_json(bundle_root, validator.DOWNSTREAM_GATE, conflate_gate)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="PIBT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_prefilter_csv_only_as_attempt_is_rejected(
    bundle_root: Path,
) -> None:
    def conflate_csv(rows: list[dict[str, str]]) -> None:
        assert len(rows) == 1
        rows[0]["attempt_count"] = "1337"

    _mutate_csv(bundle_root, validator.PIBT_COMMIT_TABLE, conflate_csv)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="PIBT_PREFILTER_ATTEMPT_CONFLATION",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_direct_csv_row_hash_break_is_rejected(bundle_root: Path) -> None:
    path = bundle_root / validator.RUNTIME_TABLE
    text = path.read_text(encoding="utf-8")
    assert "NO_OPTIMIZATION_NOT_RUN" in text
    path.write_text(
        text.replace(
            "NO_OPTIMIZATION_NOT_RUN",
            "FORGED_PASS",
            1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="CSV_ROW_HASH_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_direct_output_binding_break_is_rejected(bundle_root: Path) -> None:
    path = bundle_root / validator.RULE_REPORT
    path.write_text(
        path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _refresh_json_bindings(
        bundle_root,
        validator.DOWNSTREAM_GATE,
        tuple(
            path
            for path in validator.OUTPUT_PATHS
            if path != validator.DOWNSTREAM_GATE
        ),
    )

    with pytest.raises(
        validator.CompletionValidationError,
        match="RULE_GATE_BINDING_DRIFT",
    ):
        validator.validate_fail_closed_completion(bundle_root)


@pytest.mark.parametrize(
    ("relative", "contradictory_claim"),
    (
        (validator.RULE_REPORT, "Stage F 已通过"),
        (validator.PIBT_REPORT, "runtime taxonomy complete = true"),
        (validator.LEARNING_DATA_REPORT, "训练已完成"),
        (validator.OFFLINE_REPORT, "已生成模型"),
        (validator.CLOSED_LOOP_REPORT, "候选已晋级"),
        (validator.FAULT_REPORT, "G4IRSF14 fault regression pass"),
        (validator.RUNTIME_REPORT, "优化已完成"),
    ),
)
def test_rehashed_nonfinal_report_contradiction_is_rejected(
    bundle_root: Path,
    relative: Path,
    contradictory_claim: str,
) -> None:
    path = bundle_root / relative
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n- {contradictory_claim}\n",
        encoding="utf-8",
        newline="\n",
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="REPORT_CONTRADICTORY_CLAIM",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_unbound_g4irsf14_model_is_rejected(bundle_root: Path) -> None:
    path = bundle_root / "artifacts/models/nested/G4IRSF14_forged.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8", newline="\n")

    with pytest.raises(
        validator.CompletionValidationError,
        match="UNAUTHORIZED_G4IRSF14_MODELS",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_duplicate_json_key_is_rejected(bundle_root: Path) -> None:
    path = bundle_root / validator.FINAL_BUNDLE
    text = path.read_text(encoding="utf-8")
    needle = (
        '  "schema": '
        '"czr005.g4irsf14.final_candidate_bundle.v1"'
    )
    assert text.count(needle) == 1
    path.write_text(
        text.replace(
            needle,
            '  "schema": "duplicate",\n' + needle,
            1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    _refresh_json_bindings(
        bundle_root,
        validator.DOWNSTREAM_GATE,
        tuple(
            path
            for path in validator.OUTPUT_PATHS
            if path != validator.DOWNSTREAM_GATE
        ),
    )

    with pytest.raises(
        validator.CompletionValidationError,
        match="DUPLICATE_JSON_KEY",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_fault_pass_is_rejected(bundle_root: Path) -> None:
    def forge_fault_pass(value: dict[str, Any]) -> None:
        value["fault_regression_pass"] = True

    _mutate_json(bundle_root, validator.FINAL_BUNDLE, forge_fault_pass)
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="FINAL_BUNDLE",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_final_report_missing_required_answer_is_rejected(
    bundle_root: Path,
) -> None:
    path = bundle_root / validator.FINAL_REPORT
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    assert sum(line.startswith("18. **") for line in lines) == 1
    path.write_text(
        "".join(line for line in lines if not line.startswith("18. **")),
        encoding="utf-8",
        newline="\n",
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="FINAL_REPORT_QUESTION_INVENTORY_DRIFT:18",
    ):
        validator.validate_fail_closed_completion(bundle_root)


def test_rehashed_final_report_contradictory_pass_claim_is_rejected(
    bundle_root: Path,
) -> None:
    path = bundle_root / validator.FINAL_REPORT
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text + "\n- promotion_allowed: true\n",
        encoding="utf-8",
        newline="\n",
    )
    _rebind_complete_chain(bundle_root)

    with pytest.raises(
        validator.CompletionValidationError,
        match="REPORT_CONTRADICTORY_CLAIM",
    ):
        validator.validate_fail_closed_completion(bundle_root)
