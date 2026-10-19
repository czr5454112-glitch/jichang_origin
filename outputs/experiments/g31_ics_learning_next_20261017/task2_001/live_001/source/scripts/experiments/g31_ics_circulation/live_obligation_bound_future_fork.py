"""Opt-in request-owned future-fork facade; source draft, no accepted speedup.

Original modules, classes and dynamic guards are untouched. The two future
operations have the original code/defaults/closures and a complete PRIVATE
globals dictionary, changing only source_proof. The private proof has the
original code, changing only its inventory global. No AST transform is needed:
inverse binding restores the exact defining namespace and identical code.
"""
from __future__ import annotations

import copy
from pathlib import Path
from types import FunctionType, SimpleNamespace
from . import live_obligation_bound_source_proof as binding

VERSION = 'g31.request_owned_bound_future_fork.v1'
PROJECT = ('scripts.experiments.g31_ics_circulation',)


def _clone(original, namespace):
    clone = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    clone.__kwdefaults__ = original.__kwdefaults__
    return clone


def _roots(future):
    core = future.core
    declared = {}
    for cls in core.Projection.__mro__:
        for name, function in vars(cls).items():
            if isinstance(function, (staticmethod, classmethod)):
                function = function.__func__
            if type(function) is FunctionType:
                declared[cls.__module__ + '.' + cls.__qualname__ + '.' + name] = function
    return {
        'original_proof': future.source_proof, 'original_inventory': future._source_inventory,
        'effective_methods': future._effective_methods, 'effective_guard_baseline': future._METHODS,
        'declared_MRO_methods': declared, 'parts_guard_baseline': future._PARTS,
        'core_function_baseline': future._CORE_FUNCTIONS, 'code_guard_baseline': future._CODES,
        'core_PARTS': core.PARTS, 'core_PROOF': core.PROOF, 'core_Projection': core.Projection,
        'core_Continuation': core.Continuation, 'future_FutureLaterFork': future.FutureLaterFork,
        'dynamic_cut': future._cut, 'original_fork': future.fork_later_action,
        'original_resume': future.resume_future_later,
        # deepcopy's known mutable dispatch table is an explicit boundary, not
        # an invitation to scan all stdlib modules or accept custom copy hooks.
        'copy_dispatch': copy._deepcopy_dispatch,
    }


def _proof_read_paths(future):
    """Finite direct byte reads plus inspect source files of original audit.

    Generated methods have synthetic filenames; their generators live in the
    explicitly included core/lazy/original files. Complete campaign closure
    remains an independent entry/exit gate; it is NOT scanned on every use.
    """
    core = future.core
    live = core.lazy.original.physics.previous
    native = live.original
    modules = (core, core.lazy, core.lazy.original, live, native, native.legacy,
               core.lazy.original.captures)
    paths = {Path(m.__file__).resolve(strict=True) for m in modules}
    functions = list(future._effective_methods().values()) + [live.actions, live.Projection.request]
    for cls in core.Projection.__mro__:
        for function in vars(cls).values():
            if isinstance(function, (staticmethod, classmethod)):
                function = function.__func__
            if type(function) is FunctionType:
                functions.append(function)
    for function in functions:
        filename = function.__code__.co_filename
        if not filename.startswith('<'):
            path = Path(filename).resolve(strict=True)
            binding.require(path.suffix == '.py', 'proof_inspect_source_not_python')
            paths.add(path)
    return tuple(sorted(paths, key=str))


class BoundFutureRequest:
    """One serial model request. Explicit close invalidates further forks."""
    def __init__(self, future, proof):
        self._original = future
        self._proof = proof
        namespace = {**vars(future), 'source_proof': proof.source_proof}
        fork = _clone(future.fork_later_action, namespace)
        resume = _clone(future.resume_future_later, namespace)
        # Both functions share exactly the original namespace with the ONE
        # source_proof replacement. Names of fork/resume in that namespace stay
        # original; neither function calls them through a global self lookup.
        self._namespace = namespace
        self.facade = SimpleNamespace(**vars(future))
        self.facade.source_proof = proof.source_proof
        proof.bind_private_calls((fork, resume))
        self._calls = (fork, resume)
        # A cheap outer identity check prevents entry through a changed private
        # globals dictionary. The actual operation is still the exact clone.
        def fork_entry(state, later_action):
            self.check_integration()
            return fork(state, later_action)
        def resume_entry(branch):
            self.check_integration()
            return resume(branch)
        self._entries = (fork_entry, resume_entry)
        self.facade.fork_later_action = fork_entry
        self.facade.resume_future_later = resume_entry
        self.check_integration()

    def check_integration(self):
        try:
            binding.require(self._proof._active, 'closed_or_invalidated_future_request')
            self._check_integration()
        except BaseException:
            self._proof._active = False
            raise

    def _check_integration(self):
        f = self._original
        binding.require(set(self._namespace) == set(vars(f))
            and all(self._namespace[k] is v for k, v in vars(f).items() if k != 'source_proof')
            and self._namespace['source_proof'] is self._proof.source_proof,
            'one_private_future_global_replacement')
        binding.require(set(vars(self.facade)) == set(vars(f))
            and all(vars(self.facade)[k] is v for k, v in vars(f).items()
                    if k not in ('source_proof', 'fork_later_action', 'resume_future_later')),
            'complete_future_facade')
        for clone, original in zip(self._calls, (f.fork_later_action, f.resume_future_later), strict=True):
            binding.require(clone.__code__ is original.__code__ and clone.__defaults__ is original.__defaults__
                and clone.__kwdefaults__ is original.__kwdefaults__ and clone.__closure__ is original.__closure__
                and clone.__globals__ is self._namespace, 'identical_future_operation_code')
        binding.require(self.facade.source_proof is self._proof.source_proof
            and self.facade.fork_later_action is self._entries[0]
            and self.facade.resume_future_later is self._entries[1], 'facade_operation_bindings')

    def close(self):
        try:
            self.check_integration()
        finally:
            self._proof.close()

    def description(self):
        self.check_integration()
        return {'schema': VERSION, 'proof_binding': self._proof.description(),
            'fork_resume_original_code_defaults_closure': True,
            'private_full_globals_single_proof_replacement': True,
            'original_cut_and_all_core_dynamic_functions': True,
            'no_original_module_mutation': True, 'native_authority': False,
            'actual_dependency_domain_acceptance_pending': True}


def bind_request():
    """All cold import, one original audit, sealing and later checks are charged.

    Caller must already be inside its source-bound whole-request budget. This
    API accepts no proof dictionary, forecast, actual endpoint or native state.
    Unsupported dependency objects invalidate the bind; never silently omit.
    """
    from . import live_obligation_future_later_fork as future
    proof = binding.bind_declared(future.source_proof, _roots(future), _proof_read_paths(future),
        project_prefixes=PROJECT)
    try:
        return BoundFutureRequest(future, proof)
    except BaseException:
        proof._active = False
        raise
