"""Independent storage counterexamples using hand-authored physical witnesses.

These tests deliberately do not import the author's fixtures or route generator.
The tiny graph is a research proxy, not a claim about the Nanning EBS hardware.
"""
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, InFlight, Leg, Network, Node, Reservation,
    RouteCandidate, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.storage_contracts import (
    StorageBag, StorageProgress, StorageSnapshot, StorageWaypointContract,
)
from scripts.experiments.ics_circulation_v3.runtime import (
    ExecutionValidator, Simulation, assert_invariants,
)
from scripts.experiments.ics_circulation_v3.prebalance import (
    conditional_supply, known_supply,
)
from scripts.experiments.ics_circulation_v3.request_service import (
    RouteRequest, summarize, validate_committed_full_route,
)


def fixture(*, release=6, arrival=0, now=0, storage_capacity=1,
            origin='A', protected=False, deadline=30, hold=2):
    graph = Network(
        {n: Node(n, 'zone', 'owner', storage_capacity if n == 'S' else 5)
         for n in ('A', 'S', 'D', 'P')},
        {e.edge_id: e for e in (Edge('AS', 'A', 'S', 2), Edge('SD', 'S', 'D', 2),
                               Edge('AD', 'A', 'D', 1), Edge('PS', 'P', 'S', 2),
                               Edge('SA', 'S', 'A', 2))})
    contract = StorageWaypointContract('S', release, 0)
    bag = StorageBag('b', origin, 'D', arrival, deadline, protected, storage=contract)
    state = StorageSnapshot(now, graph, {'t': Tray('t', origin, 'loaded', 'b')},
                            {'b': bag}, module=FixedLocalModule(unload_ticks=1,
                            hold_by_node={'D': hold}),
                            storage_progress={})
    return state


def route(state, legs=(('AS', 0, 2), ('SD', 6, 8)), *, tray='t', bag='b'):
    legs = tuple(Leg(*leg) for leg in legs)
    arrival = legs[-1].arrive if legs else state.now
    unload = arrival + state.module.unload_ticks
    return RouteCandidate('audit', bag, tray, legs, unload,
                          unload + state.module.hold_ticks('D'),
                          state.version, 'audit', True)


def start(state=None, *, mode='whole_route', legs=None):
    engine = Simulation(state or fixture(), route_mode=mode,
                        control_mode='external', reactive_empty_dispatch=False)
    visible = engine.observe()
    proposal = route(visible) if legs is None else route(visible, legs)
    verdict = engine.intervene(proposal)
    assert verdict.accepted, verdict.reason
    return engine


@pytest.mark.parametrize('mode', ['whole_route', 'next_edge'])
def test_mandatory_storage_cannot_be_skipped_at_any_commit_mode(mode):
    s = fixture()
    proposal = route(s, (('AD', 0, 1),))
    before = asdict(s)
    verdict = ExecutionValidator().commit(s, proposal, route_mode=mode)
    assert not verdict.accepted
    assert asdict(s) == before


@pytest.mark.parametrize('departure, accepted', [(5, False), (6, True), (7, True)])
def test_public_release_is_exact_half_open_departure_boundary(departure, accepted):
    s = fixture()
    proposal = route(s, (('AS', 0, 2), ('SD', departure, departure + 2)))
    assert ExecutionValidator().validate(s, proposal).accepted is accepted


def test_final_deadline_protection_applies_after_storage_and_unload():
    s = fixture(protected=True, deadline=8)
    verdict = ExecutionValidator().validate(s, route(s))
    assert not verdict.accepted
    s.bags['b'] = replace(s.bags['b'], deadline=9)
    assert ExecutionValidator().validate(s, route(s)).accepted


