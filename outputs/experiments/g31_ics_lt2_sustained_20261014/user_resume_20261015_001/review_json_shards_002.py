"""No prediction: verify narrow wiring fix and prepare external wrapper."""
from datetime import datetime, timezone
from pathlib import Path
import json
from scripts.experiments.g31_ics_circulation import measure_json_prediction_shards as m

here=Path(__file__).resolve().parent;out=here.parent
old=out/'json_prediction_shards_RPC_prepare_001';new=out/'json_prediction_shards_RPC_prepare_002'
plan=m.read(new/'preregistered_protocol.json');previous=m.read(old/'preregistered_protocol.json')
assert m.sha(new/'preregistered_protocol.json')=='6960f3205c5eef7fbb8ec4f772defadbaac682e5e859f6433a5c3f4ee5ea92e1'
m.verify_pins(new,plan)
original=out/'json_prediction_RPC_prepare_002';m.old.verify_pins(original,m.read(original/'preregistered_protocol.json'))
module='scripts/experiments/g31_ics_circulation/measure_json_prediction_shards.py'
before=(old/'source'/module).read_text(encoding='utf8');after=(new/'source'/module).read_text(encoding='utf8')
assert before.replace("output[value['directory']]","output/value['directory']").replace('EXPECTED_PURE_TESTS = 60','EXPECTED_PURE_TESTS = 61')==after
changed=[n for n,d in plan['source_sha256'].items() if previous['source_sha256'][n]!=d]
assert set(changed)=={module,'tests/test_g31_circulation_json_prediction_shards.py'}
assert plan['images']==previous['images'] and plan['cases']==previous['cases']
oldw=here/'invoke_json_prediction_shards_RPC_001_measured.ps1';w=here/'invoke_json_prediction_shards_RPC_002_measured.ps1'
assert not w.exists()
w.write_text(oldw.read_text(encoding='utf8').replace('json_prediction_shards_RPC_prepare_001','json_prediction_shards_RPC_prepare_002').replace('02be2c7b8e13ece2bce535558f9b64caecdee3961091ca6dfc0f89ad55382544','6960f3205c5eef7fbb8ec4f772defadbaac682e5e859f6433a5c3f4ee5ea92e1').replace('efed29ccec020951c52f9ec7c4f6d9264125a870535e702f886c5db280543033','e1b65f89047370172236d4eeb69fe6ab64345df6137a7862f64fdaeb3afdb7b6'),encoding='utf8')
def ref(p):return {'path':str(p.resolve()),'sha256':m.sha(p)}
r={'status':'passed_root_narrow_campaign_wiring_fix_review','recorded_utc':datetime.now(timezone.utc).isoformat(),'plan':ref(new/'preregistered_protocol.json'),'source_count':88,'old_JSON_source_count':85,'source_pins_passed':True,'runtime_change':'Only WindowsPath subscript changed to path join; purecount60->61; new campaign-to-constructor regression.','changed_sources':changed,'wiring_proof':ref(new/'wiring_fix_proof_001.json'),'prior_independent_review':ref(old/'independent_source_review_001.json'),'prior_root_review':ref(old/'root_prelaunch_review_001.json'),'wrapper':ref(w),'same_two_images_and_inputs':True,'native_calls':0,'prediction_calls':0,'performance_executed':False,'complete100ms_certified':False}
dest=new/'root_prelaunch_review_001.json';assert not dest.exists();m.write(dest,r)
print(json.dumps({'review':ref(dest),'wrapper':ref(w)}))
