import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_transport_evidence import (
    arrival_count_distributions, distribution, observation_episodes, opportunity_summary,
)


def test_arrival_labels_keep_zero_bins_and_identical_mass_across_widths():
    rows = [dict(origin=1, arrival=0.), dict(origin=1, arrival=59.9),
            dict(origin=1, arrival=300.), dict(origin=1, arrival=600.)]
    counts = arrival_count_distributions(rows, [1, 2], start=0., end=600.)
    assert [counts[str(w)]["1"]["total_arrivals"] for w in (60, 300, 600)] == [3, 3, 3]
    assert counts["60"]["1"]["zero_fraction"] == .8
    assert counts["600"]["2"]["zero_fraction"] == 1.
    assert counts["600"]["1"]["count"] == 1


def test_missing_and_gapped_station_samples_do_not_fabricate_continuity():
    samples = [dict(at=0., stock=1, waiting=0), dict(at=60., stock=0, waiting=1),
        dict(at=120., stock=None, waiting=None), dict(at=300., stock=0, waiting=2),
        dict(at=360., stock=1, waiting=0)]
    result = observation_episodes(samples)
    first, second = result["shortage_episodes"]
    assert first == dict(start=60., left_censored=False, end=60., right_censored=True,
                        observed_duration_seconds=0.)
    assert second["left_censored"] and not second["right_censored"]
    assert result["observed_stock_to_zero_seconds"]["p50"] == 60.
    assert result["missing_samples"] == 1


def test_opportunities_count_physical_trays_not_candidate_edges():
    move = lambda tray, dest: dict(kind="transfer", source=1, tray_id=tray, destination=dest)
    result = opportunity_summary([dict(catalog=dict(candidates=[dict(kind="noop"), move("a", 2),
        move("a", 3)]))])
    assert result["counts"]["multiple_destinations"] == 1
    assert result["counts"]["multiple_trays"] == 0
    assert result["counts"]["multiple_sources"] == 0
    assert result["tray_count"]["p50"] == 1.


def test_empty_quantiles_remain_missing():
    assert distribution([])["p95"] is None
    with pytest.raises(ValueError, match="nonfinite"):
        distribution([float("nan")])
