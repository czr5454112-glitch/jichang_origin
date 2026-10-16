"""Fixed96 conformance of owned execution; no execution during preparation.

The prior full diagnostic is an independent saved comparison, not a claim that
its removed graph measurements were made again by this runtime candidate.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import traceback
from types import FunctionType,SimpleNamespace
import xml.etree.ElementTree as ET
from . import validate_full32_future_suffix as previous
from . import live_obligation_owned_prefix_evaluator as runtime
from . import prepare_live_owned_initial_runtime_v2 as ready
from . import initial_owner_route_image as image

ROOT,OUT=previous.ROOT,previous.OUT
MODULE=__package__+'.validate_owned_full32_runtime'
SCHEMA='g31.owned_full32_runtime_conformance.v1'
SOURCE=OUT/'live_owned_initial_runtime_source_prepare_002'
# This driver consumes only corrected canonical archive002, never archive001.
SOURCE_SHA='37e6e8366b4d319b4ec0a566981864f56e3fa9914505340d100d4e159b4837fd'
REFERENCE=OUT/'full32_future_suffix_prepare_001'
REFERENCE_SHA='c48367f67be44aea409369d72f632228d28839fe1580fcda6bdacdabbdf7d811'
PURE=OUT/'owned_full32_runtime_driver_pure_001'
TESTS=('tests/test_g31_circulation_owned_full32_runtime_driver.py',)
EXPECTED_TESTS=20
LIMIT=360.
CASES,ORDER,GROUP_ORDER=previous.CASES,previous.ORDER,previous.GROUP_ORDER
sha,read,write,ref,bytes_of=previous.sha,previous.read,previous.write,previous.ref,previous.bytes_of
require=previous.require


# Only an isolated complete prediction reaches the durable writer. No model
# object/frame or callback is inserted into the model graph.
_SAVE_CODE,_SAVE_PROOF=runtime._rewrite(runtime.execute_group,[
    ("return {'memory_label':label,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}",
     'return _durable_save(label,predictions[label])')])
_WORKER_CODE,_WORKER_PROOF=runtime._rewrite(previous.worker,[
    ('evaluator.audit_group(result,targets)',
     "_audit_group(result,targets,plan['groups'][group_key]['comparison_only_group'])")])


def execute_group(group,make_context,save_prediction,*,model,future):
    """Same runtime plus isolated-output persistence; no target accepted."""
    result={'prefix_index':group['prefix_index'],'candidate_indices':copy.deepcopy(group['candidate_indices']),
        'context_constructions':0,'detail':None,'rows':{f'vector_{i:02d}':{'candidate_index':i,
            'action':copy.deepcopy(a),'status':'unknown_unexecuted'}
            for i,a in zip(group['candidate_indices'],group['actions'],strict=True)}}
    try:
        require(model is runtime.future.core and future is runtime.future,'unchanged_runtime_factories')
        result['context_constructions']+=1
        context=make_context(group['prefix_index'],copy.deepcopy(group['representative_action']))
        function=FunctionType(_SAVE_CODE,{**runtime.execute_group.__globals__,'_durable_save':save_prediction},
            runtime.execute_group.__name__,runtime.execute_group.__defaults__,runtime.execute_group.__closure__)
        item=function(group,context);result=item['detail']
    except Exception:
        result['error']=traceback.format_exc()
        for row in result['rows'].values():row['status']='unknown_group_error'
    return result


def _without_graph_encoding(value):
    require(type(value) is dict and all(k in value for k in ('graph_sha256','graph_encoded_bytes')),'old_graph_metadata')
    return {key:copy.deepcopy(item) for key,item in value.items() if key not in ('graph_sha256','graph_encoded_bytes')}


def audit_values(result,targets,old):
    """Saved data only. Never calls a model or fabricates removed proof flags."""
    require(tuple(targets)==previous.domain.LATER and len(result['rows'])==2,'audit_two_candidates')
    inner=result['detail'];prior=old['result']['detail']
    require(result['context_constructions']==1 and old['status']=='exact_two_future_suffixes'
        and old['result']['status']=='exact_two_future_suffixes','one_context_and_prior_exact')
    require(inner['prefix']['status']==prior['prefix']['status']=='supported_known_B_cut'
        and inner['prefix']['parent_unconsumed'] is True,'supported_retained_parent')
    require(inner['prefix'].get('isolation_basis')==runtime.OWNERSHIP
        and inner['prefix'].get('diagnostic_graphs_computed') is False
        and not any(k in inner['prefix'] for k in ('complete_graph_only_future_action_changed','three_mutable_graphs_disjoint','parent_graph_sha256')),
        'no_fabricated_diagnostic_flags')
    require(bytes_of(inner['counts'])==bytes_of(prior['counts']),'original_execution_counts')
    require(len(inner['points'])==len(prior['points']) and bytes_of(inner['points'])==bytes_of([
        _without_graph_encoding(point) for point in prior['points']]),'all_retained_semantic_points')
    require(bytes_of(inner['prefix']['point'])==bytes_of(_without_graph_encoding(prior['prefix']['point'])),
        'retained_selected_cut_point')
    require(tuple(inner['suffixes'])==previous.domain.LATER,'ordered_suffixes')
    for (key,execution),choice in zip(result['rows'].items(),previous.domain.LATER,strict=True):
        suffix=inner['suffixes'][choice];old_suffix=prior['suffixes'][choice]
        require(execution['status']=='unknown_prediction_returned_audit_pending'
            and suffix['status']=='returned' and old_suffix['status']=='returned','returned_not_postsave_failed')
        require(suffix.get('isolation_basis')==runtime.OWNERSHIP
            and 'parent_and_unconsumed_sibling_isolated' not in suffix,'new_isolation_scope')
        require(bytes_of(suffix['terminal_state'])==bytes_of(_without_graph_encoding(old_suffix['terminal_state']))
            and bytes_of(suffix['initial_cut_action'])==bytes_of(old_suffix['initial_cut_action']),
            'terminal_and_actual_future_action')
        artifact=suffix['prediction'];require(sha(artifact['path'])==artifact['sha256'],'prediction_hash')
        raw=gzip.decompress(Path(artifact['path']).read_bytes());target=targets[choice]
        require(raw==target,'complete_prediction_bytes:'+choice)
        require(previous.paired.json_signature(json.loads(raw))==previous.paired.json_signature(json.loads(target)),
            'types_floathex_order:'+choice)
    # No partial success labels are committed before both sibling audits pass.
    for row,choice in zip(result['rows'].values(),previous.domain.LATER,strict=True):
        row.update(status='exact_conformance',suffix=copy.deepcopy(inner['suffixes'][choice]))
    result.update(status='exact_two_future_suffixes',comparison_scope='Complete prediction bytes and all retained point/terminal/action/count fields.',
        diagnostic_graphs_remeasured=False,prior_graph_audit_is_saved_reference_only=True)


def _audit_group(result,targets,reference):
    require(sha(reference['path'])==reference['sha256'],'comparison_only_group_hash')
    audit_values(result,targets,read(reference['path']))


def source_gate():
    require(type(SOURCE_SHA) is str and len(SOURCE_SHA)==64,'canonical_runtime_source_not_ready')
    require(sha(SOURCE/'plan.json')==SOURCE_SHA and sha(REFERENCE/'plan.json')==REFERENCE_SHA,'source_and_reference_plans')
    source=read(SOURCE/'plan.json');old=read(REFERENCE/'plan.json');receipt=read(REFERENCE/'receipt.json')
    require(receipt['status']=='exact_full96_future_suffixes' and receipt['exact_rows']==96
        and receipt['unknown_rows']==0 and receipt['source_changed']==[],'original_full96_conformance')
    for folder,plan in ((SOURCE,source),(REFERENCE,old)):ready.verify_archive(ROOT,folder,plan)
    return source,old


def source_files():
    files=[(n,(ROOT/n).read_bytes()) for n in read(SOURCE/'plan.json')['source_sha256']]
    entries=[MODULE,__package__+'.run_owned_full32_runtime_driver_pure','tests.test_g31_circulation_owned_full32_runtime_driver']
    files.extend(image.source_closure(ROOT,entries).items())
    return ready.merge_sources(ROOT,files)


def source_proof():
    require(_NS['worker'].__code__ is _WORKER_CODE and _NS['evaluator'].execute_group is execute_group
        and _NS['_audit_group'] is _audit_group,'private_worker_wiring')
    allowed={'BOOT','MODULE','SCHEMA','source_files','pure_gate','check_plan','prepare','worker','execute','main','evaluator','_audit_group'}
    require(set(_NS)==set(previous.__dict__)|{'_audit_group'}
        and all(_NS[k] is v for k,v in previous.__dict__.items() if k not in allowed),'worker_complete_defining_globals')
    return {'schema':SCHEMA,'save_inverse_AST':copy.deepcopy(_SAVE_PROOF),'worker_inverse_AST':copy.deepcopy(_WORKER_PROOF),
        'runtime':runtime.source_proof(),'unchanged_default_GC':True,'original360_budget_code':True,
        'source_files_only_audit':True,'comparison_only_after_complete_output_saved':True,
        'graph_metrics_not_recreated':True,'native_calls':0,'100ms_certified':False}


def pure_gate():
    receipt=read(PURE/'receipt.json');bounded=read(PURE/'bounded_parent_receipt.json')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['tests']==EXPECTED_TESTS and receipt['source_changed']==[],'driver_pure')
    require(len(cases)==EXPECTED_TESTS and not any(n.tag in ('failure','error','skipped') for row in cases for n in row),'driver_pure_cases')
    require(sha(PURE/'tests.xml')==receipt['XML_sha256'] and bounded['status']=='passed'
        and bounded['receipt_sha256']==sha(PURE/'receipt.json'),'driver_pure_closed')
    for name,digest in receipt['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(PURE/'source'/name)==digest,'tested_driver_source:'+name)
    source_gate();require(read(SOURCE/'plan.json')['source_proof']['provider']['execution']==runtime.source_proof(),
        'runtime_source_proof_unchanged')


def check_plan(plan):
    _CHECK(plan)
    require(plan['owned_runtime_source_plan']=={'path':str(SOURCE/'plan.json'),'sha256':SOURCE_SHA}
        and plan['diagnostic_reference_plan']=={'path':str(REFERENCE/'plan.json'),'sha256':REFERENCE_SHA},'fixed_prior_references')
    require(plan['owned_driver_source_proof']==source_proof(),'owned_driver_proof')
    for key in GROUP_ORDER:require('comparison_only_group' in plan['groups'][key],'old_group_reference')


def prepare(output):
    source,old=source_gate();pure_gate();files=source_files();saved_rows=read(REFERENCE/'rows.json');saved_groups=read(REFERENCE/'groups.json')
    require(tuple(saved_rows)==ORDER and tuple(saved_groups)==GROUP_ORDER,'old_full_denominator')
    output.mkdir(parents=True,exist_ok=False);rows=copy.deepcopy(old['rows']);groups=copy.deepcopy(old['groups']);evidence={}
    for key in ORDER:
        old_input=rows[key]['initial_input'];require(sha(old_input['path'])==old_input['sha256'],'old_initial_input')
        public=read(old_input['path']);path=(output/'inputs'/key).with_suffix('.json');path.parent.mkdir(parents=True,exist_ok=True)
        write(path,public);require(bytes_of(public)==bytes_of(read(path)),'input_copy')
        target=saved_rows[key]['prediction'];require(saved_rows[key]['status']=='exact_conformance' and sha(target['path'])==target['sha256'],'accepted_prediction')
        rows[key].update(status='unknown_unexecuted',initial_input=ref(path),comparison_only_prediction=copy.deepcopy(target))
        for item in (old_input,target,rows[key]['comparison_only_actual_raw'],ref(path)):evidence[item['path']]=item['sha256']
    for key in GROUP_ORDER:
        record=groups[key];keys=record['candidate_keys'];previous.qualify_pair([read(rows[k]['initial_input']['path']) for k in keys],record['group']['actions'])
        require(saved_groups[key]['status']=='exact_two_future_suffixes','old_group_exact')
        path=(output/'comparisons'/key).with_suffix('.json');path.parent.mkdir(parents=True,exist_ok=True);write(path,saved_groups[key])
        record['comparison_only_group']=ref(path);record['status']='unknown_unexecuted';evidence[str(path)]=sha(path)
    mapping=ready.archive_sources(ROOT,output,files)
    for folder,names in ((SOURCE,('plan.json','ready.json')),(REFERENCE,('plan.json','receipt.json','rows.json','groups.json','entry_pins.json','exit_pins.json','bounded_execution.json','external_application_wall.json')),
        (PURE,('plan.json','receipt.json','tests.xml','bounded_parent_receipt.json','external_application_wall.json'))):
        for name in names:evidence[str(folder/name)]=sha(folder/name)
    plan={**copy.deepcopy(old),'schema':SCHEMA,'rows':rows,'groups':groups,
        'source_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()},'source_archive':mapping,
        'evidence_sha256':evidence,'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'owned_runtime_source_plan':ref(SOURCE/'plan.json'),'diagnostic_reference_plan':ref(REFERENCE/'plan.json'),
        'owned_driver_source_proof':source_proof(),
        'budget_basis':{'prior_full96_diagnostic_actual_seconds':216.9747081,'fixed_seconds':LIMIT,
            'scope':'Same360 shared import/pin/context/48prefix/96clone+suffix/export/audit budget. Removing diagnostic work is a hypothesis, not a measured speed or100ms claim.'},
        'rules':['Original fixed3x32 actions and48 independent initial A/B context pairs; no scoped/context optimization.',
            'Only original initial public fields and the fixed action enter runtime; reference futures only read after durable outputs.',
            'All65 source inventories per full32 and80 original cut calls/32 complete clones retained; first invalid cut keeps both unknown.',
            'Original graph diagnostic results are saved reference evidence; this run does not recompute or fabricate graph hashes/isolation measurements.',
            'Exact full prediction bytes/types/floathex/chronology and every retained point/terminal/action/count field compared.',
            'No actual native authority/hidden-state coverage/utility/100ms certificate. Default GC remains unchanged.'],
        'model_runs_during_preparation':0}
    check_plan(plan);ready.verify_archive(ROOT,output,plan)
    write(output/'plan.json',plan);write(output/'rows.json',rows);write(output/'groups.json',groups)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':ref(output/'plan.json'),'source_count':len(files),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')],
        'native_calls':0,'model_predictions':0})


_NS={**previous.__dict__,'BOOT':BOOT,'MODULE':MODULE,'SCHEMA':SCHEMA,'source_files':source_files,'pure_gate':pure_gate,
    'check_plan':check_plan,'prepare':prepare,'evaluator':SimpleNamespace(execute_group=execute_group),'_audit_group':_audit_group}
_CHECK=FunctionType(previous.check_plan.__code__,{**previous.check_plan.__globals__,'SCHEMA':SCHEMA},'check_plan')
for _name in ('worker','execute','main'):
    _old=getattr(previous,_name);_code=_WORKER_CODE if _name=='worker' else _old.__code__
    _value=FunctionType(_code,_NS,_name,_old.__defaults__,_old.__closure__);_value.__kwdefaults__=_old.__kwdefaults__;_NS[_name]=_value
worker,execute,main=(_NS[name] for name in ('worker','execute','main'))


if __name__=='__main__':raise SystemExit(main())