def test_whole_route_dwell_holds_same_bag_and_never_supplies_storage_empty():
    engine = start()
    assert known_supply(engine.state)[0].node == 'D'
    assert known_supply(engine.state)[0].at == 11
    engine.advance(2)
    progress = engine.state.storage_progress['b']
    assert (progress.arrived_at, progress.departed_at) == (2, None)
    assert engine.state.trays['t'].bag_id == 'b'
    assert engine.state.trays['t'].mode == 'loaded'
    assert engine.state.completed == {}
    engine.advance(5)
    assert engine.state.trays['t'].node == 'S'
    assert engine.state.trays['t'].bag_id == 'b'
    assert all(item.node != 'S' for item in known_supply(engine.state))
    engine.advance(6)
    assert engine.state.storage_progress['b'].departed_at == 6
    engine.advance(9)
    assert engine.state.completed == {'b': 9}
    assert engine.state.trays['t'].mode == 'holding'
    engine.advance(11)
    assert engine.state.trays['t'].mode == 'empty'
    assert set(engine.state.trays) == {'t'}


def test_next_edge_arrival_does_not_equal_final_service_or_supply():
    engine = start(mode='next_edge')
    assert not known_supply(engine.state)
    assert conditional_supply(engine.state)[0].node == 'D'
    engine.advance(2)
    assert engine.state.trays['t'].node == 'S'
    assert engine.state.trays['t'].bag_id == 'b'
    assert not engine.state.completed
    assert 't' not in engine.state.plans
    assert not known_supply(engine.state)
    assert engine.state.storage_progress['b'].arrived_at == 2
    visible = engine.observe()
    early = route(visible, (('SD', 2, 4),))
    assert not engine.intervene(early).accepted
    legal = route(engine.observe(), (('SD', 6, 8),))
    assert engine.intervene(legal).accepted
    engine.advance(11)
    assert engine.state.completed == {'b': 9}
    assert engine.state.storage_progress['b'].departed_at == 6


def test_same_tick_storage_ingress_and_departure_both_have_actual_milestones():
    engine = start(fixture(release=2), legs=(('AS', 0, 2), ('SD', 2, 4)))
    engine.advance(2)
    progress = engine.state.storage_progress['b']
    assert (progress.arrived_at, progress.departed_at) == (2, 2)
    assert engine.state.trays['t'].node is None
    engine.advance(7)
    assert engine.state.completed == {'b': 5}


def test_late_ingress_cannot_be_replaced_by_scheduled_release():
    engine = start(fixture(release=1), legs=(('AS', 0, 2), ('SD', 2, 4)))
    engine.advance(1)
    assert 'b' not in engine.state.storage_progress
    engine.advance(2)
    assert engine.state.storage_progress['b'].arrived_at == 2


@pytest.mark.parametrize('pause', [0, 1, 2, 5, 6, 8, 9])
def test_checkpoint_restores_real_storage_cursor_without_invented_history(pause):
    engine = start()
    engine.advance(pause)
    resumed = Simulation.from_checkpoint(engine.checkpoint())
    assert resumed.state.storage_progress == engine.state.storage_progress
    actual = engine.advance(12)
    replay = resumed.advance(12)
    assert actual == replay
    assert actual.final_snapshot.storage_progress['b'].arrived_at == 2
    assert actual.final_snapshot.storage_progress['b'].departed_at == 6


def test_old_entered_edge_ingress_is_observed_without_fabricating_departure():
    s = fixture(now=1)
    s.trays['t'] = Tray('t', None, 'in_transit', 'b')
    s.old_in_transit = (InFlight('t', 'AS', 0, 2),)
    engine = Simulation(s, control_mode='external', reactive_empty_dispatch=False)
    engine.advance(2)
    assert engine.state.storage_progress['b'].arrived_at == 2
    assert engine.state.storage_progress['b'].departed_at is None
    assert not known_supply(engine.state)
    assert not engine.state.completed


def test_storage_capacity_is_real_node_occupancy():
    s = fixture()
    s.trays['blocker'] = Tray('blocker', 'S')
    verdict = ExecutionValidator().validate(s, route(s))
    assert not verdict.accepted
    assert 'capacity' in verdict.reason


