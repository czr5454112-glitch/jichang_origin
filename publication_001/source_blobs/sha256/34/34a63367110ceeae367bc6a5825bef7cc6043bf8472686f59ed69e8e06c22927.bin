"""Failure-aware saved audit factory; no campaign, native or predictor run.

The caller supplies the new source-bound campaign module. Every invocation has
its own namespace and explicit branch envelope. Saved input never grants native
authority. Original successful endpoint, root, physical, query and RPC checks
are retained; failure facts and certification are separate outputs.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import textwrap
from types import SimpleNamespace

from . import verify_initial_owner_route_entry_codec_campaign as previous
from . import verify_initial_single_capture_endpoints as endpoints
from . import initial_owner_route_single_capture_integration as integration

private, require = integration.private, integration.require
shared = previous.shared
MALFORMED = (ValueError, TypeError, KeyError, IndexError, AssertionError)


def tree(function): return ast.parse(textwrap.dedent(inspect.getsource(function)))
def dump(value): return ast.dump(value, include_attributes=False)


def _error(error):
    return {'status': 'invalid' if isinstance(error, MALFORMED) else 'audit_error',
        'error_type': type(error).__name__, 'error': str(error)}


def _attempt(function, *args, **kwargs):
    try: return {'status': 'passed', 'value': function(*args, **kwargs)}
    except Exception as error: return _error(error)


def _hash_raw_root(raw):
    # Diagnostic identity only; never a substitute for the original replay.
    return _attempt(endpoints.record_hash, {
        'root_records': raw.get('root_records'),
        'failed_root_admission': raw.get('failed_root_admission')})


def _compile_body(name, body, returned, namespace):
    definition = ast.parse('def '+name+'(raw, row, key):\n    pass\n').body[0]
    definition.body = copy.deepcopy(body) + ast.parse('return '+returned).body
    syntax = ast.Module(body=[definition], type_ignores=[])
    scope = dict(namespace)
    exec(compile(ast.fix_missing_locations(syntax), '<single-capture-independent-check:'+name+'>', 'exec'), scope)
    return scope[name]


def _core_functions(namespace):
    """Replace only the old endpoint loop; preserve all other original checks.

