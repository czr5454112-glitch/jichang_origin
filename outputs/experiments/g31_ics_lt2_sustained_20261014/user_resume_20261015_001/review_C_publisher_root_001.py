from pathlib import Path
import json
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_complete_root_c_normalizer as a

HERE=Path(__file__).resolve().parent
DEST=a.OUT/'C_publisher_pair_prepare_001'
expected='840329a5c7eaf928f92b7c6d9a4bbfaf08bdf12260141e41f2863746e2df4072'
assert a.sha(DEST/'plan.json')==expected
plan=a.read(DEST/'plan.json')
assert a.sha(a.__file__)=='965ac698c7bd6cf3ec673c0a8fd1a2489ffc88d18b0312d233f48a7ab9d6424b'
assert len(plan['source_sha256'])==145 and len(plan['input_raw'])==18
assert plan['row_order']==a.declarations(plan['input_raw']) and len(plan['row_order'])==72
assert plan['hard_timeout_seconds']==240 and plan['binding_source_proof']==a.binding.source_proof()
for path,digest in plan['source_sha256'].items():assert a.sha(path)==a.sha(DEST/plan['source_archive'][path])==digest
pure=[]
for label,count in (('harness_pure',27),('binding_pure',8)):
    ref=plan[label];path=Path(ref['path']);assert a.sha(path)==ref['sha256']
    xml=path.parent/'tests.xml'
    suites=ET.parse(xml).getroot().findall('testsuite')
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert counts==dict(tests=count,failures=0,errors=0,skipped=0)
    pure.append({'label':label,'receipt':ref,'XML_sha256':a.sha(xml),'counts':counts})
assert not (DEST/'execution_claim').exists()
body=(HERE/'invoke_c_saved18_root_002_measured.ps1').read_text(encoding='utf8')
replacements={
 'c_tree_normalizer_saved18_prepare_002':'C_publisher_pair_prepare_001',
 '3d9688ced5b68f72d924f46876a064c0063276ac9b20bf5c2ccc88a182025e3e':expected,
 'ready_for_one_bounded_data_parity_attempt':'ready_for_one_bounded_full_publisher_cost_attempt',
 'review_complete_tree_normalizer_saved18_v2':'measure_complete_root_c_normalizer --execute',
 'g31.C_normalizer.saved18.external_wall.v2':'g31.C_publisher.ABBA72.external_wall.v1',
 'whole_python_within_180_seconds=($taskWall -le 180)':'whole_python_within_240_seconds=($taskWall -le 240)',
 'shared_owned_seconds=180;fixed_rows=18;required_direct_C_supported=18;model_calls=0;native_simulation_calls=0':
  'shared_owned_seconds=240;fixed_inputs=18;publisher_calls=72;required_direct_C_supported=18;model_calls=0;native_simulation_calls=0',
 'Complete fixed18 root data parity,16closed2unknown retained. Require direct bound C builtin supported18, complete ordered typed scalar and floathex equality, fresh containers, original codec bytes and strict decode. All imports,6124toolchain and source/raw/runtime entryexit hashes, loading, validation, copies, exports and exit included. Verification cost only; no performance or complete100ms claim.':
  'Fixed actual entrycodec18 x ABBA72 complete data publisher A originalPython normalization B verifiedC normalization. Complete originalcodec strictdecode hashledger publisherreturn and originaldeadline/eventclocks retained. Require18 directC fullargument preflights and72 complete saved readbacks. Imports,6124tools,145+169/135sources,18raws,runtime,load,binding,allpreflight/export/teardown/exit included in240. Mock component costs only, no actual native100ms or business effect.',
 "if ($taskWall -gt 180) {throw 'Whole Python saved18 parity budget exceeded'}":
  "if ($taskWall -gt 240) {throw 'Whole Python complete C publisher cost budget exceeded'}"
}
for old,new in replacements.items():
    assert body.count(old)==1,old
    body=body.replace(old,new)
wrapper=HERE/'invoke_C_publisher_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.C_publisher.full_cost.root_review.v1','plan_sha256':expected,'sources':145,
 'raw_fixture_reads_during_review':0,'C_loads_during_review':0,'native_calls':0,'pure':pure,
 'review':[
  'Full new driver/test/binding and reused complete72checker read. A actual entrycodec, B verifiedC; original functioncode/defaults/closures/fullglobals retained, exactly provider substitution plus shared mockproof/time.',
  'Each real EVIDENCE normalization argument directly checked by exact Cbuiltin for nonNotImplemented/fulltypedorderedfloathex/newcontainer result before measured ABBA. Its cost is in whole, not sample spans.',
  'All72 full records exported then strict readback compared by existing semantic_record exceptions only regenerated body/finalization/return clocks; original event/root/deadline clocks and all other fields remain.',
  '18input denominator16closed2unknown retained,36 samples perarm, ABBA fixed. Negative/equal roots preserved, no adaptive retry or omittedcases.',
  'Source/runtime/toolchain/raw/loaded checks entryexit, defaultGC, allsetup/export/teardown inside240; external clock includes interpreter startup and finalexit.',
  'Public source closure includes145; full original169/135 and6124toolchain checks deferred to ownedwhole. Review does not preload actualfixtures or C extension.',
  'Require completed_fixed_entry_codec_C_mock_ABBA receipt and passed_exact_complete_entry_codec18_C_normalizer_ABBA72 report,72samples,direct18,exit0,external<=240. This is never nativecomplete100ms.'
 ],'wrapper_sha256':a.sha(wrapper),'source_sha256':a.sha(__file__)}
review_path=DEST/'root_source_review_001.json'
with review_path.open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_bounded_full_publisher_cost_attempt','plan_sha256':expected,
 'root_review':{'path':str(review_path),'sha256':a.sha(review_path)},'wrapper_sha256':a.sha(wrapper)}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review_sha256':a.sha(review_path),'ready_sha256':a.sha(DEST/'root_ready_001.json'),'wrapper_sha256':a.sha(wrapper)}))
