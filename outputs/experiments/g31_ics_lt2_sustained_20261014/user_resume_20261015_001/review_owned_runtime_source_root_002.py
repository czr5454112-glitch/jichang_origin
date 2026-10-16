from pathlib import Path
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import live_obligation_owned_same_information_search as search
from scripts.experiments.g31_ics_circulation import prepare_live_owned_initial_runtime_v2 as prepare
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=prepare.ROOT;sha=prepare.sha
DEST=OUT/'live_owned_initial_runtime_source_prepare_002'
expected='37e6e8366b4d319b4ec0a566981864f56e3fa9914505340d100d4e159b4837fd'
assert sha(DEST/'plan.json')==expected
plan=json.loads((DEST/'plan.json').read_bytes());assert len(plan['source_sha256'])==188
prepare.verify_archive(ROOT,DEST,plan)
for name,digest in plan['source_sha256'].items():
    assert not Path(name).is_absolute() and not Path(name).drive and '\\' not in name
    current=(ROOT/name).resolve();saved=(DEST/plan['source_archive'][name]).resolve()
    assert current.is_relative_to(ROOT) and saved.is_relative_to(DEST) and current!=saved
    assert sha(current)==digest==sha(saved)
assert plan['source_proof']==search.source_proof()
old=json.loads((OUT/'live_owned_initial_runtime_source_prepare_001/plan.json').read_bytes())
for name in ('live_obligation_owned_prefix_evaluator','live_obligation_owned_initial_provider','live_obligation_owned_same_information_search'):
    key='scripts/experiments/g31_ics_circulation/'+name+'.py'
    assert plan['source_sha256'][key]==old['source_sha256'][key]
for name in ('test_g31_circulation_future_later_paired_driver','test_g31_circulation_live_initial_decision_seam','test_g31_circulation_future_later_fork'):
    assert 'tests/'+name+'.py' in plan['source_sha256']
pure=OUT/'live_owned_initial_runtime_pure_002'
assert sha(pure/'receipt.json')=='8747aa45d84d7a34f985526e668339af556e4aa24e73ac41950849ed682f7a62'
assert sha(pure/'tests.xml')=='084aa3ecce416c8ad2cfcfdece13ec9f1865ed713e481dcc06289a5751ae4a78'
assert sha(pure/'external_application_wall.json')=='73a204c701f91557d813e4b213d066fc0b40ab511ed314d7c1b0facd372b8e8f'
prepare.verify_archive(ROOT,pure,json.loads((pure/'plan.json').read_bytes()))
xml=ET.parse(pure/'tests.xml');assert len(xml.findall('.//testcase'))==71
assert not any(xml.findall('.//'+k) for k in ('failure','error','skipped'))
assert sha(HERE/'owned_runtime_archive_failure_root_001.json')=='e562fb2425a687a8de4a48933e3cddcf10d8235963d3c83f2f116355fd6e549c'
result={'schema':'g31.owned_initial_runtime.root_source_review.v2','plan_sha256':expected,
 'review_script_sha256':sha(__file__),'sources_current_and_independent_archive_verified':188,
 'focused_pure_tests':71,'prior_invalid_archive_still_rejected':True,'actual_model_calls':0,'native_calls':0,
 'notes':[
 'Root read all3 unchanged runtime modules,original paired/group/provider/future fork,47runtime tests,corrected v2prepare/pure and24 filesystem/fullprepare tests. Independent current/archive rehash verifies188 canonical unique sources plus corrected pure archive.',
 'Source-only accepted: inverse AST removes only diagnostics; original dynamic guards,16freshinitialcontexts,32wholegraphclones,80cuts65source inventories retained. All complete outputs and post-save unknowns preserved; v2 final current revalidation explicit.',
 'New ROOT-relative canonical merge resolves absolute predecessor reads, equal bytes only for aliases, rejects escape/drive-relative input, prechecks all destinations, uses exclusive writes and serialized-plan revalidation before ready. Rootchecked every saved path contained and different from live path.',
 'Old336-key package remains invalid (186unique/180badarchive), prior47 test assertions passed on current sources only. Samebyte currentwrites in oldattempt acknowledged; new71 pass is fresh evidence and does not repair old archive.',
 'Closed serial private construction ownership, no arbitrary private-state tamper guarantee. No fabricated graph flags; old independent graph audit remains historical reference only.',
 'Next fixed48groups/96fulloutputs must compare bytes/types/order/floathex and retained semantic points/terminal/counts after save. No real model/native/100ms/online superiority/full-day claim here.']}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(result,f,indent=2)
print(json.dumps({'review_sha256':sha(path),'status':'corrected_source_reviewed_actual_conformance_pending'}))
