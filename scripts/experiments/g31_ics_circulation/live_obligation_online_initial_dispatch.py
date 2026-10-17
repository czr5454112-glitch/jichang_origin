"""Owner-local dispatch with a conservative component execution gate.

All seven arms pay the same full32 provider. No case label, saved outcome or
peer proposal is accepted here. A successful returned record means only that a
local command was submitted, or the selected native default required none.
Actual ACK/physical outcome, strict five-job protection, later re-estimation
and the complete100ms boundary require the enclosing campaign evidence.
"""
from __future__ import annotations
import copy
import time

from . import live_obligation_owned_same_information_search as search
from . import live_obligation_initial_decision_adapter_v2 as origin
from . import live_obligation_component_compatibility as compatibility

SCHEMA = 'g31.live_obligation.owner_local_initial_dispatch.v1'
ARMS = {
    'incumbent': ('incumbent', 'all'),
    'fixed_initial_MPC': ('finite_MPC', 'fixed_initial'),
    'later_default_MPC': ('finite_MPC', 'later_default'),
    'coordinate_strict': ('coordinate_strict', 'all'),
    'coordinate_plateau': ('coordinate_plateau', 'all'),
    'pair_repair': ('pair_repair', 'all'),
    'finite_MPC': ('finite_MPC', 'all'),
}


def require(ok, reason):
    if not ok:
        raise ValueError('online_initial_dispatch:' + reason)


def _submitted(client, owner, identity, component, causal, creating_root):
    """Read only this newly issued owner's row; do not query peer state."""
    row = client.rows[identity]
    kind = component['kind']
    expected = {'request_id': identity, 'owner_id': owner,
                **{k: v for k, v in component.items() if k != 'kind'}}
    if kind != 'transfer':
        expected['kind'] = kind
    require(row['kind'] == kind and row['request'] == expected,
            'immutable_submitted_component')
    creation = client.creations[identity]
    require(creation == {'creating_root': creating_root, 'kind': kind, 'causal': causal},
            'actual_creation_lineage')
    return {'request_id': identity, 'kind': kind, 'request': copy.deepcopy(row['request']),
            'creation': copy.deepcopy(creation), 'immediate_reply': copy.deepcopy(row['reply'])}


def _own_ids(client, owner):
    return {identity for identity, row in client.rows.items()
            if row['request']['owner_id'] == owner}


def _failed_submission(client, owner, before, progress):
    """A local row can precede a physical call whose result was never returned.

    Record only newly created own rows, with no query or retry. Missing reply
    or creation metadata does not prove that the native call did not happen.
    """
    identities = sorted(_own_ids(client, owner) - before)
    progress['new_own_request_ids_after_error'] = identities
    progress['dispatch_outcome'] = 'unknown_no_inference_from_missing_reply'
    if len(identities) == 1:
        identity = identities[0]
        progress['native_request_id'] = identity  # Before any fallible copy.
        row = client.rows[identity]
        progress['partial_submission'] = {'request_id': identity,
            'local_row': copy.deepcopy(row),
            'creation_present': identity in client.creations,
            'creation': copy.deepcopy(client.creations.get(identity)),
            'reply_present': 'reply' in row,
            'physical_execution_certified': False}


def _secondary(progress, phase, error):
    # The enclosing request must preserve its client/outbox independently if
    # even the progress sink cannot be written (for example MemoryError).
    try:
        progress.setdefault('instrumentation_errors', []).append(
            {'phase': phase, 'error_type': type(error).__name__})
        progress['instrumentation_complete'] = False
    except BaseException:
        pass


