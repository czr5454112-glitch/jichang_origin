"""SOURCE-ONLY constructor-prelude composition; not a campaign or C loader.

The accepted timer and its original boundary remain unchanged. A new private
scheduler uses the reviewed passive prelude callable. Only that callable's NEW
instrumentation boundary is extended with the new scheduler/branch paths.
Original boundary records survive by identity, without a third warm check.
No observations, native authority, model outputs or physical policy change.
This is a serial version-closed binding, not an adversarial mutation sandbox.
"""
from __future__ import annotations

import copy
import time
from types import SimpleNamespace

from . import single_capture_static_inventory_runtime as previous
from . import constructor_prelude_instrumentation as diagnostic

SCHEMA = 'g31.single_capture.constructor_prelude_lifetime.v1'
private, require = previous.private, previous.require
metadata, verify_files = previous.metadata, previous.verify_files
paths, provider = previous.paths, previous.provider
_FIELDS = ('functions', 'namespaces', 'classes', 'locations', 'containers')


def _snapshot_domain(value):
    cls = previous.static._ProgramBoundary
    require(type(value) is cls and set(vars(value)) == set(_FIELDS),
        'prelude_exact_boundary_snapshot')
    require(type(value.functions) is list and all(type(getattr(value, name)) is tuple
        for name in _FIELDS[1:]), 'prelude_boundary_snapshot_types')


def _merge_into(target, original, extra):
    """Cold construction only; preserve every complete old record by identity.

No source record is edited, filtered, deduplicated or reconstructed. Repeated
records remain repeated checks, and their real costs stay in binding.check.
"""
    cls = previous.static._ProgramBoundary
    require(type(target) is cls and not vars(target), 'prelude_fresh_merge_target')
    _snapshot_domain(original)
    _snapshot_domain(extra)
    target.functions = [*original.functions, *extra.functions]
    for name in _FIELDS[1:]:
        setattr(target, name, getattr(original, name) + getattr(extra, name))
    _snapshot_prefix(target, original, extra)


def _snapshot_prefix(current, original, extra):
    for value in (current, original, extra):
        _snapshot_domain(value)
    for name in _FIELDS:
        actual, first, last = (getattr(value, name) for value in (current, original, extra))
        require(len(actual) == len(first) + len(last)
            and all(a is b for a, b in zip(actual, (*first, *last))),
            'prelude_complete_snapshot_prefix:' + name)


def compose(live, static_record, prelude_record, *, clock=time.perf_counter_ns):
    """Cold bind; callers must charge this complete call to provider setup.

Synthetic callers may supply labelled Python-only compositions. This function
does not validate or manufacture C authority, and never changes the normalizer.
"""
    require(type(prelude_record) is dict and type(prelude_record.get('rows')) is list
        and not prelude_record['rows'], 'prelude_fresh_lifetime_rows')
    prelude_record['cold_started_ns'] = clock()
    try:
        accepted = previous.compose(live, static_record, clock=clock)
        before = accepted.constructor_timer.boundary
        bound = diagnostic.bind_timer(accepted.constructor_timer, prelude_record['rows'])
        run = private(accepted.run_continuation, {'ActualAdvanceChain': bound.call})
        run._source_proof = copy.deepcopy(accepted.run_continuation._source_proof)
        branch = private(accepted.run_branch, {'run_continuation': run})

        # Allocate the exact target first so its identity is stable throughout
        # cold construction. Its contents are completed before any check/use.
        merged = object.__new__(previous.static._ProgramBoundary)
        guard = SimpleNamespace(original=bound.instrumentation_boundary,
            extra=None, merged=merged)
        result = SimpleNamespace(accepted=accepted, prelude=bound, guard=guard,
            original_timer_boundary=before, static_binding=accepted.static_binding,
            constructor_timer=accepted.constructor_timer,
            run_continuation=run, run_branch=branch)
        extra = previous.static._ProgramBoundary(
            functions=(run, branch, compose, composition_proof, _snapshot_domain,
                       _snapshot_prefix, _merge_into),
            locations=((guard, 'original'), (guard, 'merged'),
                (accepted.constructor_timer, 'boundary'),
                (result, 'accepted'), (result, 'prelude'), (result, 'guard')),
            containers=(vars(result), run._source_proof))
        guard.extra = extra
        _merge_into(merged, guard.original, extra)

        # These are new private binding objects, not the accepted timer or any
        # imported module/class. The frozen prelude proof still checks the same
        # generated function/hooks and this exact boundary/check class.
        bound.call.boundary = merged
        bound.call._boundary_expected = merged
        bound.instrumentation_boundary = merged
        proof = composition_proof(result)
    except BaseException as error:
        try:
            prelude_record.update(cold_status='failed', cold_finished_ns=clock(),
                cold_error_type=type(error).__name__)
        except BaseException:
            # A new diagnostic export/clock failure cannot replace the original
            # source/setup exception. Incomplete cold metadata remains unknown.
            pass
        raise
    prelude_record.update(cold_status='returned', cold_finished_ns=clock(),
        binding_proof=proof)
    # The original static record retains all its original fields/clocks and
    # constructor rows. Its full source proof now explicitly includes the new
    # private callable, as does the enclosing accepted C record.
    static_record['binding_proof'] = proof
    return result


