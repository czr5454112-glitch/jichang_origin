from pathlib import Path
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import prepare_single_capture_owned_codec as source
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=source.gate.ROOT;sha=source.gate.sha
DEST=OUT/'single_capture_owned_codec_source_prepare_001'
expected='63c2aab25f133ba72df76533a4f53b9fa0cfb962ca748c9dd970117d1479cb00'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==156
for name,digest in plan['source_sha256'].items():
    assert not Path(name).is_absolute() and not Path(name).drive and '\\' not in name
    current=(ROOT/name).resolve();saved=(DEST/plan['source_archive'][name]).resolve()
    assert current.is_relative_to(ROOT) and saved.is_relative_to(DEST) and current!=saved
    assert saved==source.gate.archive_target(DEST,name) and sha(current)==digest==sha(saved)
for name,row in plan['evidence'].items():
    saved=(DEST/row['archive']).resolve();assert saved.is_relative_to(DEST) and saved!=Path(name).resolve()
    assert sha(name)==row['sha256']==sha(saved)
assert sha(DEST/'source_proof.json')==plan['source_proof_sha256']
assert json.loads((DEST/'source_proof.json').read_bytes())==source.candidate.source_proof()
assert sha(DEST/'source_preparation.json')=='f53fb8a065f65930c2f351f7eab5882d066003a7ccffd0e6387beaefb7ca08df'
pure=OUT/'single_capture_owned_codec_pure_001'
assert sha(pure/'receipt.json')=='6842d7a940ff617fcc552c4a0d4537bf36b9e3f8fb7566af2c03ece540b55000'
assert sha(pure/'tests.xml')=='4588013e3dad02ad613a3a7c337414cd0fc82b02d3f7f56519c767941b252da9'
xml=ET.parse(pure/'tests.xml');assert len(xml.findall('.//testcase'))==45
assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
result={'schema':'g31.single_capture.owned_C_publisher.root_source_review.v1','plan_sha256':expected,
 'review_script_sha256':sha(__file__),'current_and_archive_sources_verified':156,'focused_pure_tests':45,
 'actual_C_loads':0,'native_calls':0,'model_calls':0,'notes':[
 'Root read complete binder,40 wiring tests plus5 path checks,pure runner,prepare and original singlecapture/entrycodec campaign. Request subclasses only evidence; same original actualchain constructor/classcell/exactdrain, collect/finalcurrent/observer and B wrapper remain.',
 'Same complete evidence publisher through verified existing Candidate B. Both scheduler and branch direct failure publication privately bound with original code/defaults/kwdefaults/closure/fullglobals. Original runtime proof and complete clocks,hash,ledger andreturn stay.',
 'Private synthetic compose is only wiring evidence, not verified C execution. Public bind calls original exact Candidate/Method/builtin/ABI/source binder, no extra fallback or implicit C load. Collection normalization/model unchanged.',
 '156canonical sources independently archived and every evidence copy bound. Old190/153 reference verification belongs to recorded pure/preparation, not newly repeated here. Future actual campaign must revalidate those roots plus binary/runtime/loaded DLL closure.',
 '45pure includes40 wiring/complete-output/clock/failure/authority cases and5 paths. Actual root C-support still requires honest provenance; fallback must not be labeled directC, all costs charged.',
 'Source accepted, actual18 campaign/failure-aware saved verification not yet prepared. Old16closed2unknown/0under100 remains. No performance or general100ms claim.']}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'review_sha256':sha(path),'status':'source_reviewed_actual_campaign_pending'}))
