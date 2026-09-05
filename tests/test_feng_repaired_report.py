"""Reporting eligibility gates must reject contaminated or selective evidence."""
import pytest

from scripts.eval import write_feng_repaired_report as report


def cell(map_name="map2", load=1.0, seed=104729, method=report.DH, complete=True):
    return {"map": map_name, "load_factor": load, "seed": seed, "method": method,
            "raw_bag_count": "10", "segment_count": "12",
            "completed_raw_bag_count": "10" if complete else "9",
            "full_population_complete": str(complete),
            "source_sha256": report.SOURCE, "class_sha256": report.CLASSES,
            "workload_identity_sha256": "same-workload", "input_sha256": "same-input",
            "map_sha256": "same-map"}


@pytest.mark.parametrize("load,complete,metric", [
    (2.0, True, "population_latency_mean_seconds"),
    (2.0, True, "scheduled_release_latency_max_seconds"),
    (1.0, False, "population_latency_p99_seconds"),
    (1.75, False, "scheduled_release_latency_mean_seconds"),
])
def test_ineligible_latency_is_rejected(load, complete, metric):
    row = cell(load=load, complete=complete)
    row[metric] = "123.4"
    with pytest.raises(ValueError, match="ineligible formal latency"):
        report.validate_cells([row])


def test_old_nanning_source_cannot_fill_new_matrix():
    row = cell(map_name="nanning")
    row["source_sha256"] = "99bf695a787accce5780996d06bbc8eb816992169ef8b731e8116a49c10f14d8"
    with pytest.raises(ValueError, match="old or unfrozen"):
        report.validate_cells([row])


def test_exact_matrix_requires_all_new_nanning_coordinates():
    rows = [cell(m, load, seed, method) for m in report.MAPS for load in report.LOADS
            for seed in report.SEEDS for method in (report.DH, report.G31, report.HCA)]
    assert report.matrix_status(report.validate_cells(rows)) == "COMPLETE"
    missing = [row for row in rows if report.key(row) != ("nanning", 2.0, 333667, report.DH)]
    assert report.matrix_status(report.validate_cells(missing)) == "INCOMPLETE"
    with pytest.raises(ValueError, match="duplicate"):
        report.validate_cells(missing + [missing[0]])


def test_incomplete_seed_disables_group_timing_without_dropping_it():
    pairs = [(cell(), cell(method=report.G31)),
             (cell(seed=130363, complete=False), cell(seed=130363, method=report.G31))]
    assert not report.timing_eligible(pairs, 1.0)
    assert report.mean(pairs, 0, "completed_raw_bag_count") == 9.5
    assert not report.timing_eligible([pairs[0]], 2.0)
    assert report.timing_eligible([pairs[0]], 1.0)


def test_same_seed_different_input_is_not_a_pair():
    dh, g31 = cell(), cell(method=report.G31)
    g31["input_sha256"] = "different-input"
    with pytest.raises(ValueError, match="unpaired input identity"):
        report.pairs_for(report.validate_cells([dh, g31]), "map2", 1.0)