def composition_proof(value):
    accepted, bound, guard = value.accepted, value.prelude, value.guard
    original_proof = previous.composition_proof(accepted)
    require(value.constructor_timer is accepted.constructor_timer is bound.timer
        and bound.timer.boundary is value.original_timer_boundary
        and value.static_binding is accepted.static_binding,
        'prelude_accepted_timer_or_boundary_changed')
    previous.static.owned._delta(accepted.run_continuation, value.run_continuation,
        {'ActualAdvanceChain': bound.call})
    previous.static.owned._delta(accepted.run_branch, value.run_branch,
        {'run_continuation': value.run_continuation})
    require(value.run_continuation._source_proof == accepted.run_continuation._source_proof
        and value.run_continuation.__globals__['publish_root']
            is accepted.run_continuation.__globals__['publish_root'],
        'prelude_original_scheduler_or_publisher')
    require(bound.call.boundary is bound.call._boundary_expected
        is bound.instrumentation_boundary is guard.merged,
        'prelude_actual_guard_identity')
    _snapshot_prefix(guard.merged, guard.original, guard.extra)
    require(any(row[0] is value.run_continuation for row in guard.extra.functions)
        and any(row[0] is value.run_branch for row in guard.extra.functions),
        'prelude_new_actual_paths_not_guarded')
    detail = diagnostic.source_proof(bound)
    guard.merged.check()
    return {**original_proof,
        'prelude_instrumentation': detail,
        'original_timer_boundary_identity_preserved': True,
        'complete_new_guard_snapshot_prefix_by_identity': True,
        'new_run_and_branch_in_existing_instrumentation_check': True,
        'third_warm_program_check_added': False,
        'original_constructor_clock_and_exact_return_type_unchanged': True,
        'all_new_diagnostic_cost_charged_in_complete_root': True,
        'finalization_or_collection_candidate_changed': False,
        'cold_binding_resource_failure_timing_equivalent': False,
        'actual18_or_C_execution_established': False}


class Provider(previous.Provider):
    def __init__(self, contract, output, write):
        self.prelude_record = {'schema': SCHEMA, 'status': 'unknown_setup',
            'cold_status': 'not_started', 'rows': [], 'diagnostic_failed': None,
            'diagnostic_errors': [], 'no_per_root_disk_write': True,
            'complete_root_budget_unchanged': True,
            'constructor_CPU_or_inventory_only_claimed': False,
            'finalization_candidate_added': False,
            'actual_direct_C_supported': None}
        super().__init__(contract, output, write)

    def save(self):
        previous.Provider.save(self)
        binding = getattr(self, 'binding', None)
        if binding is not None:
            self.prelude_record['diagnostic_failed'] = binding.prelude.probe.failed
            self.prelude_record['diagnostic_errors'] = copy.deepcopy(binding.prelude.probe.errors)
        self.prelude_record['status'] = self.record['status']
        self.write(self.output/'constructor_prelude_lifetime.json', self.prelude_record)

    def open(self, schema):
        def new_compose(live, record):
            return compose(live, record, self.prelude_record)
        function = private(previous.Provider.open, {
            'compose': new_compose, 'composition_proof': composition_proof})
        previous.static.owned._delta(previous.Provider.open, function,
            {'compose': new_compose, 'composition_proof': composition_proof})
        return function(self, schema)


def source_proof():
    require(Provider.close is previous.Provider.close
        and Provider.failed is previous.Provider.failed, 'prelude_provider_close_changed')
    return {'schema': SCHEMA,
        'previous_provider': previous.source_proof(),
        'frozen_prelude_module': diagnostic.SCHEMA,
        'same_C_open_code_private_compose_and_proof_only': True,
        'same_C_module_spec_loader_DLL_files_and_close': True,
        'original_timer_boundary_unmodified': True,
        'new_guard_original_prefix_and_path_extension': True,
        'no_per_root_disk_write': True,
        'new_campaign_and_saved_verifier_supplied': False,
        'C_native_model_or_actual18_execution': False,
        'complete100ms_or_speed_claim': False}
