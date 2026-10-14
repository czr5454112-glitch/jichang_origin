"""Freeze identities and register actual local receipts without Git writes."""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).absolute().parents[3]
E = ROOT / 'outputs/experiments/g31_ics_long_term_20261013'
D = ROOT / 'docs/g31_ics_circulation'
INTEGRITY = E / 'session011_handoff_integrity_001.json'
assert not INTEGRITY.exists()

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def git(cwd, *args):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, check=True).stdout.decode('utf-8').strip()

build = read(E / 'p1_build_011/receipt.json')
validation = read(E / 'live_validation_009/receipt.json')
binary = ROOT / 'build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd'
assert build['status'] == validation['status'] == 'passed'
assert validation['counts'] == dict(tests=342, failures=0, errors=0, skipped=0)
assert sha(binary) == validation['binary_sha256'] and sha(binary) in build['binary_sha256'].values()
checks = {}
for label, receipt in [('build011', build), ('live009', validation),
        ('checkpoint007_compiled_sources', read(E/'p1_checkpoint_validation_007/receipt.json')),
        ('legacy004_compiled_sources', read(E/'legacy_parity_004/receipt.json'))]:
    expected = receipt['source_before']
    differences = [p for p,h in expected.items() if sha(ROOT/p) != h]
    assert not differences, (label, differences)
    assert not receipt.get('source_changed'), label
    checks[label] = dict(files=len(expected), mismatches=differences)
protected = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(protected) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
states = {}
for label,p in [('circulation',ROOT),('user_original',ROOT.parent)]:
    assert not git(p,'diff','--cached','--name-only')
    states[label] = dict(branch=git(p,'branch','--show-current'), head=git(p,'rev-parse','HEAD'), staged=[])
assert states['circulation']['head'] == '46cc46ab6bc121628fd6357e9f3c7636745fd732'
integrity = dict(schema='g31.session011_handoff_integrity.v1',status='passed',
    binary_sha256=sha(binary),source_identity_checks=checks,git_states=states,
    protected_file=str(protected),protected_file_sha256=sha(protected),committed=False,pushed=False,
    scope='Current source and compiled identity checks, not an extra test execution; no publication.')
INTEGRITY.write_text(json.dumps(integrity,indent=2)+'\n',encoding='utf-8')

folders = ['p1_build_010','p1_build_011','protocol_command_tests_010_001','owner_command_tests_001',
    'live_validation_007','live_validation_008','live_validation_009','p1_checkpoint_validation_007','legacy_parity_004',
    'protocol_control_native_010_001','protocol_control_native_011_001',
    'protocol_controller_before_010_001','protocol_controller_after_010_001','protocol_controller_after_011_001',
    'protocol_route_aba_before_001','protocol_route_aba_after_011_001',
    'protocol_demand_capture_before_001','protocol_demand_capture_after_011_001',
    'protocol_tick_boundary_before_001','protocol_tick_boundary_after011_001',
    'p7_native009_microprofile_001','p7_native009_microprofile_002',
    'p2_original_2x_reactive_compact_H86400_010_001','p5_dependency_repair_006_001',
    'p5_dependency_repair_006_development_001','p5_dependency_repair_006_development_002',
    'demand_ack_signature_tests_001','demand_ack_signature_tests_002','demand_ack_signature_tests_003','demand_ack_signature_tests_004',
    'original_protocol_24_prepare_001','original_protocol_24_011_001','original_protocol_24_budget_011_001']
selected = [E/name/'receipt.json' for name in folders]
selected += [E/name for name in ['p2_original_2x_signature_comparison_010_001.json',
    'p5_receiving_cut_certificate_001.json','p5_receiving_cut_certificate_002.json',
    'original_protocol_24_review_011_001/assessment.json',INTEGRITY.name]]
