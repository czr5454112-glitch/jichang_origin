"""Cold static-inventory composition and charged constructor diagnostics.

The accepted C provider is opened/closed by its original code. This module does
not load an extension on import. Constructor records are diagnostics, not a
native capability, and do not certify any CPU-time attribution. No record keeps
a root, client, session, policy, observation, ACK or result reference.
"""
from __future__ import annotations
import copy
import time
from types import SimpleNamespace

from . import single_capture_owned_codec_runtime as original
from . import initial_owner_route_static_inventory as static

require, private = original.require, static.private
SCHEMA = 'g31.single_capture.static_inventory_lifetime.v1'
metadata, verify_files = original.metadata, original.verify_files
paths, provider = original.paths, original.provider


def _root_fields(root):
    # This is a passive projection of already-owned instance slots. It performs
    # no native query and never invokes a property or a user-defined getattr.
    try:
        values = object.__getattribute__(root, '__dict__')
    except AttributeError:
        values = {}
    if type(values) is not dict:
        values = {}
    names = {'request_id': str, 'started_ns': int, 'deadline_ns': int, 'cutoff_ns': int}
    return {name: values.get(name) if type(values.get(name)) is kind else None
        for name, kind in names.items()}


class ConstructorTimer:
    """One serial binding; the returned object is the original exact class."""
    def __init__(self, exact_class, rows, clock=time.perf_counter_ns):
        self.exact_class, self.rows, self.clock = exact_class, rows, clock
        self.boundary = None

    def __call__(self, session, client, root, policies):
        if self.boundary is not None:
            self.boundary.check()
        row = {'ordinal': len(self.rows), 'root': _root_fields(root),
            'status': 'unknown_constructor_started', 'error_type': None}
        self.rows.append(row)
        # Metadata/allocation before this clock remains inside the original
        # complete root. The interval below is the complete constructor call,
        # not a sample of inventory alone or an event-time difference.
        row['started_ns'] = self.clock()
        try:
            value = self.exact_class(session, client, root, policies)
        except BaseException as error:
            row['finished_ns'] = self.clock()
            row['status'], row['error_type'] = 'constructor_raised', type(error).__name__
            raise
        else:
            row['finished_ns'] = self.clock()
            if type(value) is not self.exact_class:
                row['status'], row['error_type'] = 'constructor_raised', 'ValueError'
                row['failure_stage'] = 'exact_return_type'
                raise ValueError('static_runtime_constructor_wrong_return_type')
            row['status'] = 'constructor_returned'
            return value


def compose(live, record, *, clock=time.perf_counter_ns):
    """Explicit source composition; live must come from the accepted binder.

Tests may pass a separately labelled Python-only fixture. This function's
shape check never turns that fixture into verified C support.
"""
    record['cold_bind_started_ns'] = clock()
    try:
        bound = static.bind(live)
        timer = ConstructorTimer(bound.ActualAdvanceChain, record['constructors'], clock)
        run = private(bound.run_continuation, {'ActualAdvanceChain': timer})
        run._source_proof = copy.deepcopy(bound.run_continuation._source_proof)
        original_branch = static.branch_function(bound)
        branch = private(original_branch, {'run_continuation': run})
        value = SimpleNamespace(static_binding=bound, constructor_timer=timer,
            run_continuation=run, run_branch=branch, original_branch=original_branch)
        # Freeze only the new program bindings, not the append-only diagnostic
        # rows. No source read/hash/compile or request state is cached here.
        timer.boundary = static._ProgramBoundary(
            functions=(_root_fields, run, branch), classes=(ConstructorTimer,),
            locations=((timer, 'exact_class'), (timer, 'rows'), (timer, 'clock'),
                       (time, 'perf_counter_ns')),
            containers=(vars(value),))
        proof = composition_proof(value)
    except BaseException as error:
        record.update(cold_bind_finished_ns=clock(), cold_bind_status='failed',
            cold_bind_error_type=type(error).__name__)
        raise
    record.update(cold_bind_finished_ns=clock(), cold_bind_status='returned',
        binding_proof=proof)
    return value


