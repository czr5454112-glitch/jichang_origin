"""Same passive three-getter journal, with the separately versioned route guard."""
from types import FunctionType
from . import live_obligation_initial_recorded_adapter as previous
from . import live_obligation_initial_decision_adapter_v2 as original

SCHEMA=previous.SCHEMA
ORDER=previous.ORDER
EndpointJournal=previous.EndpointJournal
endpoint_data=previous.endpoint_data


def _clone(function,namespace):
    result=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__;return result


_NS={**vars(previous),'original':original}
make_functions=_clone(previous.make_functions,_NS)
_NS['make_functions']=make_functions
collect_initial_decision=_clone(previous.collect_initial_decision,_NS)
revalidate_first_component=_clone(previous.revalidate_first_component,_NS)


def source_proof():
    before=previous.source_proof();proof=original.source_proof()
    previous.require(make_functions.__code__ is previous.make_functions.__code__
        and collect_initial_decision.__code__ is previous.collect_initial_decision.__code__
        and revalidate_first_component.__code__ is previous.revalidate_first_component.__code__, 'exact_recording_code')
    previous.require(all(_NS[k] is v for k,v in vars(previous).items() if k not in ('original','make_functions')),
        'recording_defining_globals')
    return {'schema':'g31.live_initial_recorded_collector.v2','passive_recording':before,'route_window':proof,
        'journal_code_and_endpoint_count_unchanged':True,'old_globals_unmodified':True}
