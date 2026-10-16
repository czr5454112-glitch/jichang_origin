from pathlib import Path
import json
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_bridge_copy_scopes as a

HERE=Path(__file__).resolve().parent
DEST=HERE.parent/'bridge_copy_scopes_cost_prepare_001'
expected='3e73a0ce84b5ef02ac6a92f95ac06296f7dc23ce268b38b3dadb66835a3ff755'
assert a.sha(DEST/'plan.json')==expected
plan=a.loads((DEST/'plan.json').read_bytes())
a.verify_pins(DEST,plan)
assert len(plan['sources'])==78 and plan['counts']['measured_invocations']==256
xml=Path(plan['pure']['xml']['path'])
counts={k:sum(int(s.get(k,0)) for s in ET.parse(xml).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=79,failures=0,errors=0,skipped=0)
assert not (DEST/'outer_claim.json').exists()
body=(HERE/'invoke_c_saved18_root_002_measured.ps1').read_text(encoding='utf8')
changes={
 'c_tree_normalizer_saved18_prepare_002':'bridge_copy_scopes_cost_prepare_001',
 '3d9688ced5b68f72d924f46876a064c0063276ac9b20bf5c2ccc88a182025e3e':expected,
 'ready_for_one_bounded_data_parity_attempt':'ready_for_one_bounded_synthetic_copy_cost_attempt',
 'review_complete_tree_normalizer_saved18_v2':'launch_bridge_copy_scopes',
 'g31.C_normalizer.saved18.external_wall.v2':'g31.bridge_copy.synthetic_cost.external_wall.v1',
 'whole_python_within_180_seconds=($taskWall -le 180)':'whole_python_within_120_seconds=($taskWall -le 120)',
 "'execution_claim'":"'outer_claim.json'",
 'shared_owned_seconds=180;fixed_rows=18;required_direct_C_supported=18;model_calls=0;native_simulation_calls=0':
  'shared_owned_seconds=120;fixed_families=2;fixed_batches=8;fixed_invocations=256;jobs_per_capture=64;capture_revisions=16;model_calls=0;native_simulation_calls=0',
 'Complete fixed18 root data parity,16closed2unknown retained. Require direct bound C builtin supported18, complete ordered typed scalar and floathex equality, fresh containers, original codec bytes and strict decode. All imports,6124toolchain and source/raw/runtime entryexit hashes, loading, validation, copies, exports and exit included. Verification cost only; no performance or complete100ms claim.':
  'Fixedsynthetic64job16revision twofamily ABBA32 each;256 measuredcalls. Original refresh versus discard-only returns and original owncapture versus temporaryborrow plusoriginalreadconsumers. Exactfullresult/order/type/floatbit/state/ACK/index/query/alias checks retained. Every fixture rebuild,validation,journal,exports,savedreadback,sourcechecks,cleanup inwhole120; isolatedspans also reported. No historicalruntimeclientstate,no native/fullpolicy replay and no whole600/full-day/100ms inference.',
 "if ($taskWall -gt 180) {throw 'Whole Python saved18 parity budget exceeded'}":
  "if ($taskWall -gt 120) {throw 'Whole Python synthetic copy cost budget exceeded'}"
}
for old,new in changes.items():
    assert body.count(old)==1,old
    body=body.replace(old,new)
wrapper=HERE/'invoke_bridge_copy_cost_root_001_measured.ps1'
with wrapper.open('x',encoding='utf8',newline='\n') as f:f.write(body)
review={'schema':'g31.bridge_copy.synthetic_cost.root_review.v1','plan_sha256':expected,'source_count':78,'pure_counts':counts,
 'review':[
  'Read all privatecopy module37pure, costdriver/fixture/launcher42pure, originalselector/BridgeOwner calls and consumer mutations. Four inverseAST expressions, originalclosure and MRO preserved.',
  'Only two discard-refresh callsites and one activationlocal owncapture borrow. Retained client_view and escapingPossessionGate originals unchanged. Complete guard executions, no digest/result caching.',
  'Synthetic seed exactly originalpurefixture AST; exactly64job16revision fresh rebuilt eachinvoke, not finalraw masquerading as clienthistory. Fixed2families8ABBA batches32each256calls.',
  'First measuredA per family is fullreference, no extraoracle. Each result compares allorderedbytes and separate alias/queries/state/index/choiceguards. OriginalgenericAPI remains.',
  'Isolatedspan includesinvoke and clockoverhead; batch includesfixture/digest/sourceinputchecks/validation/fullcompare/journal/cleanup. Wholeowned120 includescampaignparent andsavedreadback; externalstartupexit measured.',
  'Refreshbenchmark has16deliveredqueries and0retries; retry/error behavior is puretested only, not performance-measured. Borrow is serialclosedsource scope and resourcefailure timing equivalence not claimed.',
  'Accept only256savedrecords8batchespassed_synthetic_cost_diagnostic_only plusinner andoutercompleted/0errors/sourcepins andexternal<=120. Localcost does not certify prior600 audit or fullpolicy.'
 ],'wrapper_sha256':a.sha(wrapper),'source_sha256':a.sha(__file__)}
path=DEST/'root_source_review_001.json'
with path.open('x',encoding='utf8') as f:json.dump(review,f,indent=2)
ready={'status':'ready_for_one_bounded_synthetic_copy_cost_attempt','plan_sha256':expected,
 'root_review':{'path':str(path),'sha256':a.sha(path)},'wrapper_sha256':a.sha(wrapper)}
with (DEST/'root_ready_001.json').open('x',encoding='utf8') as f:json.dump(ready,f,indent=2)
print(json.dumps({'review_sha256':a.sha(path),'ready_sha256':a.sha(DEST/'root_ready_001.json'),'wrapper_sha256':a.sha(wrapper)}))
