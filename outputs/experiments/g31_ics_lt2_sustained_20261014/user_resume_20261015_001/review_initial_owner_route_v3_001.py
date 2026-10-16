"""Root review of the versioned live JSON/failure-clock integration repair."""
from pathlib import Path
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import initial_owner_route_campaign_v3 as c
out=c.OUT/'initial_owner_route_campaign_v3_prepare_001'; here=Path(__file__).parent
expected='e5459ab579d76e65c76ee41b0a4bc5f06224f3be0796ace6636ec4d0a2f7b46d'
plan=c.verify_plan(out,expected)
assert len(plan['source_sha256'])==130 and len(plan['compiled_source_archive_sha256'])==67 and len(plan['rows'])==18
loaded=c.check_loaded_sources(plan)
counts={k:sum(int(s.get(k,0)) for s in ET.parse(plan['pure_XML']['path']).getroot().iter('testsuite'))
        for k in ('tests','failures','errors','skipped')}
assert counts==dict(tests=134,failures=0,errors=0,skipped=0)
assert plan['pure_XML']['sha256']=='d4470e5307ee24655cc55320aabd7e906e77429938c7624a5a54c3a7687a0ad4'
old_counts={}
for name,count in (('initial_owner_route_campaign_prepare_002',124),('initial_owner_route_campaign_v2_prepare_001',129)):
    folder=c.OUT/name; old=c.read(folder/'campaign.json')
    assert len(old['source_sha256'])==count
    for path,digest in old['source_sha256'].items():
        assert c.sha(path)==c.sha(folder/old['source_archive'][path])==digest
    old_counts[name]=count
assert c.sha(c.ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp')=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_initial_owner_route_v3_001_measured.ps1'
assert not wrapper.exists()
text=(here/'invoke_initial_owner_route_campaign_002_measured.ps1').read_text(encoding='utf8')
launcher=c.ROOT/'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_campaign_v3.py'
changes={
 'initial_owner_route_campaign_prepare_002':'initial_owner_route_campaign_v3_prepare_001',
 '937d8505d33feeead2bfbbeb3479bb0038a82fbdd013ba2273700123e519d3e5':expected,
 'launch_initial_owner_route_campaign':'launch_initial_owner_route_campaign_v3',
 '95163bd5324df786fe87aa3457050e35fa05ae4f2dbd8327d6da0058bbbc1b50':c.sha(launcher),
 'g31.initial_owner_route.external_application_wall.v1':'g31.initial_owner_route.external_application_wall.v3',
 'Original bridge ended. Both other agents reported no active children and paused new pure, native, benchmark and heavy I/O until this performance window closes.':'Fresh96 functional campaign and bridge prelaunch review ended. Other agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this performance window closes.',
}
for before,after in changes.items():
    assert before in text; text=text.replace(before,after)
with wrapper.open('x',encoding='utf8',newline='\n') as f: f.write(text)
report={'schema':'g31.initial_owner_route.root_prelaunch_review.v3',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'passed_finite_native_attempt_ready',
 'campaign_sha256':expected,'source_preparation':c.reference(out/'source_preparation.json'),
 'live_archive_sources_verified':130,'compiled027_archive_sources_verified':67,
 'loaded_project_sources_verified':len(loaded),'older_source_packages_unchanged':old_counts,
 'pure_tests':counts,'startup_reference':plan['startup_reference'],
 'reviewed_rules':[
  'Same original18 fixed arms,actual NativeSession and fixed B@.11/fullH40 continuation; unchanged old request,collector,ledger and worker image.',
  'Actual collector and retained live authority precede bounded builtin representation normalization. No normalization of session,accepted handles or capability ledger.',
  'All builtin tuples convert to fresh lists; this is representation conversion,not field authorization. Original dynamic model guards still reject invalid field shapes.',
  'Resources only in conditional_model_input bundle require homogeneous exact nonnegative integer keys or canonical ASCII decimal string keys, exact integer node identity; mixed keys,aliases/custom/nonfinite/cycles rejected.',
  'SavedJSON fixture only proves int resource shape; accepted027 binding-specific node/edge tuple fixture separately reproduces the actual live strict codec failure.',
  'Every available lifecycle timestamp exact nonnegative integer; order and export bounds checked. Missing-raw branch duration remains distinct from unknown root duration.',
  'Aborted predictor not restarted or falsely CLOSED; failed root admitted clock and typed builtin evidence retained. No postexception physics advancement.',
  'One600s owned process tree and all18 rows; complete root includes actual collection,codec,RPC,final reread,submission,retry,ACK,firsthop and outside-return costs. Cold/failed/shared costs retained separately without subtraction or amortization.',
  'Existing full endpoint/immutable RPC/full physical audit retained; fault rows are not certified by normal point-model assumptions.',
 ],
 'limits':['Finite2 initial integration only,not full32/general/cold100ms.','No original-day or joint-method certificate.','Unrelated system/user load uncontrolled.'],
 'producer':c.reference(__file__),'wrapper':c.reference(wrapper),'native_executions':0,'model_evaluations':0}
review=out/'root_prelaunch_review_001.json'
with review.open('x',encoding='utf8') as f: json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as f:
    json.dump({'status':'ready_for_one_bounded_actual_attempt','campaign_sha256':expected,
      'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
      'native_dispatched':False,'fixed_native_branches':18,'owned_seconds':600},f,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper),'launcher_sha256':c.sha(launcher)}))
