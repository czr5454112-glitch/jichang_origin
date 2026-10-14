"""Register immutable receipts and current continuation state; no Git writes."""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).absolute().parents[3]
E = ROOT / 'outputs/experiments/g31_ics_long_term_20261013'
D = ROOT / 'docs/g31_ics_circulation'
INTEGRITY = E / 'session009_handoff_integrity_001.json'
assert not INTEGRITY.exists(), 'This evidence registration may run only once.'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def git(cwd, *args):
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, check=True)
    return r.stdout.decode('utf-8').strip()

build = read(E / 'p1_build_009/receipt.json')
validation = read(E / 'live_validation_006/receipt.json')
binary = ROOT / 'build_lt_session_009/python/czr005_circulation.cp311-win_amd64.pyd'
assert build['status'] == validation['status'] == 'passed'
assert sha(binary) == build['binary_sha256'][str(binary)] == validation['binary_sha256']
source_checks = {}
for label, receipt in [('build009', build), ('live006', validation)]:
    expected = receipt['source_before']
    mismatches = [name for name, digest in expected.items() if sha(ROOT / name) != digest]
    assert not mismatches, (label, mismatches)
    source_checks[label] = {'files': len(expected), 'mismatches': mismatches}
protected = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(protected) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
git_states = {}
for label, p in [('circulation', ROOT), ('user_original', ROOT.parent)]:
    staged = git(p, 'diff', '--cached', '--name-only')
    assert not staged, (label, staged)
    git_states[label] = {'branch': git(p, 'branch', '--show-current'),
                         'head': git(p, 'rev-parse', 'HEAD'), 'staged': []}
assert git_states['circulation']['head'] == '46cc46ab6bc121628fd6357e9f3c7636745fd732'
integrity = {'schema': 'g31.session009_handoff_integrity.v1', 'status': 'passed',
             'binary_sha256': sha(binary), 'source_identity_checks': source_checks,
             'git_states': git_states, 'protected_file': str(protected),
             'protected_file_sha256': sha(protected), 'committed': False, 'pushed': False,
             'scope': 'current source against actual build/regression receipt; no new tests or publication'}
INTEGRITY.write_text(json.dumps(integrity, indent=2) + '\n', encoding='utf-8')

