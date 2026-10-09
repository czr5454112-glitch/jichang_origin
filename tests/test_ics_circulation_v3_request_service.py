"""Complete request denominators, conservative fallback and owner permissions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.model import Bag, Tray
from scripts.experiments.ics_circulation_v3.request_service import (
    AttemptFault, OUTCOMES, ResourceOwner, RouteRequest, RoutingRequestService,
    TransportScript, validate_committed_full_route,
)
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.run_request_service import cases, run, service_for, snapshot_fixture


@pytest.mark.parametrize("case", cases(), ids=lambda case: case.name)
def test_controlled_failure_and_success_classification(case):
    owner = ResourceOwner(case.state)
    request = RouteRequest(case.name, "bag", "tray", max_attempts=case.max_attempts)
    result = service_for(owner, case).handle(request, case.transport)
    assert result.status == case.expected_outcome
    assert result.status in OUTCOMES
    assert result.attempts <= request.max_attempts
    assert set(owner.snapshot().trays) == set(case.state.trays)
    assert set(owner.snapshot().bags) == set(case.state.bags)
    if result.status == "proven_infeasible":
        assert result.proof["kind"] == "complete_directed_static_no_path"
        assert result.proof["destination"] not in result.proof["reachable_cut"]
    else:
        assert result.proof is None


def test_owner_binds_authorization_to_request_identity_even_for_direct_calls():
    state = snapshot_fixture()
    state.trays["other_tray"] = Tray("other_tray", "A", "loaded", "other_bag")
    state.bags["other_bag"] = Bag("other_bag", "A", "B", 0, 20)
    owner = ResourceOwner(state)
    observation, summary = owner.observe()
    candidate = RegionalCandidateGenerator(deadline_ms=None).generate(observation, "other_bag", "other_tray", k=1)[0]
    request = RouteRequest("bound", "bag", "tray")
    assert owner.revalidate(candidate, request, summary).reason == "request_action_identity_mismatch"
    outcome, receipt, replayed = owner.commit(candidate, request)
    assert outcome.reason == "request_action_identity_mismatch"
    assert receipt is None and not replayed
    assert owner.snapshot() == state


def test_stale_dependency_retries_fresh_observation_without_restamping_candidate():
    owner = ResourceOwner(snapshot_fixture())
    script = TransportScript((AttemptFault(stale_summary_before_delivery=True),))
    result = RoutingRequestService(owner).handle(RouteRequest("retry", "bag", "tray"), script)
    assert result.status == "new_route_success" and result.attempts == 2
    first, second = result.attempts_trace
    assert first["selected_candidate"]["dependency_version"] == 0
    assert second["selected_candidate"]["dependency_version"] == 1
    assert owner.snapshot().version == 2
    assert "owner_revalidation:stale_dependency_summary" in first["events"]


def test_lost_ack_has_distinct_physical_and_client_outcomes():
    owner = ResourceOwner(snapshot_fixture())
    service = RoutingRequestService(owner)
    request = RouteRequest("ack", "bag", "tray", max_attempts=1)
    lost = service.handle(request, TransportScript((AttemptFault(lose_acknowledgement=True),)))
    assert lost.status == "communication_failure"
    assert lost.owner_committed and not lost.acknowledged
    accepted = owner.snapshot()
    recovered = service.handle(request)
    assert recovered.status == "new_route_success"
    assert recovered.receipt_replayed and recovered.acknowledged
    assert owner.snapshot() == accepted


def test_simulated_transport_is_separate_from_real_compute():
    fault = AttemptFault(queue_ms=7, snapshot_message_ms=11, commit_message_ms=13, acknowledgement_ms=17)
    result = RoutingRequestService(ResourceOwner(snapshot_fixture())).handle(
        RouteRequest("timing", "bag", "tray"), TransportScript((fault,)))
    times = result.timings
    assert times["simulated_queue_ms"] == 7
    assert times["simulated_communication_ms"] == 41
    assert times["accounted_end_to_end_ms"] == times["local_wall_ms"] + 48
    assert times["actual_network_ms"] is None
    assert all(times[key] >= 0 for key in ("generation_ms", "feature_ms", "score_ms", "revalidation_ms", "commit_compute_ms"))


def test_full_route_fallback_does_not_publish_or_consume_capacity_again():
    case = next(case for case in cases() if case.name == "valid_entered_full_old_route")
    owner = ResourceOwner(case.state)
    before = owner.snapshot()
    result = RoutingRequestService(owner).handle(RouteRequest("fallback", "bag", "tray"))
    assert result.status == "still_valid_old_route"
    assert not result.owner_committed  # No new receipt for this request ID.
    assert owner.snapshot() == before
    assert validate_committed_full_route(before, RouteRequest("x", "bag", "tray")).accepted


def test_bare_proposal_is_never_a_committed_old_fallback():
    state = snapshot_fixture()
    RegionalCandidateGenerator(deadline_ms=None).generate(state, "bag", "tray", k=1)
    assert not validate_committed_full_route(state, RouteRequest("no_commit", "bag", "tray")).accepted


@pytest.mark.parametrize("stage", ["factory", "generator", "feature", "scorer"])
def test_broken_local_extension_retains_request_and_does_not_mutate_state(stage):
    def fail(*args, **kwargs):
        raise RuntimeError("controlled extension failure")
    class BrokenGenerator:
        generate = fail
    kwargs = ({"generator_factory": fail} if stage == "factory" else
              {"generator_factory": lambda: BrokenGenerator()} if stage == "generator" else
              {"feature_builder": fail} if stage == "feature" else {"selector": fail})
    owner = ResourceOwner(snapshot_fixture())
    before = owner.snapshot()
    result = RoutingRequestService(owner, **kwargs).handle(RouteRequest(f"broken:{stage}", "bag", "tray"))
    assert result.status == "local_processing_failure"
    assert result.attempts == 1 and not result.owner_committed
    assert owner.snapshot() == before
    assert "controlled extension failure" in result.reason


def test_scoring_observation_is_isolated_and_cannot_change_fixed_module():
    def mutate(observation, candidates, features):
        observation.module.hold_by_node["B"] = 1000
        observation.trays.clear()
        features[0]["usable_at"] = -100
        return candidates[0]
    owner = ResourceOwner(snapshot_fixture())
    result = RoutingRequestService(owner, selector=mutate).handle(RouteRequest("isolated", "bag", "tray"))
    assert result.status == "new_route_success"
    assert owner.snapshot().module.hold_ticks("B") == 0
    assert set(owner.snapshot().trays) == {"tray"}


@pytest.mark.parametrize("field,value", [("max_attempts", True), ("max_attempts", 1.5),
                                         ("max_attempts", 0), ("candidate_count", False),
                                         ("candidate_count", 2.5), ("candidate_count", -1)])
def test_count_bounds_require_actual_positive_integers(field, value):
    request = replace(RouteRequest("bad_parameter", "bag", "tray"), **{field: value})
    result = RoutingRequestService(ResourceOwner(snapshot_fixture())).handle(request)
    assert result.status == "commit_failure" and result.reason == "invalid_request_parameters"
    assert result.attempts == 0


def test_concurrent_retransmissions_only_commit_one_physical_prefix():
    owner = ResourceOwner(snapshot_fixture())
    service = RoutingRequestService(owner)
    request = RouteRequest("one_logical_request", "bag", "tray", max_attempts=3)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: service.handle(request), range(4)))
    final = owner.snapshot()
    assert final.version == 1 and len(final.plans) == 1
    assert all(response.status == "new_route_success" for response in responses)
    assert len({response.candidate_id for response in responses}) == 1
    assert sum(not response.receipt_replayed for response in responses) == 1


def test_request_id_collision_cannot_authorize_a_different_action():
    owner = ResourceOwner(snapshot_fixture())
    service = RoutingRequestService(owner)
    assert service.handle(RouteRequest("shared_id", "bag", "tray")).status == "new_route_success"
    before = owner.snapshot()
    result = service.handle(RouteRequest("shared_id", "different_bag", "tray"))
    assert result.status == "commit_failure" and result.reason == "request_id_collision"
    assert owner.snapshot() == before


def test_runner_reconciles_every_request_including_local_processing_failure(tmp_path):
    summary = run(tmp_path, repeats=1)
    assert summary["request_count"] == summary["unique_request_count"] == len(cases())
    assert summary["denominator_reconciles"] and summary["all_expected_classifications_match"]
    assert summary["outcome_counts"]["local_processing_failure"] == 1
    assert summary["owner_committed_but_unacknowledged_count"] == 1
    assert summary["accounted_with_synthetic_transport_over_100ms_count"] >= 1
