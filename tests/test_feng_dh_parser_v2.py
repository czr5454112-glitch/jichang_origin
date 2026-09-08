"""Missing native clocks stay censored; invalid completion and identity still fail."""
import csv
import json
from pathlib import Path

import pytest

from scripts.eval import run_feng_dh_paper_suite as old
from scripts.eval import run_feng_dh_paper_suite_v2 as new


@pytest.mark.parametrize("value", [None, "", "N/A", " NaN ", "nan"])
def test_missing_clocks(value):
    assert new.finite_or_none(value) is None


@pytest.mark.parametrize("value", ["inf", "-inf", "garbage", float("nan"), float("inf")])
def test_invalid_clocks_rejected(value):
    with pytest.raises(ValueError):
        new.finite_or_none(value)


def fixture(tmp_path, complete=True):
    canonical = tmp_path / "canonical.jsonl"
    canonical.write_text(json.dumps({"task_id": 1, "segment_id": 0, "leg": "direct", "start": 1,
        "goal": 2, "pass_time": 10., "std": 10000.}) + "\n", encoding="utf-8")
    row = {"source_raw_bag_id": 1, "segment_id": 0, "start": 1, "goal": 2, "release_seconds": 10,
        "completion_time_seconds": "20" if complete else "N/A", "admission_time_seconds": "12" if complete else "N/A",
        "status": "COMPLETED" if complete else "AT_LOADING_OR_JUNCTION", "final_node": 2 if complete else 1}
    return {"canonical_path": str(canonical), "raw_bag_count": 1}, row


def save(tmp_path, row, duplicate=False):
    with (tmp_path / "segments.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
        if duplicate:
            writer.writerow(row)


def test_completed_metrics_exactly_unchanged(tmp_path):
    identity, row = fixture(tmp_path)
    save(tmp_path, row)
    assert old.normalize(identity, tmp_path) == new.normalize(identity, tmp_path)
    assert new.normalize(identity, tmp_path)["metrics"]["tht_D_mean_seconds"] == 10


@pytest.mark.parametrize("admitted", [False, True])
def test_unfinished_is_full_denominator_with_no_survivor_mean(tmp_path, admitted):
    identity, row = fixture(tmp_path, False)
    if admitted:
        row["admission_time_seconds"] = "12"
    save(tmp_path, row)
    with pytest.raises(ValueError):
        old.normalize(identity, tmp_path)
    result = new.normalize(identity, tmp_path)
    assert result["full_population_complete"] is False
    assert result["metrics"]["raw_bag_denominator"] == 1
    assert result["metrics"]["completed_raw_bag_count"] == 0
    assert all(v is None for k, v in result["metrics"].items() if k.startswith("tht_"))


@pytest.mark.parametrize("patch", [
    {"completion_time_seconds": "N/A"}, {"admission_time_seconds": "N/A"},
    {"final_node": 3}, {"goal": 3}, {"release_seconds": 11},
    {"completion_time_seconds": "98260"}, {"admission_time_seconds": "21"},
    {"source_raw_bag_id": 2}, {"completion_time_seconds": "inf"}])
def test_invalid_completed_identity_or_time_rejected(tmp_path, patch):
    identity, row = fixture(tmp_path)
    row.update(patch)
    save(tmp_path, row)
    with pytest.raises(ValueError):
        new.normalize(identity, tmp_path)


def test_duplicate_population_rejected(tmp_path):
    identity, row = fixture(tmp_path)
    save(tmp_path, row, True)
    with pytest.raises(ValueError):
        new.normalize(identity, tmp_path)


def test_recovery_spec_cannot_dispatch_java(tmp_path, monkeypatch):
    spec = tmp_path / "recovery.json"
    spec.write_text(json.dumps({"native_recovery_from": {"source": "old"}}), encoding="utf-8")
    monkeypatch.setattr(new.subprocess, "run", lambda *a, **kw: pytest.fail("Java must not run"))
    with pytest.raises(ValueError, match="never rerun Java"):
        new.run_spec(spec, tmp_path / "output")


def test_three_accepted_native_cells_match_exactly():
    plan = new.read(new.ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v4/plan.json")
    compared = []
    for cell in plan["cells"]:
        output = Path(cell["output_dir"])
        if (cell["method"] != new.METHOD or cell["seed"] != 104729 or cell["speed_mps"] != 2.5
                or (cell["map"] == "nanning" and cell["load_factor"] == 2)):
            continue
        spec = new.read(cell["spec_path"])
        _, identity = new.external._identity_payload(Path(spec["workload_identity_path"]))
        assert old.normalize(identity, output) == new.normalize(identity, output)
        compared.append(cell["cell_id"])
    assert len(compared) == 3
