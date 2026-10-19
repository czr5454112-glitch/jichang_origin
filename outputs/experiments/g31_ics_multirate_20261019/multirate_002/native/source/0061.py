"""Closed native027 owner-view representation, never session authority.

Only the native binding's node_records and edge_records row tuples may become
lists. All fields/scalars and sequence order are retained. No arbitrary JSON
hooks, numeric dictionary-key conversion, nonfinite values or other tuples.
"""
import math

SCHEMA = 'g31.native027_owner_view_representation.v1'
MAX_DEPTH, MAX_NODES = 64, 200000


def normalized_view(value):
    if type(value) is not dict:
        raise ValueError('owner_view_not_builtin_dict')
    if not {'node_records','edge_records'} <= value.keys():
        raise ValueError('owner_view_missing_binding_tables')
    active, count = set(), 0

    def walk(item, path=(), depth=0):
        nonlocal count
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise ValueError('owner_view_tree_limit')
        kind = type(item)
        row = len(path) == 2 and path[0] in ('node_records', 'edge_records') and type(path[1]) is int
        if row and (kind not in (list, tuple) or len(item) != (6 if path[0] == 'node_records' else 4)):
            raise ValueError('owner_view_binding_row_shape')
        if kind in (str, int, bool, type(None)):
            return item
        if kind is float:
            if not math.isfinite(item): raise ValueError('owner_view_nonfinite')
            return item
        if kind not in (dict, list, tuple):
            raise ValueError('owner_view_nonbuiltin')
        if id(item) in active: raise ValueError('owner_view_cycle')
        if kind is tuple and not row:
            raise ValueError('owner_view_tuple_outside_binding_rows')
        active.add(id(item))
        try:
            if kind in (list, tuple):
                return [walk(member, path+(index,), depth+1) for index, member in enumerate(item)]
            result = {}
            for key, member in item.items():
                if type(key) is not str: raise ValueError('owner_view_nonstring_key')
                if not path and key in ('node_records','edge_records') and type(member) is not list:
                    raise ValueError('owner_view_binding_table_not_list')
                result[key] = walk(member, path+(key,), depth+1)
            return result
        finally:
            active.remove(id(item))
    return walk(value)


def equivalent_views(a, b):
    """Exact scalar types, float bits, keys and sequence order after row repair.

Dictionary insertion order is not an identity: the sealed adapter sorts object
keys. No value, key, timestamp or ordered array member may be discarded.
"""
    left, right = normalized_view(a), normalized_view(b)
    def equal(x, y):
        if type(x) is not type(y): return False
        if type(x) is dict:
            return x.keys() == y.keys() and all(equal(v,y[k]) for k,v in x.items())
        if type(x) is list:
            return len(x) == len(y) and all(equal(v,w) for v,w in zip(x,y,strict=True))
        if type(x) is float: return x.hex() == y.hex()
        return x == y
    return left, equal(left, right)
