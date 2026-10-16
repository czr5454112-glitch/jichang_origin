"""Root metadata/source review; no extension loading or18raw/toolchain sweep."""
from pathlib import Path
import hashlib
import json
from scripts.experiments.g31_ics_circulation import review_complete_tree_normalizer_saved18_v2 as a

here = Path(__file__).resolve().parent
out = a.OUT/'c_tree_normalizer_saved18_prepare_002'
expected = '3d9688ced5b68f72d924f46876a064c0063276ac9b20bf5c2ccc88a182025e3e'
assert a.sha(out/'plan.json') == expected
assert a.sha(a.__file__) == '482efb2b7cce682e0e9bc414b2185b91e4bf3e4b94cdcadf8b39fd1b274de46d'
plan = a.read(out/'plan.json')
assert plan['schema'] == 'g31.C_normalizer.fixed18_saved_parity.v2' and plan['limit_seconds'] == 180
assert len(plan['source_sha256']) == 10
assert {p: hashlib.sha256(b).hexdigest() for p, b in a.closure().items()} == plan['source_sha256']
for name, digest in plan['source_sha256'].items():
    assert a.sha(a.ROOT/name) == a.sha(out/'source'/name) == digest
assert a.frozen_sources() == plan['original_frozen_sources']
build, rows, runtime = a.metadata()
assert rows == plan['fixed_input_rows'] and len(rows) == 18
assert runtime == plan['runtime_dependencies'] and build['binary'] == plan['binary']
assert a.sha(plan['binary']['path']) == plan['binary']['sha256'] == 'e95b1de151c7628b32707bde17c4342f528b3de47af430d18be8d57b2ecb6786'
assert a.comparator_controls() == {'type_order_signedzero_tuple_extra_unicode_negatives': 7,
                                 'alias_negative': 1, 'source_byte_negatives': 2}
assert not (out/'execution_claim').exists()
assert not (a.OUT/'c_tree_normalizer_saved18_prepare_001/execution_claim').exists()
body = (here/'invoke_phase_b_six_root_001_measured.ps1').read_text(encoding='utf8')
changes = {
    'live_phase_b_pause_prepare_001': 'c_tree_normalizer_saved18_prepare_002',
    'be90c0042ac1073e7c880275c2fc412a0d11242bc06189bfc93a52eb309a8fbb': expected,
    'ready_for_one_bounded_conformance_attempt': 'ready_for_one_bounded_data_parity_attempt',
    'execution_claim.json': 'execution_claim',
    'validate_live_phase_b_pause --execute --output $taskFolder --expected-plan $taskPlanSha':
        'review_complete_tree_normalizer_saved18_v2 --output $taskFolder --plan-sha256 $taskPlanSha',
    'g31.passive_phase_b_six.external_wall.v1': 'g31.C_normalizer.saved18.external_wall.v2',
    'whole_python_within_120_seconds=($taskWall -le 120)': 'whole_python_within_180_seconds=($taskWall -le 180)',
    'shared_owned_seconds=120;fixed_rows=6;maximum_model_evaluations=6;expected_hook_points=14;native_calls=0':
        'shared_owned_seconds=180;fixed_rows=18;required_direct_C_supported=18;model_calls=0;native_simulation_calls=0',
    'Fixed6 passive model runs,14 snapshot points, full prediction bytes against frozen lazy comparands, complete alias graph and isolation checks. Independent actual supplied inventories do not establish model-point relations. Whole launch/import/pins/model/copy/check/export/cleanup/exit included. No resumability, native authority, hidden-state coverage, online efficacy or100ms certificate.':
        'Complete fixed18 root data parity,16closed2unknown retained. Require direct bound C builtin supported18, complete ordered typed scalar and floathex equality, fresh containers, original codec bytes and strict decode. All imports,6124toolchain and source/raw/runtime entryexit hashes, loading, validation, copies, exports and exit included. Verification cost only; no performance or complete100ms claim.',
    "if ($taskWall -gt 120) {throw 'Whole Python six-input budget exceeded'}":
        "if ($taskWall -gt 180) {throw 'Whole Python saved18 parity budget exceeded'}",
}
for before, after in changes.items():
    assert body.count(before) == 1, before
    body = body.replace(before, after)
wrapper = here/'invoke_c_saved18_root_002_measured.ps1'
with wrapper.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(body)
ref = lambda p: {'path': str(Path(p).resolve()), 'sha256': a.sha(p)}
review = out/'root_source_review_001.json'
report = {'schema': 'g31.C_normalizer.saved18.root_review.v2', 'plan_sha256': expected,
    'source_count': 10, 'prior_frozen_counts': [169, 135], 'raw_reads': 0,
    'extension_loads': 0, 'toolchain_sweep_in_prelaunch': False, 'owned_seconds': 180,
    'reviewed': [
        'Read entire v1/v2 driver and original candidate/completecodec sources. All18 full root_records[0] objects including clocks and ledger, no field exclusion.',
        'V1 source preparation remains unexecuted. V2 directly calls verified builtin for every row, rejects NotImplemented and checks type/order/floathex/fresh containers against original Python plus wrapped calls and fullcodec.',
        'Completecodec function code/defaults/closure/kwdefaults remain, full defining globals retained, only private normalization facade differs. Original encoder bytes and strict decoder remain exact.',
        'All frozen source, build/function archive, pyd, runtime,6124toolchain and raw pins rechecked inside execution at both ends. Loaded project and runtime paths matched; GC remains enabled.',
        '61functional accepted, current pin and ABI match3.11.9 nonlimited contract; no new simulation loaded. Stable-input and recursion privatefield limitation remains.',
        'A passing parity gate cannot establish speed. Resource/source/import/mismatch failures or180 timeout remain unknown; no replay/native retry.',
    ], 'comparator_negative_controls': a.comparator_controls(),
    'source': ref(__file__), 'wrapper_sha256': a.sha(wrapper)}
with review.open('x', encoding='utf8') as stream:
    json.dump(report, stream, indent=2, allow_nan=False)
with (out/'root_ready_001.json').open('x', encoding='utf8') as stream:
    json.dump({'status': 'ready_for_one_bounded_data_parity_attempt', 'plan_sha256': expected,
        'root_review': ref(review), 'wrapper_sha256': a.sha(wrapper),
        'owned_seconds': 180, 'dispatched': False}, stream, indent=2)
print(json.dumps({'review_sha256': a.sha(review), 'ready_sha256': a.sha(out/'root_ready_001.json'),
                  'wrapper_sha256': a.sha(wrapper)}))
