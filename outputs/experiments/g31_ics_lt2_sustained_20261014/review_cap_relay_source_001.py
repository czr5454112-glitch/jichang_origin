"""Independent source/archive review; never opens a native session."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
TARGET = OUT/'original_low_wip_cap_relay_prepare_001'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
campaign = read(TARGET/'campaign.json')
assert sha(TARGET/'campaign.json') == 'cdd989387f84292ab4f3d07f5f22ec1d83429726114257f2a3a620d9d600c4ac'
assert set(campaign['case_plans']) == {'cap8'}
case = TARGET/'cap8'; plan = read(case/'preregistered_protocol.json')
assert sha(case/'preregistered_protocol.json') == campaign['case_plans']['cap8'] == '59e2d0923b8fdd2647d382edaad5ab0aacd72b5307d38972878ac7a9c3cc6025'
assert plan['source_before'] == campaign['source_before']
for name, digest in plan['source_before'].items():
    path = Path(name)
    assert sha(path) == digest == sha(case/'source_archive'/path.relative_to(ROOT)), name
for name, digest in plan['compiled_source_sha256'].items():
    assert sha(case/'compiled_source_archive'/name) == digest, name
for name, digest in plan['authority_pins'].items(): assert sha(name) == digest, name
assert sha(plan['binary']) == plan['binary_sha256']
for name,digest in plan['bootstrap_pins'].items(): assert sha(Path(plan['bootstrap_reference'])/name)==digest
prior = campaign['contract']['prior_attempt_reference']
for name,digest in prior['artifacts'].items(): assert sha(Path(prior['directory'])/name)==digest
xml = OUT/'cap_barrier_relay_pure_003.xml'
suites = ET.parse(xml).getroot().findall('testsuite')
counts={k:sum(int(s.attrib[k]) for s in suites) for k in ('tests','failures','errors','skipped')}
assert counts == {'tests':55,'failures':0,'errors':0,'skipped':0}
report = {'status':'passed_independent_source_bound_review_no_native',
 'campaign_sha256':sha(TARGET/'campaign.json'),'plan_sha256':sha(case/'preregistered_protocol.json'),
 'runtime_sources_live_and_archive_verified':len(plan['source_before']),
 'compiled_archive_files_verified':len(plan['compiled_source_sha256']),
 'binary_sha256':plan['binary_sha256'],'tests':{'xml':str(xml),'sha256':sha(xml),**counts,'independently_rerun':False},
 'reviewer_source_sha256':sha(__file__),
 'scope':['Core executes frozen quiescent owner first; exactly one typed source-local publication follows first fresh cap transition; no copied peer wire payload.',
 'Fresh current view/latest peer barrier is recorded during the same full saved-policy replay; relay submission is next actual API and required own ACK is bound to actual returned query and typed digest.',
 'All 28506 job and 22 tray identities remain; eight supply LOAD/UNLOAD/HOLD lifecycles, actual H86400, final empty, all physical received ACKs and physical audit independently gate success.',
 'One cap8 worker plus verifier under the single owned 2400-second Job; errors/open proof remain unknown. Old cap3 is historical reference, not new same-policy pair.',
 'Full corrected policy replay occurs once; this review did not repeat old large raw scans or run native/test execution.'],
 'limits':['No actual candidate execution yet; no speed, protection or complete-request100ms claim.',
 'Launcher clock begins at BOOT after interpreter startup; external PowerShell Stopwatch must retain startup and final export. Parent final evidence hashing/export is outside the child Job deadline and remains in outer wall.',
 'No additional physical request is a source-code property, not yet a physical trace equality result.'],
 'concrete_remaining_blockers':[], 'native_executions':0}
target = TARGET/'independent_source_review_001.json'
with target.open('x',encoding='utf8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'status':report['status']}))
