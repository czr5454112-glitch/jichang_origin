"""Selection-only addendum over immutable actual FQI checkpoints.

No fitting or native imports. The target is the optimal return on the observed,
legal development DAG, not the globally optimal value or a held-out estimate.
The amendment is explicitly made after inspecting development diagnostics.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
import time

SCHEMA = 'g31.foundation.fqi_checkpoint_selection.v1'
PLAN_SCHEMA = 'g31.foundation.fqi_selection_plan.v1'
ADDENDUM_SCHEMA = 'g31.foundation.fqi_selection_addendum.v1'
CRITERION = 'minimum_development_supported_empirical_optimal_mse_then_earliest_iteration'
OLD_CRITERION = 'minimum_development_behavior_return_mse_then_earliest_iteration'
TOKEN = 'g31_fqi_checkpoint_selection_v1'
FEATURE_SOURCE_SHA = '4b4ff7a0aa74c47302c0da9e0a67770af99c0239bb44a3120c09193c757abc9d'


def select_airport_paired_checkpoint(models, datasets):
    """New-schema entry for dev action regret; not the historical DAG MSE."""
    from .foundation_airport_pair_ranker import SCHEMA as PAIR_SCHEMA, select_on_dev
    require(models and all(model.get('schema') == PAIR_SCHEMA for model in models),
            'explicit_airport_paired_models')
    require(all(dataset['pair']['parent']['split'] == 'dev' for dataset in datasets),
            'airport_selection_development_only')
    result = select_on_dev(models, datasets)
    return dict(result, selection_entry_schema='g31.foundation.airport_paired_selection.v1',
        historical_small_domain_checkpoints_modified=False,
        historical_empirical_DAG_optimality_claimed=False)


def require(ok, reason):
    if not ok:
        raise ValueError('fqi_selection:' + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_number')
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path)}


def state_key(observation):
    # Exactly the frozen training support identity, not a learned-feature alias.
    return digest({k: v for k, v in observation.items() if k not in ('episode_id', 'decision_id', 'opportunity')})


def row_key(row):
    return row['source']['sha256'], row['decision_id']


def admissible(mask):
    require(type(mask) is list and len({c['action_id'] for c in mask}) == len(mask), 'unique_candidate_ids')
    require(all(type(c['enabled']) is bool for c in mask), 'boolean_enabled')
    result = {}
    for candidate in mask:
        if not candidate['enabled']:
            continue
        guard = candidate['guard_status']
        if guard == 'original_fixed_rule':
            passed = True
        else:
            delta = candidate.get('per_job_delta')
            passed = guard == 'passed' and isinstance(delta, dict) and bool(delta) and all(number(v) <= 0 for v in delta.values())
        if passed:
            # Action IDs may alias one semantic action; support uses semantics.
            result[digest(candidate['semantic'])] = candidate['semantic']
    return result


def supported_empirical_targets(rows, *, owner, peer_policy_id, gamma):
    """Pure deterministic, closed-DAG validation and exact supported optimal DP."""
    gamma = number(gamma)
    require(0 <= gamma <= 1 and bool(rows), 'gamma_and_nonempty')
    require(len({row_key(r) for r in rows}) == len(rows), 'duplicate_actual_decision')
    by_id = {row_key(r): r for r in rows}
    grouped = {}
    state_actions = {}
    for row in rows:
        require(row['split'] == 'development' and row['owner'] == owner
                and row['peer_policy_id'] == peer_policy_id, 'development_owner_peer_only')
        require(row['training_eligible'] is True and row['truncated'] is False
                and type(row['terminated']) is bool, 'closed_actual_transition_only')
        require(number(row['gamma']) == gamma, 'gamma_changed')
        obs = row['observation']; start = number(row['reward']['start']); end = number(row['reward']['end'])
        require(number(obs['at']) == start and 0 <= start < end, 'actual_reward_clock')
        action_key = digest(row['action']); state = state_key(obs)
        admissible(row['candidate_mask'])  # validate unique IDs before checking the selected alias
        require(any(c['action_id'] == row['selected_action_id'] and c['semantic'] == row['action']
                    and digest(c['semantic']) in admissible([c])
                    for c in row['candidate_mask']), 'chosen_not_legal_exact_alias')
        key = (state, action_key)
        grouped.setdefault(key, []).append(row)
        state_actions.setdefault(state, set()).add(action_key)
        number(row['reward']['value'])
        if row['terminated']:
            require(row['next_observation'] is None and row['next_decision_id'] is None
                    and not row['next_candidate_mask'], 'terminal_has_successor')
        else:
            next_key = (row['source']['sha256'], row['next_decision_id'])
            require(next_key in by_id, 'actual_successor_missing')
            nxt = by_id[next_key]
            require(nxt['observation'] == row['next_observation']
                    and number(nxt['reward']['start']) == end, 'actual_successor_not_bound')
            require(row['next_candidate_mask'] == nxt['candidate_mask'], 'actual_successor_candidate_mask_not_bound')
    graph = {}
    for key, group in grouped.items():
        signatures = set()
        for row in group:
            next_state = None if row['terminated'] else state_key(row['next_observation'])
            support = [] if row['terminated'] else sorted(set(admissible(row['next_candidate_mask']))
                                                          & state_actions.get(next_state, set()))
            require(row['terminated'] or bool(support), 'unsupported_successor')
            signatures.add((number(row['reward']['value']), row['terminated'], next_state, tuple(support),
                            number(row['reward']['start']), number(row['reward']['end'])))
        require(len(signatures) == 1, 'nondeterministic_state_action_reward_successor_or_support')
        reward, terminal, successor, support, start, end = next(iter(signatures))
        graph[key] = {'reward': reward, 'terminal': terminal, 'successor': successor,
                      'support': list(support), 'start': start, 'end': end,
                      'provenance': [{'source_sha256': r['source']['sha256'], 'decision_id': r['decision_id']} for r in group]}
    values = {}; visiting = set()
    def solve(key):
        if key in values:
            return values[key]
        require(key not in visiting, 'cyclic_observed_graph')
        require(key in graph, 'missing_graph_action')
        visiting.add(key); node = graph[key]
        continuation = 0. if node['terminal'] else max(solve((node['successor'], action)) for action in node['support'])
        values[key] = node['reward'] + gamma * continuation
        visiting.remove(key)
        return values[key]
    targets = []
    for row in rows:
        key = state_key(row['observation']), digest(row['action'])
        targets.append({'source_sha256': row['source']['sha256'], 'decision_id': row['decision_id'],
                        'state_sha256': key[0], 'semantic_sha256': key[1], 'target_value': solve(key)})
    nodes = [{'state_sha256': k[0], 'semantic_sha256': k[1], **v, 'supported_optimal_value': values[k]}
             for k, v in sorted(graph.items())]
    return {'schema': 'g31.foundation.supported_empirical_development_graph.v1',
            'gamma': gamma, 'owner': owner, 'peer_policy_id': peer_policy_id, 'targets': targets, 'nodes': nodes,
            'row_weighting': 'original_development_rows_equal', 'rows': len(rows), 'unique_state_actions': len(nodes),
            'deterministic': True, 'acyclic': True, 'closed': True, 'unobserved_actions_bootstrapped': False,
            'global_optimality_claim': False, 'heldout_estimate': False}


def feature_function(source_bytes):
    """Use only the exact audited public-feature source; omit numpy and fitting."""
    require(hashlib.sha256(source_bytes).hexdigest() == FEATURE_SOURCE_SHA, 'unapproved_feature_source')
    module = ast.parse(source_bytes.decode('utf8'))
    module.body = [n for n in module.body if not (isinstance(n, ast.Import) and any(a.name == 'numpy' for a in n.names))
                   and not (isinstance(n, ast.FunctionDef) and n.name in ('fit', 'predict'))]
    namespace = {'__name__': 'pinned_public_features_stdlib'}
    exec(compile(module, 'frozen_repeated_public_features', 'exec'), namespace)
    return namespace['features']


def forward(model, observation, action, feature_fn):
    require(model['schema'] == 'g31.foundation.repeated_action_value.v1'
            and model['native_execution_authority'] is False, 'model_schema_or_authority')
    require(model['model_sha256'] == digest({k: v for k, v in model.items() if k != 'model_sha256'}), 'model_content_hash')
    features = feature_fn(observation, action); names = model['feature_names']; parameters = model['parameters']
    require(sorted(features) == names and len(names) == 123, 'feature_names')
    require(len(parameters['center']) == len(parameters['scale']) == len(names), 'normalizer_shape')
    require(all(number(s) > 0 for s in parameters['scale']), 'positive_scale')
    x = [(number(features[n]) - number(c)) / number(s)
         for n, c, s in zip(names, parameters['center'], parameters['scale'], strict=True)]
    require(len(parameters['layers']) == 3, 'three_layers')
    for index, layer in enumerate(parameters['layers']):
        require(len(layer['weight']) == len(layer['bias']) == (64, 64, 1)[index], 'layer_shape')
        require(all(len(w) == len(x) for w in layer['weight']), 'weight_shape')
        x = [math.fsum(number(a) * b for a, b in zip(w, x, strict=True)) + number(bias)
             for w, bias in zip(layer['weight'], layer['bias'], strict=True)]
        if index < 2:
            x = list(map(math.tanh, x))
    require(number(parameters['target_scale']) > 0, 'positive_target_scale')
    return number(x[0] * parameters['target_scale'] + number(parameters['target_center']))


def choose(metrics, seeds, iterations):
    require(len(seeds) == len(set(seeds)) and iterations == list(range(max(iterations) + 1)), 'complete_seed_iteration_grid')
    require(len(metrics) == len(seeds) * len(iterations)
            and {(m['seed'], m['iteration']) for m in metrics} == {(s, i) for s in seeds for i in iterations},
            'missing_duplicate_or_extra_checkpoint')
    for metric in metrics:
        require(number(metric['development_supported_empirical_optimal_mse']) >= 0, 'nonnegative_mse')
    return [min((m for m in metrics if m['seed'] == seed),
                key=lambda m: (m['development_supported_empirical_optimal_mse'], m['iteration'])) for seed in seeds]


def archive_references(registration_path):
    """Frozen source order follows the launcher's persisted source_pins mapping."""
    registration_path = Path(registration_path)
    registration = read(registration_path)
    archives = {p: registration_path.parent / 'source' / (f'{i:04d}' + Path(p).suffix)
                for i, p in enumerate(registration['source_pins'])}
    require(all(sha(archives[p]) == expected for p, expected in registration['source_pins'].items()), 'historical_source_archive_changed')
    outer = read(registration_path.parent / 'receipt.json')
    require(outer['status'] == 'completed' and outer['source_changed'] == []
            and outer['process']['exitcode'] == 0
            and outer['process']['child_released_only_after_job_assignment'] is True, 'historical_outer_not_closed')
    return registration, outer, archives


