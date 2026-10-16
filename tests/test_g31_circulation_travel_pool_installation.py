"""Experimental installation must preserve explicit reference and cleanup."""
import pytest
from scripts.experiments.g31_ics_circulation import analytic_control
from scripts.experiments.g31_ics_circulation.install_public_travel_pool import installed_public_travel_pool
from scripts.experiments.g31_ics_circulation.public_travel_pool import PublicTravel


def data():
    return {"owner_id": "A", "now": 0., "node_records": [[0, 0, .1], [1, 0, .2]],
            "edge_records": [[0, 1, 1., 2.]], "edge_contracts": [], "known_faults": []}


def test_factory_reuses_only_implicit_search_and_keeps_explicit_reference():
    view = data()
    expected = PublicTravel(view).path(0, 1)
    with installed_public_travel_pool() as (pool, counters):
        assert analytic_control.PublicTravel(view).path(0, 1) == expected
        assert analytic_control.PublicTravel(view).path(0, 1) == expected
        fresh = analytic_control.PublicTravel(view, _reuse_source_searches=False)
        assert type(fresh) is PublicTravel and not fresh._reuse_source_searches
        assert fresh.path(0, 1) == expected
        assert counters == {"checkouts": 2, "explicit_fresh_searches": 1}
        assert (pool.hits, pool.misses) == (1, 1)
    assert analytic_control.PublicTravel is PublicTravel


def test_exception_restores_original_and_next_worker_starts_cold():
    with pytest.raises(LookupError, match="controller_failure"):
        with installed_public_travel_pool():
            analytic_control.PublicTravel(data()).path(0, 1)
            raise LookupError("controller_failure")
    assert analytic_control.PublicTravel is PublicTravel
    with installed_public_travel_pool() as (pool, _):
        analytic_control.PublicTravel(data()).path(0, 1)
        assert pool.misses == 1 and pool.hits == 0


def test_nested_installation_fails_without_replacing_outer_factory():
    with installed_public_travel_pool():
        outer = analytic_control.PublicTravel
        with pytest.raises(ValueError, match="another_installation"):
            with installed_public_travel_pool():
                pass
        assert analytic_control.PublicTravel is outer
        assert analytic_control.PublicTravel(data()).path(0, 1)[1] == (0, 1)
    assert analytic_control.PublicTravel is PublicTravel


def test_foreign_factory_change_is_rejected_and_original_restored():
    with pytest.raises(RuntimeError, match="factory_changed"):
        with installed_public_travel_pool():
            analytic_control.PublicTravel = object
    assert analytic_control.PublicTravel is PublicTravel
