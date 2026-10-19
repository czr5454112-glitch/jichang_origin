"""Finite supplied-model deadline experiment, not an online admission contract.

All methods use the same admission-to-codec clock and reserved finalization
interval. Candidate simulations remain atomic and complete; an overrun stays
an overrun. The caller supplies the method's order/selection and finalization.
No supplied callback can turn this module into a native permission certificate.
"""
from __future__ import annotations

from copy import deepcopy
import json
import time

from . import public_preference_request_context as context_base
from .public_preference_static_context import StaticImplementation

VERSION = 'supplied_projection_wall_budget_v1'


def run(bundle, actions=None, *, budget_ns, reserve_ns, select, finalize,
        maximum_candidates=32, implementation=None, choose_next=None, clock=time.perf_counter_ns):
    """Return encoded experimental output and a separately measured envelope.

The clock starts before argument checks, factory setup, guards or copies.
``select`` returns an evaluated conditional-prediction index or None; its work
is timed. ``finalize`` receives isolated supplied data and has to implement any
real final check elsewhere. Its result is retained, never trusted as authority.
The internal end follows response encoding; caller return/envelope bookkeeping
is explicitly outside it and requires an external launch-to-return measurement.
"""
    accepted = clock()
    if type(accepted) is not int or accepted < 0:
        raise ValueError('wall_budget:clock')
    if (type(budget_ns) is not int or type(reserve_ns) is not int or
            not 0 <= reserve_ns <= budget_ns or budget_ns <= 0 or
            type(maximum_candidates) is not int or maximum_candidates not in (4, 32) or
            (actions is not None and (type(actions) is not list or not 0 < len(actions) <= 32)) or
            not callable(select) or not callable(finalize) or
            (choose_next is not None and not callable(choose_next))):
        raise ValueError('wall_budget:declared_contract')
    last = accepted
    def now():
        nonlocal last
        value = clock()
        if type(value) is not int or value < last:
            raise ValueError('wall_budget:clock_regressed')
        last = value
        return value
    deadline, solve_deadline = accepted + budget_ns, accepted + budget_ns - reserve_ns
    spans = []
    cold = implementation is None
    start = now()
    implementation = StaticImplementation() if cold else implementation
    if type(implementation) is not StaticImplementation:
        raise TypeError('wall_budget:implementation')
    context = implementation.context(bundle)
    # Real probes derive the input-dependent domain here, after admission. An
    # explicitly supplied list is a caller-declared domain, never a free hidden
    # precomputation performed by this implementation.
    context_base._closed_tree(actions)
    declared = context.actions() if actions is None else deepcopy(actions)
    rows = [{'action': action, 'status': 'unknown_unexecuted', 'prediction': None}
            for action in declared]
    spans.append({'stage': 'setup_and_complete_input_validation', 'start_ns': start, 'end_ns': now()})
    incumbent, failure = None, None
    for _ in range(maximum_candidates):
        if now() >= solve_deadline or all(row['status'] == 'evaluated' for row in rows):
            break
        start = now()
        try:
            index = (next(i for i, row in enumerate(rows) if row['status'] == 'unknown_unexecuted')
                     if choose_next is None else choose_next(deepcopy(rows), incumbent))
            if index is not None and (type(index) is not int or not 0 <= index < len(rows)
                    or rows[index]['status'] != 'unknown_unexecuted'):
                raise ValueError('wall_budget:invalid_or_repeated_candidate')
        except Exception as error:
            failure = {'stage': 'method_candidate_choice', 'error': repr(error)}
            index = None
        spans.append({'stage': 'method_candidate_choice', 'start_ns': start, 'end_ns': now()})
        if index is None or now() >= solve_deadline:
            break
        action = declared[index]
        start = now()
        prediction = context.predict(action)
        rows[index].update(status='evaluated', prediction=prediction)
        # Selection gets copies; it cannot mutate snapshot, candidates or code.
        try:
            selected = select(deepcopy(rows), incumbent)
        except Exception as error:
            failure = {'stage': 'method_selection', 'error': repr(error)}
            spans.append({'stage': 'candidate_and_method_selection', 'candidate': index,
                          'start_ns': start, 'end_ns': now()})
            break
        if selected is not None:
            if (type(selected) is not int or not 0 <= selected < len(rows) or
                    rows[selected]['status'] != 'evaluated' or
                    rows[selected]['prediction'].get('status') != 'conditional_prediction'):
                raise ValueError('wall_budget:unevaluated_or_unknown_incumbent')
        incumbent = selected
        spans.append({'stage': 'candidate_and_method_selection', 'candidate': index,
                      'start_ns': start, 'end_ns': now()})
    start = now()
    proposal = None if incumbent is None else deepcopy(rows[incumbent])
    try:
        final = finalize(context.snapshot(), proposal, deadline)
        context_base._closed_tree(final)
        json.dumps(final, ensure_ascii=False, allow_nan=False)
    except Exception as error:
        final = {'status': 'unknown_finalization_failed', 'error': repr(error)}
    spans.append({'stage': 'supplied_finalization', 'start_ns': start, 'end_ns': now()})
    start = now()
    payload = {'schema': VERSION, 'candidate_limit': maximum_candidates, 'declared_action_count': len(declared),
        'action_domain_scope': 'derived_inside_request' if actions is None else 'supplied_by_caller',
        'candidate_domain_available': bool(declared),
        'candidate_rows': rows, 'failure': failure,
        'incumbent_index': incumbent, 'finalization': deepcopy(final),
        'native_current_identity_verified': False, 'native_permission_verified': False,
        'complete_request_100ms_certified': False,
        'scope': 'Conditional supplied-model projections; unexecuted actions remain unknown. Callback output is not native authority.'}
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')
    encoded_end = now()
    spans.append({'stage': 'response_codec', 'start_ns': start, 'end_ns': encoded_end})
    elapsed = encoded_end - accepted
    return {'response_bytes': encoded, 'accepted_ns': accepted, 'encoded_end_ns': encoded_end,
        'observed_admission_through_codec_ns': elapsed, 'observed_overrun_ns': max(0, elapsed-budget_ns),
        'observed_budget_met_through_codec': elapsed <= budget_ns,
        'budget_ns': budget_ns, 'reserve_ns': reserve_ns, 'solve_deadline_ns': solve_deadline,
        'factory_cold_cost_included': cold, 'spans': spans,
        'unassigned_inside_envelope_ns': elapsed-sum(row['end_ns']-row['start_ns'] for row in spans),
        'excluded_after_internal_end': 'Return/envelope bookkeeping and caller output; external full wall still required.',
        'complete_request_100ms_certified': False, 'future_hard_deadline_guaranteed': False}
