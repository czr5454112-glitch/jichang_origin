"""Pure source packaging; does not execute the saved audit or any native code."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
import audit_saved_route_native027_phase as audit

p=audit.p;root=p.ROOT;out=p.OUT
folder=out/'route_native027_saved_audit_prepare_001';folder.mkdir(exist_ok=False)
source=out/'original_route_native027_phase_prepare_002'
target=out/'route_native027_saved_audit_001'
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
campaign=p.old.read(source/'campaign.json')
new=[root/'audit_saved_route_native027_phase.py',root/'launch_saved_route_native027_phase.py',
     root/'tests/test_g31_circulation_saved_route_phase.py',Path(__file__).resolve()]
pins=dict(campaign['source_before'])
pins.update({str(path):sha(path) for path in new})
for path,digest in pins.items():
    path=Path(path);assert sha(path)==digest
    dest=folder/'source'/path.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,dest);assert sha(dest)==digest
xml=out/'saved_route_phase_pure_001.xml'
suites=ET.parse(xml).getroot().findall('testsuite')
counts={key:sum(int(s.attrib[key]) for s in suites) for key in ('tests','failures','errors','skipped')}
assert counts=={'tests':14,'failures':0,'errors':0,'skipped':0}
actual_pins,outer=audit.original_inventory(source)
plain=p.old.read(source/'plain/receipt.json');timed=p.old.read(source/'timed/receipt.json')
last=timed['cases']['ack_withheld_in_window']['parent_child_end_ns']
elapsed=(last-plain['parent_measured_start_ns'])/1e9
diagnosis={'actual_six_children_completed_at_seconds_from_campaign_measurement':elapsed,
 'upper_remaining_verification_seconds_within600':600.-elapsed,
 'sum_six_child_wall_seconds':sum(r['whole_child_wall_seconds'] for rec in (plain,timed) for r in rec['cases'].values()),
 'original_status':outer['status'],'original_process_status':outer['process']['status'],
 'reason_scope':'Repeated full API materialization/normalization/serialization is a source-derived cost candidate, not an observed profiler attribution. Original verifier emitted no intermediate stage measurements.',
 'new_algorithm':'Original case validation executes once per case and its final-return callback uses the same decoded rows for phase checks. Exact API comparisons use one normalized row pair at a time; all current/reference controller parts and plain/timed API equality remain required.',
 'original_timeout_preserved':True,'native_rerun_required':False}
plan={'schema':'g31.saved_route_phase_audit.preparation.v1','status':'prepared_saved_audit_unexecuted',
 'source_campaign':str(source),'source_campaign_sha256':sha(source/'campaign.json'),
 'original_external_receipt_sha256':sha(source/'external_launch_receipt.json'),
 'source_pins':pins,'original_evidence_pins':actual_pins,'diagnosis':diagnosis,
 'pure_tests':{'path':str(xml),'sha256':sha(xml),**counts},
 'native_executions':0,'audit_hard_limit_seconds':1800.,'original_native_campaign_limit_seconds':600.,
 'scope':'Independent saved audit only; success must not rewrite the timed-out producer or become a within600s campaign claim.'}
p.old.write(folder/'plan.json',plan)
ready={'schema':'g31.saved_route_phase_audit.ready.v1','status':'prepared_no_execution',
 'plan_path':str(folder/'plan.json'),'plan_sha256':sha(folder/'plan.json'),'output':str(target),
 'execute_command':[sys.executable,'-m','launch_saved_route_native027_phase','--source',str(source),'--output',str(target),
    '--expected-auditor-sha256',sha(root/'audit_saved_route_native027_phase.py'),
    '--expected-launcher-sha256',sha(root/'launch_saved_route_native027_phase.py')],
 'source_count':len(pins),'pure_tests':counts,'hard_limit_seconds':1800.,'native_executions':0}
p.old.write(folder/'ready.json',ready)
assert all(sha(path)==digest for path,digest in pins.items())
print(json.dumps({'ready':str(folder/'ready.json'),'sha256':sha(folder/'ready.json'),'plan_sha256':sha(folder/'plan.json'),
 'sources':len(pins),'diagnosis':diagnosis}))
