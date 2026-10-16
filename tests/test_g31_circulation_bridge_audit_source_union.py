"""Original unexecuted12 plus15 new small resolver/runner cases; no actual C/raw."""
from test_g31_circulation_bridge_saved_c_digest_driver import *

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import bridge_audit_source_union as u
from scripts.experiments.g31_ics_circulation import audit_bridge_saved_c_digest_v2 as v2
from scripts.experiments.g31_ics_circulation import run_bridge_saved_c_digest_driver_pure_v2 as run


def make_tree(root, files):
    for name, text in files.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf8')
    return root


def reference_base(root, entries):
    result = set()
    for entry in entries:
        function = u.old.r.original.clone(u.base.source_paths,
            {**u.base.source_paths.__globals__, 'ROOT': root, '__file__': str(entry)})
        result.update(function())
    return result


def test_union_root_inventory_is_exact19_and12():
    paths, modules, proof = u.root_inventory()
    assert len(paths) == 19 and len(modules) == 12
    assert len(proof['base_wrapper_functions']) == 6
    assert len(proof['image_wrapper_functions']) == 4


def test_union_base_diamond_cycle_and_duplicate_root(tmp_path):
    make_tree(tmp_path, {'a.py': 'import b\nimport c\n', 'b.py': 'import d\n',
                         'c.py': 'import d\n', 'd.py': 'import a\n'})
    entries = [tmp_path / 'a.py', tmp_path / 'b.py', tmp_path / 'a.py']
    walker, proof = u.seeded_walker(u.base.source_paths, {'ROOT': tmp_path})
    assert set(walker(entries)) == reference_base(tmp_path, entries)
    assert proof['inverse_AST_exact'] is True


def test_union_base_both_module_and_package_targets_retained(tmp_path):
    make_tree(tmp_path, {'a.py': 'import x\n', 'x.py': '', 'x/__init__.py': ''})
    entries = [tmp_path / 'a.py']
    walker, _ = u.seeded_walker(u.base.source_paths, {'ROOT': tmp_path})
    actual = set(walker(entries))
    assert actual == reference_base(tmp_path, entries)
    assert tmp_path / 'x.py' in actual and tmp_path / 'x/__init__.py' in actual


def test_union_base_relative_and_initializer_semantics(tmp_path):
    make_tree(tmp_path, {'p/__init__.py': '', 'p/a.py': 'from . import b\n',
                         'p/b.py': 'from .. import top\n', 'top.py': ''})
    entries = [tmp_path / 'p/a.py', tmp_path / 'p/b.py']
    walker, _ = u.seeded_walker(u.base.source_paths, {'ROOT': tmp_path})
    assert set(walker(entries)) == reference_base(tmp_path, entries)


def test_union_missing_mandatory_entry_preserves_error(tmp_path):
    entries = [tmp_path / 'missing.py']
    walker, _ = u.seeded_walker(u.base.source_paths, {'ROOT': tmp_path})
    with pytest.raises(FileNotFoundError): reference_base(tmp_path, entries)
    with pytest.raises(FileNotFoundError): walker(entries)


def test_union_visited_reused_only_within_one_collection(tmp_path):
    make_tree(tmp_path, {'a.py': 'import b\n', 'b.py': '', 'c.py': 'import a\n'})
    parsed = []
    def parse(text, *args, **kwargs):
        parsed.append(text); return ast.parse(text, *args, **kwargs)
    fake_ast = SimpleNamespace(**{**vars(ast), 'parse': parse})
    walker, _ = u.seeded_walker(u.base.source_paths, {'ROOT': tmp_path, 'ast': fake_ast})
    seen = set()
    walker([tmp_path / 'a.py'], seen)
    walker([tmp_path / 'c.py'], seen)
    assert len(parsed) == 3 and len(seen) == 3
    walker([tmp_path / 'a.py'])  # New invocation without shared set must re-read.
    assert len(parsed) == 5


def test_union_image_multiple_roots_equal_original_separate_calls(tmp_path):
    make_tree(tmp_path, {'p/__init__.py': '', 'p/a.py': 'from . import b\n',
                         'p/b.py': 'from . import a\n', 'z.py': 'from p import b\n'})
    image = u.old.routing_gate.old.image
    roots = ('p.a', 'z', 'p.a', 'missing_external')
    expected = {}
    for name in roots: expected.update(image.source_closure(tmp_path, (name,)))
    assert image.source_closure(tmp_path, roots) == expected


