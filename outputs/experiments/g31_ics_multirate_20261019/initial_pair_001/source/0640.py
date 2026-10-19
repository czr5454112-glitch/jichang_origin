"""Saved-only verifier repair: retain defining-module global dependencies.

The actual151-source producer remains failed at its final saved verification.
This new verifier can audit its saved evidence separately, never overwrite the
producer receipt or execute another native branch. All old checks stay exact.
"""
from __future__ import annotations
import builtins
import dis
from types import CodeType
from . import verify_initial_owner_route_entry_campaign as frozen

c=frozen.c
require,exact=frozen.require,frozen.exact
root_replay=frozen.root_replay
complete_query_replay=frozen.complete_query_replay
NAMES=('endpoint_replay','immutable_calls','rpc_replay','pair_comparison',
       'predictor_lifetime','branch_attempt','verify_saved','_original_verify_branch','verify_branch')

# v1 copied the gate wrapper's module dictionary, which does not contain Path,
# gzip/json and other globals used by functions originally defined in v3/base.
# Restore only missing defining-module globals; all v1 policy/verifier bindings
# (including both levels of the new root predicate) remain the same.
_defining=frozen.previous.old
_namespace={**vars(_defining),**frozen._namespace}
ADDED_GLOBAL_NAMES=tuple(sorted(set(_namespace)-set(frozen._namespace)))
for _name in NAMES:
    _namespace[_name]=globals()[_name]=frozen.shared(getattr(frozen,_name),_namespace)


def global_load_names(code):
    result={item.argval for item in dis.get_instructions(code) if item.opname=='LOAD_GLOBAL'}
    for value in code.co_consts:
        if isinstance(value,CodeType):result.update(global_load_names(value))
    return result


def missing_globals(function):
    present=set(function.__globals__)|set(vars(builtins))
    return sorted(global_load_names(function.__code__)-present)


def source_proof():
    for name in NAMES:
        current=globals()[name];previous=getattr(frozen,name)
        require(current.__code__ is previous.__code__ and current.__closure__==previous.__closure__,
                'entry_saved_repair_changed_check_code')
        require(not missing_globals(current),'entry_saved_repair_missing_globals:'+name)
    require(root_replay is frozen.root_replay
        and root_replay.__globals__['old'].root_replay is frozen._root_original,
        'entry_saved_repair_changed_root_binding')
    return {'schema':'g31.initial_entry.saved_verifier_globals_repair.v1',
        'old_failure':'NameError Path at verify_saved before any saved branch audit',
        'added_defining_module_globals':list(ADDED_GLOBAL_NAMES),
        'old_missing_globals':{name:missing_globals(getattr(frozen,name)) for name in NAMES},
        'new_missing_globals':{name:missing_globals(globals()[name]) for name in NAMES},
        'all_original_verifier_code_and_closures_unchanged':True,
        'first_hop_replay_binding_unchanged':True,
        'producer_status':'failed_preserved',
        'native_execution_or_authority_added':False}
