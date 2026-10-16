"""Bounded diagnostic only: action reads before an existing strict cut.

No native execution, online policy, cache, or timing comparison is introduced.
Every one of the original 6 x 32 candidates is still fully predicted separately.
"""
from pathlib import Path
from types import FunctionType
import ast, copy, hashlib, inspect, json, sys, time
from scripts.experiments.g31_ics_circulation import public_preference_protection_cut as cut
from scripts.experiments.g31_ics_circulation import bounded_windows_job
from test_g31_circulation_preference_request_context import bundle, ordered

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE.parent / 'action_dependency_diagnostic_001'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    with path.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)

def read_action(projection, key):
    projection.observed_action_keys.add(key)
    return projection.action[key]

def scalar_key(value):
    return (type(value).__name__, value.hex() if type(value) is float else value)

def diagnostic():
    proof = cut.source_proof()
    modules = (cut, cut.original, cut.original.legacy, cut.closed)
    pins = {str(Path(m.__file__).resolve().relative_to(ROOT)):sha(m.__file__) for m in modules}
    tree = ast.parse(inspect.getsource(cut.original))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Projection')
    # Exhaust the source's action attribute uses: one private deepcopy assignment
    # plus exactly the four indexed semantic reads in run. No hidden whole-dict use.
    attributes = [n for n in ast.walk(cls) if isinstance(n, ast.Attribute)
                  and isinstance(n.value, ast.Name) and n.value.id == 'self' and n.attr == 'action']
    assert len(attributes) == 5
    assert sum(isinstance(n.ctx, ast.Store) for n in attributes) == 1
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    direct_reads = [ast.unparse(n) for n in ast.walk(init) if isinstance(n, ast.Subscript)
                    and isinstance(n.value, ast.Name) and n.value.id == 'action']
    assert direct_reads == ["action['empty_departure']"]
    assert 'self.action' not in inspect.getsource(cut.original.legacy)
    original_run = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    expected = {'empty_departure', 'initial_action', 'return_delay', 'later_action'}
    class Observe(ast.NodeTransformer):
        def __init__(self): self.keys = []
        def visit_Subscript(self, node):
            if ast.unparse(node.value) == 'self.action':
                assert isinstance(node.ctx, ast.Load) and isinstance(node.slice, ast.Constant)
                self.keys.append(node.slice.value)
                return ast.copy_location(ast.Call(func=ast.Name(id='_read_action', ctx=ast.Load()),
                    args=[ast.Name(id='self',ctx=ast.Load()), copy.deepcopy(node.slice)], keywords=[]), node)
            return self.generic_visit(node)
    visitor = Observe()
    instrumented = visitor.visit(copy.deepcopy(original_run))
    assert len(visitor.keys) == 4 and set(visitor.keys) == expected
    class Restore(ast.NodeTransformer):
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == '_read_action':
                return ast.Subscript(value=ast.Attribute(value=ast.Name(id='self',ctx=ast.Load()),
                    attr='action',ctx=ast.Load()), slice=copy.deepcopy(node.args[1]), ctx=ast.Load())
            return self.generic_visit(node)
    assert ast.dump(Restore().visit(copy.deepcopy(instrumented)), include_attributes=False) == ast.dump(original_run, include_attributes=False)
    ns = {**cut.original.Projection.run.__globals__, '_read_action':read_action}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[instrumented],type_ignores=[])),
                 str(__file__)+':observed_run', 'exec'), ns)
    observed_run = ns['run']
    rows, case_rows = [], []
    for index in range(6):
        value = bundle(index)
        context = cut.closed.RequestContext(value)
        actions = context.actions()
        assert len(actions) == 32
        baseline = cut.original.predict(value, actions[0])
        reference = cut._reference_times(baseline)
        assert reference is not None
        class Observed(cut.original.Projection):
            def __init__(self, supplied, action):
                self.observed_action_keys = {'empty_departure'}
                super().__init__(supplied, action)
            def run(self):
                assert not self.completed
                self.completed = cut._CompletionLedger(self, reference)
                try:
                    return observed_run(self)
                except cut._Rejected as rejected:
                    rejected.read_keys = sorted(self.observed_action_keys)
                    raise
        original = cut.original._predict
        evaluate = FunctionType(original.__code__, {**original.__globals__, 'Projection':Observed},
                                original.__name__, original.__defaults__, original.__closure__)
        evaluate.__kwdefaults__ = copy.deepcopy(original.__kwdefaults__)
        previous = []
        counts = {'full':0,'strict_cut':0,'hypothetically_reusable_prior_clause':0,'new_clause':0}
        for action_index, action in enumerate(actions):
            # This complete independent reference is diagnostic work, never policy input.
            full = cut.original.predict(value, action)
            assert full['status'] == 'conditional_prediction'
            row = {'case_index':index,'action_index':action_index,'action':action}
            try:
                candidate = evaluate(value, action)
            except cut._Rejected as rejected:
                w = rejected.witness
                assert full['completion'][w['job']] == w['candidate_completed_at'] > reference[w['job']]
                assert list(w['completed_prefix'].items()) == list(full['completion'].items())[:len(w['completed_prefix'])]
                counts['strict_cut'] += 1
                matches = [p for p in previous if all(scalar_key(p['action'][k]) == scalar_key(action[k]) for k in p['read_keys'])]
                for prior in matches:
                    # Direct differential validation of every hypothetical reused witness.
                    assert ordered(prior['witness']) == ordered(w)
                row.update(status='existing_strict_prefix_cut', read_keys=rejected.read_keys,
                           witness=w, hypothetical_prior_matches=[p['action_index'] for p in matches])
                if matches:
                    counts['hypothetically_reusable_prior_clause'] += 1
                else:
                    counts['new_clause'] += 1
                    previous.append(row)
            else:
                assert ordered(candidate) == ordered(full)
                assert all(full['completion'][j] <= reference[j] for j in reference)
                assert not any(all(scalar_key(p['action'][k]) == scalar_key(action[k]) for k in p['read_keys']) for p in previous)
                row.update(status='full_exact', read_keys=sorted(expected))
                counts['full'] += 1
            rows.append(row)
        case_rows.append({'case_index':index,'counts':counts})
    assert pins == {str(Path(m.__file__).resolve().relative_to(ROOT)):sha(m.__file__) for m in modules}
    result = {'schema':'g31.action_dependency_diagnostic.v1','status':'bounded_pure_differential_passed',
        'source_sha256':pins,'source_proof':proof,'run_AST_restores_exactly':True,
        'cases':case_rows,'rows':rows,'full_candidates_separately_executed':192,
        'observed_cut_candidates_separately_executed':192,'full_baselines':6,
        'native_calls':0,'policy_changes':0,'new_cache_implemented':False,'performance_claim':False,
        'scope':'Potential within-request reuse only. Independent complete predictions are retrospective differential oracles; no saved outcome enters a policy. All 32 candidate queries would still be charged; unknown suffix remains unknown. No result applies to different snapshots, baseline, action domain, source, wire contract, or native decisions.',
        'unproved_for_implementation':['Closed production guard+source binding for clause replay','Cost and full request effect','Independent hostile-input tests','Native model validity and joint-method advantage'],
        'research_sources':[{'url':'https://arxiv.org/abs/cs/9308101','use':'Prior art: dependency-directed backtracking, no novelty claim'},
          {'url':'https://www.cs.cmu.edu/~rwh/papers/sap/mlw05.pdf','use':'Prior art: dynamic dependencies and memoization; no transfer of their speed claims'}],
        'producer_sha256':sha(__file__)}
    write(OUT/'report.json',result)
    print(json.dumps({'cases':case_rows,'report_sha256':sha(OUT/'report.json')}))

if '--child' in sys.argv:
    assert sys.stdin.readline() == sha(__file__)+'\n'
    diagnostic()
else:
    OUT.mkdir(exist_ok=False)
    start = time.perf_counter()
    with (OUT/'stdout.log').open('x',encoding='utf8') as stdout,(OUT/'stderr.log').open('x',encoding='utf8') as stderr:
        process = bounded_windows_job.run([sys.executable,str(Path(__file__).resolve()),'--child'],
            timeout=45.,stdout=stdout,stderr=stderr,admission=sha(__file__),cwd=ROOT)
    write(OUT/'bounded_execution.json',{'process':process,'outside_seconds':time.perf_counter()-start,
        'source_sha256':sha(__file__),'native_calls':0,'timing_comparison':False})
    print(json.dumps({'process':process,'report_sha256':sha(OUT/'report.json') if (OUT/'report.json').exists() else None}))
    if process['status'] != 'exited' or process['exitcode'] != 0: raise SystemExit(1)
