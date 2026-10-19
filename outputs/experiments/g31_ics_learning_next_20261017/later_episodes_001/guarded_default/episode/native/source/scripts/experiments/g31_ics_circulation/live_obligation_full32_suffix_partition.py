"""Source-only action partition draft; does not execute any model or policy.

The accepted fork changes only later_action. Therefore all three earlier
coordinates form a prefix key:2*4*2=16, not eight. This is action coverage,
never coverage of unknown remote/native states. No runtime evaluator yet.
"""
from __future__ import annotations
import copy
import itertools
import math
import struct

FIELDS=('initial_action','empty_departure','return_delay','later_action')
INITIAL=('native_default','prefer_2')
RETURN=(0.,.5)
LATER=('native_default','prefer_8')


def require(value,reason):
    if not value:raise ValueError('full32_suffix_partition:'+reason)


def token(value):
    if type(value) is str:return ('str',value)
    if type(value) is float and math.isfinite(value):return ('float64',struct.pack('>d',value).hex())
    raise ValueError('full32_suffix_partition:exact_declared_scalar_type')


def partition(actions):
    """Validate exact ordered Cartesian shape; infer the four public windows.

This function alone validates a supplied domain's shape. Only
partition_original_domain binds it to the actual frozen source vocabulary.
No caller-supplied domain is promoted to native/model authority.
"""
    require(type(actions) is list and len(actions)==32,'full32_denominator')
    require(all(type(a) is dict and tuple(a)==FIELDS for a in actions),'ordered_action_fields')
    keys=[tuple(token(a[k]) for k in FIELDS) for a in actions]
    require(len(set(keys))==32,'unique32')
    windows=[]
    for a in actions:
        value=a['empty_departure'];token(value)
        if all(token(value)!=token(v) for v in windows):windows.append(value)
    require(len(windows)==4,'four_public_windows')
    expected=[dict(zip(FIELDS,row)) for row in itertools.product(INITIAL,windows,RETURN,LATER)]
    require(keys==[tuple(token(a[k]) for k in FIELDS) for a in expected],'original_cartesian_order')
    groups=[]
    for offset in range(0,32,2):
        pair=actions[offset:offset+2]
        require(tuple(pair[0][k] for k in FIELDS[:-1])==tuple(pair[1][k] for k in FIELDS[:-1]),'past_coordinates_fixed')
        groups.append({'prefix_index':offset//2,'prefix_key':copy.deepcopy({k:pair[0][k] for k in FIELDS[:-1]}),
            'representative_action':copy.deepcopy(pair[0]),'candidate_indices':[offset,offset+1],
            'actions':copy.deepcopy(pair),'strict_cut':'first known B first_reuse_route post-collect/pre-action',
            'outcomes':[{'candidate_index':offset+i,'status':'unknown_unexecuted'} for i in range(2)]})
    return {'schema':'g31.live_obligation.full32_suffix_partition.v1','status':'partition_only_no_model_execution',
        'logical_candidates':32,'prefixes':16,'future_suffixes':32,'groups':groups,
        'public_windows':copy.deepcopy(windows),'same_initial_snapshot_required':True,
        'native_authority':False,'hidden_state_coverage':False,'online_protection_certified':False}


def partition_original_domain():
    # Deliberately lazy imports: merely importing this draft performs no source
    # checks, expensive domain construction or model execution.
    from . import live_obligation_future_later_fork as future
    proof=future.source_proof()
    actions=future.core.lazy.original.physics.previous.actions()
    result=partition(actions)
    result['source_proof']=proof
    result['bound_domain_function']='public_live_obligation_projection.actions'
    result['future_API_unchanged']=True
    return result
