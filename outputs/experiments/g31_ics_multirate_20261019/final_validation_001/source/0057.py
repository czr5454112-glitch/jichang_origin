"""Private, saved-only bridge replay substitutions; no policy or native changes.

Policy still receives the original ReplayTape deepcopy. Only the offline
observer's immediately repeated copy is replaced with its private decoded row.
"""
from __future__ import annotations
import ast
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import inspect
import json
import math
from pathlib import Path
import textwrap
import time
import sys
from types import SimpleNamespace
from . import audit_bridge_serialize_once_saved as old
from . import native_host

base, r, original, require = old.base, old.r, old.original, old.require
full = original.original
_FUNCTIONS = (
    full.verify_case, full.physical_outcomes, full.validate_clocks,
    full.classify_observation, r.original.assess, r.original.operations,
    base.verify_saved, base.normalized_owners, base.ReplayTape.__init__,
    base.ReplayTape.__getattr__, native_host.audit_result,
    original.PrefixComparison.consume, original.PrefixComparison.finish,
)
_IDENTITIES = tuple((fn, fn.__code__) for fn in _FUNCTIONS)


def source_proof():
    require(all(fn.__code__ is code for fn, code in _IDENTITIES), 'linear_consumer_code_changed')
    for fn, _ in _IDENTITIES:
        bound = sys.modules[fn.__module__]
        for component in fn.__qualname__.split('.'):bound = getattr(bound, component)
        require(bound is fn, 'linear_consumer_identity_changed')
    # The package pins every defining source and its transitive imports. These
    # are the consumers whose aliases into shared decoded raw/input were read.
    return {
        'schema': 'g31.bridge.linear_readonly_consumer_proof.v1',
        'functions': {fn.__module__+'.'+fn.__qualname__: hashlib.sha256(
            inspect.getsource(fn).encode('utf8')).hexdigest() for fn in _FUNCTIONS},
        'shared_paths': ['raw_final.json.gz', 'input.json.gz'],
        'readonly_argument_review': {
            'outer_verify_case': 'reads raw/input; constructs separate frames/outcomes/report; never passes shared raw to policy',
            'inner_verify_saved': 'normalizes owners into fresh JSON trees; deepcopies input before adding transfers',
            'physical_outcomes': 'indexes raw fields by reference but writes only new local containers',
            'audit_result': 'indexes contracts/receipts by reference but updates only new local physical accounting maps',
            'assess_and_operations': 'construct fresh result/operation maps; never mutate referenced raw job/decision fields',
        },
        'observer_ownership': 'Original decoded result remains private to audit; original deepcopy is the sole actor return. Latest/frame evidence never receives the actor object.',
        'limits': 'Source-bound private call graph, not a general runtime immutability sandbox. New/mutated consumer code invalidates the package.'
    }


def ordered_equal(a, b):
    """Equal iff compact ordered JSON agrees for the decoded builtin domain.

    Unsupported objects use the old encoder, not Python equality. All accepted
    floats are finite and repr-exact, including the sign of zero.
    """
    ta, tb = type(a), type(b)
    allowed = (dict, list, str, int, float, bool, type(None))
    if ta not in allowed or tb not in allowed:
        return full.ordered(a) == full.ordered(b)
    if ta is not tb:
        return False
    if ta is dict:
        if not all(type(k) is str for k in a) or not all(type(k) is str for k in b):
            return full.ordered(a) == full.ordered(b)
        return len(a) == len(b) and all(ka == kb and ordered_equal(va, vb)
            for (ka, va), (kb, vb) in zip(a.items(), b.items()))
    if ta is list:
        return len(a) == len(b) and all(ordered_equal(x, y) for x, y in zip(a, b))
    if ta is float:
        require(math.isfinite(a) and math.isfinite(b), 'linear_nonfinite_json')
        return repr(a) == repr(b)
    if ta is int:
        # Match the original integer-string conversion domain/limit too.
        return str(a) == str(b)
    return a == b


def semantic_equal(a, b):
    def view(row):
        if row['endpoint'] != 'advance_to':
            return row
        top = dict(row); result = dict(row['result'])
        wall = result.pop('wall_seconds')
        require(full.finite(wall), 'serialize_bridge_native_wall')
        top['result'] = result
        return top
    return ordered_equal(view(a), view(b))


