"""Independent source/metadata review; no model, native, tests or raw replay."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
P=OUT/'live_obligation_native_domain_prepare_001'
OLD=OUT/'live_obligation_native_probe_prepare_004'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def ref(p):return {'path':str(p),'sha256':sha(p)}
planpath=P/'preregistered_protocol.json'
assert sha(planpath)=='dc9cc27b6a04eae5eb8ce5d97b9ef844e00657b2cec34004bafb41f952586c04'
plan=read(planpath);old=read(OLD/'preregistered_protocol.json')
assert len(plan['source_sha256'])==75 and len(old['source_sha256'])==73
for path,digest in plan['source_sha256'].items():
    assert sha(path)==sha(P/plan['source_archive'][path])==digest
for path,digest in old['source_sha256'].items():
    assert sha(path)==sha(OLD/old['source_archive'][path])==digest
assert plan['native_branch_budget']==96 and plan['hard_timeout_seconds']==600.
assert plan['strict_protection_tolerance']==0. and plan['native_forks']==0 and plan['max_native_workers']==1
assert plan['case_order']==['mechanism','no_overlap','insufficient_advance']
expected=[case+f'/vector_{i:02d}' for case in plan['case_order'] for i in range(32)]
assert plan['branch_order']==expected and list(plan['rows'])==expected
assert plan['first_return_action_semantics']['first_return_not_before']==7.84
frozen=OUT/'live_obligation_projection_prepare_003'
for case in plan['case_order']:
    source=read(frozen/(case+'.input.json'))
    group=[row for row in plan['rows'].values() if row['case']==case]
    assert len(group)==32 and sum(row['vector']['initial_action']=='native_default' for row in group)==16
    assert sum(row['vector']['later_action']=='native_default' for row in group)==16
    for i in range(32):
        key=case+f'/vector_{i:02d}';path=P/'inputs'/(key+'.json')
        assert sha(path)==plan['input_file_sha256'][key]
        value=read(path);assert value.pop('owner_notifications')=={'enabled':True}
        assert json.dumps(value,sort_keys=True,separators=(',',':'))==json.dumps(source,sort_keys=True,separators=(',',':'))
        assert plan['rows'][key]['method']=='fixed_feasibility' and plan['rows'][key]['fault'] is None
for reference in [plan['binary'],plan['native_contract_reference'],plan['semantic_gate_reference'],plan['interpreter'],*plan['auxiliary_references'].values()]:
    assert sha(reference['path'])==reference['sha256']
xml=Path(plan['auxiliary_references']['pure_tests']['path'])
cases=ET.parse(xml).getroot().findall('.//testcase')
assert len(cases)==38 and not any(n.tag in ('failure','error','skipped') for row in cases for n in row)
paths=[ROOT/'scripts/experiments/g31_ics_circulation'/name for name in (
    'live_obligation_domain_guard.py','live_obligation_domain_adapter.py',
    'live_obligation_native_domain_contract.py','research_live_obligation_native_domain.py')]
report={'schema':'g31.live_native96.independent_source_review.v1','status':'no_concrete_source_blocker_found',
    'plan':ref(planpath),'reviewed_sources':{str(path):sha(path) for path in paths},
    'current_and_archive_source_count':75,'prior004_current_and_archive_unchanged':73,'pure_XML':ref(xml),
    'inspected_pure_counts':{'tests':38,'failures':0,'errors':0,'skipped':0},
    'checks':{
      'actual_contract_recognition':'Case is identified from complete public graph/resource/event contract plus all retained job CONTRACT_FIELDS. Same-graph no_overlap is distinguished by actual job release contract, not row.case. Native collector still binds exact session/owner, delivered digest/selfACK/peer message, current own view and retained contracts.',
      'conditional_scope':'Equal capture times are not claimed atomic. Initial committed-load projection and later receipt-derived stable intervals retain conditional/current_state_certified=false; future/pending actions and malformed or unsupported population remain unknown.',
      'absolute_return':'The .5 alternative is max(actual decision time, frozen7.84); second return allows only immediate. Submission and saved assessor both call the same return_earliest contract. It is not now+.5.',
      'unchanged_input':'All96 prewritten inputs reduce byte-semantically to their corresponding frozen pure003 three inputs by removing exactly owner_notifications.enabled=true. No physical parameters or action ordering retuned.',
      'denominators':'All96 fixed slots remain. Each16-member reference requires complete assessed family plus assessed incumbent; full32 optimum requires all32 assessed. Missing input, fallback, rejected/unexecuted preference or exception keeps the row unknown even if physical completion occurred.',
      'strict_protection':'Exact per-job candidate completion<=reference completion, no tolerance; objective sum in sorted business-ID order. Frozen32-budget model selections are mapped after execution, not used as native-oracle policy inputs.',
      'failure_and_budget':'One owned600s child covers child imports, prechecks,44+21 entry/exit validation, all96 attempts and saved checks. Parent import/outer startup/export remain separate external application wall as explicitly declared;600 is not a complete platform-startup bound. Exceptions preserve partial current state without result_at/advance.',
      'old_sources':'All73 current and archived004 sources still match their old pins. New files contain the domain extension; old003/004 raw evidence is not relabeled.'},
    'limits':['Source and saved metadata review only. No new test, predictor, native session or saved raw004 replay by this reviewer.',
              'The38 XML success is inspected, not independently rerun.',
              'Actual96 native execution, full saved outcome/closure verification and external wall remain required.',
              'No online optimizer, atomic joint protocol, all-offered protection or100ms result is certified.'],
    'new_native_calls':0,'new_predictor_calls':0,'reviewer_tests_run':0,'reviewer_source_sha256':sha(__file__)}
target=P/'independent_source_review_control_001.json'
with target.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
print(json.dumps({'path':str(target),'sha256':sha(target),'status':report['status']}))
