"""Opt-in exact shallow native-query cloning; complex inputs use deepcopy."""
from contextlib import contextmanager
import copy as standard_copy

from . import protocol_control

_ATOMIC=(str,int,float,bool,type(None))
_BASE=frozenset(("request_id","status","attempt"))
_SHAPES=frozenset((_BASE|{extra})|ack for extra in ("kind","physical_resolution")
    for ack in (frozenset(),frozenset(("last_delivered_ack",))))


def query_view_copy(value,memo=None):
    """Fresh root and ACK dictionaries; no mutable alias is reused or erased.

    Explicit memo, unknown root fields, nested objects, custom types and
    potentially aliased/cyclic structures all retain normal deepcopy behavior.
    Atom identities, including signed zero/NaN floats, match deepcopy's behavior.
    """
    if memo is not None or type(value) is not dict:
        return standard_copy.deepcopy(value,memo)
    if any(type(key) is not str for key in value) or frozenset(value) not in _SHAPES:
        return standard_copy.deepcopy(value,memo)
    for key,item in value.items():
        if key=="last_delivered_ack":
            if type(item) is not dict or any(type(k) is not str or type(v) not in _ATOMIC for k,v in item.items()):
                return standard_copy.deepcopy(value,memo)
        elif type(item) not in _ATOMIC:
            return standard_copy.deepcopy(value,memo)
    result=value.copy()
    if "last_delivered_ack" in value:result["last_delivered_ack"]=value["last_delivered_ack"].copy()
    return result


class _CopyFacade:
    deepcopy=staticmethod(query_view_copy)
    def __getattr__(self,name):return getattr(standard_copy,name)


@contextmanager
def installed_query_view_copy():
    """Replace only this module's copy reference; standard-library state stays."""
    if protocol_control.copy is not standard_copy:raise ValueError("query_view_copy:another_facade")
    facade=_CopyFacade();protocol_control.copy=facade
    try:yield
    finally:
        changed=protocol_control.copy is not facade
        protocol_control.copy=standard_copy
        if changed:raise RuntimeError("query_view_copy:facade_changed")
