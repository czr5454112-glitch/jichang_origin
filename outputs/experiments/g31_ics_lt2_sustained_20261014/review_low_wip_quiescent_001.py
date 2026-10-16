"""Source/pin-only review. Do not read active tapes or run native sessions."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import research_original_low_wip_quiescent as r

root=r.reference.ROOT
folder=r.reference.OUT/'original_low_wip_quiescent_prepare_001'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
ready_path=folder/'ready.json';campaign_path=folder/'campaign.json'
assert sha(ready_path)=='58eb4e886740db17dbe421d4f2ea254a5aa97eb005a11ee345a56095bccc148d'
assert sha(campaign_path)=='e89b5984673b5f6c2a9a3698e7d8def6b54eb7ca7eb292a17b78447a5bf4d26c'
ready,campaign=read(ready_path),read(campaign_path)
checks={}
for name,digest in campaign['case_plans'].items():
    case=folder/name;planpath=case/'preregistered_protocol.json';assert sha(planpath)==digest
    plan=read(planpath)
    assert len(plan['source_before'])==82 and len(plan['compiled_source_sha256'])==67
    for path,h in plan['source_before'].items():
        assert sha(path)==h==sha(case/'source_archive'/Path(path).relative_to(root))
    for path,h in plan['compiled_source_sha256'].items():assert sha(case/'compiled_source_archive'/path)==h
    assert sha(plan['binary'])==plan['binary_sha256'] and sha(case/'input.json.gz')==plan['input_sha256']
    assert plan['horizon']==86400. and plan['offered']==28506 and plan['trays']==22
    assert plan['supply_cap']=={'cap3':3,'cap8':8}[name]
    checks[name]={'runtime_source_archive_pins':82,'compiled_archive_pins':67,'binary_input_pins':True,
                  'horizon':plan['horizon'],'offered':plan['offered'],'trays':plan['trays'],'supply_cap':plan['supply_cap']}
xml=Path(ready['pure_tests']['path']);assert sha(xml)==ready['pure_tests']['sha256']
suites=ET.parse(xml).getroot().findall('testsuite')
counts={k:sum(int(s.attrib[k]) for s in suites) for k in ('tests','failures','errors','skipped')}
assert counts=={'tests':57,'failures':0,'errors':0,'skipped':0}
proof=r.candidate.prove_only_cap_check_moved()
result={'schema':'g31.low_wip_quiescent.independent_source_review.v1','status':'no_concrete_blocker_in_reviewed_scope',
 'ready':{'path':str(ready_path),'sha256':sha(ready_path)},'campaign_sha256':sha(campaign_path),
 'source_checks':checks,'candidate_ast_proof':proof,'pure_xml_inspected':{'path':str(xml),'sha256':sha(xml),**counts},
 'findings':[
  'The candidate class only moves the original cap test after current received-ACK barrier and before invitation/current-empty checks. Own refresh/retries and required ACK relay execute first.',
  'Stopping new publications on exhausted cap is not a job-completion claim. Every actual supply below cap retains original fresh empty/current source permit/peer FIFO/ACK barriers.',
  'The new process-local installation restores all substituted reference globals in finally, and nested base installation uses the candidate class. Frozen original producer files remain unchanged.',
  'New whole-tree2400 launcher includes workers, saved verification and comparison; each arm persists unknown on failure. The stopped original attempt is not extended or relabeled.',
  'Corrected saved verifier reads the actual ProtocolClient call.request.request_id and rejects conflicting top-level ID. It reruns the complete saved policy before promoting independent verification; old failing verifier/receipt remain unchanged.',
  'Completed old arms require exact jobs/trays/physical receipts and ordered physical transfer/query tape. Incomplete old arms retain unknown with only verified prefix comparison. Message histories/native seals are explicitly not assumed equal after new publication quiescence.',
  'The two new arms compare exact prefix through first actual cap3 proof, not a later completion time that would hide the intentional post-cap divergence.'
 ],
 'limits':['Source/pin review only; no native execution, no saved original full-tape replay by this reviewer, no actual speedup or protection certificate.',
           'Inspected57-test XML without rerunning that suite. Original completed-arm acceptance still requires the separate corrected actual saved replay.',
           'Old source-only plan001 had one changed new review-helper pin; it remains unaccepted as a full executable preparation. This new package binds the corrected helper.'],
 'review_script_sha256':sha(__file__),'native_executions':0}
target=folder/'independent_source_review_001.json';assert not target.exists()
target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'path':str(target),'sha256':sha(target)}))
