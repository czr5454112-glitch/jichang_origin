"""Unchanged selectors with explicit owned32 provider and v2 current guard.

Only private defining globals change. Original modules/classes/functions remain
unchanged; this creates no native execution or protection capability.
"""
from __future__ import annotations
from types import FunctionType
from . import live_obligation_same_information_search as previous
from . import live_obligation_owned_initial_provider as provider
from . import live_obligation_initial_decision_adapter_v2 as origin

METHODS,RESTRICTIONS=previous.METHODS,previous.RESTRICTIONS
_NAMES=('_known','select','propose_initial')
_ORIGINAL={name:getattr(previous,name) for name in _NAMES}
_CODES={name:function.__code__ for name,function in _ORIGINAL.items()}
_NAMESPACE={**previous.__dict__,'provider':provider,'origin':origin}
for _name,_function in _ORIGINAL.items():
    _clone=FunctionType(_function.__code__,_NAMESPACE,_name,_function.__defaults__,_function.__closure__)
    _clone.__kwdefaults__=_function.__kwdefaults__
    _NAMESPACE[_name]=_clone
_known,select,propose_initial=(_NAMESPACE[name] for name in _NAMES)


def source_proof():
    allowed={'provider','origin',*_NAMES}
    previous.require(set(_NAMESPACE)==set(previous.__dict__)
        and all(_NAMESPACE[name] is value for name,value in previous.__dict__.items() if name not in allowed),
        'owned_search_complete_defining_globals')
    previous.require(_NAMESPACE['provider'] is provider and _NAMESPACE['origin'] is origin
        and all(getattr(previous,name) is original and original.__code__ is _CODES[name]
            and _NAMESPACE[name].__code__ is _CODES[name]
            and _NAMESPACE[name].__defaults__ is original.__defaults__
            and _NAMESPACE[name].__kwdefaults__ is original.__kwdefaults__
            and _NAMESPACE[name].__closure__ is original.__closure__
            for name,original in _ORIGINAL.items()),'owned_search_code_and_v2_origin')
    return {'schema':'g31.owned_initial_same_information_search.v1','unchanged_function_code':list(_NAMES),
        'only_defining_global_replacements':sorted(allowed),'provider':provider.source_proof(),
        'v2_final_current_revalidation':True,'native_authority':False,'100ms_certified':False}