def validate_addendum(addendum, contract, receipt_sha):
    require(addendum['schema'] == ADDENDUM_SCHEMA and addendum['criterion'] == CRITERION
            and addendum['prior_criterion'] == OLD_CRITERION, 'one_explicit_criterion_repair')
    require(addendum['development_already_inspected'] is True and addendum['formal_holdout_accessed'] is False
            and addendum['selection_only'] is True and addendum['fit_count'] == 0
            and addendum['native_branches'] == 0 and addendum['maximum_revisions'] == 1, 'selection_only_amendment_scope')
    require(addendum['training_seeds'] == contract['training_seeds']
            and addendum['allowed_iterations'] == list(range(contract['iterations'] + 1))
            and addendum['row_weighting'] == 'original_development_rows_equal', 'frozen_grid_and_weighting')
    require(addendum['collection_contract_sha256'] == digest(contract)
            and addendum['training_receipt_sha256'] == receipt_sha, 'addendum_original_binding')


def make_plan(training_directory, training_registration_path, addendum_path):
    """Prepare only; root registers the returned plan before running the CLI."""
    directory = Path(training_directory).resolve()
    # Authenticate the requested directory using registration metadata before
    # reading any result there, including when a caller accidentally names test.
    registration = read(training_registration_path)
    original_plan_path = registration['args'][registration['args'].index('--plan') + 1]
    original_output = registration['args'][registration['args'].index('--output') + 1]
    require(Path(original_output).resolve() == directory
            and Path(registration['assessment']['path']).resolve() == directory / 'receipt.json', 'training_attempt_directory_binding')
    receipt = read(directory / 'receipt.json'); training_plan = read(directory / 'preregistered_plan.json')
    contract = receipt['contract']; validate_addendum(read(addendum_path), contract, sha(directory / 'receipt.json'))
    require(contract['checkpoint_selection'] == OLD_CRITERION, 'unexpected_previous_criterion')
    allowed = {'train': set(contract['train_parent_groups']), 'development': set(contract['development_parent_groups'])}
    require(allowed['train'].isdisjoint(allowed['development'])
            and (allowed['train'] | allowed['development']).isdisjoint(contract['evaluation_plan']['held_out_parent_groups']), 'split_overlap')
    # Validate declared split/parent before following any collection path.
    require(all(e['split'] in allowed and e['parent_group'] in allowed[e['split']] for e in training_plan['episodes']), 'training_plan_contains_nonallowed_split')
    registration, outer, archives = archive_references(training_registration_path)
    require(outer['assessment'] == receipt, 'training_outer_receipt_binding')
    require(original_plan_path in archives and sha(archives[original_plan_path]) == sha(directory / 'preregistered_plan.json'),
            'training_plan_archive_binding')
    require(sha(training_plan['contract']['path']) == training_plan['contract']['sha256']
            and read(training_plan['contract']['path']) == contract, 'original_collection_contract_binding')
    require(all(registration['source_pins'].get(p) == expected for p, expected in training_plan['sources'].items()), 'training_source_binding')
    paths = [directory / n for n in ('receipt.json', 'preregistered_plan.json', 'transitions.json', 'training_gate.json',
                                      'paired_early_witnesses.json')]
    paths += [Path(addendum_path), Path(training_registration_path), Path(training_registration_path).parent / 'receipt.json',
              Path(training_plan['contract']['path']), *archives.values()]
    # Historical collection references are restricted to the declared six train/dev directories and their registrations.
    episode_dirs = {Path(e['directory']).resolve() for e in training_plan['episodes']}
    for reference in training_plan['references']:
        path = Path(reference['path']).resolve()
        if path.name == 'registration.json':
            reg, result, collection_archives = archive_references(path)
            declared_output = Path(reg['assessment']['path']).resolve().parent
            require(declared_output in episode_dirs, 'registration_outside_allowed_collection')
            paths += [path, path.parent / 'receipt.json', *collection_archives.values()]
        else:
            require(path.parent in episode_dirs, 'reference_outside_allowed_collection')
            paths.append(path)
        require(sha(path) == reference['sha256'], 'original_training_reference_changed')
    for item in receipt['history']:
        require(type(item['seed']) is int and item['seed'] in contract['training_seeds']
                and type(item['iteration']) is int and 0 <= item['iteration'] <= contract['iterations'], 'history_grid_identity')
        for kind, reference in item['saved_intermediate'].items():
            require(kind in ('checkpoint', 'targets') and Path(reference['path']).resolve()
                    == directory / 'iterations' / f"seed_{item['seed']}_iteration_{item['iteration']}_{kind}.json",
                    'history_artifact_outside_training_directory')
        paths += [Path(v['path']) for v in item['saved_intermediate'].values()]
    require(all(Path(m['checkpoint']['path']).resolve() == directory / f"checkpoint_seed_{m['seed']}.json"
                for m in receipt['models']), 'prior_selection_outside_training_directory')
    paths += [Path(m['checkpoint']['path']) for m in receipt['models']]
    feature_originals = [p for p in archives if Path(p).name == 'foundation_repeated_value.py']
    require(len(feature_originals) == 1 and registration['source_pins'][feature_originals[0]] == FEATURE_SOURCE_SHA, 'feature_archive_required')
    source_path = Path(__file__).resolve()
    return {'schema': PLAN_SCHEMA, 'criterion': CRITERION, 'training_directory': str(directory),
            'training_registration': str(Path(training_registration_path).resolve()),
            'addendum': str(Path(addendum_path).resolve()), 'feature_source': str(archives[feature_originals[0]].resolve()),
            'sources': {str(source_path): sha(source_path)},
            'references': [ref(p) for p in sorted(set(map(lambda p: p.resolve(), paths)), key=str)],
            'training_seeds': contract['training_seeds'], 'allowed_iterations': list(range(contract['iterations'] + 1)),
            'fit_count': 0, 'native_branches': 0, 'formal_holdout_accessed': False}