class Progress:
    LIMIT = 1024
    def __init__(self, directory, clock=time.perf_counter_ns):
        self.path = Path(directory)/'progress.jsonl'; self.clock = clock
        self.count = 0; self.failed = False
        self.stream = self.path.open('x', encoding='utf8')
    def emit(self, event, **fields):
        require(not self.failed and self.count < self.LIMIT, 'linear_progress_budget_or_failure')
        try:
            value = {'record': self.count, 'at_ns': self.clock(), 'event': event, **fields}
            text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n'
            require(len(text.encode('utf8')) <= 4096, 'linear_progress_row_limit')
            require(self.stream.write(text) == len(text), 'linear_progress_short_write')
            self.stream.flush(); self.count += 1
        except BaseException:
            self.failed = True
            raise
    @contextmanager
    def stage(self, name):
        start = self.clock(); self.emit('stage_start', stage=name)
        try:
            yield
        except BaseException as error:
            # Never mask the original verifier error with a progress failure.
            try:self.emit('stage_failed', stage=name, error_type=type(error).__name__)
            except BaseException:pass
            raise
        else:self.emit('stage_end', stage=name, elapsed_ns=self.clock()-start)
    def wrap(self, name, fn):
        def call(*args, **kwargs):
            with self.stage(name):return fn(*args, **kwargs)
        return call
    def close(self):
        try:self.stream.flush()
        finally:self.stream.close()


class SharedReads:
    def __init__(self, directory, progress, loader=base.gzread):
        self.directory = Path(directory).resolve(); self.progress = progress; self.loader = loader
        self.allowed = {self.directory/'raw_final.json.gz', self.directory/'input.json.gz'}
        self.values = {}; self.requests = {}; self.decodes = {}
    def read(self, path):
        path = Path(path).resolve()
        self.requests[path] = self.requests.get(path, 0)+1
        if path in self.allowed and path in self.values:
            self.progress.emit('shared_decoded_read', path=path.name, logical_reads=self.requests[path])
            return self.values[path]
        with self.progress.stage('decode:'+str(path)):
            value = self.loader(path)
        self.decodes[path] = self.decodes.get(path, 0)+1
        if path in self.allowed:self.values[path] = value
        return value
    def finish(self):
        require(set(self.values) == self.allowed and all(self.requests.get(p) == 2 and self.decodes.get(p) == 1
            for p in self.allowed), 'linear_shared_read_denominator')
        return {str(p): {'logical_reads': self.requests[p], 'decodes': self.decodes[p]} for p in sorted(self.allowed)}


