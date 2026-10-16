"""Pure final preflight; no NativeSession or experiment dispatch."""
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import research_original_low_wip_cap_relay as driver

ROOT = driver.reference.ROOT
OUT = driver.reference.OUT
directory = OUT / 'original_low_wip_cap_relay_prepare_001'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
ref = lambda p: {'path': str(Path(p).resolve()), 'sha256': sha(p)}
def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

began = time.perf_counter()
with driver.installed():
    campaign = driver.reference.verify_campaign(directory)
assert sha(directory / 'campaign.json') == 'cdd989387f84292ab4f3d07f5f22ec1d83429726114257f2a3a620d9d600c4ac'
assert campaign['case_plans'] == {'cap8': '59e2d0923b8fdd2647d382edaad5ab0aacd72b5307d38972878ac7a9c3cc6025'}
xml = OUT / 'cap_barrier_relay_pure_003.xml'
suites = [dict(s.attrib) for s in ET.parse(xml).getroot().iter('testsuite')]
assert sum(int(s['tests']) for s in suites) == 55
assert all(int(s[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
review = directory / 'independent_source_review_001.json'
assert sha(review) == '6cb672f4f01704f580fbb88c8f516ce250ded20a0155eca40cd2aa69d3d7d0e4'
reviewed = json.loads(review.read_text(encoding='utf-8'))
assert reviewed['concrete_remaining_blockers'] == []
assert reviewed['campaign_sha256'] == sha(directory / 'campaign.json')
wrapper = OUT / 'user_resume_20261015_001/invoke_low_wip_cap_relay_measured.ps1'
assert sha(wrapper) == '08957ec74e28972fa795b3eaca9305d1b61cbac039d133588917ba67e77d26e1'
assert json.loads((directory / 'branch_ledger.json').read_text()) == {'cap8': {'status': 'unknown_unexecuted'}}
assert not (directory / 'external_launch_claim.json').exists()
precheck = {
    'schema': 'g31.cap_relay.readiness_precheck.v1',
    'status': 'passed_pure_preflight_native_unexecuted',
    'script': ref(__file__), 'campaign': ref(directory / 'campaign.json'),
    'case_plan': ref(directory / 'cap8/preregistered_protocol.json'),
    'runtime_live_archive_count': len(campaign['source_before']),
    'compiled_archive_count': reviewed['compiled_archive_files_verified'],
    'tests': {**ref(xml), 'suites': suites}, 'independent_review': ref(review),
    'wrapper': ref(wrapper), 'preflight_wall_seconds': time.perf_counter() - began,
    'native_executions': 0,
}
write(directory / 'readiness_precheck_001.json', precheck)
ready = {
    'schema': 'g31.original_low_wip_cap_relay.v1.ready',
    'status': 'ready_native_unexecuted_review_closed',
    'output': str(directory), 'campaign_sha256': sha(directory / 'campaign.json'),
    'preregistered_plan_path': str(directory / 'campaign.json'),
    'preregistered_plan_sha256': sha(directory / 'campaign.json'),
    'execute_command': ['C:\\PROGRAMING\\python3.11.9\\python.exe', '-m',
        'scripts.experiments.g31_ics_circulation.launch_original_low_wip_cap_relay',
        '--output', str(directory), '--campaign-sha256', sha(directory / 'campaign.json')],
    'native_workers': 1, 'native_branches': 1, 'total_shared_seconds': 2400,
    'supply_caps': {'cap8': 8}, 'horizon_each': 86400, 'offered_each': 28506,
    'trays_each': 22, 'max_physical_requests': 30,
    'case_plans': campaign['case_plans'], 'source_sha256': campaign['source_before'],
    'runtime_archive_count_each': 82, 'compiled_archive_count_each': {'cap8': 67},
    'precheck': ref(directory / 'readiness_precheck_001.json'),
    'pure_tests': precheck['tests'], 'independent_source_review': ref(review),
    'external_wrapper': ref(wrapper), 'native_binary_sha256': reviewed['binary_sha256'],
    'new_same_policy_cap3_cap8_pair': False, 'complete_100ms_certified': False,
    'notes': [
        'Fresh cap8 only; old cap3 is historical reference and old cap8 timeout remains unknown.',
        'Actual complete horizon, all offered job states, full saved-policy/API replay, eight same-token lifecycles, both cap proofs and actual own delivered relay ACKs gate success.',
        'Owned 2400-second Windows Job includes worker and saved verifier; outer wrapper records startup and final export wall.',
        'Pure readiness only; root dispatches the exact command after checking these hashes.'
    ],
}
write(directory / 'ready.json', ready)
print(json.dumps({'ready': ref(directory / 'ready.json'), 'precheck': ref(directory / 'readiness_precheck_001.json'), 'native_executions': 0}))
