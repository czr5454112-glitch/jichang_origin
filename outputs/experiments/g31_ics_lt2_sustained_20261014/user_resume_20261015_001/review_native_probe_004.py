"""Root prelaunch readback; no native imports or prediction execution."""
import datetime, difflib, hashlib, json
from pathlib import Path
from scripts.experiments.g31_ics_circulation import research_live_obligation_native_probe as m

root=m.ROOT; out=m.OUT; here=Path(__file__).resolve().parent
new=out/'live_obligation_native_probe_prepare_004'; old=out/'live_obligation_native_probe_prepare_003'
plan=m.read(new/'preregistered_protocol.json'); previous=m.read(old/'preregistered_protocol.json')
assert m.sha(new/'preregistered_protocol.json')=='7f5b1937a44efb2c7fe9b376765a1b9ddb44a9ad93575cadf48f6e0dc06acabc'
m.verify(new,plan)
assert plan['input_file_sha256']==previous['input_file_sha256']
assert plan['rows']==previous['rows'] and plan['binary']==previous['binary']
changed=[]; diffs={}
for path,digest in plan['source_sha256'].items():
    if digest!=previous['source_sha256'][path]:
        changed.append(Path(path).name)
        diffs[Path(path).name]=''.join(difflib.unified_diff((old/previous['source_archive'][path]).read_text(encoding='utf8').splitlines(True),(new/plan['source_archive'][path]).read_text(encoding='utf8').splitlines(True)))
assert set(changed)=={'live_obligation_native_guard.py','research_live_obligation_native_probe.py'}
old_wrapper=here/'invoke_live_obligation_native_probe_003_measured.ps1'
wrapper=here/'invoke_live_obligation_native_probe_004_measured.ps1'
text=old_wrapper.read_text(encoding='utf8').replace('live_obligation_native_probe_prepare_003','live_obligation_native_probe_prepare_004').replace('774f6d08159568e5d9e3d73a677fbdd25237708c69427d04adf5895106107ec5','7f5b1937a44efb2c7fe9b376765a1b9ddb44a9ad93575cadf48f6e0dc06acabc').replace('9f5c22eea4a9cb28633974859be1b4a1b60773d205311b1f6f5b17020c827c57','2d87ee2eed5890008a30bf3fba2b5a634b25a9b914854ee77798bda77d2fdad9')
assert not wrapper.exists()
wrapper.write_text(text,encoding='utf8')
record={'status':'passed_root_typed_loading_schema_review','recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'plan':m.reference(new/'preregistered_protocol.json'),'wrapper':m.reference(wrapper),'source_count':len(plan['source_sha256']),'changed_sources':changed,'input_actions_binary_identical_to003':True,'native027_observed_LOAD_START_source_reviewed':True,'actual003_three_hash_bound_captures_reviewed':True,'typed_loading_guard':'Only stationary E loading availability can equal future observed load_complete_at/service_ready_at >now; original ready kind, known bit, derived start<=floor, identity, occupancy, ACK union and freshness checks preserved. All other tray availability<=floor.','pure_test_reference':plan['auxiliary_references']['pure_tests'],'pure_tests':67,'fixed_branch_count':3,'shared_seconds':120,'runtime':'accepted027','native003_unknown_unchanged':True,'full96_native_certified':False,'native_dispatched':0,'diffs':diffs}
dest=new/'root_prelaunch_review_001.json'
assert not dest.exists();m.write(dest,record)
print(json.dumps({'review':m.reference(dest),'wrapper':m.reference(wrapper),'changed':changed,'diffs':diffs},indent=2))
