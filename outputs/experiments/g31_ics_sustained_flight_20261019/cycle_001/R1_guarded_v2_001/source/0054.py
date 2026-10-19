"""Restricted MODEL later-action fork. No native/remote-state authority.

Only phase B after collect/before action is supported. All past actions and
model control frames remain unchanged. Old same-action APIs are not modified.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import math
from pathlib import Path
from types import FunctionType
from . import live_obligation_conditional_continuation as core

VERSION = 'g31.conditional_future_later_fork.v1'
CORE_SHA = '31ad32a9a74d90dc64400b801a16fceb73abc73db1d9cf9850aa8fa3f4fb6b63'
LATER = ('native_default', 'prefer_8')
FIELDS = ('initial_action', 'empty_departure', 'return_delay', 'later_action')
OBSOLETE = ('return_decision', 'later_decision')
_ISSUER = object()


def require(ok, reason):
    if not ok: raise ValueError('future_later_fork:'+reason)


def finite(value): return type(value) in (int, float) and math.isfinite(value)


def _parents(tree):
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def action_uses(tree):
    """Reject whole-action escapes/dynamic keys instead of assuming no read."""
    parents = _parents(tree); rows = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == 'self' and node.attr == 'action'): continue
        parent = parents[node]
        if isinstance(node.ctx, ast.Store):
            require(isinstance(parent, ast.Assign) and len(parent.targets) == 1
                and core.dump(parent.targets[0]) == core.dump(node)
                and ast.unparse(parent.value) == 'copy.deepcopy(action)', 'whole_action_store')
            rows.append({'field': '*constructor_copy*', 'access': 'Store'})
        else:
            require(isinstance(parent, ast.Subscript) and parent.value is node
                and isinstance(parent.slice, ast.Constant) and type(parent.slice.value) is str
                and parent.slice.value in FIELDS, 'whole_action_escape_or_dynamic_key')
            rows.append({'field': parent.slice.value, 'access': type(parent.ctx).__name__})
    return rows


def _effective_methods():
    result = {}
    for cls in core.Projection.__mro__:
        for name, value in vars(cls).items():
            if isinstance(value, staticmethod): value = value.__func__
            if isinstance(value, FunctionType) and name not in result: result[name] = value
    return result


def _tree(function):
    if function is core.lazy.Projection.run: return core.generated_run_tree()[0]
    if function is core.lazy.Projection.activate: return core.lazy_activate_tree()
    return core.tree_of(function)


def analyze_decide(tree):
    """The one live later read must be in the post-collect phase-B tail."""
    body = tree.body[0].body
    collect = core.statements('info,screen,view=self.collect(owner,p)')[0]
    positions = [i for i, node in enumerate(body) if core.dump(node) == core.dump(collect)]
    require(len(positions) == 1, 'one_collect')
    require(not any(row['field'] == 'later_action'
        for row in action_uses(ast.Module(body=body[:positions[0]+1], type_ignores=[]))),
        'later_read_before_collection')
    reads = [node for node in ast.walk(tree) if isinstance(node, ast.Subscript)
        and ast.unparse(node) == "self.action['later_action']"]
    require(len(reads) == 1 and isinstance(reads[0].ctx, ast.Load), 'one_live_later_read')
    parents = _parents(tree); current = reads[0]; lineage = []
    while current in parents:
        current = parents[current]; lineage.append(current)
    tests = [ast.unparse(node.test) for node in lineage if isinstance(node, ast.If)]
    require("known and self.action['later_action'] == 'prefer_8'" in tests
        and "p['phase'] == 'first_return'" in tests, 'later_read_branch')
    phase = next(node for node in lineage if isinstance(node, ast.If)
        and ast.unparse(node.test) == "p['phase'] == 'first_return'")
    require(any(reads[0] is node for item in phase.orelse for node in ast.walk(item)),
        'later_read_is_first_return_else_only')
    require(any(isinstance(node, ast.Return) for item in body[positions[0]+1:]
        if isinstance(item, ast.If) and ast.unparse(item.test) == "screen['status'] == 'conditional_retry_admissible'"
        for node in ast.walk(item)), 'fresh_pair_returns_before_read')
    return {'collect_before_live_read': True, 'fresh_pair_returns_before_live_read': True,
        'live_read_only_nonreturn_known_tail': True}


def _source_inventory():
    require(hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest() == CORE_SHA, 'core_source')
    _, core_proof = core.build_parts()
    methods = _effective_methods(); inventory = {}
    for name, function in methods.items():
        uses = action_uses(_tree(function))
        if uses: inventory[name] = uses
    require(set(inventory) == {'run', 'decide'}, 'unreviewed_effective_action_consumer')
    # The effective constructor delegates to this inherited constructor, which
    # translates only empty_departure into the legacy action. Later mode there
    # is fixed native_keep, independent of the requested future preference.
    native = core.lazy.original.physics.previous.original.Projection
    live = core.lazy.original.physics.previous.Projection
    allowed = {native.__init__, native.run, core.lazy.original.Projection.run,
        live.request, core.lazy.original.Projection.decide}
    super_uses = {}
    for cls in core.Projection.__mro__:
        for name, function in vars(cls).items():
            if isinstance(function, staticmethod): function = function.__func__
            if not isinstance(function, FunctionType): continue
            uses = action_uses(_tree(function))
            if uses:
                require(function in allowed, 'unreviewed_super_action_consumer')
                super_uses[function.__module__+'.'+function.__qualname__] = uses
    require(action_uses(core.tree_of(live.request)) == [{'field': 'return_delay', 'access': 'Load'}],
        'inherited_request_consumes_later')
    actions = core.tree_of(core.lazy.original.physics.previous.actions)
    products = [node for node in ast.walk(actions) if isinstance(node, ast.Call)
        and ast.unparse(node.func) == 'itertools.product']
    require(len(products) == 1 and len(products[0].args) == 4
        and isinstance(products[0].args[-1], ast.Tuple)
        and tuple(node.value for node in products[0].args[-1].elts) == LATER,
        'later_choices_not_independent_declared_domain')
    for cls in core.Projection.__mro__:
        constructor_function = vars(cls).get('__init__')
        if not isinstance(constructor_function, FunctionType): continue
        require(not any(isinstance(node, ast.Subscript) and ast.unparse(node) == "action['later_action']"
            for node in ast.walk(core.tree_of(constructor_function))), 'constructor_reads_later_field')
    constructor = core.tree_of(native.__init__)
    require(action_uses(constructor) == [{'field': '*constructor_copy*', 'access': 'Store'}],
        'native_constructor_action_use')
    calls = [node for node in ast.walk(constructor) if isinstance(node, ast.Call)
        and ast.unparse(node.func) == 'super().__init__']
    require(len(calls) == 1 and ast.unparse(calls[0].args[1]) ==
        "{'initial_next': 1, 'departure': action['empty_departure'], 'later_mode': 'native_keep'}",
        'legacy_action_independent_of_later')
    require(core.Projection.notify_local_lifecycle is core.lazy.original.Projection.notify_local_lifecycle,
        'obsolete_scheduler_override')
    life = core.tree_of(core.Projection.notify_local_lifecycle)
    require(len(life.body[0].body) == 1 and isinstance(life.body[0].body[0], ast.Pass),
        'obsolete_scheduler_not_noop')
    scheduled = []
    for name, function in methods.items():
        for node in ast.walk(_tree(function)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'schedule':
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and argument.value in OBSOLETE:
                        scheduled.append(name)
    require(not scheduled, 'obsolete_later_event_is_scheduled')
    decision_proof = analyze_decide(core.tree_of(core.lazy.original.Projection.decide))
    run = core.generated_run_tree()[0]; parents = _parents(run)
    later = [node for node in ast.walk(run) if isinstance(node, ast.Subscript)
        and ast.unparse(node) == "self.action['later_action']"]
    require(len(later) == 1, 'one_obsolete_run_read')
    cursor = later[0]; tests = []
    while cursor in parents:
        cursor = parents[cursor]
        if isinstance(cursor, ast.If): tests.append(ast.unparse(cursor.test))
    require("kind == 'later_decision'" in tests, 'obsolete_read_not_isolated')
    capture_tree = ast.parse(Path(core.lazy.original.captures.__file__).read_bytes())
    require(not any(isinstance(node, ast.Attribute) and node.attr == 'action'
        for node in ast.walk(capture_tree)), 'capture_reads_action')
    return {'schema': VERSION, 'core_source_sha256': CORE_SHA, 'core_control_flow_proof': core_proof,
        'effective_action_uses': inventory, 'declared_super_action_uses': super_uses,
        'both_later_choices_in_independent_cartesian_domain': True,
        'constructor_legacy_action_later_independent': True,
        'obsolete_scheduler_effective_noop': True, 'obsolete_event_producers': scheduled,
        'obsolete_run_later_read_only_in_unreachable_event_kind': True, **decision_proof,
        'capture_does_not_read_action': True, 'native_authority': False,
        'coverage_of_unknown_remote_states_certified': False}


_METHODS = _effective_methods()
_PARTS = dict(core.PARTS)
_CORE_FUNCTIONS = {name: getattr(core, name) for name in ('validate', 'fork_conditional', 'resume_same_action', '_drive')}
_CODES = {function: function.__code__ for function in
    (*_METHODS.values(), *_PARTS.values(), *_CORE_FUNCTIONS.values())}


def source_proof():
    require(_effective_methods() == _METHODS and all(core.PARTS.get(k) is v for k, v in _PARTS.items())
        and set(core.PARTS) == set(_PARTS)
        and all(getattr(core, k) is v for k, v in _CORE_FUNCTIONS.items())
        and all(function.__code__ is code for function, code in _CODES.items()), 'loaded_source_binding_changed')
    return copy.deepcopy(_source_inventory())


def _cut(state):
    core.validate(state, pc=core.PC)
    engine, frames = state._engine, state._frames
    decision = frames['decide']
    pending, view, info, screen = (decision[k] for k in ('p', 'view', 'info', 'screen'))
    require(decision['owner'] == 'B' and pending['phase'] == 'first_reuse_route', 'unsupported_phase_or_owner')
    require(type(engine.action) is dict and set(engine.action) == set(FIELDS)
        and type(engine.action['later_action']) is str and engine.action['later_action'] in LATER,
        'action_domain')
    require(info.get('status') == 'conditional_validated_later_v3_data'
        and screen.get('status') == 'not_admitted', 'unknown_or_recollecting_cut')
    require(finite(engine.time) and finite(view['now']) and view['owner_id'] == 'B' and view['now'] == engine.time
        and frames['run']['event'][0] == engine.time, 'stale_cut_epoch')
    require(all(finite(pending[k]) for k in ('at', 'deadline', 'policy_quiet_since'))
        and pending['at'] <= engine.time < pending['deadline']
        and finite(decision['s']['quiet']) and decision['s']['quiet'] <= engine.time, 'expired_cut')
    current = core.lazy.original.policy.local_target(view, pending['trigger_tray'], pending['phase'])
    tray = engine.trays['L']
    require(tray['node'] == current['node'] == 7 and tray['mode'] == current['mode'] == 'loaded'
        and tray['job'] == current['business_bag_id'] == 'reuse1'
        and tray['edge_from'] == tray['edge_to'] == -1
        and tray['generation'] == current['generation']
        and tray['traversal_id'] == current['traversal_id'], 'current_model_L_changed')
    bound = info['bundle']['trays']['L']['service_ready_at']
    require(finite(bound) and engine.time + core.lazy.original.WIRE < bound, 'expired_route_wire_window')
    require('reuse1' not in engine.choice_jobs, 'later_action_already_consumed')
    previous = [row for row in engine.collection_trace if row.get('phase') == 'first_reuse_route']
    require(type(pending['recollection_index']) is int and pending['recollection_index'] in (0, 1)
        and len(previous) == pending['recollection_index']
        and all(row.get('disposition') == 'one_fresh_pair_requested' for row in previous),
        'earlier_phase_B_action_or_missing_prefix')
    require(not any(row.get('kind') == 'route' and row['request'].get('business_bag_id') == 'reuse1'
        for row in engine.client_rows.values()), 'prior_reuse_route_command')
    require(not any(row[3] in OBSOLETE for row in engine.events), 'obsolete_action_event_in_heap')
    return {'at': engine.time, 'phase': pending['phase'], 'owner': decision['owner'],
        'request_id': pending['request_id'], 'recollection_index': pending['recollection_index'],
        'retained_service_bound': bound, 'original_action_bytes': state._action_bytes}


class FutureLaterFork:
    """Factory-owned pure branch, not a native/cross-process capability."""
    def __init__(self, state, evidence, before, after, issuer):
        require(issuer is _ISSUER, 'factory_only')
        self._state, self._evidence = state, evidence
        self._before, self._after = before, after
        self._consumed = False

    def description(self):
        return {'schema': VERSION, 'program_counter': core.PC, 'consumed': self._consumed,
            'model_time': self._evidence['at'], 'owner': 'B', 'phase': 'first_reuse_route',
            'before_action': copy.deepcopy(self._before), 'after_action': copy.deepcopy(self._after),
            'changed_fields': [k for k in FIELDS if self._before[k] != self._after[k]],
            'native_authority': False, 'same_source_model_history_only': True,
            'unknown_remote_state_coverage_certified': False}


def fork_later_action(state, later_action):
    """One graph clone, then one explicit authorized future-field replacement."""
    source_proof(); evidence = _cut(state)
    require(type(later_action) is str and later_action in LATER, 'undeclared_future_action')
    child = core.fork_conditional(state)
    before = copy.deepcopy(child._engine.action)
    child._engine.action['later_action'] = later_action
    after = copy.deepcopy(child._engine.action)
    require(core.lazy.original.context.encoded({k:before[k] for k in FIELDS if k != 'later_action'})
        == core.lazy.original.context.encoded({k:after[k] for k in FIELDS if k != 'later_action'}),
        'past_action_changed')
    # Explicit new contract: create a NEW fixed-action continuation after the
    # restricted replacement. Do not change or bypass old validate/drive code.
    child = core.Continuation(child._engine, child._frames, core.lazy.original.context.encoded(after))
    core.validate(child, pc=core.PC)
    return FutureLaterFork(child, evidence, before, after, _ISSUER)


def resume_future_later(branch):
    require(type(branch) is FutureLaterFork and not branch._consumed, 'invalid_or_consumed_future_fork')
    source_proof(); evidence = _cut(branch._state)
    require(evidence['at'] == branch._evidence['at']
        and evidence['request_id'] == branch._evidence['request_id']
        and core.lazy.original.context.encoded(branch._state._engine.action) == core.lazy.original.context.encoded(branch._after),
        'changed_future_fork')
    branch._consumed = True
    # Exact four-frame tail, once, without a second collection. A later point
    # is returned under the new fixed action's ordinary same-action contract.
    return core.resume_same_action(branch._state)


def proposed_six_pair_plan():
    """Reviewable next experiment, not a driver or permission to execute."""
    order = ['mechanism/vector_00', 'mechanism/vector_25', 'no_overlap/vector_00',
        'no_overlap/vector_25', 'insufficient_advance/vector_00', 'insufficient_advance/vector_17']
    counterparts = ['mechanism/vector_01', 'mechanism/vector_24', 'no_overlap/vector_01',
        'no_overlap/vector_24', 'insufficient_advance/vector_01', 'insufficient_advance/vector_16']
    return {'schema': VERSION+'.proposed_six_pairs', 'status': 'source_plan_only_not_dispatched',
        'order': order, 'counterpart_order': counterparts, 'prefix_runs': 6,
        'supported_known_B_cut_budget': 6, 'paired_suffix_budget': 12,
        'same_and_changed_later_choices': list(LATER),
        'initial_input_source': 'live_phase_b_pause_prepare_001 frozen six initial supplied contexts',
        'comparison_source': 'live_communication_lazy_prepare_001 frozen complete96 predictions',
        'fixed_earlier_fields': list(FIELDS[:-1]), 'shared_owned_seconds_proposed': 120.,
        'cost_basis': 'Prior same-six four-frame execution took18.6451326s for39resumes. New6prefix/12suffix clones, repeated fullsource guards, outputs and all comparison costs must be measured; this is a bound proposal, not a guaranteed runtime.',
        'gate': 'At exactly the first known first_reuse_route post-collect/pre-tail point, clone the entire engine+frames graph separately for each declared later choice; unknown earlier points resume the original fixed action and remain in the denominator.',
        'comparisons': ['Same choice complete JSON bytes against its existing frozen prediction.',
            'Changed choice complete JSON bytes against the declared counterpart; no new initial run of counterpart.',
            'Exact physical/communication/collection chronology, unchanged prefix and internal alias isolation.',
            'Unknown/expired cut or any mismatch retained as unknown; no action-specific timing patch.'],
        'forbidden': ['new native execution', 'native forks', 'actual opaque-ID mapping',
            'replaying or rerunning a prefix as continuation', 'past action changes',
            'extra collections/retries', 'full32 or remote-belief coverage claims', '100ms/protection certification'],
        'retrospective_comparands_not_heldout': True, 'native_calls': 0}
