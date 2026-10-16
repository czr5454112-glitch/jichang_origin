"""Separate candidate for the actual first EDGE_ENTER observation.

Data-only predicate. Native authority still requires the accepted actual session,
fresh owner-A query and complete drain in a separately versioned integration.
The original post-exit predicate and ACK closure are deliberately unchanged.
"""
from __future__ import annotations
import copy
import hashlib
import math
from pathlib import Path
from . import initial_owner_route_contract as old

ROOT=Path(__file__).resolve().parents[3]
ARCHIVE=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_build_001/source'
PINS={
    str(Path(old.__file__).resolve()):'1dc8d45abbf547401232faca189c4fc111feab95db47654eee508854569b619f',
    str(ARCHIVE/'cpp/ics_core/bindings/circulation_session_binding.hpp'):'66cbba8a046c5ee863241a6b449731be430caae37c046ec9e392ac232d380f66',
    str(ARCHIVE/'cpp/ics_core/runtime/circulation_runtime_impl.hpp'):'3af08de9a344698fb70dc1c718abc94fd6c6a9429427848f4c3d06a246154edc',
}
_ORIGINAL=old.observed_first_hop
_ORIGINAL_CODE=_ORIGINAL.__code__

def source_proof():
    for name,digest in PINS.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:
            raise ValueError('entry_hop:unreviewed_source')
    if old.observed_first_hop is not _ORIGINAL or _ORIGINAL.__code__ is not _ORIGINAL_CODE:
        raise ValueError('entry_hop:changed_original_predicate')
    return {'schema':'g31.initial_entry_hop.source_proof.v1','source_sha256':dict(PINS),
        'binding':'edge_exit_at is emitted from an actual EDGE_ENTER receipt matching the current private traversal. The binding computes a public exit bound from that already observed start; it does not inspect a future event.',
        'reservation':'Current edge fields alone are insufficient; reserve_enter sets them before EDGE_ENTER. Missing edge_exit_at cannot prove entry.',
        'identity':'Public traversal_id is not the internal receipt traversal. No equality between them and no inverse floating subtraction is used.',
        'integration_required':'Accepted actual NativeSession027 and fresh owner-A observe_protocol; original command query, ACK closure and complete same-time drain remain required.',
        'comparison_limit':'Earlier root closure removes later root admissions and can change background request IDs. No unchanged-ID or tape-prefix claim transfers from the notification gate.',
        'native_dispatched':False,'data_alone_grants_authority':False}

def observed_first_hop(view,source):
    previous=_ORIGINAL(view,source)
    if previous is not None:
        return previous
    try:
        if type(view) is not dict or type(source) is not dict or view['owner_id']!='A':
            return None
        now=view['now']
        if type(now) not in (int,float) or not math.isfinite(now) or now<old.START:
            return None
        if (source['tray_id']!='L' or source['business_bag_id']!='loaded' or source['mode']!='loaded'
                or type(source['node']) is not int or source['node']!=0
                or type(source['committed_prefix']) is not list or source['committed_prefix']!=[0]
                or any(type(x) is not int for x in source['committed_prefix'])
                or any(type(source[k]) is not int or source[k]<0 for k in ('generation','traversal_id'))
                or any(type(source[k]) is not int or source[k]!=-1 for k in ('edge_from','edge_to','reception_node'))):
            return None
        if type(view['trays']) is not list or any(type(t) is not dict for t in view['trays']):
            return None
        rows=[t for t in view['trays'] if t.get('tray_id')==source['tray_id']]
        if len(rows)!=1:
            return None
        tray=rows[0];prefix=tray['committed_prefix'];exit_at=tray.get('edge_exit_at')
        if (tray['mode']!='loaded' or tray['business_bag_id']!=source['business_bag_id']
                or type(tray['generation']) is not int or tray['generation']!=source['generation']
                or type(tray['traversal_id']) is not int or tray['traversal_id']<0
                or type(prefix) is not list or prefix!=[0] or any(type(x) is not int for x in prefix)
                or any(type(tray[k]) is not int or tray[k]!=0 for k in ('node','edge_from'))
                or type(tray['edge_to']) is not int or tray['edge_to'] not in (1,2)
                or type(exit_at) not in (int,float) or not math.isfinite(exit_at) or exit_at<=now):
            return None
        return {'from':0,'to':tray['edge_to'],'observed_at':now,
                'evidence':'observed_entry_future_exit','tray':copy.deepcopy(tray)}
    except (KeyError,TypeError,ValueError,OverflowError):
        return None
