"""New96 actual counterfactual campaign using retained own delivered history.

No old trajectory is promoted or used for online choice. The actual run is a
separate bounded invocation after source/pure review, not part of preparation.
"""
from __future__ import annotations
import copy,gzip,json,sys,time,traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from types import FunctionType
from . import research_live_obligation_recollection_v2 as base
from . import live_obligation_historical_adapter as adapter
from . import live_obligation_historical_policy as policy
from . import verify_live_obligation_historical as saved

prior=base.prior
ROOT,OUT,ORDER,CASE_ORDER=base.ROOT,base.OUT,base.ORDER,base.CASE_ORDER
HARD_TIMEOUT=600.
require,sha,read,write,reference=base.require,base.sha,base.read,base.write,base.reference
OLD_PLAN=OUT/'live_obligation_recollection_native_v2_prepare_001/preregistered_protocol.json'
OLD_PLAN_SHA='f0db13dfee5ba0329664137cbcb1ef1452dc18be785950423cc8a7b6e020f6f8'
HISTORY_PREP=OUT/'historical_goal_service_source_prepare_001/source_preparation.json'
HISTORY_PREP_SHA='93c8f76b701417f986688b550691dc71b1af831bd4fdd79e6620503e4c77540b'
TEST_XML=OUT/'historical_native_campaign_pure_002.xml'
PURE_TEST_COUNT=82
SCHEMA='g31.live_obligation_historical_fixed96.v1'

def _clone(function,namespace):
    result=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result

_private={**vars(prior),'adapter':adapter,'OwnerPolicy':policy.OwnerPolicy}
_private['owner_first_action']=_clone(prior.owner_first_action,_private)
_native_branch=_clone(prior._run_branch,_private)
export_attempts=_clone(base.export_attempts,globals())
run_branch=_clone(base.run_branch,globals())
comparisons=base.comparisons
source_closure=base.source_closure

def verify(output,plan):
    require(plan['schema']==SCHEMA and plan['case_order']==CASE_ORDER and plan['branch_order']==ORDER
        and plan['rows']==prior.probe_rows() and plan['native_branch_budget']==96
        and plan['hard_timeout_seconds']==600.,'fixed96_plan')
    prior.domain_contract.validate_rows(plan['rows'])
    require(set(plan['source_sha256'])==set(map(str,source_closure())),'loaded_source_closure')
    for path,digest in plan['source_sha256'].items():
        require(sha(path)==sha(output/plan['source_archive'][path])==digest,'source_pin')
    for key in ORDER:
        p=output/'inputs'/(key+'.json')
        require(sha(p)==plan['input_file_sha256'][key] and read(p)==prior.native_scene(plan['rows'][key]['case']),'input_pin')
    require(plan['runtime_overlay']==prior.RUNTIME_OVERLAY and plan['strict_protection_tolerance']==0.
        and plan['common_horizon']==40. and plan['native_forks']==0,'physical_contract')
    for ref in (plan['binary'],plan['interpreter'],plan['native_contract_reference'],plan['semantic_gate_reference'],
                *plan['auxiliary_references'].values()):require(sha(ref['path'])==ref['sha256'],'reference_pin')