def test_union_resolver_tests_directory_difference_is_not_widened(tmp_path):
    make_tree(tmp_path, {'a.py': 'from helper import value\n', 'tests/helper.py': 'value=1\n'})
    paths, _ = u.seeded_walker(u.base.source_paths, {'ROOT': tmp_path})
    cooperative, _ = u.seeded_walker(u.old.r.original.source_paths, {'ROOT': tmp_path})
    assert tmp_path / 'tests/helper.py' not in set(paths([tmp_path / 'a.py']))
    assert tmp_path / 'tests/helper.py' in set(cooperative([tmp_path / 'a.py']))


def test_union_missing_and_extra_original_domain_both_rejected():
    for actual in ({'a'}, {'a', 'b', 'c'}):
        with pytest.raises(ValueError, match='union_domain'):
            u.require_domain(actual, {'a', 'b'}, 'fixture')
    u.require_domain({'a', 'b'}, {'a', 'b'}, 'fixture')


def test_union_added_file_domain_is_fixed_four():
    assert len(u.EXTRA) == len(set(u.EXTRA)) == 4
    assert v2.MODULE.replace('.', '/') + '.py' in u.EXTRA
    assert run.MODULE.replace('.', '/') + '.py' in u.EXTRA
    assert v2.TEST in u.EXTRA
    with pytest.raises(ValueError, match='union_domain'):
        u.require_domain(set(u.EXTRA) | {'unlisted.py'}, set(u.EXTRA), 'added')


def test_union_driver_gate_inverse_and_private_globals():
    values = v2.namespace()
    assert values['MODULE'] == v2.MODULE and values['DRIVER_PURE_MODULE'] == run.MODULE
    for function, expected in ((u.old.check_driver_pure, 5), (u.old.prepare, 1)):
        copied, proof = v2.adapted(function, values)
        assert proof['inverse_AST_exact'] is True and proof['count_literals'] == expected
        assert copied.__globals__ is values
    assert values['source_files'] is v2.source_files
    assert values['audit'].__code__ is u.old.audit.__code__


def test_union_pure_keeps_owned_main_and_only_new_test_module():
    journal = SimpleNamespace(append=lambda *args: None)
    values = run.namespace(journal)
    assert values['main'].__code__ is run.original.main.__code__
    assert values['worker'].__code__ is run.original.worker.__code__
    assert values['EXPECTED_TESTS'] == 27 and values['LIMIT'] == 120
    assert values['TEST'] == v2.TEST


def test_union_stage_journal_bound_order_and_typed_clock(tmp_path):
    journal = run.Journal(tmp_path / 'stages.jsonl'); journal.LIMIT = 2
    journal.append('collect', 'started'); journal.append('collect', 'completed')
    with pytest.raises(ValueError, match='journal_limit'): journal.append('extra', 'started')
    journal.close()
    rows = [json.loads(line) for line in (tmp_path / 'stages.jsonl').read_text().splitlines()]
    assert [row['sequence'] for row in rows] == [0, 1]
    assert all(type(row['at_ns']) is int for row in rows)
    assert rows[0]['at_ns'] <= rows[1]['at_ns']
    raw = (tmp_path / 'stages.jsonl').read_bytes()
    for name in ('parent_stages.jsonl', 'worker_stages.jsonl'): (tmp_path / name).write_bytes(raw)
    v2.check_stage_journals(tmp_path)
    for mutation in ('bool_clock', 'missing_newline', 'unclosed'):
        changed = [dict(row) for row in rows]
        if mutation == 'bool_clock': changed[0]['at_ns'] = True
        if mutation == 'unclosed': changed = changed[:1]
        value = ''.join(json.dumps(row) + '\n' for row in changed).encode()
        if mutation == 'missing_newline': value = value[:-1]
        (tmp_path / 'worker_stages.jsonl').write_bytes(value)
        with pytest.raises(ValueError): v2.check_stage_journals(tmp_path)


def test_union_stage_export_error_does_not_mask_original_failure():
    failure = MemoryError('original')
    class Broken:
        def append(self, phase, event):
            if event == 'failed': raise OSError('journal')
    def stop(): raise failure
    with pytest.raises(MemoryError) as caught: run.traced(Broken(), 'test', stop)()
    assert caught.value is failure


def test_union_proof_has_no_cross_check_cache_or_test_success_claim():
    proof = u.source_proof()
    assert proof['old_domain'] == 134 and proof['all_hashes_rechecked_each_call'] is True
    assert proof['cross_check_cache'] is False
    assert proof['no_CPU_attribution_from_old_timeout'] is True
