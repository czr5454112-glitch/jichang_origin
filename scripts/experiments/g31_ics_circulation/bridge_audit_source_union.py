"""Versioned per-collection shared traversals; no source/hash lifetime cache.

The failed bcdp1 plan records the completed original134 collection. Every call
rechecks those current/archive bytes, every old manual root and the C gate16.
Different import resolvers remain separate; no tests/ path widening is hidden.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
from pathlib import Path
from . import audit_bridge_saved_c_digest as old

ROOT, OUT, base, require = old.ROOT, old.OUT, old.base, old.require
ANCHOR = OUT / 'bcdp1'
PLAN_SHA = 'df4bb1995188626493f7f9e93b709240c90472ad8c24a730b10219e543d44af4'
OUTER_SHA = 'b81b5d0a409d4a49ad0c632eb3d084c645264973fdd75c05e77942706020a75f'
EXTRA = (
    'scripts/experiments/g31_ics_circulation/bridge_audit_source_union.py',
    'scripts/experiments/g31_ics_circulation/audit_bridge_saved_c_digest_v2.py',
    'scripts/experiments/g31_ics_circulation/run_bridge_saved_c_digest_driver_pure_v2.py',
    'tests/test_g31_circulation_bridge_audit_source_union.py',
)


def seeded_walker(function, namespace=None):
    """Only seed and invocation-local found initialization change; inverse AST."""
    original = ast.parse(inspect.getsource(function))
    changed = copy.deepcopy(original)
    fn = changed.body[0]
    require(isinstance(fn, ast.FunctionDef) and not fn.args.args
            and len(fn.body) >= 2, 'union_original_walker_signature')
    first, second = fn.body[:2]
    require(isinstance(first, ast.Assign) and len(first.targets) == 1
            and isinstance(first.targets[0], ast.Name) and first.targets[0].id == 'pending'
            and isinstance(first.value, ast.List)
            and isinstance(second, ast.Assign) and len(second.targets) == 1
            and isinstance(second.targets[0], ast.Name) and second.targets[0].id == 'found'
            and ast.dump(second.value) == ast.dump(ast.parse('set()', mode='eval').body),
            'union_original_seed_shape')
    fn.args = ast.parse('def f(entries, found=None): pass').body[0].args
    first.value = ast.parse('list(entries)', mode='eval').body
    second.value = ast.parse('set() if found is None else found', mode='eval').body
    inverse = copy.deepcopy(changed)
    inverse.body[0].args = copy.deepcopy(original.body[0].args)
    inverse.body[0].body[0].value = copy.deepcopy(original.body[0].body[0].value)
    inverse.body[0].body[1].value = copy.deepcopy(original.body[0].body[1].value)
    require(ast.dump(inverse, include_attributes=False) == ast.dump(original, include_attributes=False),
            'union_walker_inverse_AST')
    values = {**function.__globals__, **(namespace or {})}
    exec(compile(ast.fix_missing_locations(changed), '<bridge_shared_source_roots>', 'exec'), values)
    return values[function.__name__], {
        'function': function.__module__ + '.' + function.__name__,
        'inverse_AST_exact': True, 'all_resolution_and_exception_statements_retained': True}


def _expression(function, expression):
    # Only pinned local source AST supplies these expressions, never CLI/data.
    return eval(compile(ast.Expression(copy.deepcopy(expression)), '<frozen_root_expression>', 'eval'),
                dict(function.__globals__))


def loop_entries(function):
    tree = ast.parse(inspect.getsource(function)).body[0]
    loops = [n for n in tree.body if isinstance(n, ast.For)]
    require(len(loops) == 1 and isinstance(loops[0].iter, ast.Tuple), 'union_single_root_loop')
    result = tuple(_expression(function, loops[0].iter))
    require(all(type(p) is type(ROOT) for p in result), 'union_path_root_types')
    return result


def image_entries(function):
    calls = [n for n in ast.walk(ast.parse(inspect.getsource(function)))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'source_closure']
    require(len(calls) == 1 and len(calls[0].args) == 2 and not calls[0].keywords,
            'union_single_image_call')
    require(_expression(function, calls[0].args[0]) == ROOT, 'union_image_root')
    result = tuple(_expression(function, calls[0].args[1]))
    require(all(type(name) is str for name in result), 'union_module_root_types')
    return result


def root_inventory():
    # Exact six original wrapper loops: 3+3+3+3+2+5. Their code/globals and
    # returned root expressions are not rewritten to infer equivalent roots.
    v3 = old.previous.previous
    wrappers = (old.closure, old.previous.closure, v3.closure, v3.old.closure,
                old.prior.closure, old.r.source_paths)
    paths = tuple(p for function in wrappers for p in loop_entries(function))
    gate = old.routing_gate
    ref = gate.old.reference
    images = (ref.sources, ref.stage_logs.sources, gate.old.sources, gate.sources)
    modules = tuple(name for function in images for name in image_entries(function))
    require(len(paths) == 19 and len(modules) == 12, 'union_exact_original_root_counts')
    return paths, modules, {'base_root_count': 19, 'image_root_count': 12,
        'base_wrapper_functions': [f.__module__ + '.' + f.__name__ for f in wrappers],
        'image_wrapper_functions': [f.__module__ + '.' + f.__name__ for f in images],
        'cooperative_and_C_resolvers': 'Original one call each; no changes to ROOT/tests handling.'}


def anchor():
    require(base.sha(ANCHOR / 'plan.json') == PLAN_SHA
            and base.sha(ANCHOR / 'external_application_wall.json') == OUTER_SHA,
            'union_failed_anchor_identity')
    plan = base.read(ANCHOR / 'plan.json')
    external = base.read(ANCHOR / 'external_application_wall.json')
    require(plan['tests'] == 12 and plan['limit_seconds'] == 120
            and external['outer_timeout'] is True and external['source_changed'] == []
            and not (ANCHOR / 'tests.xml').exists() and not (ANCHOR / 'worker.json').exists(),
            'union_anchor_stays_failed')
    hashes = plan['source_sha256']
    require(type(hashes) is dict and len(hashes) == 134, 'union_original134')
    for name, digest in hashes.items():
        require(base.sha(ROOT / name) == base.sha(ANCHOR / 'source' / name) == digest,
                'union_anchor_current_archive:' + name)
    return hashes


def require_domain(actual, expected, label):
    require(set(actual) == set(expected), 'union_domain:' + label)


def collect():
    hashes = anchor()  # Full current/archive check every invocation, no cache.
    paths, modules, _ = root_inventory()
    shared_base, _ = seeded_walker(base.source_paths)
    base_seen = set()
    old_paths = set(shared_base(paths, base_seen))
    # Preserve original separate resolver and explicit historical union checks.
    old_paths.update(old.r.original.source_paths())
    old_paths.update(Path(name) for name in old.previous.previous.frozen_preparation()['source_before'])
    image = old.routing_gate.old.image
    old_paths.update(ROOT / name for name in image.source_closure(ROOT, modules))
    old.routing_gate.source_revision()
    C_sources = old.authority.gate.namespace()['project_closure']()
    for name, digest in C_sources.items():
        require(base.sha(ROOT / name) == digest, 'union_C_project_hash:' + name)
        old_paths.add(ROOT / name)
    old_names = {path.resolve().relative_to(ROOT).as_posix() for path in old_paths}
    require_domain(old_names, hashes, 'recorded_original134')
    # Continue the SAME base traversal visited set with version-only roots.
    # No cross-invocation state and no file bytes/hash cache is retained.
    new_paths = set(shared_base((ROOT / name for name in EXTRA), base_seen)) | old_paths
    names = {path.resolve().relative_to(ROOT).as_posix() for path in new_paths}
    require_domain(names, set(hashes) | set(EXTRA), 'exact_added_four')
    result = {name: (ROOT / name).read_bytes() for name in sorted(names)}
    for name, digest in hashes.items():
        require(hashlib.sha256(result[name]).hexdigest() == digest, 'union_collection_drift:' + name)
    return result


def source_proof():
    _, _, roots = root_inventory()
    _, walker = seeded_walker(base.source_paths)
    return {'schema': 'g31.bridge.saved_source_union.v1', 'roots': roots, 'walker': walker,
        'anchor_plan': {'path': str(ANCHOR / 'plan.json'), 'sha256': PLAN_SHA},
        'failed_external': {'path': str(ANCHOR / 'external_application_wall.json'), 'sha256': OUTER_SHA},
        'old_domain': 134, 'added_exact_files': list(EXTRA),
        'all_hashes_rechecked_each_call': True, 'cross_check_cache': False,
        'no_CPU_attribution_from_old_timeout': True}