def prepare(output):
    require(not output.exists(),'immutable_output')
    require(sha(OLD_PLAN)==OLD_PLAN_SHA and sha(HISTORY_PREP)==HISTORY_PREP_SHA,'frozen_prior_boundaries')
    old=read(OLD_PLAN);history=read(HISTORY_PREP)
    for p,digest in old['source_sha256'].items():require(sha(p)==sha(OLD_PLAN.parent/old['source_archive'][p])==digest,'old85_source_pin')
    for p,item in history['source_archive'].items():require(sha(p)==sha(item['archive']['path'])==item['sha256'],'historical_pure_source_pin')
    suites=ET.parse(TEST_XML).getroot().findall('testsuite')
    require(PURE_TEST_COUNT>0 and len(suites)==1 and int(suites[0].get('tests',0))==PURE_TEST_COUNT
        and all(int(suites[0].get(k,-1))==0 for k in ('failures','errors','skipped')),'campaign_pure_gate')
    output.mkdir(parents=True);sources=source_closure();pins={str(p):sha(p) for p in sources};archives={}
    for p in sources:
        dest=output/'source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(p.read_bytes());archives[str(p)]=str(dest.relative_to(output))
    plan={**{k:copy.deepcopy(old[k]) for k in ('case_order','branch_order','rows','native_branch_budget','hard_timeout_seconds',
        'binary','native_contract_reference','semantic_gate_reference','runtime_overlay','same_physical_inputs_and_fixed_actions',
        'failure_and_partial_rule','scope','first_return_action_semantics','references','cost_scope','common_horizon',
        'strict_protection_tolerance','native_forks','max_native_workers')},'schema':SCHEMA,
        'source_sha256':pins,'source_archive':archives,'input_file_sha256':{},'interpreter':reference(sys.executable),
        'communication_policy':'Same one-recollection and bounded reply policy; current B may consume its retained own delivered final-entry ACK history. No new retry or retiming.',
        'history_source_contract':{'owner_client':'exact fixture.LocalTransport, same native session and current admission; immutable own submitted call prefix and row aliases checked',
            'history':'actual B own client_commands planning-v3 selfACK; current E capture may come from B received A envelope',
            'raw_fields':'original clamped ready field preserved; separate derived service deadline and full provenance',
            'limits':'only final goal-loaded E/P; no synthetic unload completion receipt; current source/ACK union/occupancy/L wire checks retained'},
        'fresh_outcomes_required':'History can support first collection and avoid old recollection; old native outcomes and normal-exchange model predictions are not reused.',
        'budget_derivation':{'old96_external_seconds':310.8429368,'fixed_shared_limit_seconds':600.,'no_extension_or_case_restart':True},
        'auxiliary_references':{name:reference(p) for name,p in {'old85_native_plan':OLD_PLAN,'history_source_pure_preparation':HISTORY_PREP,
            'history_pure_tests':OUT/'historical_goal_service_pure_001.xml','history_saved_replay':OUT/'historical_goal_service_saved_replay_001.json',
            'residual_source_diagnosis':OUT/'live_obligation_recollection_v2_residual_001.json','pure_tests':TEST_XML,
            'pure_test_source':ROOT/'tests/test_g31_circulation_historical_native_campaign.py',
            **{'frozen_'+case:OUT/'live_obligation_projection_prepare_003'/(case+'.input.json') for case in CASE_ORDER}}.items()}}
    for key in ORDER:
        p=output/'inputs'/(key+'.json');p.parent.mkdir(parents=True,exist_ok=True)
        data=prior.native_scene(plan['rows'][key]['case']);write(p,data)
        require(prior.validate_runtime_input(data)==read(plan['auxiliary_references']['frozen_'+plan['rows'][key]['case']]['path']),'frozen_physical_input')
        plan['input_file_sha256'][key]=sha(p)
    write(output/'preregistered_protocol.json',plan);verify(output,plan)
    command=[sys.executable,'-m','scripts.experiments.g31_ics_circulation.launch_live_obligation_historical','--launch','--output',str(output)]
    receipt={'status':'prepared_unexecuted','plan_sha256':sha(output/'preregistered_protocol.json'),
        'source_count':len(sources),'native_executions':0,'model_evaluations':0,'launch_command':command}
    write(output/'prepare_receipt.json',receipt);return receipt

# Keep the accepted worker bytecode and accounting. Change receipt metadata at
# its single write boundary; never publish a provisional old-schema receipt.
def worker(output):
    def worker_write(path,data):
        if path==output/'receipt.json':
            require(data['schema']=='g31.live_obligation_recollection_fixed96_receipt.v2','worker_receipt_schema')
            data={**data,'schema':'g31.live_obligation_historical_fixed96_receipt.v1',
                  'historical_own_client_binding':True}
        write(path,data)
    _clone(base.worker,{**globals(),'write':worker_write})(output)