def composition_proof(value):
    bound = value.static_binding
    static_proof = static.binding_proof(bound)
    static.owned._delta(bound.run_continuation, value.run_continuation,
        {'ActualAdvanceChain': value.constructor_timer})
    static.owned._delta(value.original_branch, value.run_branch,
        {'run_continuation': value.run_continuation})
    require(value.constructor_timer.exact_class is bound.ActualAdvanceChain
        and value.constructor_timer.__class__ is ConstructorTimer
        and type(value.constructor_timer.boundary) is static._ProgramBoundary,
        'static_runtime_exact_constructor')
    value.constructor_timer.boundary.check()
    require(value.run_continuation._source_proof == bound.run_continuation._source_proof
        and value.run_continuation.__globals__['publish_root'] is bound.publish_root,
        'static_runtime_scheduler_or_publisher')
    require(bound._actual_root_drain.__globals__['ActualAdvanceChain'] is bound.ActualAdvanceChain,
        'static_runtime_exact_drain')
    return {'schema': 'g31.single_capture.static_inventory_runtime_source.v1',
        'static_inventory': static_proof,
        'same_original_complete_runtime_query_proof': True,
        'scheduler_code_defaults_closure_full_globals_exact_except_constructor': True,
        'branch_code_defaults_closure_full_globals_exact_except_run': True,
        'constructor_callable_returns_reviewed_exact_class': True,
        'constructor_class_cell_dynamic_guards_and_exact_drain_unchanged': True,
        'publisher_collection_native_policy_and_clocks_unchanged': True,
        'constructor_metadata_clock_append_cost_in_complete_root': True,
        'additional_timing_binding_boundary_checked_in_root': True,
        'constructor_interval_is_wall_not_CPU_or_inventory_only': True,
        'sidecar_contains_no_runtime_authority': True,
        'per_root_disk_write_added': False, 'actual_direct_C_support_measured': False}


class Provider(original.Provider):
    def __init__(self, contract, output, write):
        self.static_record = {'schema': SCHEMA, 'status': 'unknown_setup',
            'cold_bind_status': 'not_started', 'constructors': [],
            'constructor_interval_scope': 'Full exact constructor call wall; metadata and append also remain inside the complete root.',
            'cold_binding_charged_to_campaign': True, 'per_root_cycle_cleanup_claimed': False,
            'constructor_CPU_or_inventory_only_claimed': False,
            'constructor_diagnostic_instrumentation_added': True,
            'inherited_C_record_no_instrumentation_field_scope': 'No C support/fallback instrumentation or duplicate C preflight; this separate constructor sidecar is explicitly added and charged.',
            'no_per_root_disk_write': True, 'actual_direct_C_supported': None}
        super().__init__(contract, output, write)

    def save(self):
        # Retain the accepted provider's file/shape; add one separate sidecar
        # at its original setup/close/failure save sites, never per root.
        original.Provider.save(self)
        self.static_record['status'] = self.record['status']
        self.write(self.output/'static_inventory_lifetime.json', self.static_record)

    def open(self, schema):
        def bind(candidate):
            live = original.binding.bind(candidate)
            return compose(live, self.static_record)
        facade = SimpleNamespace(**{**vars(original.binding), 'bind': bind,
            'branch_function': lambda value: value.run_branch,
            'binding_proof': composition_proof})
        implementation = private(original.Provider.open, {'binding': facade})
        static.owned._delta(original.Provider.open, implementation, {'binding': facade})
        return implementation(self, schema)


def source_proof():
    require(Provider.close is original.Provider.close and Provider.failed is original.Provider.failed,
        'static_runtime_changed_provider_close')
    return {'schema': 'g31.single_capture.static_inventory_provider_source.v1',
        'accepted_C_open_code_only_private_binding_facade': True,
        'accepted_C_module_spec_loader_DLL_and_all_file_checks_retained': True,
        'accepted_C_close_and_failure_code_unchanged': True,
        'cold_static_binding_and_complete_constructor_timings': True,
        'same_C_original_fallback_counts_remain_unknown': True,
        'no_C_native_model_load_on_source_proof': True,
        'complete100ms_or_speed_claim': False}