selected += list(E.glob('p5_dependency_tests_*.xml')) + list(E.glob('original_protocol_prepare_tests_*.xml'))
index = D/'RESULT_INDEX.jsonl'
existing = [json.loads(line) for line in index.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
known = {r['id']:r for r in existing}
new = []
for p in sorted(set(selected)):
    assert p.is_file(), p
    identity = 'LT-RAW-' + p.relative_to(E).as_posix()
    if identity in known:
        assert known[identity]['artifact_sha256'] == sha(p), identity
        continue
    if p.suffix == '.xml':
        cases = ET.parse(p).findall('.//testcase')
        counts = dict(tests=len(cases),failures=sum(c.find('failure') is not None for c in cases),
            errors=sum(c.find('error') is not None for c in cases),skipped=sum(c.find('skipped') is not None for c in cases))
        obj = dict(status='failed' if counts['errors'] or counts['failures'] else 'passed',counts=counts)
    else:
        obj = read(p)
    record = dict(id=identity,artifacts=p.relative_to(ROOT).as_posix(),artifact_sha256=sha(p),
        recorded_status=obj.get('status','recorded; inspect actual case outcomes'),source_changed=obj.get('source_changed'),
        binary_sha256=obj.get('binary_sha256'),independent_source=False,
        scope='Version-bound actual local evidence, including failures, preparation and truncated runs. Passing is not method novelty, global optimality or full 100ms certification; overlapping tests are not additive.')
    if 'counts' in obj: record['counts'] = obj['counts']
    new.append(record)
with index.open('a',encoding='utf-8',newline='\n') as stream:
    for r in new: stream.write(json.dumps(r,ensure_ascii=False)+'\n')

s = read(D/'RESEARCH_STATE.json')
s.update(current_stage='P1/P3 real unified owner protocol verified in declared scope; P2 original selected circulation; P4/P5 strong negative evidence; P6 held; P7 not met',
    active_experiment=None, execution_status='All experiments finished; frozen native011 and342 related regressions. No stage/commit/push.',
    current_binary=dict(path=binary.relative_to(ROOT).as_posix(),sha256=sha(binary),build_receipt=(E/'p1_build_011/receipt.json').relative_to(ROOT).as_posix()),
    final_regression=dict(artifact=(E/'live_validation_009/receipt.json').relative_to(ROOT).as_posix(),counts=validation['counts'],source_changed=[]),
    last_verified_checkpoint='C++ checkpoint007:611 event boundaries x2, default runtime and mature clone checks; compiled source unchanged in011. Python342 includes protocol/controller fork+JSON continuation and immutable capture cache restore. Partial controller tick resume explicitly rejected; no persistent physical checkpoint migration.',
    source_freeze_note='Source against build011/live009/checkpoint007/legacy004 verified at session011_handoff_integrity_001. Full-day performance is010-bound; P5 final16+earlier domains006-bound. No transplant of old receipts to a new experiment.',
    committed=False,pushed=False,requires_user_decision=False)
s['blocked_claims'] = [x for x in s['blocked_claims'] if not x.startswith(('Native009','Owner protocol is transfer-only'))]
s['blocked_claims'] += [
    'Latest full-day0102x owner+publication still2/194 over100ms,max101.0037ms,P99=100.7863ms. Complete request/two-machine/deployment gates unpassed.',
    'Original24 owner-protocol comparison preserves24 completions/23returns/19late. R1 permission0 so joint adds no route. All16service forecasts rejected; ordinary predictive release requests explain~1.031percent benefit.',
    'Current protocol controller only resumes completed public control boundaries, not an interrupted intra-tick cursor; native process persistence not implemented.',
    'P5 two-real-boundary16branches do not improve aggregate cost or guarantee all-offered protection. Restricted cut necessity bound rules out a specific target intersection, not general optimization.',
    'One-shot service estimates may expire during long same-stage blocking without automatic refresh; source-delay command rejection and missing forecast information need event-triggered diagnosis.'
]
s['stage_gates'].update(
    P1='Unified native transfer+route+demand+forecast+withdraw+cancel, delivered ACKs and native+JSON controller continuation tested; partial controller ticks/persistent migration remain unsupported.',
    P2='Partial: original151nodes227edges24selected jobs/one real tray,23 actual received returns on011; all24 complete but19late. Full mother flow conservative proxy still blocks.',
    P3='Partial: R1/R2 actual faulted protocol on synthetic factors; original selected input has no R1 permission and16delayed service forecasts rejected. Predictive conditional-release R2 active with unchanged owner guards. On-demand automatic event activation/long-blocked forecast refresh next.',
    P4='Same-information finite native references plus original selected witness/necessary lower bounds; global optimum unknown. Specific two-baseline intersection infeasible in fixed3tray long-cut factor.',
    P5='research_candidate: new16real two-boundary interventions exchange D0/D1 delay with equal cost; ordinary strong feedback remains competitive; no robust new-method increment.',
    P6='Held at candidate/information/same-G31 continuation/main-method gates; no large label/training campaign.',
    P7='NOT MET: latest measured010 whole-day2x subchain exceeds100ms2/194; full original0/57012 business completion.011 correctness and selected24 protocol runs do not certify full timing, field model or two-machine deployment.')
s['next_actions'] = [
    'Continue native011/statev2 in the existing circulation worktree. Read final010-011 progress and novelty22-24; do not reimport or repeat old V3/one-tray milestones.',
    'P3:implement legal local-event-triggered R1/forecast activation and common strong analytic comparison. Diagnose16source-delay forecast rejections and stale one-shot forecasts during long blocking without changing original permissions or sampling contract.',
    'P5:retain fixed-cut negative cases; check physical target compatibility, then evaluate time-aware receiving/joint handoff choices only in a common model with actual feasible slack. Compare strong rolling analytic feedback, generic closure/retiming and same-G31 reference with all normal-service protection.',
    'P7:profile exact public observation/codec on the preserved late-day hotspot; separately measure whole active original requests including native delivery revalidation/confirmation. Preserve2/194overruns and ordinary failures; add explicit serialization isolation before deployment claims.',
    'P2:retain full original zero-as-closed/FIFO/on-carrier negative contract pending real physical evidence; preserve original directed topology, finite tray counts, all tasks, deadlines and fixed local authority.',
    'P6:no bulk old-label training; only justified small same-continuation diagnostics after candidate/information/novel-method evidence. P1-P7/TRE-CIE requirements stay unchanged.',
    'Fresh outputs/binaries for new native source. No stage/commit/push, fees or equipment. Disk below20percent: bounded gzip evidence only, no deletion of history.'
]
s['resume_commands']['full_day_hotspot'] = 'python -m scripts.experiments.g31_ics_circulation.run_original_control --binary build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd --scale 2 --horizon 86400 --control-period 900 --max-events 160000 --wall-budget 240 --compact-projection --output outputs/experiments/g31_ics_long_term_20261013/original_2x_recheck_new'
s['resume_commands']['unified_protocol'] = 'python -m scripts.experiments.g31_ics_circulation.validate_protocol_control --binary build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd --output outputs/experiments/g31_ics_long_term_20261013/protocol_recheck_new'
s['resume_commands']['original_protocol'] = 'python -m scripts.experiments.g31_ics_circulation.run_original_protocol --binary build_lt_session_011/python/czr005_circulation.cp311-win_amd64.pyd --expected-binary-sha256 '+sha(binary)+' --output outputs/experiments/g31_ics_long_term_20261013/original_protocol_recheck_new'
s['resume_commands']['transfer_protocol'] = s['resume_commands']['transfer_protocol'].replace('session_009','session_011')
s['new_result_registration'] = dict(script=str(Path(__file__).relative_to(ROOT)),added_raw_entries=len(new),total_index_entries=len(existing)+len(new))
for p in selected:
    if p.suffix=='.json' and read(p).get('status') in ('passed','reached','equivalent','executed_comparison_not_research_gate'):
        rel=p.relative_to(E).as_posix()
        if rel not in s['verified_artifacts']: s['verified_artifacts'].append(rel)
(D/'RESEARCH_STATE.json').write_text(json.dumps(s,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(dict(status='registered',new_receipts=len(new),total_index=len(existing)+len(new),source_checks=checks,git_states=states)))
