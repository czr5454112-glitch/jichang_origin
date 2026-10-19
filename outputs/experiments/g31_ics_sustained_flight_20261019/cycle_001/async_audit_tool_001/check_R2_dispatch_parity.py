"""Offline AST and byte-exact dispatch trace checks. No native binary/session.

Saved legal public inputs feed a stub returning only pending submission replies.
This tests Python data/call equivalence, never physical execution/authority.
"""
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_repeated_native as native


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def structure(run):
    plan = json.loads((run/'plan.json').read_text())
    source = next(key for key in plan['source_archive'] if key.endswith('foundation_repeated_native.py'))
    old = ast.parse((run/plan['source_archive'][source]).read_text())
    new = ast.parse(Path(native.__file__).read_text())
    before = next(n for n in old.body if isinstance(n, ast.ClassDef) and n.name == 'OwnerPolicy')
    after = next(n for n in new.body if isinstance(n, ast.ClassDef) and n.name == 'OwnerPolicy')
    unchanged = []
    for method in before.body:
        if not isinstance(method, ast.FunctionDef): continue
        current = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == method.name)
        if method.name == 'decide_current_body':
            method.body = [n for n in method.body if not
                (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'before')
                and not isinstance(n, ast.Delete)]
            for node in ast.walk(method):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'route_tray':
                    node.func.attr = '_dispatch_current_route'
            assert ast.dump(method) == ast.dump(current), 'only discarded record removed and exact dispatch call redirected'
        else:
            assert ast.dump(method) == ast.dump(current), method.name
            unchanged.append(method.name)
    for name in ('observation', 'run_branch', 'actual_effects', 'protected', 'current_route_local_mask', 'choose_current_candidate'):
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(a) == ast.dump(b), name
    return {'unchanged_owner_methods': unchanged, 'default_route_method_exact': True,
        'current_full_guard_observation_mask_rank_require_current_and_final_record_preserved': True}


def parity(folder):
    raw = json.loads(gzip.decompress((folder/'raw.json.gz').read_bytes())); result = []
    for decision in raw['repeated_decisions']:
        if decision['current_admission']['execution_mode'] != 'protected_current': continue
        evidence = next(row['evidence'] for row in raw['repeated_attempts']['B'] if
            row['evidence']['collection']['request_id'] == decision['current_admission']['collection_request_id'])
        view = evidence['information']['raw_endpoints']['view']; tray = decision['opportunity']['target']
        causal = {'relation': 'current_guarded_result', 'predecessor_protocol_id': evidence['collection']['request_id'],
            'continuation_parent_roots': [evidence['collection']['root']]}
        def make():
            session = SimpleNamespace(physical_time=decision['selected_at'],
                protocol_planning_snapshots_v3=lambda owner: evidence['information']['raw_endpoints']['received'],
                submit_protocol_command=lambda request: {'status': 'pending', 'reason': 'command_enqueued'})
            policy = object.__new__(native.OwnerPolicy)
            policy.session, policy.client = session, native.bound.LocalTransport(session)
            policy.client.rows, policy.client.calls = copy.deepcopy((evidence['own_outbox'], evidence['own_calls']))
            current_root = next(r for r in raw['owner_activation_admissions'] if r['root_id'] == decision['current_admission']['owner_root'])
            policy.client.context = copy.deepcopy(current_root)
            policy.client.context['protocol_ids'] = [i for i in policy.client.context['protocol_ids'] if i in evidence['own_outbox']]
            policy.client.roots = [policy.client.context]
            policy.client.creations = {key: copy.deepcopy(raw['request_creations'][key]) for key in evidence['own_outbox']}
            policy.owner, policy.episode = 'B', decision['opportunity']['episode_id']
            policy.mode, policy.resident = raw['specification']['mode'], object() if raw['specification']['mode'] == 'async' else None
            policy._in_new_collection = True
            policy.ledger = SimpleNamespace(audit_copy=lambda: copy.deepcopy(evidence['retained']))
            policy.repeated_decisions = [{'fixture_preceding_record': 'retained'}]
            policy.choices = copy.deepcopy([r for r in raw['continuation']['route_choices'] if r['at'] < decision['selected_at']])
            policy.route_keys = {(r['job'], r['local_tray']['generation'], r['local_tray']['traversal_id']) for r in policy.choices}
            return policy
        def encode(policy):
            return json.dumps({'client': {name: getattr(policy.client, name) for name in
                ('calls', 'rows', 'creations', 'roots', 'ack_handling')}, 'choices': policy.choices,
                'route_keys': sorted(policy.route_keys), 'decisions': policy.repeated_decisions},
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        for destination in (None, 3, 8):
            old, new = make(), make(); prefix = len(old.repeated_decisions)
            old_id = old.route_tray(view, tray, destination, causal)
            del old.repeated_decisions[prefix:]
            new_id = new._dispatch_current_route(view, tray, destination, causal)
            assert old_id == new_id and encode(old) == encode(new)
            result.append({'decision_id': decision['decision_id'], 'destination': destination,
                'exact_identity_and_trace_bytes': True, 'trace_bytes': len(encode(new)),
                'trace_sha256': hashlib.sha256(encode(new)).hexdigest()})
    return {'raw': reference(folder/'raw.json.gz'), 'cases': result}


if __name__ == '__main__':
    cycle = ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
    output = Path(__file__).parent/'R2_dispatch_parity_001.json'; assert not output.exists()
    result = {'schema': 'g31.R2.discarded_observation_parity.v1', 'source': reference(native.__file__),
        'script': reference(__file__), 'structure': structure(cycle/'R1_guarded_v2_001'),
        'runs': [parity(cycle/name) for name in ('R1_guarded_v2_001', 'R1_async_v2_001')],
        'native_started': False, 'grant_native_authority': False, 'physical_outcome_validation_still_requires_new_native': True}
    output.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({'status': 'passed', 'byte_exact_dispatch_cases': sum(len(r['cases']) for r in result['runs']), 'report': reference(output)}))
