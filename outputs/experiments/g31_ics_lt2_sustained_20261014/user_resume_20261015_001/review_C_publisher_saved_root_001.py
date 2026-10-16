from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DEST = OUT/'C_publisher_saved_review_prepare_001'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
expected = '510ee1590e4c871eff6f25dd2ef5bf69262850575aaf50fb42e5cb1b086ce1d9'
assert sha(DEST/'plan.json') == expected
plan = json.loads((DEST/'plan.json').read_bytes())
assert len(plan['source_sha256']) == 147 and plan['hard_application_seconds'] == 120
assert plan['producer_source_count'] == 145 and plan['focused_pure_tests'] == 14
assert sha(ROOT/'scripts/experiments/g31_ics_circulation/review_complete_root_c_publisher_saved.py') == 'ad21c350c9b5b1fa458a1e8fcb627c155f7386a3f92accafa6b2d953bb3bd116'
for path, digest in plan['source_sha256'].items():
    assert sha(path) == digest == sha(DEST/plan['source_archive'][path]), path
assert not (DEST/'execution_claim').exists()
body = (HERE/'invoke_phase_b_saved_root_001_measured.ps1').read_text(encoding='utf8')
replacements = {
 'live_phase_b_pause_saved_review_prepare_001': 'C_publisher_saved_review_prepare_001',
 '8d5436594e96b9e2bd609bce2c2c0185177935698a45b0b3c0715141708fe48e': expected,
 'ready_for_one_bounded_saved_passive_review': 'ready_for_one_independent_C_publisher_saved_review',
 'review_live_phase_b_pause_saved --output $taskFolder --plan-sha256 $taskPlanSha': 'review_complete_root_c_publisher_saved --execute --output $taskFolder --expected-plan $taskPlanSha',
 'g31.passive_six.independent_saved.external_wall.v1': 'g31.C_publisher.independent_saved.external_wall.v1',
 'shared_owned_seconds=120;fixed_rows=6;expected_point_metadata=14;model_calls=0;native_simulation_calls=0': 'shared_owned_seconds=120;fixed_inputs=18;saved_publisher_rows=72;C_extension_loads=0;model_calls=0;native_simulation_calls=0',
 'Independent saved-only six full prediction byte readback, fourteen point chronology metadata, original initial/later guards and complete actual inventory reconstruction. All source/archive/data/loaded pins entryexit and exports inside120. No models/native/C and no independent alias or snapshot revalidation: graphs were not saved. No resumability, hidden-history coverage or100ms claim.': 'Independent saved-only72 complete publisher records against18 original fixtures. Original145/169/135source and6124toolchain/raw/runtime guards; strict types/order/floathex and regenerated clocks; original event/deadline fields retained;36samples perarm and all18paired outcomes recomputed. Producer direct18C support and alias facts remain producer observations. No C loading/model/native/performance or complete100ms claim.',
 'Whole Python passive saved review budget exceeded': 'Whole Python independent C publisher saved review budget exceeded',
}
for old, new in replacements.items():
    assert body.count(old) == 1, old
    body = body.replace(old, new)
wrapper = HERE/'invoke_C_publisher_saved_root_001_measured.ps1'
with wrapper.open('x', encoding='utf8', newline='\n') as stream: stream.write(body)
review = {'schema':'g31.C_publisher.independent_saved.root_review.v1','plan_sha256':expected,
 'source_count':147,'source_sha256':sha(__file__),'wrapper_sha256':sha(wrapper),
 'review':[
  'Independent author reader and14focused tests read in full; original guard routines retained, no C/model/native dispatch.',
  'All72raw records strictly decoded,18source fixtures full semantic equality, exactABBA order and36/36sample statistics with all18paired outcomes andexport chronology.',
  'Only previous regenerated clock exceptions; currentclock formulas checked, original root deadlines/events remain in semantic equality.',
  'Producer loaded99to100/runtime/source/GC and76.6456392whole receipt checked;18directC/alias facts explicitly producer-only statements.',
  'Own147source archives and original145/169/135/6124/raw guards entryexit; shared120 including imports,decode,verification,exports andprocess exit.',
  'Accept only report passed_independent_saved72_complete_record_review plus external exit0 andwhole<=120; any mismatch/failure remains unknown, never100ms.'
 ],'raw_reads_during_review':0,'dispatched':False}
with (DEST/'root_source_review_001.json').open('x',encoding='utf8') as f: json.dump(review,f,indent=2)
ready={'status':'ready_for_one_independent_C_publisher_saved_review','plan_sha256':expected,
 'root_review':{'path':str(DEST/'root_source_review_001.json'),'sha256':sha(DEST/'root_source_review_001.json')},'wrapper_sha256':sha(wrapper)}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f: json.dump(ready,f,indent=2)
print(json.dumps({'review_sha256':sha(DEST/'root_source_review_001.json'),'ready_sha256':sha(DEST/'root_ready_001.json'),'wrapper_sha256':sha(wrapper)}))