def test_future_storage_identity_and_publication_are_hidden_until_arrival():
    s = fixture(arrival=4)
    bag = s.bags.pop('b')
    s.storage_progress.clear()
    s.trays['t'] = Tray('t', 'A')
    engine = Simulation(s, [bag], control_mode='external')
    assert not engine.observe().bags
    assert not engine.observe().storage_progress
    engine.advance(3)
    assert 'b' not in engine.observe().bags
    engine.advance(4)
    observation = engine.observe()
    assert isinstance(observation.bags['b'], StorageBag)
    assert observation.bags['b'].storage.release_at == 6


def test_storage_contract_cannot_be_silently_supplied_to_plain_snapshot():
    s = fixture()
    plain = Snapshot(s.now, s.network, s.trays, s.bags, module=s.module)
    with pytest.raises((ValueError, AssertionError)):
        Simulation(plain)


def test_dependency_summary_binds_milestones_even_without_version_bump():
    s = fixture(now=2)
    before = summarize(s)
    s.storage_progress['b'] = StorageProgress('t', s.bags['b'].storage, arrived_at=2)
    assert summarize(s).resources_sha256 != before.resources_sha256


def test_storage_checkpoint_progress_is_detached_from_observation():
    engine = start()
    engine.advance(2)
    observation = engine.observe()
    observation.storage_progress.clear()
    assert engine.state.storage_progress['b'].arrived_at == 2


def test_illegal_preinstalled_old_route_is_not_a_valid_fallback():
    s = fixture()
    proposal = route(s, (('AD', 0, 1),))
    from scripts.experiments.ics_circulation_v3.runtime import candidate_reservations
    s.plans['t'] = proposal
    s.reservations = candidate_reservations(s, proposal)
    request = RouteRequest('fallback-audit', 'b', 't')
    assert not validate_committed_full_route(s, request).accepted


def test_replacement_planning_forecast_does_not_mutate_actual_ingress():
    s = fixture()
    s.replaceable_trays = ('t',)
    engine = start(s)
    engine.advance(1)
    validator = ExecutionValidator()
    context = validator.prepare_replacement(engine.state, 't')
    assert context.anchor_node == 'S' and context.anchor_time == 2
    assert 'b' not in engine.state.storage_progress
    assert 'b' not in context.planning_snapshot.storage_progress
    proposal = route(context.planning_snapshot, (('SD', 6, 8),))
    assert validator.replace_suffix(engine.state, context, proposal).accepted
    assert 'b' not in engine.state.storage_progress
    engine.advance(2)
    assert engine.state.storage_progress['b'].arrived_at == 2
    engine.advance(11)
    assert engine.state.completed == {'b': 9}


def test_private_replacement_view_cannot_be_committed_or_run_as_physics():
    s = fixture()
    s.replaceable_trays = ('t',)
    engine = start(s)
    engine.advance(1)
    context = ExecutionValidator().prepare_replacement(engine.state, 't')
    proposal = route(context.planning_snapshot, (('SD', 6, 8),))
    assert not ExecutionValidator().commit(context.planning_snapshot, proposal).accepted
    with pytest.raises((ValueError, AssertionError)):
        Simulation(context.planning_snapshot)


def test_mutated_storage_planning_projection_cannot_authorize_owner_replace():
    s = fixture()
    s.replaceable_trays = ('t',)
    engine = start(s)
    engine.advance(1)
    validator = ExecutionValidator()
    context = validator.prepare_replacement(engine.state, 't')
    context.planning_snapshot.projected_storage_progress['b'] = replace(
        context.planning_snapshot.projected_storage_progress['b'], departed_at=2)
    proposal = route(context.planning_snapshot, (('SD', 2, 4),))
    before = asdict(engine.state)
    assert not validator.replace_suffix(engine.state, context, proposal).accepted
    assert asdict(engine.state) == before


def test_origin_at_storage_requires_actual_observation_before_authorization():
    s = fixture(origin='S')
    proposal = route(s, (('SD', 6, 8),))
    assert not ExecutionValidator().validate(s, proposal).accepted
    engine = Simulation(s, control_mode='external')
    observation = engine.observe()
    assert observation.storage_progress['b'].arrived_at == 0
    assert engine.intervene(route(observation, (('SD', 6, 8),))).accepted


