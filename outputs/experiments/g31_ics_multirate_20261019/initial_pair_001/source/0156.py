"""Representation-only boundary after the real initial native collector.

This module grants no native authority. It accepts closed builtin data only;
tuple/list is a wire representation difference, and integer resource keys are
normalized only in the declared model bundle's resources dictionary. The
original collector, current checks and predictor dynamic guards still run.
"""
from __future__ import annotations
import math
from . import initial_owner_route_image as wire

SCHEMA = 'g31.initial_owner_route_json_boundary.v2'


def normalize(value):
    """Fresh JSON tree, retaining order, scalar types and every field/value.

Integer key conversion is allowed only at a dict named resources immediately
inside a conditional_model_input bundle. Mixed aliases are rejected, not
silently merged. No user hooks, custom containers, nonfinite floats or cycles.
"""
    active, count = set(), [0]

    def walk(item, depth, resources=False):
        count[0] += 1
        if depth > wire.MAX_DEPTH or count[0] > wire.MAX_ARTIFACT_NODES:
            raise ValueError('initial_json_v2:tree_limit')
        kind = type(item)
        if kind in (str, int, bool, type(None)):
            return item
        if kind is float:
            if not math.isfinite(item):
                raise ValueError('initial_json_v2:nonfinite')
            return item
        if kind not in (dict, list, tuple):
            raise ValueError('initial_json_v2:non_builtin')
        if id(item) in active:
            raise ValueError('initial_json_v2:cycle')
        active.add(id(item))
        try:
            if kind in (list, tuple):
                return [walk(v, depth + 1) for v in item]
            result = {}
            model_bundle = (item.get('status') == 'conditional_model_input'
                            and type(item.get('contract')) is dict
                            and type(item.get('resources')) is dict)
            for key, member in item.items():
                if resources:
                    if type(key) is int and key >= 0:
                        emitted = str(key)
                    elif type(key) is str and key.isascii() and key.isdecimal() and str(int(key)) == key:
                        emitted = key
                    else:
                        raise ValueError('initial_json_v2:resource_key')
                    if (type(member) is not dict or type(member.get('node')) is not int
                            or member['node'] != int(emitted)):
                        raise ValueError('initial_json_v2:resource_identity')
                else:
                    if type(key) is not str:
                        raise ValueError('initial_json_v2:non_string_key')
                    emitted = key
                if emitted in result:
                    raise ValueError('initial_json_v2:key_collision')
                walk(emitted, depth + 1)
                result[emitted] = walk(member, depth + 1, model_bundle and key == 'resources')
            return result
        finally:
            active.remove(id(item))

    return walk(value, 0)


def encode(value):
    return wire.encode(normalize(value))


def artifact_encode(value):
    return wire.artifact_encode(normalize(value))


def typed_failure_snapshot(value):
    """Lossless bounded builtin tree for failed evidence, never policy input.

Unlike JSON objects, entry arrays retain integer keys and tuple distinctions.
Unsupported objects are not inspected or serialized through arbitrary hooks.
"""
    active, count = set(), [0]
    def visit(v, depth=0):
        count[0] += 1
        if depth > wire.MAX_DEPTH or count[0] > wire.MAX_ARTIFACT_NODES:
            raise ValueError('failed_evidence_limit')
        k = type(v)
        if k in (str, int, bool, type(None)):
            return {'type': k.__name__, 'value': v}
        if k is float:
            return {'type': 'float', 'hex': v.hex()}
        if k not in (dict, list, tuple) or id(v) in active:
            raise ValueError('failed_evidence_unsupported_or_cycle')
        active.add(id(v))
        try:
            return {'type': k.__name__, 'items':
                [[visit(a, depth+1), visit(b, depth+1)] for a,b in v.items()] if k is dict
                else [visit(a, depth+1) for a in v]}
        finally:
            active.remove(id(v))
    return visit(value)
