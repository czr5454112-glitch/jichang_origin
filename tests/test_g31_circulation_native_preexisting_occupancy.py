"""Pure native-campaign contract guards; no extension or native clock is used."""
import copy
import json
import math
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import research_native_preexisting_occupancy as runner


def completed_rows():
    rows = runner.protocol("business")["rows"]
    for row in rows.values():
        row.update(status="assessed", summary={"completion": dict.fromkeys(runner.model.JOBS, 1.), "completion_sum": 5.,
            "business_complete": True, "common_horizon_complete": True, "audit": {"status": "passed"},
            "rolling_model_inputs_verified": True, "rolling_fallback_count": 0})
    return rows


def test_new_native_configs_rebuild_potential_without_mutating_saved_pure_domain():
    for case in runner.domain.cases():
        old = runner.domain.make_bundle(case)["contract"]; before = copy.deepcopy(old)
        native = runner.native_scene(case)
        assert old == before and len(old["heuristic_time"]) == 9
        assert len(native["node_records"]) == len(native["heuristic_time"]) == 10
        assert all(len(row) == 10 for row in native["heuristic_time"])
        assert native["heuristic_time"][9][9] == 0.
        for key in old:
            if key not in ("heuristic_time", "potential_contract", "owner_notifications"):
                assert native[key] == old[key]
        assert len(native["jobs"]) == 5 and len(native["trays"]) == 3


def test_preregistered_two_stage_denominators_and_all_four_fixed_windows():
    gate, business = runner.protocol(), runner.protocol("business")
    assert gate["native_branch_budget"] == len(gate["rows"]) == 9
    assert business["native_branch_budget"] == len(business["rows"]) == 60
    assert sum(row["fault"] is not None for row in gate["rows"].values()) == 3
    for case in runner.domain.cases():
        rows = [r for r in business["rows"].values() if r["case"] == case]
        assert len(rows) == 10 and {r["method"] for r in rows} == set(runner.METHODS)
        assert {r["method"] for r in rows if r["method"].startswith("fixed_window_")} == {"fixed_window_" + str(i) for i in range(4)}
    assert all(row["status"] == "unknown_unexecuted" for row in business["rows"].values())
    assert len(business["row_configuration_sha256"]) == 60


def test_import_closure_includes_absolute_potential_dependency_and_archive_paths(tmp_path):
    plan = runner.prepare(tmp_path/"prepared", "delivery_gate")
    assert any(p.endswith("scripts\\eval\\run_g4irsf28_service_potential.py") or p.endswith("scripts/eval/run_g4irsf28_service_potential.py") for p in plan["source_sha256"])
    for source, archived in plan["source_archive"].items():
        assert runner.sha(tmp_path/"prepared"/archived) == plan["source_sha256"][source]
    for key, expected in plan["row_configuration_sha256"].items():
        data = json.loads((tmp_path/"prepared"/"inputs"/(key+".json")).read_text(encoding="utf-8"))
        assert runner.config_sha(data) == expected


@pytest.mark.parametrize("defect", ("missing", "nonfinite", "unfinished", "censored", "audit_failed", "wrong_sum"))
def test_incomplete_fixed_reference_remains_unknown_with_full_denominator(defect):
    rows = completed_rows(); case = runner.domain.cases()[0]["case_id"]; row = rows[case+"/fixed_window_3"]
    if defect == "missing": row["status"] = "unknown_unexecuted"
    elif defect == "nonfinite": row["summary"]["completion"]["blocker"] = math.nan
    elif defect == "unfinished": row["summary"]["completion"]["blocker"] = -1.
    elif defect == "censored": row["summary"]["common_horizon_complete"] = False
    elif defect == "audit_failed": row["summary"]["audit"]["status"] = "failed"
    else: row["summary"]["completion_sum"] = -1.
    report = runner.assess(rows, "business")[case]
    assert not report["complete_fixed_family"]
    assert len(report["methods"]) == 10
    assert report["methods"]["coordinate_plateau"]["strict_protected_vs_complete_finite_fixed_family"] is None


def test_all_five_jobs_strict_zero_protection():
    rows = completed_rows(); case = runner.domain.cases()[4]["case_id"]
    row = rows[case+"/resource_pair_repair"]
    row["summary"]["completion"]["blocker"] += 1e-12
    row["summary"]["completion_sum"] = sum(row["summary"]["completion"].values())
    report = runner.assess(rows, "business")[case]["methods"]["resource_pair_repair"]
    assert report["strict_protected_vs_incumbent"] is False
    assert report["strict_protected_vs_complete_finite_fixed_family"] is False


@pytest.mark.parametrize("defect", ("missing_row", "wrong_case", "wrong_method"))
def test_action_label_cannot_hide_or_rebind_rows(defect):
    rows = completed_rows(); key = next(iter(rows))
    if defect == "missing_row": rows.pop(key)
    elif defect == "wrong_case": rows[key]["case"] = runner.domain.cases()[1]
    else: rows[key]["method"] = "coordinate_plateau"
    assert runner.assess(rows, "business")["status"] == "unknown_incomplete_or_misbound_denominator"


def test_business_cannot_skip_delivery_gate():
    with pytest.raises(ValueError, match="requires_completed_delivery_gate"):
        runner.require_delivery_gate(None, "a"*64, {})


def test_no_method_can_use_pure_or_forged_native_flag():
    for method in runner.METHODS:
        for info in ({}, {"native_delivery_verified": True, "status": "conditional_validated_later_data"},
                     {"native_delivery_verified": False, "status": "conditional_native_delivered_later_model_input"}):
            assert runner.choose(info, method)["selected_action"] is None