def choose_and_submit(native, session, client, owner, publication_id, accepted, *,
                      arm, incumbent_index, progress):
    """One owner invocation; native exceptions propagate with partial evidence.

The enclosing caller must start its complete request clock before publications
and retain this progress dictionary if execution raises. Nothing here advances
native time, activates an owner, refreshes an ACK, or reads a peer's proposal.
The returned live ledger belongs only to the collected owner; it is not saved
as JSON. The selected suffix is initially nonbinding, not a rolling replan.
"""
    started = time.perf_counter_ns()
    require(type(progress) is dict and not progress, 'fresh_progress_sink')
    require(owner in ('A', 'B') and arm in ARMS and type(incumbent_index) is int
            and 0 <= incumbent_index < 32, 'predeclared_arm_and_incumbent')
    progress.update(schema=SCHEMA, owner=owner, arm=arm, incumbent_index=incumbent_index,
        stage='initial_collection', status='unknown_unexecuted', started_ns=started,
        selected_action=None, native_request_id=None, native_default_no_command=False,
        selection=None, immediate_component=None, submission=None,
        instrumentation_complete=True, instrumentation_errors=[],
        native_protection_certified=False, native_physical_execution_certified=False,
        complete_request_100ms_certified=False, online_rolling_reestimation=False,
        cost_scope='This call includes own collection, full32/provider/selector, current recollection, evidence copies and submit. Earlier publication and later ACK/physical descendants plus caller serialization remain in the enclosing complete request.',
        future_components='A local initial estimate only; no later model re-estimation or peer consensus is certified.')
    decision = None
    primary_error = None
    before_submit = None
    try:
        decision = origin.collect_initial_decision(native, session, owner, publication_id, client, accepted)
        if type(decision) is not origin.InitialDecision:
            progress.update(status='unknown_initial_collection', collection=copy.deepcopy(decision))
            return progress, None
        progress['collection'] = decision.audit_copy()
        method, restriction = ARMS[arm]
        progress['stage'] = 'same32_provider_and_selection'
        selection = search.propose_initial(decision, method=method,
            incumbent_index=incumbent_index, restriction=restriction)
        progress['selection'] = selection
        action = selection.get('selected_action')
        if action is None:
            progress['status'] = 'unknown_no_admissible_estimate'
            return progress, decision._ledger
        progress['stage'] = 'conditional_component_compatibility'
        compatible = compatibility.select_component(selection, owner, incumbent_index)
        progress['compatibility'] = compatible
        action = compatible['selected_action']
        if action is None:
            progress['status'] = 'unknown_no_compatible_component'
            return progress, decision._ledger
        # Retain the complete proposal before the final native recollection.
        # Earlier provider-local revalidation is not reused as dispatch proof.
        progress['selected_action'] = copy.deepcopy(action)
        progress['stage'] = 'immediate_current_recollection'
        current = origin.revalidate_first_component(decision, action)
        progress['immediate_component'] = copy.deepcopy(current)
        if current.get('status') != 'fresh_local_component_proposal':
            progress['status'] = 'unknown_final_local_guard'
            return progress, decision._ledger
        require(current['owner'] == owner and current['public_sha256'] == decision._digest
                and current['at'] == decision._at == session.physical_time,
                'same_owner_current_proposal')
        component = current['component']
        # Prepare only local lineage and plain fields. Recheck the actual
        # collection immediately after this work and before submission.
        causal = {'relation': 'result_handling',
            'predecessor_protocol_id': publication_id,
            'continuation_parent_roots': [client.creations[publication_id]['creating_root']],
            'decision_information_sha256': decision._digest,
            'online_initial_arm': arm, 'online_initial_restriction': restriction,
            'local_initial_estimate_vector': copy.deepcopy(action),
            'component_compatibility_contract': compatible['contract'],
            'peer_proposal_read': False, 'later_model_reestimation_performed': False}
        payload = {k: v for k, v in component.items() if k != 'kind'}
        creating_root = client.context['root_id']
        before_submit = _own_ids(client, owner)
        if component['kind'] != 'no_command_native_default':
            progress['intended_creation'] = {'creating_root': creating_root,
                'kind': component['kind'], 'causal': copy.deepcopy(causal)}
        origin.require_current(decision)
        progress['stage'] = 'immediate_dispatch'
        if component['kind'] == 'no_command_native_default':
            require(owner == 'A' and action['initial_action'] == 'native_default'
                and component == {'kind': 'no_command_native_default', 'actual_next_unknown': True},
                'actual_default_is_not_physical_success')
            progress.update(status='selected_native_default_no_command', native_default_no_command=True)
        else:
            require(component['kind'] == ('route' if owner == 'A' else 'transfer'), 'owner_component_kind')
            progress['submission_started_ns'] = time.perf_counter_ns()
            identity = client.submit(owner, component['kind'], 'online-initial', causal=causal, **payload)
            # Save the identity before diagnostic assertions: an already issued
            # physical request cannot disappear if later export/checking fails.
            progress['native_request_id'] = identity
            progress['submission_returned_ns'] = time.perf_counter_ns()
            progress['submission'] = _submitted(client, owner, identity, component, causal, creating_root)
            progress['status'] = 'local_component_submitted_ACK_and_physical_outcome_pending'
        progress['stage'] = 'returned_local_dispatch'
        return progress, decision._ledger
    except BaseException as error:
        primary_error = error
        try:
            progress.update(status='unknown_raised_dispatch_outcome_unconfirmed', error_type=type(error).__name__)
            if before_submit is not None:
                _failed_submission(client, owner, before_submit, progress)
        except BaseException as evidence_error:
            _secondary(progress, 'failed_submission_evidence', evidence_error)
        raise
    finally:
        try:
            progress['finished_ns'] = time.perf_counter_ns()
            progress['call_wall_ms'] = (progress['finished_ns'] - started)/1e6
        except BaseException as clock_error:
            _secondary(progress, 'final_clock', clock_error)
            try:
                progress['call_wall_ms'] = None
                progress['status'] = 'unknown_incomplete_instrumentation'
            except BaseException:
                pass
            if primary_error is None:
                raise
