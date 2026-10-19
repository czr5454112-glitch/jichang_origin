"""Initial-only, on-demand conditional forecasts; no native execution authority.

The original full32 provider remains the teacher. A private invocation of its
owned runner changes only the ordered CHOICES global to the requested subset.
No unrequested suffix is cloned or resumed; a required shared prefix can still
use its original default representative, whose future action is not yet read.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
import traceback
from contextlib import contextmanager
from types import FunctionType

from . import live_obligation_owned_initial_provider as teacher
from . import live_obligation_component_compatibility as compatibility

SCHEMA = 'g31.foundation.budgeted_initial_provider.v1'
origin = teacher.origin
domain = teacher.domain
execution = teacher.execution
binding = teacher.binding
_RUN = execution._run
_RUN_CODE = _RUN.__code__
_GLOBALS = dict(_RUN.__globals__)


def require(value, reason):
    if not value:
        raise ValueError('foundation_budgeted:' + reason)


def score_candidates(observation, candidates, model_version='semantic_rule_v1'):
    """Deterministic semantic baseline; higher scores receive earlier rollout."""
    require(type(observation) is dict and model_version == 'semantic_rule_v1', 'rule_input_version')
    return [-action['empty_departure'] - action['return_delay']
        - .001 * (action['initial_action'] != 'native_default')
        - .0001 * (action['later_action'] != 'native_default') for action in candidates]


def _check_subset_run(function, choices):
    require(execution._run is _RUN and _RUN.__code__ is _RUN_CODE, 'owned_runner_identity')
    require(set(_RUN.__globals__) == set(_GLOBALS)
        and all(_RUN.__globals__[name] is value for name, value in _GLOBALS.items()),
        'owned_runner_globals')
    require(type(choices) is tuple and choices and len(set(choices)) == len(choices)
        and choices == tuple(choice for choice in domain.LATER if choice in choices), 'ordered_suffix_subset')
    require(function.__code__ is _RUN_CODE and function.__defaults__ is _RUN.__defaults__
        and function.__kwdefaults__ is _RUN.__kwdefaults__ and function.__closure__ is _RUN.__closure__,
        'subset_runner_code_defaults_closure')
    require(set(function.__globals__) == set(_GLOBALS)
        and function.__globals__['CHOICES'] is choices
        and all(function.__globals__[name] is value for name, value in _GLOBALS.items() if name != 'CHOICES'),
        'only_declared_suffix_subset_global')


def _subset_run(choices):
    namespace = {**_GLOBALS, 'CHOICES': choices}
    function = FunctionType(_RUN_CODE, namespace, _RUN.__name__, _RUN.__defaults__, _RUN.__closure__)
    function.__kwdefaults__ = _RUN.__kwdefaults__
    _check_subset_run(function, choices)
    return function


def source_contract(request):
    original = teacher.source_proof(request)
    for choices in ((domain.LATER[0],), (domain.LATER[1],), domain.LATER):
        _subset_run(choices)
    return {'schema': SCHEMA, 'original_full32_source_contract': original,
        'original_contract_counts_describe_teacher_not_this_execution': True,
        'changed_global': 'CHOICES', 'allowed_change': 'ordered nonempty subset of original two future suffixes',
        'runner_code_defaults_closure_unchanged': True, 'all_other_defining_globals_unchanged': True,
        'same_original_cut_and_complete_clone': True, 'initial_context_cache': False,
        'source_inventory_scope': 'one_request_not_a_resident_service', 'native_authority': False}


def execute_selected_prefix(request, group, context, indices):
    """Execute only selected siblings with original guards and private state."""
    facade = execution._bound_future(request)
    expected = domain.partition(facade.core.lazy.original.physics.previous.actions())['groups']
    require(type(group) is dict and type(group.get('prefix_index')) is int
        and 0 <= group['prefix_index'] < len(expected)
        and teacher.encoding(group) == teacher.encoding(expected[group['prefix_index']]), 'original_prefix_group')
    require(type(indices) is tuple and indices and len(indices) == len(set(indices))
        and all(type(index) is int and index in group['candidate_indices'] for index in indices), 'requested_group_indices')
    selected = tuple(index for index in group['candidate_indices'] if index in indices)
    choices = tuple(group['actions'][group['candidate_indices'].index(index)]['later_action'] for index in selected)
    function = _subset_run(choices)
    predictions = {}

    def save(label, value):
        raw = execution.previous.bytes_of(value)
        predictions[label] = json.loads(raw)
        return {'memory_label': label, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    detail = function(context, copy.deepcopy(group['representative_action']),
        execution.evaluator.MAXIMUM_CUTS, facade.core, facade, save)
    error = None
    try:
        _check_subset_run(function, choices)
        request.check_integration()
        require(tuple(detail['suffixes']) == choices, 'only_requested_suffix_outputs')
        require(detail['counts']['future_forks'] <= len(selected)
            and detail['counts']['future_resumes'] <= len(selected), 'actual_suffix_budget')
    except Exception:
        error = traceback.format_exc()
    return {'prefix_index': group['prefix_index'], 'candidate_indices': list(selected),
        'context_constructions': 1, 'detail': detail, 'predictions': predictions,
        'binding_error': error, 'isolation_basis': execution.OWNERSHIP, 'native_authority': False}


class BudgetedBatch:
    """Immutable data only; neither construction nor a saved copy grants authority."""
    __slots__ = ('_bytes', '_digest', '_data', '_sealed')

    def __init__(self, data):
        raw = teacher.encoding(data)
        object.__setattr__(self, '_bytes', raw)
        object.__setattr__(self, '_digest', hashlib.sha256(raw.encode()).hexdigest())
        object.__setattr__(self, '_data', teacher.previous._freeze(json.loads(raw)))
        object.__setattr__(self, '_sealed', (self._bytes, self._digest, self._data))

    def __setattr__(self, name, value):
        raise ValueError('foundation_budgeted:immutable_batch')

    def __delattr__(self, name):
        raise ValueError('foundation_budgeted:immutable_batch')

    def _checked(self):
        require(type(self) is BudgetedBatch and type(self._sealed) is tuple and len(self._sealed) == 3
            and all(current is sealed for current, sealed in zip(
                (self._bytes, self._digest, self._data), self._sealed, strict=True)), 'batch_integrity')
        return self._data

    def query(self, index):
        data = self._checked()
        require(type(index) is int and index in data['requested_indices'], 'candidate_not_requested')
        return teacher.previous._copy_frozen(data['rows'][index])

    def audit_copy(self):
        result = teacher.previous._copy_frozen(self._checked())
        result.update(batch_sha256=self._digest, dispatch_authorized=False,
            native_authority=False, saved_copy_has_authority=False)
        return result


@contextmanager
def _measure(timings, stage):
    started = time.perf_counter_ns()
    try:
        yield
    finally:
        timings[stage] = timings.get(stage, 0) + time.perf_counter_ns() - started


def public_compatible_indices(owner, actions):
    domain.partition(actions)
    require(owner in compatibility.OWNER_FIELDS, 'known_public_contract_owner')
    baseline = actions[4]
    require(teacher.encoding(baseline) == teacher.encoding(compatibility.protocol.incumbent_action()),
        'unchanged_public_incumbent')
    indices = ([4] if owner == 'A' else [index for index, action in enumerate(actions)
        if all(domain.token(action[field]) == domain.token(baseline[field])
            for field in compatibility.OWNER_FIELDS['A'])])
    require(indices == ([4] if owner == 'A' else [0, 1, 4, 5, 8, 9, 12, 13]),
        'frozen_public_compatible_domain')
    return indices


def _requested(public, actions, budget, incumbent_index, scorer, model_version, indices,
               *, allowed_indices=None, prefix_budget=None, ranking_policy='score'):
    require(type(budget) is int and 1 <= budget <= len(actions), 'candidate_budget')
    require(type(incumbent_index) is int and incumbent_index == 4, 'frozen_incumbent04')
    allowed = list(range(len(actions))) if allowed_indices is None else list(allowed_indices)
    require(allowed and len(allowed) == len(set(allowed)) and incumbent_index in allowed
        and all(type(index) is int and 0 <= index < len(actions) for index in allowed), 'public_candidate_domain')
    groups = domain.partition(actions)['groups']
    prefixes = {index: group['prefix_index'] for group in groups for index in group['candidate_indices']}
    require(prefix_budget is None or type(prefix_budget) is int and 1 <= prefix_budget <= len(groups), 'prefix_budget')
    require(ranking_policy in ('score', 'marginal_prefix_cost'), 'ranking_policy')
    limit = len(groups) if prefix_budget is None else prefix_budget
    accounting = {'eligible_candidate_indices': allowed, 'legal_domain_size': len(allowed),
        'scored_candidate_indices': [], 'scoring_row_count': 0, 'candidate_budget': budget,
        'prefix_budget': prefix_budget, 'ranking_policy': ranking_policy,
        'incremental_cost_scope': 'Unit prefix setup plus unit suffix; ranking heuristic, not milliseconds or calibrated prediction.',
        'incremental_cost_units': {'new_prefix': 1, 'suffix': 1}, 'selection_steps': []}
    if indices is not None:
        require(type(indices) in (tuple, list) and 1 <= len(indices) <= budget
            and all(type(index) is int and index in allowed for index in indices)
            and len(set(indices)) == len(indices) and incumbent_index in indices, 'explicit_budget_includes_incumbent')
        requested = [incumbent_index, *(index for index in indices if index != incumbent_index)]
        require(len({prefixes[index] for index in requested}) <= limit, 'explicit_prefix_budget')
        scores = None
    else:
        function = score_candidates if scorer is None else scorer
        values = function(observation=copy.deepcopy(public), candidates=copy.deepcopy([actions[index] for index in allowed]),
            model_version=model_version)
        require(type(values) in (list, tuple) and len(values) == len(allowed)
            and all(type(value) in (int, float) and math.isfinite(value) for value in values), 'finite_same_order_scores')
        scores = [None] * len(actions)
        for index, value in zip(allowed, values, strict=True):
            scores[index] = value
        accounting.update(scored_candidate_indices=list(allowed), scoring_row_count=len(allowed))
        requested, used_prefixes = [incumbent_index], {prefixes[incumbent_index]}
        while len(requested) < budget:
            available = [index for index in allowed if index not in requested
                and (prefixes[index] in used_prefixes or len(used_prefixes) < limit)]
            if not available:
                break
            selected = min(available, key=lambda index: (
                int(prefixes[index] not in used_prefixes) if ranking_policy == 'marginal_prefix_cost' else 0,
                -scores[index], index))
            requested.append(selected)
            used_prefixes.add(prefixes[selected])
    used_prefixes = set()
    for index in requested:
        new_prefix = prefixes[index] not in used_prefixes
        accounting['selection_steps'].append({'candidate_index': index, 'prefix_index': prefixes[index],
            'new_prefix': new_prefix, 'incremental_cost_units': 1 + int(new_prefix)})
        used_prefixes.add(prefixes[index])
    accounting.update(requested_prefix_indices=sorted(used_prefixes), requested_prefix_count=len(used_prefixes),
        requested_candidate_count=len(requested), eligible_candidates_not_requested=len(allowed) - len(requested),
        estimated_total_cost_units=len(used_prefixes) + len(requested))
    return tuple(requested), scores, accounting


def _selection(result, decision, incumbent_index):
    rows = result['rows']
    baseline = rows[incumbent_index]
    eligible = [index for index in result['requested_indices']
        if compatibility.known(baseline) and compatibility.known(rows[index])
        and all(rows[index]['completion'][job] <= baseline['completion'][job] for job in teacher.JOBS)]
    selected = min(eligible, key=lambda index: (sum(rows[index]['completion'][job] for job in teacher.JOBS), index)) if eligible else None
    selection = {'selected_index': selected, 'selected_action': copy.deepcopy(rows[selected]['action']) if selected is not None else None,
        'accounting': {'query_indices': list(result['requested_indices'])},
        'allowed_candidate_indices': list(result['requested_indices']),
        'provider_evidence': {'owner': result['owner'], 'rows': rows}, 'dispatch_authorized': False}
    compatible = compatibility.select_component(selection, result['owner'], incumbent_index)
    proposal = origin.unknown('no_known_protected_compatible_candidate')
    if compatible['selected_action'] is not None:
        proposal = origin.revalidate_first_component(decision, compatible['selected_action'])
    return {'conditional_best_index': selected, 'component_compatibility': compatible,
        'selected_index': compatible['selected_index'], 'selected_action': compatible['selected_action'],
        'current_revalidation': proposal, 'native_authority': False, 'dispatch_authorized': False,
        'requires_original_dispatch_and_current_checks': True}


def evaluate_budgeted(decision, *, budget=8, incumbent_index=4, scorer=None,
                      model_version='semantic_rule_v1', candidate_indices=None, compatible_only=False,
                      prefix_budget=None, ranking_policy='score'):
    """Rank legal observation data before any rollout; K includes incumbent04.

