"""Metadata-only ready finalizer after the narrow wiring fix; never executes."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parent
folder=OUT/'json_prediction_shards_RPC_prepare_002'
pure=OUT/'json_prediction_shards_pure_002'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
parser=argparse.ArgumentParser()
parser.add_argument('--wrapper',type=Path,required=True)
parser.add_argument('--wrapper-sha256',required=True)
parser.add_argument('--root-review',type=Path,required=True)
parser.add_argument('--root-review-sha256',required=True)
args=parser.parse_args()
assert sha(args.wrapper)==args.wrapper_sha256 and sha(args.root_review)==args.root_review_sha256
planpath=folder/'preregistered_protocol.json'
assert sha(planpath)=='6960f3205c5eef7fbb8ec4f772defadbaac682e5e859f6433a5c3f4ee5ea92e1'
plan=json.loads(planpath.read_bytes());gate=json.loads((pure/'receipt.json').read_bytes())
cases=ET.parse(pure/'tests.xml').getroot().findall('.//testcase')
assert gate['status']=='passed' and gate['source_changed']==[] and gate['tests']==len(cases)==61
assert not any(c.tag in ('failure','error','skipped') for row in cases for c in row)
assert sha(pure/'tests.xml')==gate['XML_sha256']
assert not any((folder/name).exists() for name in ('execution_claim.json','ledger.json','report.json','bounded_execution.json','external_application_wall.json'))
ready={'schema':'g31.json_prediction_exact_two_shards_ready.v1','status':'prepared_unexecuted_root_dispatch_only',
    'output':str(folder),'preregistered_plan_path':str(planpath),'preregistered_plan_sha256':sha(planpath),
    'source_count':len(plan['source_sha256']),'images':plan['images'],'pure_tests':61,
    'pure_receipt':ref(pure/'receipt.json'),'pure_XML':ref(pure/'tests.xml'),
    'prepare_receipt':ref(folder/'prepare_receipt.json'),'external_wrapper':ref(args.wrapper),
    'root_prelaunch_review':ref(args.root_review),'wiring_fix_proof':ref(folder/'wiring_fix_proof_001.json'),
    'prior_failed_attempt':ref(OUT/'json_prediction_shards_failure_diagnosis_001.json'),
    'execute_command':[str(Path(sys.executable).resolve()),'-m',
        'scripts.experiments.g31_ics_circulation.measure_json_prediction_shards','--launch','--output',str(folder),
        '--plan-sha256',sha(planpath)],
    'external_execute_command':['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(args.wrapper.resolve())],
    'hard_timeout_seconds':120.,'logical_requests':24,'physical_processes':6,
    'physical_RPC_requests':36,'physical_full_baselines':36,'candidate_queries':768,
    'native_calls':0,'performance_campaign_executed':False,
    'change_scope':'001 failed before predictor creation due to WindowsPath indexing. Only path join and functional count changed; one campaign wiring regression added. Failed001/negative regression retained.',
    'old_pipeline_comparison_limit':'New common LogicalClient adds isolation, whole-output codec and deep-copied ledger work to BOTH arms. Compare only this package single versus split, not its A directly to prior207.71ms.',
    'scope':'Fixed2worker hypothesis,0..15/16..31. Every B worker executes fresh full guards/potential/baseline. All ordered full/partial outputs and baselines must match. Sum worker compute is nested WALL duration, not CPU/caller latency. Cold/startup/close/duplicate work not amortized.',
    'wrapper_scope':'Stopwatch includes full Python parent startup/import/prechecks, children/requests/merge/codec/ledger/tails, saved verification and parent exit. Declared PowerShell/tool startup and external digest/export are harness exclusions.',
    'complete_100ms_certified':False,'finalizer_source_sha256':sha(__file__)}
review=folder/'independent_source_review_001.json'
if review.is_file():ready['independent_source_review']=ref(review)
with (folder/'ready.json').open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(ready,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
print(json.dumps({'ready':str(folder/'ready.json'),'sha256':sha(folder/'ready.json'),
    'plan_sha256':sha(planpath),'source_count':ready['source_count'],'native_calls':0,
    'performance_campaign_executed':False}))