@pytest.mark.parametrize('consumer', ['partition', 'clock', 'joint', 'atomic', 'reactive'])
def test_unsupported_consumers_refuse_storage_initial_state_before_work(consumer):
    from scripts.experiments.ics_circulation_v3.partition_observation import observe_partition
    from scripts.experiments.ics_circulation_v3.distributed_clock import DistributedClock
    from scripts.experiments.ics_circulation_v3.joint_reference import JointDomain, reactive_reference, solve_joint
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    s = fixture()
    calls = {
        'partition': lambda: observe_partition(s, 'owner'),
        'clock': lambda: DistributedClock(s),
        'joint': lambda: solve_joint(s, domain=JointDomain(10)),
        'atomic': lambda: solve_atomic_joint(s, domain=AtomicJointDomain(10)),
        'reactive': lambda: reactive_reference(s, domain=JointDomain(10)),
    }
    before = asdict(s)
    with pytest.raises(ValueError, match='storage_contract_not_supported'):
        calls[consumer]()
    assert asdict(s) == before


@pytest.mark.parametrize('consumer', ['clock', 'joint', 'atomic', 'reactive'])
def test_unsupported_consumers_inspect_future_tape_without_silently_exhausting_it(consumer):
    from scripts.experiments.ics_circulation_v3.distributed_clock import DistributedClock
    from scripts.experiments.ics_circulation_v3.joint_reference import JointDomain, reactive_reference, solve_joint
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    source = fixture(arrival=4)
    bag = source.bags['b']
    s = Snapshot(0, source.network, {'t': Tray('t', 'A')}, {})
    tape = (item for item in (bag,))
    calls = {
        'clock': lambda: DistributedClock(s, tape),
        'joint': lambda: solve_joint(s, tape, domain=JointDomain(10)),
        'atomic': lambda: solve_atomic_joint(s, tape, domain=AtomicJointDomain(10)),
        'reactive': lambda: reactive_reference(s, tape, domain=JointDomain(10)),
    }
    with pytest.raises(ValueError, match='storage_contract_not_supported'):
        calls[consumer]()
    assert not s.bags and not s.plans


def test_joint_owner_admission_does_not_bypass_storage_validator():
    from scripts.experiments.ics_circulation_v3.joint_transactions import commit_joint
    s = fixture()
    before = asdict(s)
    assert not commit_joint(s, (route(s, (('AD', 0, 1),)),)).accepted
    assert asdict(s) == before
    assert commit_joint(s, (route(s),)).accepted


def test_unpublished_or_wrong_carrier_storage_contract_fails_closed():
    for updates in ({'published_at': 1}, {'carrier_policy': 'off_carrier'},
                    {'evidence_status': 'confirmed'}, {'release_at': True}):
        s = fixture()
        s.bags['b'] = replace(s.bags['b'], storage=replace(s.bags['b'].storage, **updates))
        with pytest.raises((ValueError, AssertionError)):
            Simulation(s)


def test_ordinary_models_keep_exact_legacy_serialization_shape():
    from dataclasses import fields
    assert tuple(f.name for f in fields(Bag)) == ('bag_id', 'origin', 'destination', 'arrival', 'deadline', 'protected')
    assert tuple(f.name for f in fields(Snapshot)) == (
        'now', 'network', 'trays', 'bags', 'reservations', 'version', 'old_in_transit',
        'module', 'plans', 'completed', 'load_times', 'empty_targets',
        'conditional_forecasts', 'forecast_history', 'replaceable_trays')


def test_full_storage_turnover_departure_and_other_ingress_share_one_tick():
    s = fixture()
    s.bags['b2'] = StorageBag('b2', 'P', 'D', 0, 30,
                             storage=StorageWaypointContract('S', 8, 0))
    s.trays['t2'] = Tray('t2', 'P', 'loaded', 'b2')
    engine = start(s)
    # Final reception remains unit capacity through the first tray's hold to
    # tick 11; the second reaches final exactly when that resource releases.
    second = route(engine.observe(), (('PS', 4, 6), ('SD', 9, 11)), tray='t2', bag='b2')
    assert engine.intervene(second).accepted
    engine.advance(6)
    assert engine.state.storage_progress['b'].departed_at == 6
    assert engine.state.storage_progress['b2'].arrived_at == 6
    assert engine.state.trays['t2'].node == 'S'
    engine.advance(14)
    assert engine.state.completed == {'b': 9, 'b2': 12}


