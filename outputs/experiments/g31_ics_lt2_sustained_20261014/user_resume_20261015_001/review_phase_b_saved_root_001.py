from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
HERE = Path(__file__).resolve().parent
DEST = OUT/'live_phase_b_pause_saved_review_prepare_001'
expected = '8d5436594e96b9e2bd609bce2c2c0185177935698a45b0b3c0715141708fe48e'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(DEST/'plan.json') == expected
plan = json.loads((DEST/'plan.json').read_bytes())
assert plan['source_count'] == 106 and plan['producer_source_count'] == 105
assert plan['hard_application_seconds'] == 120 and plan['new_model_calls'] == plan['new_native_calls'] == 0
assert sha(ROOT/'scripts/experiments/g31_ics_circulation/review_live_phase_b_pause_saved.py') == 'fc4cfbec726b7f6b2a9f3969b7395c21398fcd10c0571e487d54deb6385ad0e7'
for path, digest in plan['source_sha256'].items():
    assert sha(path) == sha(DEST/plan['source_archive'][path]) == digest
assert not (DEST/'execution_claim').exists()
body = (HERE/'invoke_c_saved18_root_002_measured.ps1').read_text(encoding='utf8')
replacements = {
    'c_tree_normalizer_saved18_prepare_002': 'live_phase_b_pause_saved_review_prepare_001',
    '3d9688ced5b68f72d924f46876a064c0063276ac9b20bf5c2ccc88a182025e3e': expected,
    'ready_for_one_bounded_data_parity_attempt': 'ready_for_one_bounded_saved_passive_review',
    'review_complete_tree_normalizer_saved18_v2': 'review_live_phase_b_pause_saved',
    'g31.C_normalizer.saved18.external_wall.v2': 'g31.passive_six.independent_saved.external_wall.v1',
    'whole_python_within_180_seconds=($taskWall -le 180)': 'whole_python_within_120_seconds=($taskWall -le 120)',
    'shared_owned_seconds=180;fixed_rows=18;required_direct_C_supported=18;model_calls=0;native_simulation_calls=0':
        'shared_owned_seconds=120;fixed_rows=6;expected_point_metadata=14;model_calls=0;native_simulation_calls=0',
    'Complete fixed18 root data parity,16closed2unknown retained. Require direct bound C builtin supported18, complete ordered typed scalar and floathex equality, fresh containers, original codec bytes and strict decode. All imports,6124toolchain and source/raw/runtime entryexit hashes, loading, validation, copies, exports and exit included. Verification cost only; no performance or complete100ms claim.':
        'Independent saved-only six full prediction byte readback, fourteen point chronology metadata, original initial/later guards and complete actual inventory reconstruction. All source/archive/data/loaded pins entryexit and exports inside120. No models/native/C and no independent alias or snapshot revalidation: graphs were not saved. No resumability, hidden-history coverage or100ms claim.',
    "if ($taskWall -gt 180) {throw 'Whole Python saved18 parity budget exceeded'}":
        "if ($taskWall -gt 120) {throw 'Whole Python passive saved review budget exceeded'}",
}
for old, new in replacements.items():
    assert body.count(old) == 1, old
    body = body.replace(old, new)
wrapper = HERE/'invoke_phase_b_saved_root_001_measured.ps1'
with wrapper.open('x', encoding='utf8', newline='\n') as stream: stream.write(body)
review = {'schema': 'g31.passive_six.independent_saved.root_review.v1', 'plan_sha256': expected,
    'source_count': 106, 'original_source_count': 105, 'source_sha256': sha(__file__),
    'review': [
        'Reader source read in full. Independent author from passive producer; saved only, no model/C/native calls.',
        'Fixed6 and14 chronology, full decompressed prediction bytes, original actual endpoint initial/later guards, full typed/ordered actual inventory checks.',
        'Original producer entry/exit/import identities and105 archives checked, together with external whole12.4314135 and original owned process.',
        'Graph not serialized: digest/alias/isolation only producer attestation. Reader does not turn these claims into independent graph proof.',
        'Whole import, entry/exit hashes, gzip/JSON/guards/export/exit inside one120. Any mismatch/error/timeout remains failed or unknown.',
        'Acceptance requires report passed_saved_six_and_fourteen_metadata_original_guards, six rows/fourteen metadata, external exit0 and <=120.'
    ], 'raw_reads_during_review': 0, 'dispatched': False, 'wrapper_sha256': sha(wrapper)}
with (DEST/'root_source_review_001.json').open('x', encoding='utf8') as stream: json.dump(review, stream, indent=2)
ready = {'status': 'ready_for_one_bounded_saved_passive_review', 'plan_sha256': expected,
    'root_review': {'path': str(DEST/'root_source_review_001.json'), 'sha256': sha(DEST/'root_source_review_001.json')},
    'wrapper_sha256': sha(wrapper)}
with (DEST/'root_ready_001.json').open('x', encoding='utf8') as stream: json.dump(ready, stream, indent=2)
print(json.dumps({'review_sha256': sha(DEST/'root_source_review_001.json'), 'ready_sha256': sha(DEST/'root_ready_001.json'), 'wrapper_sha256': sha(wrapper)}))
