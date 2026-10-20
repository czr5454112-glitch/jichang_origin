"""Experimental closed primitive bytes key; frozen regional pool stays unchanged.

pickle is used ONLY for dumps of validated built-in primitives. No loads,
user-defined reducers, native state, truth versions or observation objects enter
the pool. Each activation still validates its complete ordered dependency key.
"""
from contextlib import contextmanager
import math
import pickle

from . import regional_path_pool as legacy

ORIGINAL_KEY=legacy.public_routing_key


def public_routing_bytes(observation):
    """Same supported input domain as the old key; different exact encoding."""
    try:
        if type(observation) is not dict:return None
        owner=observation["owner_id"]
        if type(owner) is not str or not owner:return None
        contracts=observation["node_contracts"];records=observation["node_records"];edges=observation["edge_records"]
        if type(contracts) not in (list,tuple) or type(records) not in (list,tuple) or type(edges) not in (list,tuple):return None
        if not 0<len(contracts)<=2048 or len(records)>2048 or len(edges)>16384:return None
        nodes=[];service=[];ids=set();service_ids=set()
        for row in contracts:
            if type(row) is not dict:return None
            node=row["node"];value=row.get("occupancy",0);kind=type(value)
            if type(node) is not int or not 0<=node<=2**31-1 or node in ids:return None
            if not ((kind is int and abs(value)<=2**53) or (kind is float and math.isfinite(value))):return None
            ids.add(node);nodes.append((node,"occupancy" in row,value))
        for row in records:
            if type(row) not in (list,tuple):return None
            node=row[0];value=row[2];kind=type(value)
            if type(node) is not int or not 0<=node<=2**31-1 or node in service_ids:return None
            if not ((kind is int and abs(value)<=2**53) or (kind is float and math.isfinite(value))):return None
            service_ids.add(node);service.append((node,value))
        if service_ids!=ids:return None
        travel=[]
        for row in edges:
            if type(row) not in (list,tuple) or len(row)!=4:return None
            u,v,length,speed=row
            if type(u) is not int or type(v) is not int or u not in ids or v not in ids:return None
            for value in (length,speed):
                kind=type(value)
                if not ((kind is int and abs(value)<=2**53) or (kind is float and math.isfinite(value))):return None
            if speed<=0 or length<0 or not math.isfinite(length/speed):return None
            travel.append((u,v,length,speed))
        edge_contracts=observation["edge_contracts"];known_faults=observation.get("known_faults",[])
        if type(edge_contracts) not in (list,tuple) or type(known_faults) not in (list,tuple):return None
        if len(edge_contracts)>16384 or len(known_faults)>16384:return None
        limits=[];faults=[]
        for row in edge_contracts:
            if type(row) is not dict:return None
            u=row["from"];v=row["to"];value=row["capacity"];kind=type(value)
            if type(u) is not int or type(v) is not int or u not in ids or v not in ids:return None
            if not ((kind is int and abs(value)<=2**53) or (kind is float and math.isfinite(value))):return None
            limits.append((u,v,value))
        for row in known_faults:
            if type(row) is not dict:return None
            u=row["from"];v=row["to"];active=row["active"]
            if type(u) is not int or type(v) is not int or u not in ids or v not in ids or type(active) is not bool:return None
            faults.append((u,v,active))
        payload=(owner,tuple(nodes),tuple(service),tuple(travel),tuple(limits),tuple(faults))
        return pickle.dumps(payload,protocol=5),frozenset(ids)
    except (KeyError,IndexError,TypeError,ValueError,OverflowError):return None


@contextmanager
def installed_regional_path_bytes(*,max_graphs=4,max_paths_per_graph=256):
    """Serial experimental override, restored even if the wrapped work fails."""
    if legacy.public_routing_key is not ORIGINAL_KEY:raise ValueError("regional_path_bytes:another_key_installation")
    legacy.public_routing_key=public_routing_bytes
    try:
        with legacy.installed_regional_path_pool(max_graphs=max_graphs,max_paths_per_graph=max_paths_per_graph) as pool:
            yield pool
    finally:
        changed=legacy.public_routing_key is not public_routing_bytes
        legacy.public_routing_key=ORIGINAL_KEY
        if changed:raise RuntimeError("regional_path_bytes:key_changed_during_installation")