def test_conditional_final_supply_remains_valid_during_storage_and_cannot_export_tray():
    engine = start(mode='next_edge')
    engine.advance(2)
    forecast = conditional_supply(engine.state)
    assert len(forecast) == 1 and forecast[0].node == 'D' and forecast[0].at == 11
    assert not known_supply(engine.state)
    engine.advance(5)
    assert conditional_supply(engine.state)[0].at == 11
    empty = RouteCandidate('empty', None, 't', (Leg('SA', 5, 7),), 7, 7,
                           engine.state.version, 'empty', destination_node='A')
    assert not ExecutionValidator().commit(engine.state, empty).accepted


def test_final_known_supply_checks_storage_plan_release_arithmetic():
    engine = start()
    engine.state.plans['t'] = replace(engine.state.plans['t'], usable_at=2)
    with pytest.raises(AssertionError):
        known_supply(engine.state)


def test_storage_generator_waits_upstream_for_real_storage_calendar():
    from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator
    from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
    s = fixture()
    s.trays['blocker'] = Tray('blocker', 'P')
    s.reservations = (Reservation('node:S', 2, 5, 'blocker'),)
    generator = StorageCandidateGenerator(CandidateGenerator(horizon=12, expansion_limit=2000))
    options = generator.generate(s, 'b', 't', 1)
    assert options
    assert options[0].legs == (Leg('AS', 3, 5), Leg('SD', 6, 8))
    assert not generator.last_diagnostics['earliest_arrival_certified']


def test_storage_generator_can_pass_final_node_before_mandatory_storage():
    from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator
    from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
    s = fixture()
    s.network = replace(s.network, edges={e.edge_id: e for e in (
        Edge('AD', 'A', 'D', 1), Edge('DS', 'D', 'S', 1), Edge('SD', 'S', 'D', 2))})
    generator = StorageCandidateGenerator(CandidateGenerator(horizon=12, expansion_limit=2000))
    options = generator.generate(s, 'b', 't', 1)
    assert options and [leg.edge_id for leg in options[0].legs] == ['AD', 'DS', 'SD']
    engine = start(s, legs=tuple((l.edge_id, l.depart, l.arrive) for l in options[0].legs))
    engine.advance(2)
    assert not engine.state.completed
    assert engine.state.storage_progress['b'].arrived_at == 2
    engine.advance(11)
    assert engine.state.completed == {'b': 9}


def test_preinstalled_disconnected_storage_plan_cannot_create_firm_supply():
    from scripts.experiments.ics_circulation_v3.runtime import candidate_reservations
    s = fixture()
    # This route starts at S although the actual tray is at A. Seeing an S
    # outgoing edge somewhere in a saved plan is not evidence of EBS ingress.
    bad = route(s, (('SD', 6, 8),))
    s.plans['t'] = bad
    s.reservations = candidate_reservations(s, bad)
    with pytest.raises(AssertionError):
        known_supply(s)


def test_preinstalled_past_legs_do_not_fabricate_storage_ingress_history():
    from scripts.experiments.ics_circulation_v3.runtime import candidate_reservations
    s = fixture(now=3)
    # AS is claimed to have ended at tick 2, yet this snapshot has no arrival
    # receipt and still places the carrier at A. It cannot be a live checkpoint.
    bad = route(s)
    s.plans['t'] = bad
    s.reservations = candidate_reservations(s, bad)
    with pytest.raises(AssertionError):
        known_supply(s)