index_path = D / 'RESULT_INDEX.jsonl'
existing = [json.loads(line) for line in index_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
ids = {x['id'] for x in existing}
selected = [E / n / 'receipt.json' for n in [
    'p1_build_008', 'p1_build_009', 'owner_protocol_tests_001',
    'owner_protocol_native_001', 'owner_protocol_native_002',
    'live_validation_006', 'p1_checkpoint_validation_006', 'legacy_parity_003',
    'p2_original_2x_reactive_compact_H86400_009_001']]
selected += list(E.glob('p5_*/receipt.json'))
selected += list(E.glob('p5_joint_window_tests_*.xml'))
selected += list(E.glob('p5_joint_window_protection_assessment_*.json'))
selected += [E / n for n in ['p5_absorbing_terminal_diagnostic_001.json',
    'owner_protocol_assertion_probe_001.json',
    'p2_original_2x_owner_index_comparison_009_001.json', INTEGRITY.name]]
new = []
for p in sorted(set(selected)):
    assert p.is_file(), p
    rel = p.relative_to(E).as_posix()
    identity = 'LT-RAW-' + rel
    if identity in ids:
        continue
    if p.suffix == '.xml':
        suites = ET.parse(p).getroot().iter('testsuite')
        counts = {k: 0 for k in ['tests', 'failures', 'errors', 'skipped']}
        for suite in suites:
            for k in counts:
                counts[k] += int(suite.attrib.get(k, 0))
        obj = {'status': 'failed' if counts['failures'] or counts['errors'] else 'passed', 'counts': counts}
    else:
        obj = read(p)
    status = obj.get('status', 'recorded; inspect artifact for per-case outcomes')
    record = {'id': identity, 'artifacts': p.relative_to(ROOT).as_posix(),
              'artifact_sha256': sha(p), 'recorded_status': status,
              'source_changed': obj.get('source_changed'),
              'binary_sha256': obj.get('binary_sha256'),
              'independent_source': False,
              'scope': 'Version-bound raw development/validation evidence; inspect individual contract and failures. No global optimality, novel-method or complete 100ms certification.'}
    if 'counts' in obj:
        record['counts'] = obj['counts']
    new.append(record); ids.add(identity)
with index_path.open('a', encoding='utf-8', newline='\n') as f:
    for obj in new:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')

comparison = read(E / 'p2_original_2x_owner_index_comparison_009_001.json')
timing = comparison['timing']['candidate']['owner_plus_publication_compute_ms']
assert comparison['status'] == 'equivalent' and timing['over_100ms'] == 8
state = read(D / 'RESEARCH_STATE.json')
state['current_stage'] = 'P1 transfer protocol engineering verified; P2/P3 partial; P4/P5 strong-reference diagnosis; P6 held; P7 measured failure'
state['working_tree_identity'] = 'codex/g31-ics-v3-circulation; uncommitted, unstaged local source; mature HEAD46cc46 unchanged'
state['active_experiment'] = None
state['execution_status'] = 'No experiment left running at handoff. User cancelled push before any commit/push.'
state['current_binary'] = {'path': binary.relative_to(ROOT).as_posix(), 'sha256': sha(binary),
                           'build_receipt': (E / 'p1_build_009/receipt.json').relative_to(ROOT).as_posix()}
state['final_regression'] = {'artifact': (E / 'live_validation_006/receipt.json').relative_to(ROOT).as_posix(),
                             'counts': validation['counts'], 'source_changed': validation['source_changed']}
state['last_verified_checkpoint'] = 'p1_checkpoint_validation_006: 611 safe boundaries x2 continuation plus default runtime/legacy clone targets; owner_protocol_tests_001 and native002 separately cover transfer faults/fork/restore. Process-bound objects, no persistent checkpoint migration.'
state['source_freeze_note'] = 'Current native009 build and live006 regression source hashes checked at session009_handoff_integrity_001. P5 final124+6+62 runs remain native006-bound with unchanged P5 sources. delivery_001 is historical; no results transplanted across versions.'
state['blocked_claims'] = [x for x in state['blocked_claims'] if not x.startswith('Native007')]
state['blocked_claims'] += [
    'Native009 compact2x full-day owner+same-owner publication:8/194 over100ms,max110.7216ms,P99=110.1694ms; complete delivery/revalidation/ACK cost still not isolated. P7 not met.',
    'Owner protocol is transfer-only. Enabled mode rejects legacy online route/demand/forecast/observe; existing R1/R2 controllers not yet integrated.',
    'P5 final124 static branches: strong baseline explains gains and hidden-source joint protection fails. One observed feedback recovers to baseline only.',
    'New shared-return synthetic factor62 branches completes all selected-policy jobs but whole-offered paired protection still fails; finite protected headroom0, global optimum unknown.',
]
state['stage_gates']['P1'] = 'Core live session/projection/checkpoint validated; opt-in native transfer ACK/loss/duplicates/timeout/owner unavailable verified21 tests+10 ledgers. R1/R2 message families and controller continuation not yet integrated into this mode; no real host crash/deployment claim.'
state['stage_gates']['P5'] = 'research_candidate:124 static branches,6 real-feedback continuations and62 shared-return continuous-control branches executed on006; protection failures and zero finite-domain headroom preserved. No reliable increment beyond ordinary strong feedback.'
state['stage_gates']['P7'] = 'NOT MET:009 full-day2x compact194 owner+publication calls,8 exceed100ms,max110.7216ms; full request includes additional unisolated work. All57012 jobs and57544events preserved; business0complete under fixed original proxy.'
state['next_actions'] = [
    'Read this state, latest progress009 section, NOVELTY_LEDGER20-21 and protocol source. Do not reimport/revert or repeat V3 fixes/one-tray cycle as the main task.',
    'Integrate lawful route/demand/service-forecast publication and delivered ACKs into owner_protocol, including cancellation/tombstones, owner recovery, stable identities, and controller checkpoint. Existing analytics must consume only delivered projections. Keep legacy/default mode and strong comparators on equal permissions.',
    'Measure actual active-request observation/forecast/assignment/submit/delivery revalidation/confirmation with attribution in native event dispatch; retain shared physical event cost separately. Diagnose compact observation and demand signature allocations; optimize semantics-preserving code without hiding8/194 overruns.',
    'P5:use actual multi-boundary supply/resource dependency changes; compare retained-assignment feedback, continuous strong analytic baseline and same-budget native reference. Keep old absorbing-terminal factor and new shared-return contract distinct; all offered protection/initial asynchronous failures remain in denominator.',
    'P2:retain full original zero-as-closed/FIFO/on-carrier negative contract pending field/data evidence. No zero-capacity edits, extra trays, task deletion or waiting permission changes to create success.',
    'P6:allow only justified small diagnostics after candidate/information/native-continuation gates; no bulk old-label training. P5 novel mechanism and full P7 remain unpassed.',
    'Fresh output directories and clean numbered binary for any native edits; update raw result index/state/novelty evidence. No stage/commit/push, no fees/devices, protect user original modification.'
]
state['resume_commands']['full_day_hotspot'] = 'python -m scripts.experiments.g31_ics_circulation.run_original_control --binary build_lt_session_009/python/czr005_circulation.cp311-win_amd64.pyd --scale 2 --horizon 86400 --control-period 900 --max-events 160000 --wall-budget 240 --compact-projection --output outputs/experiments/g31_ics_long_term_20261013/original_2x_recheck_new'
state['resume_commands']['transfer_protocol'] = 'python -m scripts.experiments.g31_ics_circulation.validate_owner_protocol --binary build_lt_session_009/python/czr005_circulation.cp311-win_amd64.pyd --output outputs/experiments/g31_ics_long_term_20261013/owner_protocol_recheck_new'
state['resume_commands']['p5_continuous_factor'] = 'python -m scripts.experiments.g31_ics_circulation.validate_joint_circulation_factor --binary build_lt_session_006/python/czr005_circulation.cp311-win_amd64.pyd --output outputs/experiments/g31_ics_long_term_20261013/p5_factor_recheck_new'
state['resume_commands']['rule'] = 'These are runnable reproduction commands, not a request to repeat unchanged passed experiments. Next implementation entry points are in next_actions.'
state['verified_artifacts'] += [str(p.relative_to(E)).replace('\\','/') for p in selected if 'development' not in str(p) and 'before' not in str(p) and p.name == 'receipt.json' and read(p).get('status') in ['passed','reached','executed'] and str(p.relative_to(E)).replace('\\','/') not in state['verified_artifacts']]
state['new_result_registration'] = {'script': str(Path(__file__).relative_to(ROOT)), 'added_raw_entries': len(new), 'total_index_entries': len(existing) + len(new)}
state['committed'] = state['pushed'] = False
(D / 'RESEARCH_STATE.json').write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({'status':'registered','new_raw_entries':len(new),'source_checks':source_checks,
                  'owner_plus_publication_compute_ms':timing,'git_states':git_states}))