Only a real, still-current InitialDecision is accepted. This returns advice,
not a dispatch capability. The final original component guard is retained;
actual submission, ACK and physical outcomes remain the caller's obligation.
"""
    started = time.perf_counter_ns()
    timings = {}
    request = None
    actions = teacher.future.core.lazy.original.physics.previous.actions()
    partition = domain.partition(actions)
    result = {'schema': SCHEMA, 'status': 'unknown_unexecuted', 'requested_indices': [],
        'rows': [{'candidate_index': index, 'action': copy.deepcopy(action),
            'status': 'not_requested', 'completion': None} for index, action in enumerate(actions)],
        'groups': [], 'counts': {'requested_candidates': 0, 'context_constructions': 0,
            'initial_engines': 0, 'initial_advances': 0, 'prefix_same_resumes': 0,
            'future_forks': 0, 'future_resumes': 0, 'known_candidate_predictions': 0},
        'source_binding': {'status': 'not_bound', 'close_completed': False},
        'model_version': str(model_version), 'native_authority': False, 'dispatch_authorized': False,
        'native_protection_certified': False, 'complete_request_100ms_certified': False,
        'scope': 'Initial-only causal forecasts; proposed peer components are assumptions, not promises or native authority.'}
    try:
        with _measure(timings, 'current_origin_and_ranking'):
            origin.require_current(decision)
            audit = decision.audit_copy()
            result.update(owner=audit['owner'], initial_public_sha256=audit['public_sha256'], actual_collection_at=audit['at'])
            require(type(compatible_only) is bool, 'compatible_only_boolean')
            allowed = public_compatible_indices(audit['owner'], actions) if compatible_only else list(range(len(actions)))
            requested, scores, accounting = _requested(audit['public'], actions, budget, incumbent_index,
                scorer, model_version, candidate_indices, allowed_indices=allowed,
                prefix_budget=prefix_budget, ranking_policy=ranking_policy)
            result.update(requested_indices=list(requested), scores=scores, candidate_budget=budget,
                allocation=accounting, public_compatibility_filter={'enabled': compatible_only,
                    'contract': compatibility.CONTRACT if compatible_only else None,
                    'source': 'current owner and unchanged public action components only; no teacher or protection labels'})
            result['counts']['requested_candidates'] = len(requested)
            for index in requested:
                result['rows'][index]['status'] = 'unknown_unexecuted'
            origin.require_current(decision)
        with _measure(timings, 'source_preparation_bind_and_setup'):
            result['source_binding']['copy_metadata_preparation'] = teacher._prepare_copy_metadata()
            request = binding.bind_request()
            result['source_contract'] = source_contract(request)
        for group in partition['groups']:
            selected = tuple(index for index in group['candidate_indices'] if index in requested)
            if not selected:
                continue
            with _measure(timings, 'fresh_contexts'):
                result['counts']['context_constructions'] += 1
                context = origin.supplied_snapshot(decision)
            with _measure(timings, 'guarded_prefix_clone_and_rollout'):
                item = execute_selected_prefix(request, group, context, selected)
            result['groups'].append(item)
            for key, value in item['detail']['counts'].items():
                result['counts'][key] += value
            require(item['binding_error'] is None, 'group_binding_invalidated:' + str(item['binding_error']))
            prefix = item['detail']['prefix']
            for index in selected:
                row = result['rows'][index]
                choice = row['action']['later_action']
                suffix = item['detail']['suffixes'][choice]
                prediction = item['predictions'].get(choice)
                completion = teacher.known_completion(prediction)
                valid = (prefix.get('status') == 'supported_known_B_cut'
                    and prefix.get('isolation_basis') == execution.OWNERSHIP
                    and prefix.get('diagnostic_graphs_computed') is False and prefix.get('parent_unconsumed') is True
                    and suffix.get('status') == 'returned' and suffix.get('isolation_basis') == execution.OWNERSHIP)
                row.update(status='conditional_forecast' if valid and completion is not None else 'unknown_projection',
                    completion=completion if valid else None, prediction=prediction, execution=copy.deepcopy(suffix))
        with _measure(timings, 'final_origin'):
            origin.require_current(decision)
        result['status'] = 'conditional_forecasts_complete' if all(
            compatibility.known(result['rows'][index]) for index in requested) else 'conditional_forecasts_with_unknowns'
    except Exception:
        result.update(status='unknown_origin_or_provider', error=traceback.format_exc())
    finally:
        if request is not None:
            with _measure(timings, 'source_inspection_and_close'):
                try:
                    result['source_binding']['before_close'] = request.description()
                    uses = result['source_binding']['before_close']['proof_binding']['proof_uses']
                    require(type(uses) is int and 1 <= uses <= 1 + 2 * len(result['requested_indices']), 'bounded_proof_uses')
                    require(result['status'] != 'conditional_forecasts_complete'
                        or uses == 1 + 2 * len(result['requested_indices']), 'complete_exact_proof_uses')
                except Exception:
                    result.update(status='unknown_origin_or_provider', inspection_error=traceback.format_exc())
                finally:
                    try:
                        request.close()
                        result['source_binding']['close_completed'] = True
                    except Exception:
                        result.update(status='unknown_origin_or_provider', close_error=traceback.format_exc())
        result['source_binding']['status'] = ('closed' if result['source_binding']['close_completed'] else 'unknown_not_closed')
    if result['status'] == 'unknown_origin_or_provider':
        for index in result['requested_indices']:
            result['rows'][index].update(status='unknown_origin_or_provider', completion=None)
    result['counts']['known_candidate_predictions'] = sum(compatibility.known(row) for row in result['rows'])
    result['evaluated_candidate_count'] = result['counts']['future_resumes']
    result['evaluated_prefix_count'] = result['counts']['initial_engines']
    if 'owner' in result and result['requested_indices']:
        try:
            with _measure(timings, 'protected_selection_and_current_revalidation'):
                result['selection'] = _selection(result, decision, incumbent_index)
        except Exception:
            result.update(status='unknown_selection_or_revalidation', selection_error=traceback.format_exc())
    result['timing'] = {'exclusive_outer_stage_ns': timings, 'preseal_wall_ns': time.perf_counter_ns() - started,
        'scope': 'Disjoint outer stages; guarded_prefix_clone_and_rollout includes nested source checks. Internal clone/rollout/source attribution not separately measured; CPU/ACK/physical completion unmeasured.'}
    seal_started = time.perf_counter_ns()
    batch = BudgetedBatch(result)
    return {'batch': batch, 'compute_wall_ms': (time.perf_counter_ns() - started) / 1e6,
        'seal_wall_ms': (time.perf_counter_ns() - seal_started) / 1e6,
        'native_authority': False, 'dispatch_authorized': False, 'complete_request_100ms_certified': False}


def initial_diagnostic(decision):
    """One B-owner K4 advice-only probe inside an admitted native adapter.

The enclosing adapter must preserve native state, require_current afterwards,
and compare requested predictions with its subsequent full32 teacher. This
callback is not a saved-data capability factory or a controller replacement.
"""
    started = time.perf_counter_ns()
    origin.require_current(decision)
    audit = decision.audit_copy()
    if audit['owner'] != 'B':
        return {'status': 'not_scheduled_for_owner_A', 'model_calls': 0, 'native_authority': False}
    measured = evaluate_budgeted(decision, budget=4)
    batch = measured.pop('batch')
    measured['report'] = batch.audit_copy()
    origin.require_current(decision)
    measured['diagnostic_through_export_wall_ms'] = (time.perf_counter_ns() - started) / 1e6
    measured['status'] = measured['report']['status']
    return measured