def test_old_transit_zero_leg_final_service_cannot_publish_early_empty():
    s = fixture(now=7)
    s.trays['t'] = Tray('t', None, 'in_transit', 'b')
    s.storage_progress['b'] = StorageProgress('t', s.bags['b'].storage, 2, 6)
    s.old_in_transit = (InFlight('t', 'SD', 6, 8),)
    engine = Simulation(s, control_mode='external')
    engine.advance(8)
    assert engine.state.plans['t'].legs == ()
    assert known_supply(engine.state)[0].at == 11
    engine.state.plans['t'] = replace(engine.state.plans['t'], unload_complete=8, usable_at=8)
    with pytest.raises(AssertionError):
        known_supply(engine.state)


def test_preinstalled_plan_cannot_bypass_final_protected_deadline():
    from scripts.experiments.ics_circulation_v3.runtime import candidate_reservations
    s = fixture(protected=True, deadline=8)
    bad = route(s)
    assert not ExecutionValidator().validate(s, bad).accepted
    s.plans['t'] = bad
    s.reservations = candidate_reservations(s, bad)
    with pytest.raises(AssertionError):
        known_supply(s)


def test_preinstalled_plan_cannot_hide_wait_at_no_wait_node():
    from scripts.experiments.ics_circulation_v3.runtime import candidate_reservations
    s = fixture()
    s.network.nodes['P'] = replace(s.network.nodes['P'], can_wait=False)
    s.network.edges.pop('SD')
    s.network.edges.update({'SP': Edge('SP', 'S', 'P', 1), 'PD': Edge('PD', 'P', 'D', 1)})
    bad = route(s, (('AS', 0, 2), ('SP', 6, 7), ('PD', 9, 10)))
    assert not ExecutionValidator().validate(s, bad).accepted
    s.plans['t'] = bad
    s.reservations = candidate_reservations(s, bad)
    with pytest.raises(AssertionError):
        known_supply(s)


@pytest.mark.parametrize('initial_storage', [False, True])
def test_distributed_checkpoint_refuses_storage_before_restoring_protocol(initial_storage):
    from scripts.experiments.ics_circulation_v3.distributed_clock import DistributedCheckpoint, DistributedClock
    source = fixture(arrival=0 if initial_storage else 4)
    if initial_storage:
        base = Simulation(source, control_mode='external').checkpoint()
    else:
        plain = Snapshot(0, source.network, {'t': Tray('t', 'A')}, {})
        base = Simulation(plain, control_mode='external').checkpoint()
        base.pending_arrivals = {4: [source.bags['b']]}
    # Deliberately no protocol dictionary: storage must be rejected before any
    # unsupported coordinator fields or state are restored.
    checkpoint = DistributedCheckpoint(base, {})
    with pytest.raises(ValueError, match='storage_contract_not_supported'):
        DistributedClock.from_checkpoint(checkpoint)


def test_old_in_transit_final_destination_cannot_bypass_unvisited_storage():
    s = fixture()
    s.trays['t'] = Tray('t', None, 'in_transit', 'b')
    s.old_in_transit = (InFlight('t', 'AD', 0, 1),)
    # An already-entered ordinary destination trip cannot be promoted to a
    # legal storage business completion merely because its endpoint is D.
    with pytest.raises(AssertionError):
        known_supply(s)


def test_preinstalled_plan_at_storage_requires_same_real_ingress_as_new_commit():
    from scripts.experiments.ics_circulation_v3.runtime import candidate_reservations
    s = fixture(origin='S')
    bad = route(s, (('SD', 6, 8),))
    assert not ExecutionValidator().validate(s, bad).accepted
    s.plans['t'] = bad
    s.reservations = candidate_reservations(s, bad)
    with pytest.raises(AssertionError):
        known_supply(s)


def test_private_replacement_projection_cannot_be_restored_as_live_checkpoint():
    s = fixture()
    s.replaceable_trays = ('t',)
    engine = start(s)
    engine.advance(1)
    context = ExecutionValidator().prepare_replacement(engine.state, 't')
    checkpoint = engine.checkpoint()
    checkpoint.state = context.planning_snapshot
    checkpoint.phase = 'routes'
    with pytest.raises((AssertionError, ValueError), match='private_storage_planning'):
        Simulation.from_checkpoint(checkpoint)
