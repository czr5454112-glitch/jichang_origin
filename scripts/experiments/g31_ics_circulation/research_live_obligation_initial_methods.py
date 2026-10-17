"""Owner-local seven-arm branch with conditional component compatibility.

Each owner selects from its own delivered facts. The public conservative
contract keeps A's incumbent components and permits B's already queried safe
deviations. Conditional compatibility grants no native resource guarantee.
The original guarded notification continuation is extracted intact.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import textwrap
import time
import traceback
from pathlib import Path
from types import FunctionType

from . import research_live_obligation_native_domain as old
from . import live_obligation_online_initial_dispatch as dispatch
from . import live_obligation_online_retained_policy as retained
from . import live_obligation_projection_protocol as protocol

SCHEMA = 'g31.live_obligation.prospective_initial_methods.v1'
SOURCE_SHA = 'd065cb78e6a37f1ae31d6a7a1a08f42c5f5e31ff746e7d765f5a15159d2a577c'
ARMS = tuple(dispatch.ARMS)
CASES = tuple(old.CASE_ORDER)
SPEC_FIELDS = ('case', 'method', 'fault', 'incumbent_index')
_ORIGINAL = old._run_branch
_CODE = _ORIGINAL.__code__


def require(ok, reason):
    if not ok:
        raise ValueError('online_initial_methods:' + reason)


def incumbent_index():
    actions = old.construction.actions()
    incumbent = protocol.incumbent_action()
    matches = [i for i, action in enumerate(actions) if action == incumbent]
    require(len(actions) == 32 and len(matches) == 1, 'unchanged_strong_incumbent')
    return matches[0]


def rows():
    incumbent = incumbent_index()
    return {case + '/' + arm: {'case': case, 'method': arm, 'fault': None,
        'incumbent_index': incumbent, 'status': 'unknown_unexecuted'}
        for case in CASES for arm in ARMS}


def _continuation_code():
    """Extract one unchanged ordered span, including all original guards.

    Original source globals are retained in full. Two edits adapt only the
    cursor domain and final aggregate. The native notification API still
    monitors both owners and requires exactly both cursor keys. Missing owners
    have no fabricated policy; activation uses the actual policy dictionary.
