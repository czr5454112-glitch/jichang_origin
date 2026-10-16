"""Finalize prepared metadata only; does not launch any experiment."""
from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
folder=OUT/'json_prediction_shards_RPC_prepare_001'
pure=OUT/'json_prediction_shards_pure_001'
wrapper=OUT/'user_resume_20261015_001/invoke_json_prediction_shards_RPC_001_measured.ps1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(p),'sha256':sha(p)}
planpath=folder/'preregistered_protocol.json'
assert sha(planpath)=='02be2c7b8e13ece2bce535558f9b64caecdee3961091ca6dfc0f89ad55382544'
assert sha(wrapper)=='04902d83b3b4cb9ea8f38d49c288998116097591fa0a60eafbb1213448ca3238'
plan=json.loads(planpath.read_bytes());gate=json.loads((pure/'receipt.json').read_bytes())
cases=ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
assert gate['status']=='passed' and gate['source_changed']==[] and gate['tests']==len(cases)==60
assert not any(c.tag in ('failure','error','skipped') for row in cases for c in row)
assert sha(pure/'tests.xml')==gate['XML_sha256']
assert not any((folder/name).exists() for name in ('execution_claim.json','ledger.json','report.json','bounded_execution.json','external_application_wall.json'))
ready={'schema':'g31.json_prediction_exact_two_shards_ready.v1','status':'prepared_unexecuted_root_dispatch_only',
    'output':str(folder),'preregistered_plan_path':str(planpath),'preregistered_plan_sha256':sha(planpath),
    'source_count':len(plan['source_sha256']),'images':plan['images'],'pure_tests':60,
    'pure_receipt':ref(pure/'receipt.json'),'pure_XML':ref(pure/'tests.xml'),
    'prepare_receipt':ref(folder/'prepare_receipt.json'),'external_wrapper':ref(wrapper),
    'execute_command':[str(Path(sys.executable).resolve()),'-m',
        'scripts.experiments.g31_ics_circulation.measure_json_prediction_shards','--launch','--output',str(folder),
        '--plan-sha256',sha(planpath)],
    'external_execute_command':['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper)],
    'hard_timeout_seconds':120.,'logical_requests':24,'physical_processes':6,
    'physical_RPC_requests':36,'physical_full_baselines':36,'candidate_queries':768,
    'native_calls':0,'performance_campaign_executed':False,
    'old_pipeline_comparison_limit':'The new common LogicalClient adds isolation, whole-output codec and deep-copied ledger work to BOTH arms. Compare only this package single versus split; do not compare its new A timing directly to prior207.71ms pipeline.',
    'scope':'Fixed2worker hypothesis only,0..15/16..31. A retains frozen compiled Engine/Client. Every B worker executes fresh full guards/potential/baseline. Ordered baseline/actions/complete-and-partial candidate outputs must match exactly; missing shard invalidates whole request. Sum worker compute is nested WALL time, not CPU or caller latency. Cold/startup/close/duplicate work never averaged away.',
    'wrapper_scope':'Stopwatch includes complete Python parent launch/import/prechecks, all children/requests/merge/codec/ledger/tails, saved verification and parent exit. Declared PowerShell/tool startup and external digest/export are harness exclusions.',
    'complete_100ms_certified':False,'finalizer_source_sha256':sha(__file__)}
with (folder/'ready.json').open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(ready,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
print(json.dumps({'ready':str(folder/'ready.json'),'sha256':sha(folder/'ready.json'),
    'plan_sha256':sha(planpath),'source_count':ready['source_count'],'native_calls':0,
    'performance_campaign_executed':False}))