Fallback sections exist only to retain independent facts after an exception.
Their concatenated statements are checked against the complete original body;
none is described as passed unless its own original statements return.
"""
    source = previous._original_verify_branch
    syntax = tree(source); original = copy.deepcopy(syntax)
    body = syntax.body[0].body
    loops = [j for j, node in enumerate(body) if isinstance(node, ast.For)
        and ast.unparse(node.iter) == "raw['initial_endpoint_records'].items()"]
    require(len(loops) == 1, 'single_saved_endpoint_loop_inventory')
    endpoint_index = loops[0]
    def at(target):
        return next(j for j, node in enumerate(body) if isinstance(node, ast.Assign)
            and ast.unparse(node.targets[0]) == target)
    calls, controls, root = at('(calls, count)'), at('stage_names'), at('root')
    physical = next(j for j, node in enumerate(body) if isinstance(node, ast.If)
        and ast.unparse(node.test) == "raw['result'] is None")
    require(endpoint_index + 1 == calls and calls + 1 == controls and controls < physical < root
        and isinstance(body[-1], ast.Return), 'single_saved_core_partition')
    sections = (
        ('binding', body[:endpoint_index], 'True'),
        ('immutable', body[calls:controls], "{'immutable_requests': calls, 'submit_retry_calls': count}"),
        ('continuation', body[controls:physical], 'True'),
        ('physical', body[physical:root], 'replay'),
        ('root', body[root:root+1], 'root'),
        ('diagnostic', body[root+1:-1], 'True'),
    )
    restored_body = []
    for label, nodes, _ in sections:
        restored_body.extend(copy.deepcopy(nodes))
        if label == 'binding': restored_body.append(copy.deepcopy(body[endpoint_index]))
    restored_body.append(copy.deepcopy(body[-1]))
    restored = copy.deepcopy(original); restored.body[0].body = restored_body
    require(dump(restored) == dump(original), 'single_saved_fallback_partition_not_exact')
    functions = {label: _compile_body('_check_'+label, nodes, returned, namespace)
        for label, nodes, returned in sections}
    removed = copy.deepcopy(body[endpoint_index]); body[endpoint_index] = ast.Pass()
    inverted = copy.deepcopy(syntax); inverted.body[0].body[endpoint_index] = removed
    require(dump(inverted) == dump(original), 'single_saved_endpoint_inverse_AST')
    # This function shares the complete repaired namespace (including Path,
    # JSON/gzip and both new-campaign root predicate layers).
    exec(compile(ast.fix_missing_locations(syntax), '<single-capture-original-branch-checks>', 'exec'), namespace)
    core = namespace['verify_branch']
    return core, functions, {'original_endpoint_loop_only_removed': True,
        'endpoint_loop_inverse_AST_exact': True, 'fallback_partition_inverse_AST_exact': True,
        'original_branch_AST_sha256': hashlib.sha256(dump(original).encode()).hexdigest(),
        'fallback_sections': [label for label, _, _ in sections]}


def _gate_only(namespace):
    source = tree(previous.verify_branch).body[0].body
    require(ast.unparse(source[0]) == 'report = _original_verify_branch(raw, row, key)'
        and ast.unparse(source[1]) == "report['query_replay'] = complete_query_replay(raw)"
        and isinstance(source[-1], ast.Return), 'single_saved_outer_gate_shape')
    return _compile_body('_check_gate', [ast.parse('report = {}').body[0], *source[2:-1]],
        "report['observation_gate']", namespace)


def _endpoint_severity(report):
    states = [row.get('status') for row in report['records']] + [p.get('status') for p in report['problems']]
    if 'audit_error' in states: return 'audit_error'
    if 'invalid' in states: return 'invalid'
    return 'verified_complete' if report['all_required_endpoints_conditionally_verified'] else 'verified_unknown'


def _branch(raw, row, key, *, branch_envelope, namespace, core, fallback, gate_check):
    # The envelope comes only from verify_saved's already validated attempt.
    # The helper independently validates all calls/outbox before selecting IDs;
    # original immutable_calls remains in its original core position as well.
    endpoint_report = endpoints.verify_records(raw.get('initial_endpoint_records'),
        calls=raw.get('calls'), outbox=raw.get('outbox'), branch_envelope=branch_envelope)
    observed = {}
    def checked_core(*args):
        value = core(*args); observed['core'] = value; return value
    def checked_query(*args):
        value = namespace['complete_query_replay'](*args); observed['query'] = value; return value
    outer = private(previous.verify_branch, {**namespace,
        '_original_verify_branch': checked_core, 'complete_query_replay': checked_query})
    complete = _attempt(outer, raw, row, key)
    if complete['status'] == 'passed':
        result = complete['value']
        checks = {'original_branch_and_query_gate': {'status': 'passed'}}
    else:
        checks = {'original_branch_and_query_gate': complete}
        if 'core' in observed:
            result = observed['core']
            checks['original_core'] = {'status': 'passed'}
        else:
            # Independent original statement groups continue on the original
            # raw object; no dummy endpoint, result or root is supplied.
            for label, function in fallback.items(): checks[label] = _attempt(function, raw, row, key)
            result = {'root': checks['root'].get('value'),
                'business': checks['physical'].get('value', {'status': 'unknown_unverified_physical'}),
                'native_state_sha256': raw.get('native_state_sha256'), 'native_reexecution': False}
            if checks['immutable']['status'] == 'passed': result.update(checks['immutable']['value'])
        query = ({'status': 'passed', 'value': observed['query']} if 'query' in observed
            else _attempt(namespace['complete_query_replay'], raw))
        checks['query'] = query; result['query_replay'] = query.get('value', {'status': 'unknown_unverified_query'})
        gate = _attempt(gate_check, raw, row, key)
        checks['gate'] = gate; result['observation_gate'] = gate.get('value', {'status': 'unknown_unverified_gate'})
    # Only the original replay's returned conclusion is reported_root. Raw
    # labels/hop/elapsed are never promoted after a failed root replay.
    root = result.get('root')
    root_verified = (complete['status'] == 'passed' or 'core' in observed or
        checks.get('root', {}).get('status') == 'passed')
    if not root_verified: root = None
    all_original = (complete['status'] == 'passed'
        and result.get('query_replay', {}).get('status') == 'passed_complete_actual_refresh_outbox_replay'
        and not str(result.get('observation_gate', {}).get('status', 'unknown')).startswith('unknown'))
    certification = endpoints.certify_reported_root(root, endpoint_report,
        root_replay_verified=root_verified and all_original, business_facts=result.get('business'))
    result.update(reported_root=certification['reported_root'],
        root=certification['certified_root'], certified_root=certification['certified_root'],
        endpoint_audit=endpoint_report, certification=certification,
        original_checks=checks, original_root_replay_verified=root_verified,
        raw_root_diagnostic_hash=_hash_raw_root(raw),
        endpoint_status=_endpoint_severity(endpoint_report))
    result['audit_status'] = ('audit_error' if any(v['status'] == 'audit_error' for v in checks.values())
        or result['endpoint_status'] == 'audit_error' else 'invalid' if
        any(v['status'] == 'invalid' for v in checks.values()) or result['endpoint_status'] == 'invalid'
        else 'passed_with_retained_unknown' if not result['root']['closed'] else 'passed')
    return result


def _rpc_checker(namespace):
    """Exact v3 per-branch RPC statements, separately failure-accounted."""
    body = tree(previous.verify_saved).body[0].body
    loop = next(node for node in body if isinstance(node, ast.For)
        and ast.unparse(node.iter) == "plan['row_order']")
    start = next(j for j, node in enumerate(loop.body) if isinstance(node, ast.Assign)
        and ast.unparse(node.targets[0]) == 'identity')
    nodes = copy.deepcopy(loop.body[start:])
    syntax = ast.parse('def _original_rpc_scope(results, key, plan, samples, raw, used):\n    pass\n')
    syntax.body[0].body = nodes + [ast.Return(value=ast.Constant(value=True))]
    scope = dict(namespace)
    exec(compile(ast.fix_missing_locations(syntax), '<single-capture-original-RPC-scope>', 'exec'), scope)
    return scope['_original_rpc_scope'], dump(ast.Module(body=nodes, type_ignores=[]))


def _saved_template(namespace):
    syntax = tree(previous.verify_saved); original = copy.deepcopy(syntax)
    loop = next(node for node in syntax.body[0].body if isinstance(node, ast.For)
        and ast.unparse(node.iter) == "plan['row_order']")
    calls = [node for node in ast.walk(loop) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'verify_branch']
    require(len(calls) == 1 and not calls[0].keywords, 'single_saved_branch_call_count')
    envelope = ast.parse("{'attempt_started_ns':attempt['started_ns'],'attempt_finished_ns':attempt['finished_ns']}", mode='eval').body
    calls[0].keywords.append(ast.keyword(arg='branch_envelope', value=envelope))
    start = next(j for j, node in enumerate(loop.body) if isinstance(node, ast.Assign)
        and ast.unparse(node.targets[0]) == 'identity')
    original_rpc = copy.deepcopy(loop.body[start:])
    loop.body[start:] = ast.parse('_checked_rpc_scope(results, key, plan, samples, raw, used)').body
    restored = copy.deepcopy(syntax)
    restored_loop = next(node for node in restored.body[0].body if isinstance(node, ast.For)
        and ast.unparse(node.iter) == "plan['row_order']")
    next(node for node in ast.walk(restored_loop) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == 'verify_branch').keywords.clear()
    restored_loop.body[start:] = original_rpc
    require(dump(restored) == dump(original), 'single_saved_attempt_RPC_inverse_AST')
    exec(compile(ast.fix_missing_locations(syntax), '<single-capture-explicit-attempt-verifier>', 'exec'), namespace)
    return namespace['verify_saved'], {'explicit_validated_attempt_envelope': True,
        'attempt_RPC_inverse_AST_exact': True, 'global_source_lifetime_denominator_checks_unchanged': True}


def make_namespace(campaign):
    """Bind the new campaign explicitly; never mutate an imported dictionary."""
    require(campaign.contract is integration.contract, 'single_saved_current_entry_contract')
    namespace = {**previous._namespace, 'c': campaign}
    original_root = shared(previous.original.root_replay,
        {**previous.original.root_replay.__globals__, 'c': campaign})
    facade = SimpleNamespace(**vars(previous.original)); facade.root_replay = original_root
    root = shared(previous.root_replay, {**previous.root_replay.__globals__, 'c': campaign, 'old': facade})
    namespace['root_replay'] = root
    namespace['complete_query_replay'] = previous.complete_query_replay
    for name in ('endpoint_replay', 'immutable_calls', 'rpc_replay', 'pair_comparison', 'predictor_lifetime', 'branch_attempt'):
        namespace[name] = shared(getattr(previous, name), namespace)
    core, fallback, core_proof = _core_functions(namespace)
    gate_check = _gate_only(namespace)
    def verify_branch(raw, row, key, *, branch_envelope):
        return _branch(raw, row, key, branch_envelope=branch_envelope,
            namespace=namespace, core=core, fallback=fallback, gate_check=gate_check)
    namespace['_original_verify_branch'] = core
    namespace['verify_branch'] = verify_branch
    rpc, rpc_AST = _rpc_checker(namespace)
    def checked_rpc(results, key, plan, samples, raw, used):
        audit = _attempt(rpc, results, key, plan, samples, raw, used)
        # Account an observed sample even if it is invalid; verification status
        # remains invalid and cannot be repaired by denominator bookkeeping.
        if key.replace('/', ':') in samples: used.add(key.replace('/', ':'))
        results[key]['RPC_audit'] = audit
        if audit['status'] != 'passed':
            results[key]['audit_status'] = audit['status']
            result = results[key]
            if 'prediction_counts' in result:
                result['reported_unverified_prediction_counts'] = result.pop('prediction_counts')
            certified = copy.deepcopy(result['root'])
            certified.update(status='unknown_or_open', closed=False, observed_within_100ms=False)
            certified.setdefault('reasons', []).append('original_RPC_scope_not_verified')
            result['root'] = result['certified_root'] = certified
            if 'certification' in result: result['certification']['certified_root'] = copy.deepcopy(certified)
    namespace['_checked_rpc_scope'] = checked_rpc
    original_pair = namespace['pair_comparison']
    def pair_comparison(control, trial):
        result = original_pair(control, trial)
        if any(row.get('audit_status') in ('invalid', 'audit_error') for row in (control, trial)):
            return {'status': 'unknown_invalid_audit_pair', 'request_pair_completed': False,
                'all_five_strict_nonregression': None, 'per_job_delta': None,
                'reported_physical_pair': result, 'full32_optimization': False,
                'model_protection_certificate': False}
        return result
    namespace['pair_comparison'] = pair_comparison
    saved, saved_proof = _saved_template(namespace)
    def verify_saved(output, expected):
        result = saved(output, expected)
        for row in result['rows'].values():
            if 'certified_root' not in row:
                # The old saved checker already verified the unexecuted/failed
                # attempt row. No raw replay conclusion or root clock exists.
                certified = {**row['root'], 'closed': False, 'observed_within_100ms': False,
                    'complete_100ms_certified': False, 'reasons': ['missing_saved_raw']}
                row.update(root=certified, certified_root=certified, reported_root=None,
                    original_root_replay_verified=False, audit_status='unknown_missing_raw',
                    endpoint_audit=None, raw_root_diagnostic_hash=None)
        bad = {key: row['audit_status'] for key, row in result['rows'].items()
            if row.get('audit_status') in ('invalid', 'audit_error')}
        result['original_schema'] = result['schema']
        result['schema'] = 'g31.initial_single_capture.failure_aware_saved.v1'
        result['status'] = ('failed_saved_audit' if bad else 'passed_saved_with_complete_unknown_denominator')
        result['invalid_or_error_branches'] = bad
        result['reported_closed_roots'] = sum(row.get('reported_root', {}).get('closed', False)
            if row.get('reported_root') is not None else False for row in result['rows'].values())
        result['all_actual_failures_retained'] = True
        result['unverified_RPC_branches'] = [key for key, row in result['rows'].items()
            if row.get('RPC_audit', {}).get('status') in ('invalid', 'audit_error')]
        result['prediction_counts_complete'] = not result['unverified_RPC_branches']
        result['prediction_counts_scope'] = 'Verified per-row subtotal; failed RPC checks remain unknown, not zero evaluations.'
        result['complete_100ms_certified'] = False
        return result
    functions = {name: namespace[name] for name in ('endpoint_replay', 'immutable_calls', 'rpc_replay',
        'pair_comparison', 'predictor_lifetime', 'branch_attempt')}
    functions['pair_comparison'] = original_pair
    functions.update(core=core, original_root_replay=original_root, root_replay=root,
        complete_query_replay=namespace['complete_query_replay'], original_rpc_scope=rpc,
        saved_template=saved, **{'fallback_'+k: v for k, v in fallback.items()})
    missing = {name: previous.previous.missing_globals(fn) for name, fn in functions.items()}
    require(all(not values for values in missing.values()), 'single_saved_missing_defining_globals')
    require(root.__globals__['c'] is campaign and root.__globals__['old'].root_replay is original_root
        and original_root.__globals__['c'] is campaign, 'single_saved_two_level_predicate')
    proof = {'schema': 'g31.initial_single_capture.saved_source.v1', **core_proof, **saved_proof,
        'recursive_LOAD_GLOBAL_missing': missing, 'endpoint_dispatch': endpoints.source_proof(),
        'original_RPC_AST_sha256': hashlib.sha256(rpc_AST.encode()).hexdigest(),
        'both_root_replay_levels_current_campaign': True, 'reported_root_only_original_replay_result': True,
        'invalid_and_audit_error_never_verified_unknown': True, 'failure_aware_native_campaign_ready': False}
    return SimpleNamespace(verify_branch=verify_branch, verify_saved=verify_saved, source_proof=lambda: copy.deepcopy(proof),
        namespace=namespace, functions=functions, fallback=fallback)


def verify_saved(output, expected):
    from . import initial_owner_route_single_capture_campaign as campaign
    return make_namespace(campaign).verify_saved(output, expected)


def source_proof():
    from . import initial_owner_route_single_capture_campaign as campaign
    return make_namespace(campaign).source_proof()