"""
    require(old._run_branch is _ORIGINAL and _ORIGINAL.__code__ is _CODE,
            'original_function_identity')
    require(hashlib.sha256(Path(old.__file__).read_bytes()).hexdigest() == SOURCE_SHA,
            'frozen_original_source')
    original = ast.parse(textwrap.dedent(inspect.getsource(_ORIGINAL))).body[0]
    begin = [i for i, node in enumerate(original.body) if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'cursors' for t in node.targets)]
    end = [i for i, node in enumerate(original.body) if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'result' for t in node.targets)]
    require(len(begin) == len(end) == 1 and begin[0] < end[0], 'one_continuation_span')
    body = copy.deepcopy(original.body[begin[0]:end[0] + 1])
    original_cursors = copy.deepcopy(body[0])
    require(ast.dump(body[0], include_attributes=False) == ast.dump(
        ast.parse("cursors = {o: 0 for o in policies}").body[0], include_attributes=False),
        'original_cursors_exact')
    body[0] = ast.parse("cursors = {'A': 0, 'B': 0}").body[0]
    # The original final aggregate indexes both policies. Keep missing owners
    # explicit. The due/activate set and native API call remain unchanged.
    indices = [i for i, node in enumerate(body) if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'continuation' for t in node.targets)]
    require(len(indices) == 1, 'one_final_aggregate')
    aggregate = body[indices[0]]
    replacement = ast.parse("continuation = _aggregate(status, policies)").body[0]
    body[indices[0]] = replacement
    restored = copy.deepcopy(body)
    restored[0] = original_cursors
    restored[indices[0]] = aggregate
    dump = lambda nodes: ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False)
    require(dump(restored) == dump(original.body[begin[0]:end[0] + 1]),
            'inverse_continuation_exact')
    template = ast.parse('def _continue(session, client, policies, progress):\n    pass\n').body[0]
    template.body = body + ast.parse('return continuation, result').body
    tree = ast.fix_missing_locations(ast.Module(body=[template], type_ignores=[]))
    namespace = dict(_ORIGINAL.__globals__)
    namespace['_aggregate'] = _aggregate
    scratch = dict(namespace)
    exec(compile(tree, '<online_initial_continuation>', 'exec'), scratch)
    function = FunctionType(scratch['_continue'].__code__, namespace, '_continue')
    require(set(namespace) == set(_ORIGINAL.__globals__) | {'_aggregate'}
        and all(namespace[k] is v for k, v in _ORIGINAL.__globals__.items()),
        'complete_original_continuation_globals')
    return function, {'original_source_sha256': SOURCE_SHA,
        'inverse_AST_unchanged_span': True,
        'replacements': ['both_requested_native_cursor_keys', 'final_aggregate_missing_owners'],
        'original_span_AST_sha256': hashlib.sha256(dump(restored).encode()).hexdigest()}


def _aggregate(status, policies):
    return {'status': status,
        'route_choices': policies['B'].choices if 'B' in policies else [],
        'returns': policies['A'].returns if 'A' in policies else [],
        'supply_lineage': policies['B'].supplies if 'B' in policies else [],
        'recovery_decisions': policies['B'].recovery if 'B' in policies else [],
        'missing_owner_policies': [o for o in ('A', 'B') if o not in policies]}


def start_owner(native, session, client, owner, publication, channel, accepted,
                *, arm, incumbent, progress, ledgers, policies):
    """Only this owner's dispatch result can create this owner's policy."""
    require(owner in ('A', 'B') and owner not in progress and owner not in policies,
            'fresh_owner_step')
    record = {}
    progress[owner] = record  # Preserve the actual sink before any fallible work.
    result, ledger = dispatch.choose_and_submit(native, session, client, owner,
        publication, accepted, arm=arm, incumbent_index=incumbent, progress=record)
    require(result is record, 'actual_progress_identity')
    ledgers[owner] = ledger
    expected = ('selected_native_default_no_command' if owner == 'A' and
        record.get('native_default_no_command') is True else
        'local_component_submitted_ACK_and_physical_outcome_pending')
    if ledger is None or record.get('status') != expected or record.get('selected_action') is None:
        record['continuation_policy_created'] = False
        return
    require(record['owner'] == owner and record['arm'] == arm
        and record['instrumentation_complete'] is True, 'own_completed_dispatch')
    if owner == 'B':
        require(type(record['native_request_id']) is str and record['native_request_id'],
                'own_actual_initial_supply')
    vector = copy.deepcopy(record['selected_action'])
    policies[owner] = retained.OwnerPolicy(native, session, client, owner, ledger,
        channel, vector, accepted, record['native_request_id'] if owner == 'B' else None)
    record['continuation_policy_created'] = True


def retrospective_vector(initial):
    """Assessment-only combination. Must never feed an owner or predictor."""
    if any(initial.get(o, {}).get('continuation_policy_created') is not True for o in ('A', 'B')):
        return None
    a, b = (initial[o]['selected_action'] for o in ('A', 'B'))
    return {'initial_action': a['initial_action'], 'empty_departure': b['empty_departure'],
            'return_delay': a['return_delay'], 'later_action': b['later_action']}


def completed_summary(data, result, client, continuation, initial, decisions):
    vector = retrospective_vector(initial)
    if vector is None:
        return {'status': 'unknown_missing_owner_initial_proposal', 'business_metrics': None,
            'strict_protected': None, 'current_state_certified': False,
            'missing_owner_policies': continuation['missing_owner_policies']}
    summary = old.assess_cell(data, result, client, continuation, vector)
    flat = [d for sequence in decisions.values() for d in sequence]
    inputs = (len(flat) == 2 and all(d['information']['native_delivery_verified'] is True for d in flat)
        and all(initial[o]['immediate_component']['status'] == 'fresh_local_component_proposal'
            and initial[o]['collection']['owner'] == o for o in ('A', 'B')))
    executed = (summary['status'] == 'assessed' and len(flat) == 2
        and all(d.get('selected_action_admitted') is True and not d['fallback_used'] for d in flat))
    summary.update(all_required_inputs_verified=inputs, selected_actions_executed=executed,
        retrospective_effective_vector=vector,
        owner_proposals_agreed_posthoc=initial['A']['selected_action'] == initial['B']['selected_action'],
        peer_proposal_used_online=False, later_model_reestimation=False,
        current_state_certified=False, native_model_protection_certified=False,
        complete_request_100ms_certified=False, strict_protected=None,
        forecast_scope='Retained initial estimate with actual current guards; no hidden-state coverage certificate.')
    summary['component_compatibility_contract'] = dispatch.compatibility.CONTRACT
    summary['conditional_component_domain_verified'] = all(
        initial[owner].get('compatibility', {}).get('contract') == dispatch.compatibility.CONTRACT
        and initial[owner]['compatibility'].get('selected_action') == initial[owner]['selected_action']
        for owner in ('A', 'B')) and vector == initial['B']['selected_action'] and all(
            vector[field] == protocol.incumbent_action()[field]
            for field in dispatch.compatibility.OWNER_FIELDS['A'])
    summary['joint_R1_R2_domain_restored'] = False
    if not inputs or not executed:
        summary['status'] = 'unknown_missing_input_or_unexecuted_initial_estimate'
    elif not summary['conditional_component_domain_verified']:
        summary['status'] = 'unknown_unverified_component_contract'
    return summary


def run_branch(native, row, contract_reference, semantic_reference, *, accepted_run, branch_key):
    progress = {'specification': copy.deepcopy(row)}
    try:
        return _run_branch(native, row, contract_reference, semantic_reference,
            accepted_run=accepted_run, branch_key=branch_key, progress=progress)
    except Exception:
        # Original capture uses const native diagnostics and actual client data,
        # never result_at/advance after failure. Initial record shape is new;
        # its saved verifier must not call the old fixed96 initial verifier.
        return old.capture_partial(progress, traceback.format_exc())


def _run_branch(native, row, contract_reference, semantic_reference, *, accepted_run, branch_key, progress):
    started = time.perf_counter_ns()
    require(type(accepted_run) is old.run_admission.RunAcceptance and accepted_run.active_for(branch_key),
            'active_run_branch')
    expected = rows()
    require(branch_key in expected and all(row.get(k) == expected[branch_key][k] for k in SPEC_FIELDS),
            'predeclared_seven_arm_domain')
    declared = accepted_run.branch_specification(branch_key)
    require(all(row.get(k) == declared.get(k) for k in SPEC_FIELDS), 'actual_registered_specification')
    runtime = accepted_run.contract_copy(branch_key)
    require(runtime['reference'] == contract_reference and runtime['contract']['binary_sha256'] ==
        native._g31_native_artifact_identity['sha256'], 'accepted_native_contract')
    data = old.native_scene(row['case'], row['fault'])
    progress.update(input=data, stage='native_session_constructor')
    session = native.NativeSession(data)
    progress.update(session=session, stage='runtime_admission')
    admission, accepted = old.adapter.bind_native027(native, session, contract_reference,
        accepted_run=accepted_run, branch_key=branch_key)
    require(accepted is not None, 'native_acceptance:' + str(admission))
    session.advance_to(.05)
    client = old.LocalTransport(session)
    channels, planning, ledgers, initial, policies = {}, {}, {}, {}, {}
    progress.update(client=client, ledgers=ledgers, initial_owners=initial, policies=policies,
                    stage='initial_publications')
    # The entire publication/collection/model/dispatch chain stays inside this
    # branch wall. No setup or proof cost is subtracted from a timing claim.
    for owner, peer in (('A', 'B'), ('B', 'A')):
        client.activate(owner, {'kind': 'initial_public_epoch', 'at': .05})
        channels[owner] = client.submit(owner, 'demand', 'seed-demand', target_owner=peer,
            message_delay=.01, publication_delay=.01)
        planning[owner] = client.submit(owner, 'planning_snapshot', 'initial-planning', target_owner=peer,
            message_delay=.01, publication_delay=.01, expiry=.21)
    session.advance_to(old.v1.START)
    progress['stage'] = 'independent_initial_owner_decisions'
    for owner in ('A', 'B'):
        client.activate(owner, {'kind': 'initial_decision_epoch', 'at': old.v1.START})
        client.refresh_owner(owner, retry=False)
        start_owner(native, session, client, owner, planning[owner], channels[owner], accepted,
            arm=row['method'], incumbent=row['incumbent_index'], progress=initial,
            ledgers=ledgers, policies=policies)
    continuation, result = _CONTINUE(session, client, policies, progress)
    progress.update(result=result, stage='retrospective_assessment')
    decisions = {o: p.decisions for o, p in policies.items()}
    summary = completed_summary(data, result, client, continuation, initial, decisions)
    raw = {'schema': SCHEMA, 'specification': copy.deepcopy(row), 'input': data,
        'initial_owners': initial, 'retained_ledgers': {o: l.audit_copy() for o, l in ledgers.items() if l is not None},
        'decisions': decisions, 'exchanges': {o: p.exchanges for o, p in policies.items()},
        'collection_policy_intervals': {o: p.quiet_periods for o, p in policies.items()},
        'native027_acceptance': accepted.audit_copy(), 'calls': client.calls, 'outbox': client.rows,
        'request_creations': client.creations, 'owner_activation_admissions': client.roots,
        'ack_handling': client.ack_handling, 'continuation': continuation,
        'native_batches': progress['native_batches'], 'result': result, 'summary': summary,
        'branch_start_ns': started, 'lineage_status': 'experimental_proxy_no_business_denominator_certificate'}
    raw['preexport_finished_ns'] = time.perf_counter_ns()
    raw['branch_preexport_wall_ms'] = (raw['preexport_finished_ns'] - started) / 1e6
    raw['timing_scope'] = ('Whole branch lower envelope includes publications, full32 for each owner, actual '
        'continuation and assessment. Caller export and run admission/closure remain additional; '
        'this is not a complete-request or CPU/wire separation certificate.')
    return raw


_CONTINUE, _CONTINUATION_PROOF = _continuation_code()


def source_proof():
    _, proof = _continuation_code()
    require(proof == _CONTINUATION_PROOF and ARMS == tuple(dispatch.ARMS), 'unchanged_branch_domain')
    return {'schema': SCHEMA, 'continuation': proof, 'branch_count': len(rows()),
        'actual_execution': False, 'later_model_reestimation': False,
        'peer_proposal_consensus_gate': False, 'retained_policy': retained.source_proof()}
