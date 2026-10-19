"""Isolate an internal builtin catalog without invoking arbitrary copy hooks.

Only exact builtin dict/list/tuple and None/bool/int/float/str values are
supported. Mutable cycles and shared-container aliases follow deepcopy
semantics, including tuples participating indirectly in a mutable cycle.
Immutable values retain their exact type and value; this is not validation
of public evidence, JSON keys, finite numbers, or native execution authority.
"""
from __future__ import annotations

VERSION = 'g31.foundation.builtin_catalog_copy.v1'
NONE_TYPE = type(None)


def isolated_copy(value):
    memo = {}

    def clone(current):
        kind = type(current)
        if kind is NONE_TYPE or kind is bool or kind is int or kind is float or kind is str:
            return current
        if kind is not dict and kind is not list and kind is not tuple:
            raise ValueError('catalog_copy:unsupported_builtin_type')
        identity = id(current)
        if identity in memo:
            return memo[identity]
        if kind is dict:
            result = {}
            memo[identity] = result
            for key, item in current.items():
                result[clone(key)] = clone(item)
            return result
        if kind is list:
            result = []
            memo[identity] = result
            result.extend(clone(item) for item in current)
            return result
        items = [clone(item) for item in current]
        if identity in memo:
            return memo[identity]
        result = current if all(item is previous for item, previous in zip(items, current)) else tuple(items)
        memo[identity] = result
        return result

    return clone(value)
