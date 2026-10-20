"""Unexecuted per-full32 integration draft for the frozen owned runtime.

Only future fork/resume proof calls use the bound facade. The exact existing
execute_group code, its durable saver, independent contexts, dynamic cuts and
whole graph copies remain. This is not a campaign entry point: real v3
dependency acceptance and focused integration tests are still prerequisites.
"""
from __future__ import annotations
import copy
import time
import traceback
from types import FunctionType, SimpleNamespace

from . import live_obligation_bound_future_fork_v3 as binding
from . import live_obligation_owned_prefix_evaluator as runtime
from . import validate_owned_full32_runtime as conformance

VERSION = 'g31.bound_owned_runtime.private_case_v3.draft1'
require = runtime.require
_FUNCTIONS = {
    'runtime_group': runtime.execute_group,
    'original_group': conformance.execute_group,
    'owned_run': runtime._run,
    'owned_group': runtime._group,
    'point': runtime._point,
    'terminal': runtime._terminal,
}
_CODES = {name: fn.__code__ for name, fn in _FUNCTIONS.items()}
_SAVE_CODE = conformance._SAVE_CODE


def _clone(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def _same_private(function, reference, namespace, changes):
    require(function.__code__ is reference.__code__ and function.__defaults__ is reference.__defaults__
        and function.__kwdefaults__ is reference.__kwdefaults__ and function.__closure__ is reference.__closure__
        and function.__globals__ is namespace, 'bound_runtime_exact_function')
    require(set(namespace) == set(reference.__globals__)
        and all(namespace[k] is value for k, value in reference.__globals__.items() if k not in changes)
        and all(namespace[k] is value for k, value in changes.items()), 'bound_runtime_complete_private_globals')


def source_proof():
    """Identity-only integration description; does not invoke original proof."""
    actual = {'runtime_group': runtime.execute_group, 'original_group': conformance.execute_group,
        'owned_run': runtime._run, 'owned_group': runtime._group,
        'point': runtime._point, 'terminal': runtime._terminal}
    require(all(actual[name] is fn and fn.__code__ is _CODES[name] for name, fn in _FUNCTIONS.items())
        and conformance._SAVE_CODE is _SAVE_CODE, 'bound_runtime_original_code_identity')
    return {'schema': VERSION,
        'exact_original_owned_execute_group_code': True,
        'exact_original_conformance_execute_group_code': True,
        'runtime_execute_group_private_changes': ['future'],
        'conformance_execute_group_private_changes': ['runtime'],
        'original_owned_run_points_terminal_dynamic_guards_unchanged': True,
        'original_durable_save_code_unchanged': True,
        'request_scope': 'one declared full32, sixteen independent initial contexts, thirty-two complete clones',
        'proof_budget': {'cold_bind': 1, 'setup_warm': 1, 'operation_warm_maximum': 64, 'total_warm_maximum': 65},
        'outside_campaign_source_checks_retained_and_separately_charged': True,
        'input_context_observation_or_model_state_cache': False,
        'native_authority': False, 'actual_integration_validated': False, '100ms_certified': False}


class BoundCaseRuntime:
    """Exactly one owned full32 proof lifetime; no target or data in factory.

The caller constructs this inside the shared whole-run clock, emits complete
failure rows if construction fails, and always calls close in finally. There
is no retry/new binding inside a case. A different case gets a fresh instance.
"""
    def __init__(self, expected_proof):
        # expected_proof is used only to compare source verification, never to
        # seed an engine or to fabricate a successful proof. It is frozen audit
        # evidence already checked by the campaign's immutable plan boundary.
        self._started_ns = time.perf_counter_ns()
        self._next = 0
        self._closed = False
        self._failed = False
        self._handle = None
        self._setup = {'status': 'unknown_setup', 'cold_bind_attempts': 0, 'setup_warm_attempts': 0}
        try:
            source_proof()
            before = time.perf_counter_ns(); self._setup['cold_bind_attempts'] = 1
            try:
                self._handle = binding.bind_request()
            finally:
                self._setup['cold_bind_ns'] = time.perf_counter_ns() - before
            self._facade = self._handle.facade
            before = time.perf_counter_ns(); self._setup['setup_warm_attempts'] = 1
            try:
                proof = self._facade.source_proof()
            finally:
                self._setup['setup_warm_ns'] = time.perf_counter_ns() - before
            require(conformance.bytes_of(proof) == conformance.bytes_of(expected_proof),
                'bound_runtime_full_setup_proof_bytes')
            self._runtime_globals = {**runtime.execute_group.__globals__, 'future': self._facade}
            self._runtime_execute = _clone(runtime.execute_group, self._runtime_globals)
            self._runtime_facade = SimpleNamespace(**vars(runtime))
            self._runtime_facade.future = self._facade
            self._runtime_facade.execute_group = self._runtime_execute
            self._group_globals = {**conformance.execute_group.__globals__, 'runtime': self._runtime_facade}
            self._group_execute = _clone(conformance.execute_group, self._group_globals)
            self.check_integration()
            self._setup['status'] = 'bound_exact_setup_proof'
            self._setup['description'] = self._handle.description()
        except BaseException:
            self._failed = True
            self._setup['error'] = traceback.format_exc()
            self._setup['status'] = 'unknown_setup_failed'
            # Construction failure does not lose its own report. The caller
            # can save setup_copy and preserve every unevaluated candidate.
            if self._handle is not None:
                try:
                    self._handle.close()
                except BaseException:
                    self._setup['close_after_failure_error'] = traceback.format_exc()
            self._closed = True
        finally:
            self._setup['setup_total_ns'] = time.perf_counter_ns() - self._started_ns

    def setup_copy(self):
        return copy.deepcopy(self._setup)

    def check_integration(self):
        try:
            require(not self._closed and not self._failed and self._handle is not None,
                'bound_runtime_closed_or_failed')
            source_proof()
            self._handle.check_integration()
            _same_private(self._runtime_execute, runtime.execute_group,
                self._runtime_globals, {'future': self._facade})
            _same_private(self._group_execute, conformance.execute_group,
                self._group_globals, {'runtime': self._runtime_facade})
            require(set(vars(self._runtime_facade)) == set(vars(runtime))
                and all(vars(self._runtime_facade)[key] is value for key, value in vars(runtime).items()
                    if key not in ('future', 'execute_group'))
                and self._runtime_facade.future is self._facade
                and self._runtime_facade.execute_group is self._runtime_execute,
                'bound_runtime_complete_facade')
        except BaseException:
            self._failed = True
            if self._handle is not None:
                self._handle._proof._active = False
            raise

    def execute_group(self, group, make_context, save_prediction):
        """Unchanged context callback/guard/model and saver; no audit target."""
        self.check_integration()
        require(type(group) is dict and type(group.get('prefix_index')) is int
            and group['prefix_index'] == self._next and self._next < 16,
            'bound_runtime_exact_prefix_order_no_retry')
        # Claim before execution, so errors cannot cause an implicit retry.
        self._next += 1
        try:
            result = self._group_execute(group, make_context, save_prediction,
                model=self._facade.core, future=self._facade)
            self.check_integration()
            return result
        except BaseException:
            self._failed = True
            self._handle._proof._active = False
            raise

    def close(self):
        """Always revoke; fewer than65 uses remains an incomplete denominator."""
        require(not self._closed, 'bound_runtime_already_closed')
        record = {'status': 'unknown_close', 'groups_claimed': self._next,
            'setup': self.setup_copy(), 'complete65_proof_uses': False}
        before = time.perf_counter_ns()
        try:
            self.check_integration()
            record['description_before_close'] = self._handle.description()
            uses = record['description_before_close']['proof_binding']['proof_uses']
            require(type(uses) is int and 1 <= uses <= 65, 'bound_runtime_proof_use_range')
            record['complete65_proof_uses'] = self._next == 16 and uses == 65
            self._handle.close()
            record['status'] = 'closed_complete65' if record['complete65_proof_uses'] else 'closed_with_incomplete_candidate_work'
        except BaseException:
            record['error'] = traceback.format_exc()
            self._failed = True
        finally:
            if self._handle is not None:
                self._handle._proof._active = False
            self._closed = True
            record['closed'] = True
            record['failed'] = self._failed
            record['close_ns'] = time.perf_counter_ns() - before
            record['whole_case_through_close_ns'] = time.perf_counter_ns() - self._started_ns
        return record
