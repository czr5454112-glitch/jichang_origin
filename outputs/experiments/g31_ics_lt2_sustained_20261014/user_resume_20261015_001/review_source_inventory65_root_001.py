from pathlib import Path
import json, sys, xml.etree.ElementTree as ET
from scripts.experiments.g31_ics_circulation import diagnose_future_source_inventory as d
DEST=d.ROOT/'outputs/si65d1'; PURE=d.ROOT/'outputs/si65p1'
expected='cc6432f563f1b447ebac5c8058f93cc6e721f6711ba33e2c1dbe6baa60bec0c6'
assert d.sha(DEST/'plan.json')==expected
assert d.sha(PURE/'receipt.json')=='9f4616c5cb6fc3bcb83bb109302b9c4e60d0f2ceb61c8040e3d464784918e533'
assert d.sha(PURE/'external_application_wall.json')=='d27487aa6154c5423ef3c7bc4f054a4468575bc38e88e16d6cf2db7399720854'
assert d.sha(DEST.with_name('si65d1.prepare_external.json'))=='6a849ed956f94db1ba1b838c168dca0fab4b298be1488defcd48e4350adef695'
plan=d.read(DEST/'plan.json');d.check_plan(DEST,plan);d.verify_archive(d.ROOT,DEST,plan)
assert len(plan['source_sha256'])==196 and len(plan['evidence_sha256'])==12
assert plan['planned_calls']==65 and plan['call_order']==list(range(65)) and plan['whole_shared_seconds']==120.
for path,digest in plan['evidence_sha256'].items():assert d.sha(path)==digest
refs=d.pure_gate();assert refs==plan['focused_pure']
cases=ET.parse(PURE/'tests.xml').findall('.//testcase')
assert len(cases)==71 and not any(n.tag in ('failure','error','skipped') for row in cases for n in row)
parent=d.read(DEST.with_name('si65d1.prepare_bounded.json')); outer=d.read(DEST.with_name('si65d1.prepare_external.json'))
assert parent['status']=='prepared_bounded_unexecuted' and parent['process']['status']=='exited' and parent['process']['exitcode']==0
assert parent['process']['windows_job_kill_on_close'] is True and parent['process']['child_released_only_after_job_assignment'] is True
assert outer['exitcode']==outer['wrapper_exitcode']==0 and type(outer['elapsed_ticks']) is int and type(outer['stopwatch_frequency']) is int
assert 0<=outer['elapsed_ticks']<=120*outer['stopwatch_frequency'] and outer['external_application_seconds']==outer['elapsed_ticks']/outer['stopwatch_frequency']
assert outer['command']==[sys.executable,'-m',d.MODULE,'--prepare','--output',str(DEST)]
assert outer['python_sha256']==outer['python_after_sha256']==d.sha(sys.executable)
assert d.sha(outer['wrapper']['path'])==outer['wrapper_after_sha256']==outer['wrapper']['sha256']
for item in outer['outputs'].values():
    if item is not None:assert d.sha(item['path'])==item['sha256']
ready=d.read(DEST/'ready.json');assert ready['plan']==d.ref(DEST/'plan.json') and ready['status']=='prepared_unexecuted'
assert not any((DEST/n).exists() for n in ('execution_claim.json','receipt.json','report.json'))
d.no_execution_extensions(pure=True)
report={'schema':'g31.source_inventory65.root_prelaunch.v1','status':'one_fixed65_diagnostic_authorized_after_exclusive_window_release',
 'script_sha256':d.sha(__file__),'plan_sha256':expected,'sources':196,'evidence':12,'pure_tests':71,
 'pure_whole_seconds':d.read(PURE/'external_application_wall.json')['external_application_seconds'],
 'metadata_whole_seconds':outer['external_application_seconds'],'command':ready['execute_command'],
 'requirements':['One65/owned120 diagnostic, exact original callable, no cache or monkeypatch. One physical call failure stops later calls and all65 rows remain.','Exclusive timing window; no model/native/customC. Default GC, complete proof bytes, pstats count and original identity, entry/exit source bindings retained.','External whole Python launch-to-exit, typedticks<=120, exact wrapper/plan/command/interpreter/rootreview and outputs binding required. All imports,proofs,exports/readbacks charged.','Cumulative profile intervals overlap. This attributes static proof cost; no speed or complete100ms claim.'],
 'read_scope':'Root read kernel/driver/pure runner and71 focused cases. Only saved sources/evidence checked here;0 actual original proof calls.'}
with (DEST/'root_review_001.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2)
print(json.dumps({'status':report['status'],'root_review_sha256':d.sha(DEST/'root_review_001.json'),'sources':196}))
