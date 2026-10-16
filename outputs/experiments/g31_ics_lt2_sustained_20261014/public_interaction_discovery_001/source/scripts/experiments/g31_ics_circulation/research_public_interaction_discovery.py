"""Finite hypothetical protection-barrier discovery; pure projections only.

This separately declared domain changes real public edge length, never the
accepted stationary input guard. The inherited event engine has retrospective
conformance in its old domain, not a native error bound in this new domain.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import time

from . import public_native_preference_projection as engine
from . import public_native_preference_search as searcher

VERSION = 'public_interaction_discovery_v1'
ROOT = Path(__file__).resolve().parents[3]
JOBS = frozenset(('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker'))
METHODS = searcher.METHODS


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def parameters(stage):
    if stage not in ('discovery', 'validation'):
        raise ValueError('undeclared_stage')
    receiver = (2., 4.) if stage == 'discovery' else (2.5, 3.5)
    return [dict(case_id=f'{stage}_b{bi}_l{li}_x{xi}', stage=stage,
                 blocker_load=block, receiver_load=load, later_extra_travel=extra)
            for bi, block in enumerate((.2, 3.))
            for li, load in enumerate(receiver) for xi, extra in enumerate((.25, .5))]


def checked_case(case):
    if type(case) is not dict or not any(canonical(case) == canonical(c)
                                        for c in parameters('discovery') + parameters('validation')):
        raise ValueError('undeclared_or_mistyped_case')


def public_windows(case):
    checked_case(case)
    # These are the unchanged four public formulas from the earlier domain;
    # their values depend only on the already-declared blocker load.
    old = next(c for c in engine.contract.domain.cases()
               if c['blocker_load'] == case['blocker_load'] and c['receiver_load'] == 3.)
    return engine.contract.domain.domain(old)['public_derivation']


def actions(case):
    times = public_windows(case)['supply_windows']
    return {(i, w, r, l): dict(initial_action=initial, empty_departure=t,
                              return_delay=delay, later_action=later)
            for i, initial in enumerate(('native_default', 'prefer_2'))
            for w, t in enumerate(times) for r, delay in enumerate((0., .5))
            for l, later in enumerate(('native_default', 'prefer_8'))}


def bundle(case):
    checked_case(case)
    old = next(c for c in engine.contract.domain.cases()
               if c['blocker_load'] == case['blocker_load'] and c['receiver_load'] == 3.)
    data = engine.contract.domain.make_bundle(old)
    # Only public static fields are retained. In particular the historical
    # 9x9 preprocessing matrix cannot leak into this ten-node hypothetical.
    static = engine.contract.supported_contract()
    static.pop('native_semantics')
    static['edge_records'] = [list(e) for e in static['edge_records']]
    static['scope'] = 'HYPOTHETICAL_PUBLIC_INTERACTION_3TRAY_5JOB_V1'
    edge = next(e for e in static['edge_records'] if tuple(e[:2]) == (7, 8))
    edge[2] = edge[2] + case['later_extra_travel'] * edge[3]
    data['contract'] = static
    data['jobs']['receiver']['load_seconds'] = case['receiver_load']
    data['scope'] = VERSION
    data['case'] = copy.deepcopy(case)
    data['online_information_delivered'] = False
    data['assumptions'] = [
        'Hypothetical complete finite initial state, not authenticated source captures.',
        'Future planning exchanges assume normal delivery and admissible local captures; actual readiness remains unknown.',
        'Changed receiver load and edge7to8 length require new native conformance before execution claims.',
        'Same five jobs, three trays, capacities, FIFO, ownership and protocol in every action of one case.']
    return data


def predict(case, supplied_bundle, action):
    """Accept exactly this new template, not caller assertion of old authority."""
    try:
        expected = bundle(case)
        if canonical(supplied_bundle) != canonical(expected):
            return {'status': 'unknown_changed_hypothetical_contract', 'completion': {}}
        if not any(canonical(action) == canonical(a) for a in actions(case).values()):
            return {'status': 'unknown_undeclared_action', 'completion': {}}
        result = engine.Projection(copy.deepcopy(supplied_bundle), copy.deepcopy(action)).run()
        result.update(discovery_version=VERSION, hypothetical_new_contract=True,
                      native_execution_certified=False, native_protection_certified=False,
                      online_information_delivered=False)
        return result
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return {'status': 'unknown_projection_exception', 'completion': {},
                'exception': type(exc).__name__ + ':' + str(exc)}


def physical_evidence(prediction, action):
    """Model trace checks only; never promote them to actual native events."""
    complete = prediction.get('completion', {})
    if (prediction.get('status') != 'conditional_prediction' or set(complete) != JOBS
            or any(type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= 40.
                   for t in complete.values())):
        return {'status': 'unknown_incomplete_prediction'}
    events = prediction.get('physical_projection', [])
    edges = [r for r in events if r.get('event') == 'EDGE_ENTER']
    commands = prediction.get('projected_commands', [])
    def one_edge(job, source):
        found = [e for e in edges if e.get('tray') == 'L' and e.get('job') == job and e.get('source') == source]
        return found[0] if len(found) == 1 else None
    initial = one_edge('loaded', 0)
    later = one_edge('reuse1', 7)
    second = one_edge('reuse2', 7)
    expected = [('reuse2', 7, 3)]
    if action['initial_action'] == 'prefer_2': expected.append(('loaded', 0, 2))
    if action['later_action'] == 'prefer_8': expected.append(('reuse1', 7, 8))
    identities = [(c.get('job'), c.get('from'), c.get('next')) for c in commands]
    commands_ok = len(identities) == len(expected) and sorted(identities) == sorted(expected) and all(
        c.get('status') == 'updated' and c.get('reserves_receiving_capacity') is False
        and type(c.get('ack_delivered_at')) in (int, float) and c['ack_delivered_at'] <= 40.
        for c in commands)
    received = [e for e in events if e.get('event') == 'EMPTY_RECEIVED' and e.get('tray') == 'L' and e.get('node') == 7]
    loads = [e for e in events if e.get('event') == 'LOAD_START' and e.get('tray') == 'L'
             and e.get('job') in ('reuse1', 'reuse2')]
    chain = (len(received) == len(loads) == 2 and [r['job'] for r in loads] == ['reuse1', 'reuse2']
             and initial is not None and later is not None and second is not None
             and complete['loaded'] < received[0]['at'] <= loads[0]['at'] < later['at']
             and complete['reuse1'] < received[1]['at'] <= loads[1]['at'] < second['at'])
    selected = (commands_ok and initial is not None and later is not None and second is not None
                and initial['target'] in ((2,) if action['initial_action'] == 'prefer_2' else (1, 2))
                and later['target'] in ((8,) if action['later_action'] == 'prefer_8' else (3, 8))
                and second['target'] == 3)
    return {'status': 'conditional_projected_actions_and_chain' if selected and chain else 'unknown_projected_action_or_chain',
            'commands_updated': commands_ok, 'selected_projected_edges': selected, 'two_reuses_of_same_L': chain,
            'initial_edge': initial, 'first_reuse_edge': later, 'second_reuse_edge': second,
            'returns': received, 'reloads': loads,
            'receiver_shared_edges': [e for e in edges if e.get('tray') == 'E' and e.get('source') in (1, 3)],
            'native_execution_certified': False}


def known(row):
    prediction = row.get('prediction', {})
    return (row.get('evidence', {}).get('status') == 'conditional_projected_actions_and_chain'
            and prediction.get('status') == 'conditional_prediction'
            and set(prediction.get('completion', {})) == JOBS
            and all(type(t) in (int, float) and math.isfinite(t) and 0 <= t <= 40.
                    for t in prediction['completion'].values()))


def protected(value, baseline):
    if not known(value) or not known(baseline): return None
    return all(value['prediction']['completion'][j] <= baseline['prediction']['completion'][j] for j in JOBS)


def cube(rows):
    if set(rows) != {(0, 0), (1, 0), (0, 1), (1, 1)} or not all(known(r) for r in rows.values()):
        return {'status': 'unknown_incomplete_cube', 'barrier': None, 'projected_chain_candidate': None}
    baseline = rows[0, 0]
    values = {k: r['prediction']['completion'] for k, r in rows.items()}
    guard = {k: protected(r, baseline) for k, r in rows.items()}
    gain = sum(values[0, 0].values()) - sum(values[1, 1].values())
    barrier = guard[1, 0] is False and guard[0, 1] is False and guard[1, 1] is True and gain > 0.
    a, c, d = (rows[k]['evidence'] for k in ((0, 0), (1, 0), (1, 1)))
    edge_changes = (a['initial_edge']['target'] != c['initial_edge']['target']
                    and c['first_reuse_edge']['target'] != d['first_reuse_edge']['target'])
    # Necessary projected chain facts, not a sufficiency theorem about native
    # dispatch or an authentication of future owner observations.
    chain = (barrier and edge_changes and values[1, 1]['loaded'] < values[0, 0]['loaded']
             and d['returns'][0]['at'] < a['returns'][0]['at']
             and values[1, 1]['receiver'] < values[1, 0]['receiver'])
    return {'status': 'complete_conditional_cube', 'barrier': barrier,
        'projected_chain_candidate': chain, 'both_route_edges_change': edge_changes, 'pair_gain': gain,
        'strict_protection': {str(k): v for k, v in guard.items()},
        'regressed_jobs': {str(k): [j for j in sorted(JOBS) if values[k][j] > values[0, 0][j]] for k in values},
        'mixed_difference_by_job': {j: values[1, 1][j] - values[1, 0][j] - values[0, 1][j] + values[0, 0][j] for j in sorted(JOBS)},
        'native_protection_certified': False}


def assess(case, cells):
    domain = actions(case)
    rows = {tuple(row['key']): row for row in cells}
    if len(cells) != len(domain) or set(rows) != set(domain) or any(canonical(rows[k]['action']) != canonical(domain[k]) for k in domain):
        return {'status': 'unknown_incomplete_or_misbound_factorial'}
    if any(canonical(row['evidence']) != canonical(physical_evidence(row['prediction'], row['action'])) for row in cells):
        return {'status': 'unknown_misbound_projected_evidence'}
    def compact(action):
        key = next(k for k, a in domain.items() if a == action)
        row = rows[key]
        if not known(row): return {'status': 'unknown_projected_action_or_chain', 'completion': {}}
        p = row['prediction']
        return {k: copy.deepcopy(p[k]) for k in ('status', 'completion', 'completion_sum')}
    methods = {name: searcher.search(domain, (0, 0, 0, 0), compact, method=name, budget=32) for name in METHODS}
    cubes = []
    for w in range(4):
        for r in range(2):
            value = cube({(i, l): rows[i, w, r, l] for i, l in itertools.product(range(2), repeat=2)})
            cubes.append({'window_index': w, 'return_index': r, **value})
    fixed = [rows[k] for k in domain if k[0] == 0]
    fixed_complete = all(known(row) for row in fixed) and known(rows[0, 0, 0, 0])
    fixed_eligible = [row for row in fixed if fixed_complete and protected(row, rows[0, 0, 0, 0]) is True]
    best = min(fixed_eligible, key=lambda row: (row['prediction']['completion_sum'], row['key']), default=None)
    # All methods use the same exact immutable public projection table, with
    # independent per-method evaluated-key caches. Native output is never used.
    return {'status': 'complete_declared_factorial', 'cell_count': 32,
        'known_projected_actions': sum(known(r) for r in rows.values()),
        'unknown_projected_actions': sum(not known(r) for r in rows.values()),
        'methods': methods, 'cubes': cubes,
        'fixed_initial_reference': {'complete': fixed_complete, 'denominator': 16,
            'best_protected_key': best['key'] if best else None,
            'completion': best['prediction']['completion'] if best else None},
        'protection_is_model_point_estimate_only': True, 'native_calls': 0}


def sources():
    names = set()
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if not path: continue
        path = Path(path).resolve()
        if path.suffix == '.py' and path.is_relative_to(ROOT): names.add(path)
    names.add(Path(__file__).resolve())
    return {str(path): sha(path) for path in sorted(names)}


def protocol():
    cases = parameters('discovery') + parameters('validation')
    return {'schema': 'g31.public_interaction_discovery.v1', 'version': VERSION,
        'cases': [{**case, 'bundle_sha256': hashlib.sha256(canonical(bundle(case)).encode()).hexdigest(),
                   'windows': public_windows(case), 'actions': [{'key': list(k), 'action': a} for k, a in actions(case).items()]}
                  for case in cases],
        'current_execution_stage': 'discovery_only', 'discovery_denominator': 256,
        'validation_denominator_reserved_unexecuted': 256, 'native_branch_budget': 0,
        'event_budget_per_prediction': 20000, 'horizon': 40., 'method_evaluation_budget': 32,
        'parameter_derivation': {'blocker_load': '.2/3 unchanged prior negative/occupied controls',
            'receiver_load_discovery': 'return edge6to7 travel2 and twice2',
            'later_extra_travel': 'entry headway.5/2 or.5; edge7to8 length=1.5+extra*speed1',
            'receiver_load_validation': 'returntravel+headway=2.5 and twice returntravel-headway=3.5'},
        'invariants': 'same full5jobs/3trays, capacity/FIFO/ownership/protocol and input within every32-action case; unchanged existing studies',
        'primary_criterion': 'At each same Ewindow/returndelay cube, both single route-coordinate changes strictly regress at least one job versus00, while pair all5<=00 and completion-sum gain>0.',
        'chain_criterion': 'Additionally projected initial and later edges both change, initial loaded completion and first L receipt at7 advance, and pair receiver completion improves versus initial-only; two sameL returns/reloads must exist.',
        'method_criterion': 'Compare strict/plateau coordinate, up-to-two-coordinate repair and exhaustive32 with same facts/action/budget; cube barrier alone is not solver necessity.',
        'fixed_reference': 'All16 native_default initial choices including all4Ewindows, bothreturns and bothlater choices; unknown if any projected action is not known.',
        'unknowns': 'All256 rows predeclared. Exceptions, missing/unfinished predictions and unexecuted/rejected modeled preferences remain unknown in comparisons.',
        'validation_policy': 'Do not evaluate reserved validation contexts before discovery report and method/parameters are frozen. Validation is independent of discovery outcomes but still the same unvalidated model, not native evidence.',
        'model_boundary': 'New hypothetical template equality is checked. Direct event-engine use does not extend old captured-input guards or certify native delivery, permissions, protection or100ms.',
        'costs': 'Record all case/row and total pure wall times. All guards/preparation charged; reused model-output table only for offline method comparison, no native outcomes.',
        'selection_rule': 'Retain every discovery result including zero candidates. Any future nominated candidate must state all discovery denominator and the ordinary methods outcomes.'}


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    plan = protocol()  # construct every input before binding import closure
    pins = sources(); archive = output / 'source'; archive.mkdir()
    for name in pins:
        relative = Path(name).relative_to(ROOT)
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(Path(name).read_bytes())
    for case in parameters('discovery') + parameters('validation'):
        write(output / (case['case_id'] + '.input.json'), bundle(case))
    write(output / 'preregistered_protocol.json', {**plan, 'source_sha256': pins})
    write(output / 'ledger.json', {case['case_id'] + '/' + '_'.join(map(str, k)):
        {'case': case, 'key': list(k), 'action': a, 'status': 'unknown_unexecuted'}
        for case in parameters('discovery') + parameters('validation') for k, a in actions(case).items()})


def run_discovery(output):
    started = time.perf_counter()
    plan_path = output / 'preregistered_protocol.json'
    plan = json.loads(plan_path.read_text()); plan_hash = sha(plan_path)
    pins = plan.pop('source_sha256')
    if canonical(plan) != canonical(protocol()): raise ValueError('changed_preregistered_protocol')
    if pins != sources(): raise ValueError('changed_source_closure')
    for name, digest in pins.items():
        if sha(output / 'source' / Path(name).relative_to(ROOT)) != digest: raise ValueError('changed_archive')
    ledger_path = output / 'ledger.json'; ledger = json.loads(ledger_path.read_text())
    if len(ledger) != 512 or any(row['status'] != 'unknown_unexecuted' for row in ledger.values()):
        raise ValueError('already_executed_or_incomplete_denominator')
    reports = []
    for case in parameters('discovery'):
        case_start = time.perf_counter(); data_path = output / (case['case_id'] + '.input.json')
        data = json.loads(data_path.read_text())
        if canonical(data) != canonical(bundle(case)): raise ValueError('changed_case_input')
        cells = []
        for key, action in actions(case).items():
            before = time.perf_counter()
            try:
                prediction = predict(case, data, action)
                evidence = physical_evidence(prediction, action)
            except Exception as exc:
                prediction = {'status': 'unknown_unexpected_projection_error', 'completion': {},
                              'exception': type(exc).__name__ + ':' + str(exc)}
                evidence = physical_evidence(prediction, action)
            row = {'key': list(key), 'action': action, 'prediction': prediction, 'evidence': evidence,
                   'wall_seconds': time.perf_counter() - before}
            cells.append(row)
            ledger[case['case_id'] + '/' + '_'.join(map(str, key))].update(
                status=evidence['status'], prediction_status=prediction['status'])
        report = {'case': case, 'input_sha256': sha(data_path), 'cells': cells,
                  'assessment': assess(case, cells), 'wall_seconds': time.perf_counter() - case_start}
        raw = output / (case['case_id'] + '.json.gz')
        raw.write_bytes(gzip.compress(json.dumps(report, allow_nan=False).encode(), compresslevel=1, mtime=0))
        reports.append({'case': case, 'raw': str(raw.resolve()), 'sha256': sha(raw),
                        'assessment': report['assessment'], 'wall_seconds': report['wall_seconds']})
        write(ledger_path, ledger)
    drift = [name for name, digest in pins.items() if sha(name) != digest]
    if sha(plan_path) != plan_hash: drift.append(str(plan_path))
    write(output / 'receipt.json', {'status': 'completed_pure_discovery' if not drift else 'invalid_source_drift',
        'schema': 'g31.public_interaction_discovery.receipt.v1', 'preregistered_protocol_sha256': plan_hash,
        'source_changed': drift, 'discovery_cells': 256, 'validation_unexecuted_cells': 256,
        'native_calls': 0, 'wall_seconds': time.perf_counter() - started, 'reports': reports,
        'limits': ['All evidence is hypothetical conditional projection in a new contract.',
                   'No native or online validation; no certified per-job protection or100ms.']})
    if drift: raise ValueError('source_drift')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true'); group.add_argument('--run-discovery', action='store_true')
    args = parser.parse_args()
    if args.prepare: prepare(args.output)
    else: run_discovery(args.output)


if __name__ == '__main__': main()