def verify_plan(plan):
    require(plan['schema'] == PLAN_SCHEMA and plan['criterion'] == CRITERION
            and plan['fit_count'] == 0 and plan['native_branches'] == 0
            and plan['formal_holdout_accessed'] is False, 'plan_scope')
    require(plan['sources'] == {str(Path(__file__).resolve()): sha(__file__)}, 'selector_source_changed')
    # Rebuild from named, explicitly allowed sources before touching arbitrary supplied reference paths.
    expected = make_plan(plan['training_directory'], plan['training_registration'], plan['addendum'])
    require(plan == expected, 'plan_references_or_source_changed')
    return expected


def select_existing(plan, output):
    started = time.monotonic(); verify_plan(plan)
    directory = Path(plan['training_directory']); receipt = read(directory / 'receipt.json'); contract = receipt['contract']
    episodes = read(directory / 'transitions.json'); gate = read(directory / 'training_gate.json')
    require(gate == receipt['gate'] and gate['status'] == 'passed'
            and gate['episodes_sha256'] == digest(episodes) and gate['contract_sha256'] == digest(contract), 'closed_training_gate_binding')
    require(receipt['status'] == 'completed_actual_fqi_training' and receipt['training_performed'] is True
            and receipt['native_executed'] is False, 'completed_training_required')
    allowed = {'train': set(contract['train_parent_groups']), 'development': set(contract['development_parent_groups'])}
    for episode in episodes:
        require(episode['split'] in allowed and episode['parent_group'] in allowed[episode['split']]
                and episode['business_and_requests_closed'] is True and episode['native_origin_verified'] is True
                and episode['rejected_transitions'] == [], 'closed_allowed_episode')
        for row in episode['transitions']:
            require(row['split'] == episode['split'] and row['parent_group'] == episode['parent_group']
                    and row['source']['sha256'] == episode['origin']['sha256'], 'row_episode_binding')
    rows = [r for e in episodes if e['split'] == 'development' for r in e['transitions'] if r['owner'] == contract['owner']]
    graph = supported_empirical_targets(rows, owner=contract['owner'], peer_policy_id=contract['peer_policy_id'], gamma=contract['gamma'])
    feature_fn = feature_function(Path(plan['feature_source']).read_bytes())
    metrics = []
    for history in receipt['history']:
        checkpoint = history['saved_intermediate']['checkpoint']; targets_ref = history['saved_intermediate']['targets']
        require(sha(checkpoint['path']) == checkpoint['sha256'] and sha(targets_ref['path']) == targets_ref['sha256'], 'checkpoint_or_training_targets_changed')
        model = read(checkpoint['path'])
        require(digest(model) == history['model_sha256'] and model['seed'] == history['seed']
                and model['training_rows_sha256'] == history['targets_sha256'] == digest(read(targets_ref['path'])), 'checkpoint_training_binding')
        predictions = [forward(model, row['observation'], row['action'], feature_fn) for row in rows]
        mse = math.fsum((prediction - target['target_value']) ** 2
                        for prediction, target in zip(predictions, graph['targets'], strict=True)) / len(rows)
        metrics.append({'seed': history['seed'], 'iteration': history['iteration'],
                        'development_supported_empirical_optimal_mse': mse,
                        'old_development_behavior_return_mse': history['development_behavior_return_mse'],
                        'predictions': predictions, 'checkpoint': checkpoint,
                        'model_content_sha256': model['model_sha256']})
    selected = choose(metrics, plan['training_seeds'], plan['allowed_iterations'])
    verify_plan(plan)  # recheck all immutable bytes before producing any selected copy
    output = Path(output).resolve(); require(not output.exists(), 'new_output_required'); output.mkdir(parents=True)
    def write(name, data):
        p = output / name
        with p.open('xb') as stream:
            stream.write(data if isinstance(data, bytes) else json.dumps(data, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n')
        return ref(p)
    copies = []
    for item in selected:
        data = Path(item['checkpoint']['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['checkpoint']['sha256'], 'checkpoint_changed_before_copy')
        copied = write(f"checkpoint_seed_{item['seed']}.json", data)
        require(copied['sha256'] == item['checkpoint']['sha256'], 'copy_not_original_bytes')
        copies.append({'seed': item['seed'], 'selected_iteration': item['iteration'], 'checkpoint': copied,
                       'original_checkpoint': item['checkpoint'], 'development_mse': item['development_supported_empirical_optimal_mse'],
                       'selected_is_fqi_iteration': item['iteration'] > 0})
    report = {'schema': SCHEMA, 'status': 'completed_selection_only', 'criterion': CRITERION,
              'plan_sha256': digest(plan), 'plan': write('selection_plan.json', plan),
              'development_graph': write('development_graph.json', graph), 'metrics': write('metrics.json', metrics),
              'models': copies, 'prior_selection_preserved': True, 'development_already_inspected': True,
              'training_performed': False, 'fit_count': 0, 'native_executed': False, 'formal_holdout_accessed': False,
              'native_improvement_established': False, 'historical_source_archives_verified': True,
              'selection_wall_seconds': time.monotonic() - started}
    write('receipt.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    require(sys.stdin.readline().strip() == TOKEN, 'bounded_parent_admission_required')
    result = select_existing(read(args.plan), args.output)
    print(json.dumps({'status': result['status'], 'models': result['models'], 'selection_wall_seconds': result['selection_wall_seconds']}))


if __name__ == '__main__':
    main()

