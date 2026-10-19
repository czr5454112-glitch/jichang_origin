"""Unexecuted revision: same audit, shared source traversal and separate27 gate."""
from __future__ import annotations
import time
BOOT = time.monotonic()
import ast
import copy
import inspect
import json
from pathlib import Path
from types import FunctionType
from . import audit_bridge_saved_c_digest as old
from . import bridge_audit_source_union as union

ROOT, OUT, require, r = old.ROOT, old.OUT, old.require, old.r
MODULE = 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_c_digest_v2'
TEST = 'tests/test_g31_circulation_bridge_audit_source_union.py'
SCHEMA = 'g31.bridge.saved_C_digest_audit.v2'
DRIVER_PURE = OUT / 'bcdp2'
DRIVER_PURE_MODULE = 'scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_driver_pure_v2'
DRIVER_PURE_SCHEMA = 'g31.bridge.saved_C_digest.driver_pure.v2'
COUNT = 27


def adapted(function, values):
    original = ast.parse(inspect.getsource(function))
    tree = copy.deepcopy(original)
    counts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value == 12:
            counts.append(node); node.value = COUNT
    expected = {'check_driver_pure': 5, 'prepare': 1}[function.__name__]
    require(len(counts) == expected, 'union_driver_only_test_count_literals')
    added = []
    journal_names = []
    journal_calls = []
    if function.__name__ == 'check_driver_pure':
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'new_names'):
                require(isinstance(node.value, ast.Tuple) and len(node.value.elts) == 3,
                        'union_driver_outer_source_domain_shape')
                node.value.elts.append(ast.Constant(union.EXTRA[0])); added.append(node.value)
        require(len(added) == 1, 'union_driver_add_collector_pin')
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'names'):
                require(isinstance(node.value, ast.Tuple) and len(node.value.elts) == 7,
                        'union_driver_output_names_shape')
                node.value.elts.extend([ast.Constant('parent_stages.jsonl'), ast.Constant('worker_stages.jsonl')])
                journal_names.append(node.value)
        require(len(journal_names) == 1, 'union_driver_journal_hashes')
        statement = ast.parse('check_stage_journals(directory)').body[0]
        require(isinstance(tree.body[0].body[-1], ast.Return), 'union_driver_final_return')
        tree.body[0].body.insert(-1, statement); journal_calls.append(statement)
    # The descriptive key changes to avoid claiming this new gate still has12.
    labels = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == 'driver_gate_separate12_from_routing37':
            node.value = 'driver_gate_separate27_from_routing37'; labels.append(node)
    require(len(labels) == (1 if function.__name__ == 'prepare' else 0), 'union_driver_label')
    inverse = copy.deepcopy(tree)
    for node in ast.walk(inverse):
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value == COUNT:
            node.value = 12
        elif isinstance(node, ast.Constant) and node.value == 'driver_gate_separate27_from_routing37':
            node.value = 'driver_gate_separate12_from_routing37'
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'new_names'):
            node.value.elts.pop()
        elif (function.__name__ == 'check_driver_pure' and isinstance(node, ast.Assign)
              and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id == 'names'):
            del node.value.elts[-2:]
    if journal_calls: inverse.body[0].body.pop(-2)
    require(ast.dump(inverse, include_attributes=False) == ast.dump(original, include_attributes=False),
            'union_driver_gate_inverse_AST')
    exec(compile(ast.fix_missing_locations(tree), '<bridge_union_driver_gate>', 'exec'), values)
    return values[function.__name__], {'function': function.__name__, 'count_literals': expected,
        'added_outer_source_pins': len(added), 'journal_output_and_check_additions': bool(journal_calls),
        'inverse_AST_exact': True}


def check_stage_journals(directory):
    for name in ('parent_stages.jsonl', 'worker_stages.jsonl'):
        raw = (directory / name).read_bytes()
        require(raw.endswith(b'\n'), 'union_driver_complete_journal_lines')
        rows = [json.loads(line) for line in raw.decode('utf8').splitlines()]
        require(0 < len(rows) <= 64, 'union_driver_journal_count')
        stack = []; last = -1
        for index, row in enumerate(rows):
            require(type(row) is dict and set(row) == {'sequence', 'phase', 'event', 'at_ns'}
                and type(row['sequence']) is int and row['sequence'] == index
                and type(row['at_ns']) is int and row['at_ns'] >= last
                and type(row['phase']) is str and row['phase'], 'union_driver_journal_row')
            last = row['at_ns']
            if row['event'] == 'started': stack.append(row['phase'])
            else:
                require(row['event'] == 'completed' and stack and stack.pop() == row['phase'],
                        'union_driver_success_journal_balance')
        require(not stack, 'union_driver_no_unfinished_stage')


def source_files(): return union.collect()
def closure(): return sorted(ROOT / name for name in source_files())


def contract():
    return {**old.contract(), 'shared_source_collection': union.source_proof(),
            'driver_pure_tests': COUNT, 'bcdp1_timeout_preserved': True}


def namespace():
    # Retain the actual old driver's complete defining globals and all its
    # helper code; only namespace topology, source collection and gate IDs vary.
    values = old.namespace()
    values.update(vars(old))
    for name, function in vars(old).items():
        if isinstance(function, FunctionType) and function.__globals__ is vars(old):
            values[name] = r.original.clone(function, values)
    values.update(__file__=__file__, BOOT=BOOT, MODULE=MODULE, TEST=TEST, SCHEMA=SCHEMA,
        DRIVER_PURE=DRIVER_PURE, DRIVER_PURE_MODULE=DRIVER_PURE_MODULE,
        DRIVER_PURE_SCHEMA=DRIVER_PURE_SCHEMA, namespace=namespace,
        source_files=source_files, closure=closure, contract=contract, check_stage_journals=check_stage_journals)
    for function in (old.check_driver_pure, old.prepare): adapted(function, values)
    return values


def main(): return namespace()['main']()


if __name__ == '__main__': raise SystemExit(main())