def transformed(fn, substitutions, namespace):
    """Exact expression replacement plus an inverse AST proof; no guard deletion."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    before = ast.dump(tree, include_attributes=False)
    counts = [0]*len(substitutions)
    class Forward(ast.NodeTransformer):
        def generic_visit(self, node):
            text = ast.dump(node, include_attributes=False)
            for i, (a, b) in enumerate(substitutions):
                if text == ast.dump(ast.parse(a, mode='eval').body, include_attributes=False):
                    counts[i] += 1
                    return ast.copy_location(ast.parse(b, mode='eval').body, node)
            return super().generic_visit(node)
    tree = Forward().visit(tree); require(counts == [1]*len(substitutions), 'linear_substitution_count')
    restored = deepcopy(tree)
    class Reverse(ast.NodeTransformer):
        def generic_visit(self, node):
            text = ast.dump(node, include_attributes=False)
            for a, b in substitutions:
                if text == ast.dump(ast.parse(b, mode='eval').body, include_attributes=False):
                    return ast.copy_location(ast.parse(a, mode='eval').body, node)
            return super().generic_visit(node)
    restored = Reverse().visit(restored)
    require(ast.dump(restored, include_attributes=False) == before, 'linear_inverse_ast')
    private = dict(namespace); exec(compile(ast.fix_missing_locations(tree), inspect.getsourcefile(fn), 'exec'), private)
    return private[fn.__name__], {'function': fn.__qualname__, 'expressions': substitutions,
        'inverse_ast_exact': True, 'original_ast_sha256': hashlib.sha256(before.encode()).hexdigest()}


def observer_result(value, replay, ordinal):
    require(replay.index == ordinal+1 and replay._observer_row['ordinal'] == ordinal
        and replay._observer_pending is True and replay._actor_return is value, 'linear_observer_read_binding')
    replay._observer_pending = False
    replay._actor_return = None
    return replay._observer_row['result']


def replay_type(comparison, progress):
    def read(path):
        value = base.gzread(path); comparison.consume(value); return value
    count = 0
    def hashed(path):
        nonlocal count
        value = base.sha(path); count += 1
        if count % 256 == 0:progress.emit('new_row_hash_progress', completed=count)
        return value
    init = r.original.clone(base.ReplayTape.__init__, {**base.ReplayTape.__init__.__globals__, 'sha': hashed})
    def start(self, directory):
        with progress.stage('new_manifest_and_all_compressed_hashes'):init(self, directory)
        progress.emit('new_row_hash_complete', completed=count)
    def retain(self, row):
        value = deepcopy(row['result'])
        self._observer_row = row; self._actor_return = value; self._observer_pending = True
        if self.index % 256 == 0:
            progress.emit('api_replay_progress', completed=self.index, old_prefix_completed=comparison.index,
                ordinal=row['ordinal'], endpoint=row['endpoint'])
        return value
    method, proof = transformed(base.ReplayTape.__getattr__,
        [("deepcopy(row['result'])", 'self._retain_and_copy(row)')],
        {**base.ReplayTape.__getattr__.__globals__, 'gzread': read})
    cls = type('LinearReplayTape', (base.ReplayTape,), {
        '__init__': start, '__getattr__': method, '_retain_and_copy': retain})
    return cls, proof


def bind(plan, redirect, progress):
    proof = source_proof(); ast_proofs = []
    shared = SharedReads(redirect.old.parent, progress)
    consume, p = transformed(original.PrefixComparison.consume,
        [('semantic_api(old) == semantic_api(row)', 'semantic_equal(old, row)')],
        {**original.PrefixComparison.consume.__globals__, 'semantic_equal': semantic_equal})
    ast_proofs.append(p)
    comparison_type = type('LinearPrefixComparison', (original.PrefixComparison,), {'consume': consume})
    with progress.stage('old_complete_prefix_manifest'):
        comparison = comparison_type(r.REFERENCE/'bridge/api', r.MANIFEST_SHA, r.PREFIX_ROWS)
    Replay, p = replay_type(comparison, progress); ast_proofs.append(p)
    def verify_source_pins(directory, producer_plan, runtime=False):
        with progress.stage('original_source_and_reference_pins'):
            r.verify_pins(directory, producer_plan, runtime=False)
            if runtime:old.check_runtime(plan)
    namespace = r.runner_namespace(); namespace['verify_pins'] = verify_source_pins
    original_factory = namespace['isolated_base']
    def private_factory(**overrides):
        original_run = overrides.get('run_policy', namespace['policy'].run_policy)
        overrides.update(gzread=shared.read,
            normalized_owners=progress.wrap('normalized_owners', base.normalized_owners),
            audit_result=progress.wrap('independent_physical_audit_result', base.audit_result),
            run_policy=progress.wrap('complete_policy_replay', original_run))
        return original_factory(**overrides)
    namespace['isolated_base'] = private_factory
    runner = SimpleNamespace(**namespace)
    private_base = SimpleNamespace(**{**vars(base), 'ReplayTape': Replay, 'gzread': shared.read,
        'gzwrite': progress.wrap('all_job_states_export', redirect.gzwrite), 'sha': redirect.sha})
    checker, p = transformed(full.verify_case, [
        ('deepcopy(value)', 'observer_result(value, self, ordinal)'),
        ('semantic_api(row) == semantic_api(base.gzread(oldpath))',
         'semantic_equal(row, base.gzread(oldpath))')],
        {**full.verify_case.__globals__, 'r': runner, 'base': private_base,
         'observer_result': observer_result, 'semantic_equal': semantic_equal,
         'physical_outcomes': progress.wrap('alloffered_physical_outcomes', full.physical_outcomes),
         'validate_clocks': progress.wrap('all_clock_and_owner_intervals', full.validate_clocks)})
    ast_proofs.append(p)
    def execute(directory):
        result = checker(directory)
        result['same_policy_old001_complete_prefix'] = comparison.finish()
        result['logging_only_comparison'] = 'Same policy/control cadence. No claim old incomplete run was a fullH performance/control arm.'
        result['reference_evidence_sha256'] = dict(r.EVIDENCE)
        stats = {'source_proof': proof, 'ast_proofs': ast_proofs, 'shared_reads': shared.finish(),
            'old_prefix_rows': comparison.index, 'new_replay_rows': result['replay']['api_rows'],
            'policy_return_deepcopy_retained': True, 'observer_copy_removed_only': True}
        return result, stats
    return execute
