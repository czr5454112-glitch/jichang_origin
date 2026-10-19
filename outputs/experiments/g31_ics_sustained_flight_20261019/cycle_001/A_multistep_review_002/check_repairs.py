"""Read-only targeted regression of independently reported learning issues."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_multistep_learning as learn


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_rejection(function, text):
    try:
        function()
    except ValueError as error:
        assert text in str(error), str(error)
        return str(error)
    raise AssertionError('accepted counterexample: ' + text)


def transition(source, identity, successor, reward, terminal):
    return {'source': {'sha256': source}, 'decision_id': identity,
        'next_decision_id': successor, 'owner': 'B', 'peer_policy_id': 'fixed-A',
        'parent_group': 'same_parent', 'split': 'train', 'training_eligible': True,
        'terminated': terminal, 'truncated': False, 'gamma': 1.,
        'reward': {'value': reward}, 'observation': {'fixture_source': source},
        'action': {'fixture': 'synthetic algebra only, no native authority'}}


def main():
    source_path = Path(learn.__file__)
    source_sha = sha(source_path)
    raw_path = OUT.parent / 'A1_three_baseline_001/raw.json.gz'
    original_sha = sha(raw_path)
    raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    # Mutate an in-memory copy only. This does not pass native-origin verification.
    decision = next(d for d in raw['repeated_decisions'] if d['selected_action_id'] == 'prefer_3')
    decision['candidate_mask'][0]['semantic']['destination'] = 8
    origin = {'raw_content_sha256': learn.digest(raw), 'sha256': original_sha,
              'path': str(raw_path), 'native_origin_verified': False}
    exported = learn.export_episode(raw, origin=origin, parent_group='three_reuse_blocker_11_1',
        split='train', peer_policy_id='fixed_original_A_repeated_returns_v1')
    row = next(r for r in exported['transitions'] if r['decision_id'] == decision['decision_id'])
    assert row['training_eligible'] is False
    assert 'semantic_route_destination' in row['censor_reason']
    assert row['action']['destination'] == 8 and row['effect']['edge']['to'] == 3
    a1 = transition('source_A', 'first', 'second', -1., False)
    a2 = transition('source_A', 'second', None, -2., True)
    b1 = transition('source_B', 'first', 'second', -10., False)
    b2 = transition('source_B', 'second', None, -20., True)
    labels = learn.monte_carlo_labels([a1, a2, b1, b2])
    returns = [r['target_value'] for r in labels]
    assert returns == [-3., -2., -30., -20.], returns
    missing = expected_rejection(lambda: learn.monte_carlo_labels([a1, b2]), 'missing_return_successor')
    duplicate = expected_rejection(lambda: learn.monte_carlo_labels([a1, a2, copy.deepcopy(a2)]),
        'duplicate_decision_in_same_episode')
    wrong_owner = copy.deepcopy(a2)
    wrong_owner['owner'] = 'A'
    owner_error = expected_rejection(lambda: learn.monte_carlo_labels([a1, wrong_owner]), 'cross_owner_return_chain')
    assert sha(raw_path) == original_sha
    assert sha(source_path) == source_sha, 'reviewed source changed during test'
    report = {'schema': 'g31.independent_multistep_repair_checks.v1', 'status': 'passed',
        'source': {'path': str(source_path), 'sha256': source_sha},
        'native_raw': {'path': str(raw_path), 'sha256': original_sha},
        'semantic_mismatch': {'training_eligible': row['training_eligible'],
            'action_destination': row['action']['destination'], 'physical_edge_to': row['effect']['edge']['to'],
            'censor_reason': row['censor_reason']},
        'same_decision_ids_distinct_sources_returns': returns,
        'missing_same_source_successor': missing, 'duplicate_same_source_id': duplicate,
        'wrong_owner_successor': owner_error,
        'native_started': False, 'training_started': False, 'original_evidence_mutated': False,
        'scope': 'Targeted regression only; not full learning-gate or mechanism certification.'}
    with (OUT / 'report.json').open('x', encoding='utf8') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
