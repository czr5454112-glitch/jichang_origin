"""Full original endpoint/physical/RPC/query audit with exact entry predicate.

Saved values never authorize a native command. Only first-hop data replay uses
the new contract; original source revalidation, actual ACK and drain stay exact.
"""
from types import FunctionType,SimpleNamespace
from . import verify_initial_owner_route_gate_campaign_v2 as previous
from . import initial_owner_route_entry_campaign as c
from . import initial_owner_route_entry_integration as integration

require,exact=c.require,previous.exact


def shared(function,namespace):
    value=FunctionType(function.__code__,namespace,function.__name__,
                       function.__defaults__,function.__closure__)
    value.__kwdefaults__=function.__kwdefaults__
    return value


# The v3 wrapper calls its original root verifier through a module reference.
# Rebind that exact path as well as the outer verifier namespace, so a saved
# old post-exit-only predicate cannot silently validate a new entry root.
original=previous.old.old
_root_original=shared(original.root_replay,{**vars(original),'c':c})
_old_facade=SimpleNamespace(**vars(original));_old_facade.root_replay=_root_original
root_replay=shared(previous.old.root_replay,{**vars(previous.old),'c':c,'old':_old_facade})


def complete_query_replay(raw):
    result=previous.complete_query_replay(raw)
    for record in raw['root_records']:
        proof=record['value']['evidence']['runtime_query_proof']
        require(exact(proof.get('first_hop_observation_contract'),integration.MARKER),
                'entry_observation_contract_missing_or_changed')
    return result


_namespace={**vars(previous),'c':c,'integration':integration,'root_replay':root_replay,
            'complete_query_replay':complete_query_replay}
for _name in ('endpoint_replay','immutable_calls','rpc_replay','pair_comparison',
              'predictor_lifetime','branch_attempt','verify_saved'):
    _namespace[_name]=globals()[_name]=shared(getattr(previous,_name),_namespace)
_namespace['_original_verify_branch']=_original_verify_branch=shared(previous._original_verify_branch,_namespace)
_namespace['verify_branch']=verify_branch=shared(previous.verify_branch,_namespace)
