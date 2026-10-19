"""Pure lifecycle-v2 endpoint gate; old endpoint bytecode is unchanged.

Only the downstream supplied-state lifecycle checker is replaced in a private
namespace. Existing digest/source/current-owner/ACK-union/known-bit/coverage
checks run in their original order. No native collector, trust token, simulator,
recollection or mutable old-module installation is provided by this module.
"""
from types import FunctionType
from . import live_obligation_domain_guard as old
from . import live_obligation_lifecycle_state_v2 as lifecycle


def _clone(function,namespace):
    result=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result


_private=dict(vars(old))
_private['later_bundle']=lifecycle.later_bundle
validate_later_pair=_clone(old.validate_later_pair,_private)
_private['validate_later_pair']=validate_later_pair
validate_collected_endpoints=_clone(old.validate_collected_endpoints,_private)

# Initial-stage support, identity and byte contracts are deliberately unchanged.
validate_pair=old.validate_pair
later_bundle=lifecycle.later_bundle
VERSION=lifecycle.VERSION
