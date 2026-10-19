"""New-policy saved replay; same full endpoints, terminals and physical audit."""
from types import FunctionType
from . import verify_live_obligation_historical as old
from . import live_obligation_unloading_policy as policy

require,json_value=old.require,old.json_value
expected_information,replay_information=old.expected_information,old.replay_information
verify_call_history=old.verify_call_history
_namespace={**old.verify_saved.__globals__,'policy':policy}
for _name in ('verify_terminal_receipts','prefix_requests','owned_at_view',
              'verify_attempts','verify_saved','verify_replies','verify_partial'):
    _source=getattr(old,_name)
    _function=FunctionType(_source.__code__,_namespace,_source.__name__,_source.__defaults__,_source.__closure__)
    _function.__kwdefaults__=_source.__kwdefaults__
    _namespace[_name]=globals()[_name]=_function
