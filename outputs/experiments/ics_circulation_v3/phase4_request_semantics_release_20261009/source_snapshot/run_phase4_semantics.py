"""Small explicit request/forecast diagnostics; not production SLA evidence."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil

from .experiment_protocol import create_output_directory
from .model import Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from .request_service import AttemptFault, ResourceOwner, RouteRequest, RoutingRequestService, TransportScript
from .runtime import ExecutionValidator, Simulation
from .prebalance import known_supply, conditional_supply
from .runtime import actual_action_key, invalidate_conditional_forecasts


def future_route(*, authorized=True, protected=False):
    nodes = {n: Node(n, 'z', 'r', capacity=4) for n in ('S', 'U', 'V', 'G')}
    edges = [Edge('SU', 'S', 'U', 1), Edge('UG', 'U', 'G', 1),
             Edge('SV', 'S', 'V', 3), Edge('VG', 'V', 'G', 3)]
    state = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                     {'t': Tray('t', 'S', 'loaded', 'b')},
                     {'b': Bag('b', 'S', 'G', 0, 40, protected=protected)},
                     replaceable_trays=('t',) if authorized else ())
    old = RouteCandidate('old', 'b', 't', (Leg('SV', 5, 8), Leg('VG', 8, 11)),
                         12, 12, 0, 'old', True, 'G')
    verdict = ExecutionValidator().commit(state, old)
    if not verdict.accepted:
        raise ValueError(f'fixture_setup_rejected:{verdict.reason}')
    return state


def run(output):
    output = create_output_directory(output)
    source = Path(__file__).parent
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.glob('*.py'))}
    snapshot_directory = output / 'source_snapshot'
    snapshot_directory.mkdir()
    for name in hashes:
        shutil.copyfile(source / name, snapshot_directory / name)
    rows = []
    definitions = [('explicit_optimization', True, False, 'update_suffix'),
                   ('owner_permission_absent', False, False, 'update_suffix'),
                   ('protected_commitment', True, True, 'update_suffix'),
                   ('keep_valid', True, False, 'keep_valid'),
                   ('new_rejects_existing', True, False, 'new_route'),
                   ('closed_future_edge', True, False, 'update_suffix'),
                   ('inflight_long_edge', True, False, 'update_suffix'),
                   ('lost_update_ack', True, False, 'update_suffix')]
    for name, authorized, protected, intent in definitions:
        state = future_route(authorized=authorized, protected=protected)
        if name == 'closed_future_edge':
            state.network.edges['SV'] = replace(state.network.edges['SV'], capacity=0)
            state.version += 1
        if name == 'inflight_long_edge':
            state = Simulation(state, route_mode='whole_route', reactive_empty_dispatch=False).advance(6).final_snapshot
            state.network.edges['VU'] = Edge('VU', 'V', 'U', 1)
            state.version += 1
        owner = ResourceOwner(state)
        request = RouteRequest(name, 'b', 't', 'whole_route', max_attempts=1,
                               intent=intent, trigger_reason=name)
        transport = TransportScript((AttemptFault(lose_acknowledgement=True),)) if name == 'lost_update_ack' else TransportScript()
        before = owner.snapshot()
        result = RoutingRequestService(owner).handle(request, transport)
        after = owner.snapshot()
        row = {'case': name, 'request': asdict(request), 'before': asdict(before),
               'result': asdict(result), 'after': asdict(after), 'state_unchanged': before == after}
        if name == 'lost_update_ack':
            recovered = RoutingRequestService(owner).handle(request)
            row['recovery'] = asdict(recovered)
            row['recovery_did_not_recommit'] = owner.snapshot() == after
        rows.append(row)
    prediction = future_route()
    prediction.plans.clear()
    prediction.reservations = ()
    prediction.network.edges['UV'] = Edge('UV', 'U', 'V', 2)
    short = RouteCandidate('short', 'b', 't', (Leg('SU', 0, 1), Leg('UG', 1, 2)),
                           3, 3, prediction.version, 'short', True, 'G')
    detour = replace(short, candidate_id='detour', legs=(Leg('SU', 0, 1), Leg('UV', 1, 3), Leg('VG', 3, 6)),
                     unload_complete=7, usable_at=7, is_baseline=False)
    before_keys = [actual_action_key(prediction, item) for item in (short, detour)]
    copies = [prediction.clone(), prediction.clone()]
    for state, candidate in zip(copies, (short, detour)):
        verdict = ExecutionValidator().commit(state, candidate, route_mode='next_edge')
        if not verdict.accepted:
            raise ValueError(f'prediction_probe_setup_rejected:{verdict.reason}')
    projection = {'full_witnesses': [asdict(short), asdict(detour)],
                  'same_committed_physical_legs': copies[0].plans['t'].legs == copies[1].plans['t'].legs,
                  'different_retained_intervention_keys': before_keys[0] != before_keys[1],
                  'actual_action_keys': before_keys,
                  'firm_supply': [[asdict(item) for item in known_supply(state)] for state in copies],
                  'conditional_supply': [[asdict(item) for item in conditional_supply(state)] for state in copies]}
    invalidate_conditional_forecasts(copies[0], 'observed_future_path_delay')
    projection['after_fault_conditional_supply'] = [asdict(item) for item in conditional_supply(copies[0])]
    projection['forecast_revision_chain_after_fault'] = [asdict(item) for item in copies[0].forecast_history] + [asdict(copies[0].conditional_forecasts['t'])]
    checks = {'explicit_update_replaces_valid_old_route': rows[0]['result']['status'] == 'updated_route_success',
              'permission_refusal_is_atomic': rows[1]['state_unchanged'],
              'protected_commitment_unchanged': rows[2]['state_unchanged'],
              'keep_valid_does_not_optimize': rows[3]['state_unchanged'],
              'new_intent_does_not_replace': rows[4]['state_unchanged'],
              'closed_future_edge_bypassed': rows[5]['result']['status'] == 'updated_route_success',
              'entered_long_leg_unchanged': rows[6]['before']['plans']['t']['legs'][0] == rows[6]['after']['plans']['t']['legs'][0],
              'lost_ack_recovery_no_second_commit': rows[7]['recovery_did_not_recommit'],
              'prefix_forecasts_separate_from_firm_supply': not any(projection['firm_supply']) and all(projection['conditional_supply']),
              'invalid_prediction_no_longer_offered': not projection['after_fault_conditional_supply']}
    summary = {'scope': 'Eight predeclared deterministic semantic probes and one conditional-interface example, not a deployment distribution',
               'request_count': len(rows), 'status_counts': {key: sum(r['result']['status'] == key for r in rows)
                                                           for key in sorted({r['result']['status'] for r in rows})},
               'checks': checks, 'all_checks_passed': all(checks.values()),
               'source_sha256': hashes, 'source_unchanged_after': hashes == {
                   p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.glob('*.py'))},
               'limitations': ['Single authoritative snapshot; no multi-owner protocol or shared message/physical clock.',
                              'Local timings include instrumentation and are not an online deadline claim.',
                              'Only explicitly authorized loaded nonprotected suffixes can change.']}
    (output / 'requests.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in rows), encoding='utf-8')
    (output / 'conditional_prediction.json').write_text(json.dumps(projection, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    raise SystemExit(0 if result['all_checks_passed'] and result['source_unchanged_after'] else 1)
