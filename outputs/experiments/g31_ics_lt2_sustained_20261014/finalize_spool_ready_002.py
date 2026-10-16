"""Pure metadata preparation; never launches the actual three-case campaign."""
import argparse
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.experiments.g31_ics_circulation import probe_original_route_update_spool as p
from scripts.experiments.g31_ics_circulation import spooled_service_tape as sink

parser = argparse.ArgumentParser(); parser.add_argument('--ready', action='store_true'); args = parser.parse_args()
began = time.perf_counter(); output = p.OUT/'original_route_spool_prepare_002'
plan = p.old.read(output/'preregistered_protocol.json')
if not args.ready: p.verify_campaign(output)
xml = p.OUT/'spool_candidate_pure_002.xml'; cases = ET.parse(xml).getroot().findall('.//testcase')
assert len(cases) == 50 and not any(child.tag in {'failure','error','skipped'} for case in cases for child in case)
old_plan = p.old.read(p.OUT/'deferred_tape_cost_001/plan.json')
assert all(p.old.sha(path) == digest for path, digest in old_plan['source_before'].items())
wrapper = p.OUT/'user_resume_20261015_001/invoke_route_spool_measured.ps1'
assert p.old.sha(wrapper) == '0a5bd975e8e5287cd8f0113a6236b99b35fb609c6550d79ac182d7e5ba912327'
precheck = output/'pure_precheck_001.json'
if not precheck.exists():
    p.old.write(precheck, {'schema':'g31.original_route_spool.pure_precheck.v1', 'status':'passed_prepared_no_native',
        'output':str(output), 'campaign_sha256':p.old.sha(output/'campaign.json'),
        'plan_sha256':p.old.sha(output/'preregistered_protocol.json'), 'source_count':len(plan['source_before']),
        'compiled_source_count':len(plan['compiled_source_sha256']), 'native_binary_sha256':plan['native_binary_sha256'],
        'tests':{'path':str(xml),'sha256':p.old.sha(xml),'passed':50,'failures':0,'errors':0,'skipped':0},
        'invocation':sink.unchanged_invocation_proof(), 'old_pure_source_count':len(old_plan['source_before']),
        'old_pure_source_changed':[], 'external_wrapper':{'path':str(wrapper),'sha256':p.old.sha(wrapper)},
        'failed_preparation_preserved':{'path':str(p.OUT/'original_route_spool_prepare_001/preparation_failure.json'),
            'sha256':p.old.sha(p.OUT/'original_route_spool_prepare_001/preparation_failure.json')},
        'metadata_attempt_note':'An earlier ad-hoc precheck used nonexistent old preregistered_protocol.json; corrected to actual plan.json before writing this receipt. No native execution.',
        'wall_seconds':time.perf_counter()-began,'native_executions':0,'complete_100ms_certified':False})
if args.ready:
    review = output/'root_source_review_001.json'; assert review.is_file()
    assert p.old.sha(review) == '5405339137c216272b0f4bab095d0a35af3632ccc228680009757555189ec261'
    checked = p.old.read(precheck)
    assert checked['plan_sha256'] == p.old.sha(output/'preregistered_protocol.json')
    assert checked['campaign_sha256'] == p.old.sha(output/'campaign.json')
    assert all(p.old.sha(path) == digest for path,digest in plan['source_before'].items())
    assert not (output/'ready.json').exists()
    campaign = output/'campaign.json'; digest = p.old.sha(campaign)
    ready = {'schema':'g31.original_route_spool.ready.v1', 'status':'prepared_reviewed_native_unexecuted',
        'output':str(output),'campaign_sha256':digest,'preregistered_plan_path':str(campaign),'preregistered_plan_sha256':digest,
        'protocol_plan':{'path':str(output/'preregistered_protocol.json'),'sha256':p.old.sha(output/'preregistered_protocol.json')},
        'execute_command':[plan['interpreter']['path'],'-m','scripts.experiments.g31_ics_circulation.launch_original_route_update_spool',
            '--output',str(output),'--campaign-sha256',digest],
        'external_wrapper':{'path':str(wrapper),'sha256':p.old.sha(wrapper)},
        'external_receipt_path':str(output/'powershell_launch_receipt.json'),
        'evidence':{str(path):p.old.sha(path) for path in (review,precheck,xml,p.OUT/'spool_candidate_pure_001.xml')},
        'source_before':plan['source_before'],'source_count':len(plan['source_before']),
        'compiled_source_count':len(plan['compiled_source_sha256']),'native_binary_sha256':plan['native_binary_sha256'],
        'readiness_source':{str(Path(__file__).resolve()):p.old.sha(__file__)},
        'pure_tests':{'passed':50,'failures':0,'errors':0,'skipped':0},'scope':p.contract(),
        'shared_hard_seconds':600.,'native_executions':0,'original_sources_modified':False,
        'complete_computation_available':False,'complete_100ms_certified':False}
    p.old.write(output/'ready.json',ready)
    print('ready',p.old.sha(output/'ready.json'))
print('precheck',p.old.sha(precheck),'sources',len(plan['source_before']),'compiled',len(plan['compiled_source_sha256']))
