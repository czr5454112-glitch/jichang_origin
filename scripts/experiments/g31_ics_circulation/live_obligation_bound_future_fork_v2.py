"""Only the static-proof binder changes; all original fork/cut/resume code stays."""
from types import FunctionType

from . import live_obligation_bound_future_fork as original
from . import live_obligation_bound_source_proof_v2 as binding

VERSION = 'g31.request_owned_bound_future_fork.v2'
_NAMESPACE = {**vars(original), 'binding': binding}
bind_request = FunctionType(original.bind_request.__code__, _NAMESPACE,
    original.bind_request.__name__, original.bind_request.__defaults__, original.bind_request.__closure__)
bind_request.__kwdefaults__ = original.bind_request.__kwdefaults__


def source_proof():
    binding.require(set(_NAMESPACE) == set(vars(original))
        and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k != 'binding')
        and _NAMESPACE['binding'] is binding, 'future_v2_one_private_binding')
    binding.require(bind_request.__code__ is original.bind_request.__code__
        and bind_request.__defaults__ is original.bind_request.__defaults__
        and bind_request.__kwdefaults__ is original.bind_request.__kwdefaults__
        and bind_request.__closure__ is original.bind_request.__closure__
        and bind_request.__globals__ is _NAMESPACE, 'future_v2_exact_original_entry')
    return {'schema': VERSION, 'binding': binding.source_proof(),
        'same_declared_roots_files_and_BoundFutureRequest': True,
        'same_original_fork_resume_cut_core': True,
        'v1_failed_actual_result_preserved': True,
        'real_bind_model_native_calls': 0, 'actual_dependency_acceptance_pending': True}
