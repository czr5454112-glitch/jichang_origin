"""Fixed six prefixes / twelve future-later suffixes; prepare is not execution."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
import xml.etree.ElementTree as ET
from . import bounded_windows_job
from . import validate_live_conditional_continuation as previous

ROOT,OUT=previous.ROOT,previous.OUT
SOURCE=OUT/'future_later_fork_source_prepare_001'
SOURCE_SHA='26debdc0452ce038a4c915ff736600db3520c63d224b3aaca810ebfa27a54062'
PURE=OUT/'future_later_paired_driver_pure_001'
MODULE=__package__+'.validate_future_later_paired_suffix'
SCHEMA='g31.future_later_paired_suffix.v1'
ORDER=previous.ORDER
CUT_COUNTS=previous.CUT_COUNTS
CHOICES=('native_default','prefer_8')
LIMIT=120.
sha,read,write,ref=previous.sha,previous.read,previous.write,previous.ref
bytes_of,graph=previous.bytes_of,previous.graph
point_description,terminal_description=previous.point_description,previous.terminal_description


def require(value,reason):
    if not value:raise ValueError('future_six:'+reason)


def remaining(elapsed):
    require(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>=0,'elapsed')
    value=LIMIT-elapsed-1.
    if value<=0:raise TimeoutError('future_six:budget_before_worker')
    return value


def check_domain(rows):
    require(type(rows) is dict and tuple(rows)==ORDER and len(rows)==6,'six_ordered_rows')
    require(tuple(row['maximum_prefix_cuts'] for row in rows.values())==CUT_COUNTS,'fixed_cut_bounds')
    for key,row in rows.items():
        require(tuple(row['suffixes'])==CHOICES,'two_later_denominator')
        left,right=row['original_action'],row['counterpart_action']
        require(set(left)==set(right)=={'initial_action','empty_departure','return_delay','later_action'},'action_fields')
        require(bytes_of({k:v for k,v in left.items() if k!='later_action'})==bytes_of({k:v for k,v in right.items() if k!='later_action'})
            and {left['later_action'],right['later_action']}==set(CHOICES),'only_future_field')


def action_graph_only(before,after,old_later,new_later):
    """Compare complete diagnostic alias graphs, changing one scalar node only."""
    data=json.loads(before);nodes=data['nodes'];root=nodes[data['root'][1]]
    require(root[0]=='tuple' and len(root[1])==2,'graph_root')
    engine=nodes[root[1][0][1]];require(engine[0]=='object','graph_engine')
    attributes=nodes[engine[2][1]];require(attributes[0]=='dict','graph_attributes')
    actions=[value for key,value in attributes[1] if key==['str','action']]
    require(len(actions)==1 and actions[0][0]=='ref','graph_action_reference')
    action=nodes[actions[0][1]];require(action[0]=='dict','graph_action')
    values=[pair for pair in action[1] if pair[0]==['str','later_action']]
    require(len(values)==1 and values[0][1]==['str',old_later],'graph_old_later')
    values[0][1]=['str',new_later]
    require(bytes_of(data)==after,'unexpected_graph_or_alias_change')


def mutable_ids(state,model):
    """Diagnostics for factory graphs; tuples may share only immutable leaves."""
    allowed=(model.Projection,model.lazy.original.captures.CaptureWorld,model.lazy.original.policy.PhaseReplyBudget)
    result=set();seen=set()
    def visit(value):
        if value is None or type(value) in (bool,int,float,str):return
        if id(value) in seen:return
        seen.add(id(value))
        if type(value) in (dict,list,set) or type(value) in allowed:result.add(id(value))
        if type(value) is dict:
            for k,v in value.items():visit(k);visit(v)
        elif type(value) in (list,tuple,set,frozenset):
            for item in value:visit(item)
        elif type(value) in allowed:visit(vars(value))
        else:raise ValueError('future_six:unknown_graph_type')
    visit((state._engine,state._frames));return result


def json_signature(value):
    """JSON tree types/order and exact float bits; no numerical tolerance."""
    if value is None:return ['none']
    if type(value) is bool:return ['bool',value]
    if type(value) is int:return ['int',str(value)]
    if type(value) is float:
        require(math.isfinite(value),'nonfinite_output');return ['float',value.hex()]
    if type(value) is str:return ['str',value]
    if type(value) is list:return ['list',[json_signature(v) for v in value]]
    require(type(value) is dict and all(type(k) is str for k in value),'non_json_output')
    return ['dict',[[k,json_signature(v)] for k,v in value.items()]]


def run_case(context,action,maximum_cuts,model,future,save_prediction):
    """Only initial supplied data/action enter the engine. No target arguments."""
    result={'status':'unknown_in_progress','prefix':{'status':'unknown_unexecuted'},'points':[],
        'suffixes':{choice:{'status':'unknown_unexecuted'} for choice in CHOICES},
        'counts':{'initial_engines':0,'initial_advances':0,'prefix_same_resumes':0,'future_forks':0,'future_resumes':0}}
    counts=result['counts'];parent=None;before=None;children={};child_graphs={}
    try:
        counts['initial_engines']+=1;state=model.start_conditional(context,action)
        if type(state) is not model.Continuation:
            result['prefix'].update(status='unknown_initial_context',prediction=save_prediction('prefix_terminal',state));return result
        counts['initial_advances']+=1;value=model.advance_to_collection_or_terminal(state)
        while type(value) is model.Continuation:
            require(len(result['points'])<maximum_cuts,'unexpected_extra_prefix_cut')
            description=point_description(value,model);result['points'].append(description)
            if description['phase']=='first_reuse_route':
                require(description['owner']=='B','unexpected_phase_B_owner')
                if description['information_status']=='conditional_validated_later_v3_data':
                    # First known B cut is irrevocably selected. If a strict
                    # current/wire/deadline guard fails, do not seek a later cut.
                    future._cut(value);parent=value;before=graph(parent,model)
                    result['prefix'].update(status='supported_known_B_cut',point=description)
                    break
                require(description['retry_status']=='conditional_retry_admissible','unknown_B_without_declared_fresh_pair')
            else:require(description['owner']=='A' and description['phase']=='first_return','unreviewed_prefix_phase')
            counts['prefix_same_resumes']+=1;value=model.resume_same_action(value)
        if parent is None:
            result['prefix'].update(status='unknown_no_supported_B_cut',prediction=save_prediction('prefix_terminal',value));return result
        # Both children originate from the identical untouched parent before
        # either suffix runs. Each uses the explicit new fork contract once.
        for choice in CHOICES:
            counts['future_forks']+=1;branch=future.fork_later_action(parent,choice)
            child=branch._state;encoded=graph(child,model)
            action_graph_only(before,encoded,action['later_action'],choice)
            require(graph(parent,model)==before,'parent_changed_by_fork')
            children[choice]=branch;child_graphs[choice]=encoded
        ids={key:mutable_ids(branch._state,model) for key,branch in children.items()}
        pids=mutable_ids(parent,model)
        require(not(ids[CHOICES[0]]&ids[CHOICES[1]]) and all(not(pids&v) for v in ids.values()),'shared_mutable_fork_state')
        result['prefix'].update(parent_graph_sha256=hashlib.sha256(before).hexdigest(),
            complete_graph_only_future_action_changed=True,three_mutable_graphs_disjoint=True)
    except Exception:
        result['prefix'].update(status='unknown_prefix_or_fork_error',error=traceback.format_exc());return result
    for choice in CHOICES:
        row=result['suffixes'][choice];branch=children[choice];child=branch._state
        try:
            require(graph(parent,model)==before and graph(child,model)==child_graphs[choice],'pre_suffix_changed')
            counts['future_resumes']+=1;value=future.resume_future_later(branch)
            if type(value) is model.Continuation:
                row.update(status='unknown_unexpected_postB_cut',point=point_description(value,model));continue
            # Save the complete returned prediction before terminal diagnostics
            # or any comparison-target decoding can fail.
            row.update(status='returned',prediction=save_prediction(choice,value))
            row['terminal_state']=terminal_description(child,model)
            row['initial_cut_action']=copy.deepcopy(branch._after)
            require(graph(parent,model)==before,'parent_changed_by_suffix')
            waiting=[other for other in CHOICES if other!=choice and not children[other]._consumed]
            require(all(graph(children[other]._state,model)==child_graphs[other] for other in waiting),'sibling_changed_by_suffix')
            previous.mutate_finished_copy(child)
            require(graph(parent,model)==before and all(graph(children[other]._state,model)==child_graphs[other] for other in waiting),
                'finished_mutation_leaked')
            row['parent_and_unconsumed_sibling_isolated']=True
        except Exception:row.update(status='unknown_suffix_error',error=traceback.format_exc())
    result['prefix']['parent_unconsumed']=parent._consumed is False
    return result


def audit_case(result,expected,targets):
    require(tuple(result['suffixes'])==CHOICES and tuple(targets)==CHOICES,'two_suffix_denominator')
    require(result['prefix']['status']=='supported_known_B_cut','missing_supported_cut')
    previous.passive.check_points(result['points'],expected)
    require(result['counts']=={'initial_engines':1,'initial_advances':1,'prefix_same_resumes':len(expected)-1,
        'future_forks':2,'future_resumes':2},'complete_execution_counts')
    require(result['prefix']['complete_graph_only_future_action_changed'] is True
        and result['prefix']['three_mutable_graphs_disjoint'] is True and result['prefix']['parent_unconsumed'] is True,'prefix_graph_proof')
    for choice in CHOICES:
        row=result['suffixes'][choice];require(row['status']=='returned','suffix_unknown:'+choice)
        artifact=row['prediction'];require(sha(artifact['path'])==artifact['sha256'],'saved_prediction_changed')
        raw=gzip.decompress(Path(artifact['path']).read_bytes());target=targets[choice]
        require(raw==target,'full_prediction_bytes:'+choice)
        a,b=json.loads(raw),json.loads(target)
        require(json_signature(a)==json_signature(b),'JSON_types_floathex_order:'+choice)
        require(row['parent_and_unconsumed_sibling_isolated'] is True,'suffix_isolation')
        row.update(whole_prediction_bytes_exact=True,JSON_types_floathex_order_exact=True,
            full_chronology_included=True)
    result['status']='exact_paired_future_suffixes'


def source_ready():
    require(sha(SOURCE/'plan.json')==SOURCE_SHA,'future_source_plan')
    plan=read(SOURCE/'plan.json')
    for name,digest in plan['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(SOURCE/plan['source_archive'][name])==digest,'future_source_changed:'+name)
    for key in ('pure_plan','pure_receipt','pure_XML','pure_bounded','pure_external','source_proof','same_action_six_plan','saved_lazy_plan','saved_lazy_rows'):
        item=plan[key];require(sha(item['path'])==item['sha256'],'source_evidence:'+key)
    return plan


def pure_gate():
    receipt=read(PURE/'receipt.json');require(receipt['status']=='passed' and receipt['source_changed']==[],'driver_pure')
    require(receipt['tests']==receipt['expected_tests']==22 and sha(PURE/'tests.xml')==receipt['XML_sha256'],'driver_pure_count')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases)==22 and not any(n.tag in ('failure','error','skipped') for row in cases for n in row),'driver_pure_XML')
    for name,digest in receipt['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(PURE/'source'/name)==digest,'driver_tested_source:'+name)
    return receipt


def source_files():
    from . import initial_owner_route_image as image
    source=source_ready();result={name:(ROOT/name).read_bytes() for name in source['source_sha256']}
    entries=[MODULE,__package__+'.run_future_later_paired_driver_pure',
        'tests.test_g31_circulation_future_later_paired_driver']
    for name,data in image.source_closure(ROOT,entries).items():
        require(name not in result or result[name]==data,'source_conflict');result[name]=data
    return dict(sorted(result.items()))


def loaded_sources(pins):
    actual={}
    for module in tuple(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if not value:continue
        path=Path(value).resolve()
        if path.suffix=='.py' and path.is_relative_to(ROOT):
            key=path.relative_to(ROOT).as_posix();digest=sha(path)
            require(pins.get(key)==digest,'unlisted_loaded:'+key);actual[key]=digest
    return dict(sorted(actual.items()))


def no_native_or_C_load():
    require(not any('czr005_circulation' in name or '_g31_complete_tree_normalizer' in name
        for name in sys.modules),'native_or_C_loaded')


def prepare(output):
    from . import live_obligation_future_later_fork as future
    source=source_ready();pure_gate();old=read(source['same_action_six_plan']['path'])
    files=source_files();output.mkdir(exist_ok=False);rows={};evidence={}
    for key,n in zip(ORDER,CUT_COUNTS,strict=True):
        item=source['pairs'][key]
        targets={item['original_action']['later_action']:item['same_choice_comparison_only'],
            item['counterpart_action']['later_action']:item['changed_choice_comparison_only']}
        rows[key]={**copy.deepcopy(item),'maximum_prefix_cuts':n,
            'expected_collections':old['rows'][key]['expected_collections'],
            'comparison_only_predictions':{choice:targets[choice] for choice in CHOICES},
            'prefix':{'status':'unknown_unexecuted'},'suffixes':{choice:{'status':'unknown_unexecuted'} for choice in CHOICES}}
        for ref_ in (item['initial_context'],*targets.values()):
            require(sha(ref_['path'])==ref_['sha256'],'selected_file');evidence[ref_['path']]=ref_['sha256']
    check_domain(rows)
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    for path in [SOURCE/'plan.json',PURE/'receipt.json',PURE/'tests.xml',PURE/'bounded_parent_receipt.json',PURE/'external_application_wall.json']:
        evidence[str(path)]=sha(path)
    for field in ('pure_plan','pure_receipt','pure_XML','pure_bounded','pure_external','source_proof','same_action_six_plan','saved_lazy_plan','saved_lazy_rows'):
        item=source[field];evidence[item['path']]=item['sha256']
    plan={'schema':SCHEMA,'order':list(ORDER),'rows':rows,'source_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()},
        'source_archive':{n:'source/'+n for n in files},'evidence_sha256':evidence,
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},'hard_application_seconds':LIMIT,
        'counts':{'initial_engines':6,'initial_advances':6,'prefix_same_resumes':8,'future_forks':12,'future_resumes':12},
        'maximum_prefix_cuts':14,'suffix_choices':list(CHOICES),'source_proof':future.source_proof(),
        'budget_basis':{'previous_same_six_seconds':18.6451326,'previous_resumes':39,'proposed_resumes':20,
            'scope':'120 includes imports/source pins/6 initial contexts/6 engines/12 graph clones/20 resumes/full graph+output audits/export/exit. Prior time is a cost reference, not a bound or product100ms claim.'},
        'rules':['Only initial supplied context and fixed action enter each of six starts; prediction targets and expected chronology are audit-only.',
            'Resume A and the original declared unknown/fresh paths with unchanged action. Select the first known B cut once; unsupported current/wire/deadline fails instead of selecting a later cut.',
            'Both choices fork the same unconsumed parent before either suffix executes. No prefix restart, replay, second collect, extra retry or adaptive sample.',
            'Each returned complete prediction is saved before target decompression or terminal diagnostics. Timeout/failure retains both suffix denominators.',
            'Full JSON bytes, decoded JSON types/order/floathex and all physical/message/collection chronology compared. Original Python container types lost in historical JSON are not newly certified.',
            'No native hidden-state/actual opaque-ID relation, belief coverage, online authority, protected utility or speed certification. Retrospective comparands.' ],
        'native_calls':0,'maximum_initial_engines':6,'maximum_future_suffixes':12}
    write(output/'plan.json',plan);write(output/'rows.json',rows)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':ref(output/'plan.json'),'source_count':len(files),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')],
        'native_calls':0,'real_model_predictions':0})


def worker(output,expected):
    from . import live_obligation_future_later_fork as future
    from . import validate_live_communication_projection as initial
    started=time.perf_counter();require(sha(output/'plan.json')==expected,'plan_hash');plan=read(output/'plan.json')
    check_domain(plan['rows']);require(plan['schema']==SCHEMA and plan['order']==list(ORDER)
        and plan['hard_application_seconds']==LIMIT and plan['maximum_initial_engines']==6 and plan['maximum_future_suffixes']==12
        and plan['maximum_prefix_cuts']==14 and plan['suffix_choices']==list(CHOICES)
        and plan['counts']==dict(initial_engines=6,initial_advances=6,prefix_same_resumes=8,future_forks=12,future_resumes=12),'closed_plan')
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'interpreter')
    no_native_or_C_load();source_ready();pure_gate();require(future.source_proof()==plan['source_proof'],'source_proof')
    pins={str(ROOT/name):digest for name,digest in plan['source_sha256'].items()}
    pins.update(plan['evidence_sha256']);pins.update({str(output/plan['source_archive'][n]):d for n,d in plan['source_sha256'].items()})
    entry={p:sha(p) for p in pins};write(output/'entry_pins.json',entry);require(entry==pins,'entry_pins')
    write(output/'loaded_entry.json',loaded_sources(plan['source_sha256']));rows=copy.deepcopy(plan['rows'])
    for key in ORDER:
        row=rows[key];row['status']='unknown_in_progress';write(output/'rows.json',rows)
        try:
            public=read(row['initial_context']['path'])
            require(set(public)=={'initial_owners','action'} and set(public['initial_owners'])=={'A','B'}
                and bytes_of(public['action'])==bytes_of(row['original_action']),'minimal_initial_input')
            contexts={o:initial.context.initial_context(**public['initial_owners'][o]) for o in ('A','B')}
            require(all(type(v) is initial.context.SuppliedContext for v in contexts.values()),'initial_guards')
            facts={o:initial.context.initial_projection_bundle(v) for o,v in contexts.items()}
            require(all(initial.context.encoded({'v':facts['A'][f]})==initial.context.encoded({'v':facts['B'][f]})
                for f in ('jobs','trays','contract','now')),'independent_initial_facts')
            def save(label,value):
                path=output/'predictions'/key/(label+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(bytes_of(value),compresslevel=1,mtime=0));artifact=ref(path)
                destination=row['prefix'] if label=='prefix_terminal' else row['suffixes'][label]
                destination.update(status='returned_audit_pending',prediction=artifact);write(output/'rows.json',rows)
                return artifact
            at=time.perf_counter();detail=run_case(contexts['A'],public['action'],row['maximum_prefix_cuts'],future.core,future,save)
            row['execution_and_snapshot_seconds']=time.perf_counter()-at
            path=(output/'details'/key).with_suffix('.json');path.parent.mkdir(parents=True,exist_ok=True);write(path,detail)
            row.update(prefix=detail['prefix'],suffixes=detail['suffixes'],counts=detail['counts'],detail=ref(path));write(output/'rows.json',rows)
            try:
                targets={choice:gzip.decompress(Path(row['comparison_only_predictions'][choice]['path']).read_bytes()) for choice in CHOICES}
                audit_case(detail,row['expected_collections'],targets)
            finally:write(path,detail);row['detail']=ref(path)
            row.update(status=detail['status'],prefix=detail['prefix'],suffixes=detail['suffixes'])
        except Exception:row.update(status='unknown_error',error=traceback.format_exc())
        write(output/'rows.json',rows)
    after={p:sha(p) for p in pins};write(output/'exit_pins.json',after);require(after==entry,'exit_drift')
    no_native_or_C_load();write(output/'loaded_exit.json',loaded_sources(plan['source_sha256']))
    exact=sum(row['status']=='exact_paired_future_suffixes' for row in rows.values())
    totals={name:sum(row.get('counts',{}).get(name,0) for row in rows.values()) for name in plan['counts']}
    write(output/'receipt.json',{'schema':SCHEMA,'status':'exact_six_paired_future_suffixes' if exact==6 and totals==plan['counts'] else 'completed_unknowns_preserved',
        'exact_rows':exact,'unknown_rows':6-exact,'counts':totals,'plan':ref(output/'plan.json'),'rows':ref(output/'rows.json'),
        'entry_pins':ref(output/'entry_pins.json'),'exit_pins':ref(output/'exit_pins.json'),
        'loaded_entry':ref(output/'loaded_entry.json'),'loaded_exit':ref(output/'loaded_exit.json'),
        'source_changed':[],'worker_seconds':time.perf_counter()-started,'native_calls':0,
        'same_model_prefix_only':True,'native_hidden_state_coverage':False,'online_protection_certified':False})


def execute(output,expected):
    require(sha(output/'plan.json')==expected and read(output/'plan.json')['schema']==SCHEMA,'launch_plan')
    with (output/'execution_claim.json').open('x',encoding='utf8') as stream:json.dump({'plan_sha256':expected,'shared_seconds':LIMIT},stream)
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',expected]
    with (output/'stdout.log').open('x') as stdout,(output/'stderr.log').open('x') as stderr:
        elapsed=time.monotonic()-BOOT
        process=bounded_windows_job.run(command,timeout=remaining(elapsed),stdout=stdout,stderr=stderr,admission=expected,cwd=ROOT)
    end=time.monotonic()-BOOT;bounded=process['status']=='exited' and process['exitcode']==0 and end<=LIMIT
    write(output/'bounded_execution.json',{'status':'bounded_worker_completed' if bounded else 'unknown_failed_or_budget_exceeded',
        'process':process,'command':command,'plan_sha256':expected,'fixed_application_seconds':LIMIT,
        'parent_before_worker_seconds':elapsed,'application_seconds_before_final_receipt':end,
        'worker_receipt':ref(output/'receipt.json') if (output/'receipt.json').is_file() else None,
        'external_python_launch_through_exit_required':True,'conformance_not_inferred_from_exit':True,'native_calls':0})
    return 0 if bounded and time.monotonic()-BOOT<=LIMIT else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan');args=p.parse_args()
    output=args.output.resolve()
    if args.prepare:prepare(output);return 0
    if args.worker:
        require(args.expected_plan and sys.stdin.readline()==args.expected_plan+'\n','owned_admission')
        try:worker(output,args.expected_plan)
        except BaseException:write(output/'worker_failure.json',{'status':'unknown_worker_failure','error':traceback.format_exc()});raise
        return 0
    require(args.execute,'explicit_action');return execute(output,args.expected_plan)


if __name__=='__main__':raise SystemExit(main())
