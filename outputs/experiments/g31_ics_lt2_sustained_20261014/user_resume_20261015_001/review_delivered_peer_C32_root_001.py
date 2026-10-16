from pathlib import Path
import json, sys, xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import measure_delivered_peer_c_encoder as m
DEST=m.OUT/'dpc_prepare_001'; PURE=m.OUT/'dpc_pure_001'
expected='cb22099c23037b14a53dd98e1ffaa7e71003c1e55913e54e0754a2d71911b1a9'
assert m.sha(DEST/'plan.json')==expected
assert m.sha(PURE/'receipt.json')=='ddb078e7b08dcae837921b6f579b7fe9656a3cdd5c0639a7daebbf60f242be6e'
assert m.sha(PURE/'tests.xml')=='d726b849cff82faf021f069ab1f63e7d312fbd3a9edb44e2a6a09cff009609da'
assert m.sha(DEST/'external_application_wall.json')=='c4a8e5576c6800f0f80ab471554be2ad7446e471448fd4a92cfb4fbe696be896'
plan=m.loads((DEST/'plan.json').read_bytes()); m.verify(DEST,plan)
assert len(plan['sources'])==95 and plan['calls']==32 and plan['arms']==['A','B','B','A'] and plan['shared_seconds']==120
assert plan['C_authority']['toolchain_members']==7779 and plan['C_authority']['runtime_members']==3082
assert plan['C_authority']['synthetic_tests']==159 and plan['C_authority']['direct_C_probes']==126 and plan['C_authority']['fallback_probes']==10
receipt=m.loads((PURE/'receipt.json').read_bytes()); cases=ET.parse(PURE/'tests.xml').findall('.//testcase')
assert receipt['status']=='passed' and receipt['tests']==83 and receipt['source_changed']==[]
assert len(cases)==83 and not any(n.tag in ('failure','error','skipped') for row in cases for n in row)
for name,digest in plan['sources'].items():assert m.sha(m.ROOT/name)==m.sha(DEST/'source'/name)==m.sha(PURE/'source'/name)==digest
assert set(plan['sources'])==set(m.sources())==set(receipt['source_sha256'])
outer=m.loads((DEST/'external_application_wall.json').read_bytes()); bounded=m.loads((DEST/'prepare_bounded.json').read_bytes())
assert outer['exit_code']==0 and outer['outer_timeout'] is False and outer['exception'] is None and outer['source_changed']==[]
assert type(outer['elapsed_ticks']) is int and type(outer['tick_frequency']) is int and 0<=outer['elapsed_ticks']<=120*outer['tick_frequency']
assert outer['whole_python_seconds']==outer['elapsed_ticks']/outer['tick_frequency']
assert outer['command']==[sys.executable,'-m',m.MODULE,'--prepare','--output',str(DEST),'--pure-dir',str(PURE)]
for item in (outer['runner'],outer['wrapper'],outer['pure_receipt'],outer['pure_external']): assert m.sha(item['path'])==item['sha256']
for name,digest in outer['output_sha256'].items():assert m.sha(DEST/name)==digest
assert bounded['status']=='completed' and bounded['process']['status']=='exited' and bounded['process']['exitcode']==0
assert bounded['process']['windows_job_kill_on_close'] is True and bounded['process']['child_released_only_after_job_assignment'] is True
ready=m.loads((DEST/'ready.json').read_bytes());assert ready['plan_sha256']==expected
assert not any((DEST/n).exists() for n in ('execution_claim.json','result.json','C_entry.json'))
record={'schema':'g31.delivered_peer_C32.root_prelaunch.v1','status':'one_fixed32_ABBA_authorized_after_exclusive_window_release',
 'review_script_sha256':m.sha(__file__),'plan_sha256':expected,'sources':95,'pure_tests':83,
 'pure_seconds':m.loads((PURE/'external_application_wall.json').read_bytes())['whole_python_seconds'],
 'metadata_seconds':outer['whole_python_seconds'],'command':ready['execute_command'],
 'requirements':['One original fixed2 query ABBA32/120, GC default, no model/native/full policy. Exactly8 batches32 calls; failed or timed-out calls remain unknown, no rerun.','A original; B same validator with only digest replaced. B actual C verification/dispatch in validator clock. Original expiry/guards/error args/identity retained; only unsupported sentinel falls back once.','Original complete typed bytes vs actual C on every fixture envelope before all32 calls, full bytes saved, caller query/contract unchanged, exact dispositions/errorargs/outcome parity and saved32 audit.','7779 toolchain+3082 runtime full entry/exit, actual module/spec/loader/builtin and DLL identity, fixture checks, import/load/oracle/export/readback/cleanup remain in120. No subtraction/amortization.','External typedticks<=120, full Python launch-exit, exact command/plan/rootreview/runner/wrapper/interpreter/outputs beforeafter pins; use actual_external_application_wall.json distinct from metadata receipt.','Historically both queries absent. Results cannot establish successful guard path frequency, full-day scaling or100ms.'],
 'review_scope':'Root read authority/probe/harness/tests, verified source union and explicit old bare helpers. Metadata only;0 actual fixture decode/C/model/native orfull toolchain rehash inthis review.'}
with (DEST/'root_review_001.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
print(json.dumps({'status':record['status'],'root_review_sha256':m.sha(DEST/'root_review_001.json'),'sources':95}))
