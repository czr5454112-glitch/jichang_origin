"""Same full saved audit with the same repaired pure screen as live policy."""
from types import FunctionType
from . import verify_live_obligation_recollection as old
from . import live_obligation_recollection_policy_v2 as policy

_namespace = dict(vars(old))
_namespace['policy'] = policy
for _name in ('verify_call_history','verify_terminal_receipts','prefix_requests','owned_at_view',
              'replay_information','verify_attempts','verify_saved','verify_replies','verify_partial'):
    _source = getattr(old, _name)
    _function = FunctionType(_source.__code__, _namespace, _source.__name__, _source.__defaults__, _source.__closure__)
    _function.__kwdefaults__ = _source.__kwdefaults__
    _namespace[_name] = globals()[_name] = _function
