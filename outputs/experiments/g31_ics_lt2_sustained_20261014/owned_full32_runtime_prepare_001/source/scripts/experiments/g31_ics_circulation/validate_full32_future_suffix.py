"""Prepared full96 retrospective conformance; execution requires a separate call."""
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
from . import validate_future_later_paired_suffix as paired
from . import live_obligation_full32_suffix_partition as domain
from . import live_obligation_full32_suffix_evaluator as evaluator

ROOT,OUT=paired.ROOT,paired.OUT
MODULE=__package__+'.validate_full32_future_suffix'
SCHEMA='g31.full32_future_suffix_conformance.v1'
CASES=('mechanism','no_overlap','insufficient_advance')
ORDER=tuple(case+f'/vector_{i:02d}' for case in CASES for i in range(32))
GROUP_ORDER=tuple(case+f'/prefix_{i:02d}' for case in CASES for i in range(16))
PRIOR=OUT/'live_communication_lazy_prepare_001'
SIX=OUT/'future_later_paired_six_prepare_001'
PURE=OUT/'full32_future_suffix_pure_001'
LIMIT=360.
TESTS=('tests/test_g31_circulation_full32_suffix_partition.py',
    'tests/test_g31_circulation_full32_suffix_evaluator.py',
    'tests/test_g31_circulation_future_later_paired_driver.py')
EXPECTED_TESTS=60
sha,read,write,ref,bytes_of=paired.sha,paired.read,paired.write,paired.ref,paired.bytes_of


def require(ok,reason):
    if not ok:raise ValueError('full32_future:'+reason)


def remaining(elapsed):
    require(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>=0,'elapsed')
    value=LIMIT-elapsed-1.
    if value<=0:raise TimeoutError('full32_future:shared_budget')
    return value


def source_files():
    from . import initial_owner_route_image as image
    result=paired.source_files()
    entries=[MODULE,__package__+'.run_full32_future_suffix_pure',
        'tests.test_g31_circulation_full32_suffix_partition','tests.test_g31_circulation_full32_suffix_evaluator']
    for name,data in image.source_closure(ROOT,entries).items():
        require(name not in result or result[name]==data,'source_conflict');result[name]=data
    return dict(sorted(result.items()))


def pure_gate():
    receipt=read(PURE/'receipt.json')
    require(receipt['status']=='passed' and receipt['source_changed']==[] and receipt['tests']==EXPECTED_TESTS,'focused_pure')
    cases=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases)==EXPECTED_TESTS and not any(n.tag in ('failure','error','skipped') for row in cases for n in row),'pure_cases')
    require(sha(PURE/'tests.xml')==receipt['XML_sha256'],'pure_XML')
    for name,digest in receipt['source_sha256'].items():
        require(sha(ROOT/name)==digest and sha(PURE/'source'/name)==digest,'tested_source:'+name)


def qualify_pair(publics,actions):
    """No native authority: exact initial JSON equality, no opaque-ID parsing."""
    require(type(publics) is list and len(publics)==2,'two_initial_inputs')
    for item,action in zip(publics,actions,strict=True):
        require(type(item) is dict and tuple(item)==('initial_owners','action') and tuple(item['initial_owners'])==('A','B'),
            'minimal_initial_shape')
        require(bytes_of(item['action'])==bytes_of(action),'input_action')
    require(bytes_of(publics[0]['initial_owners'])==bytes_of(publics[1]['initial_owners']),'paired_initial_endpoint_bytes')


def check_plan(plan):
    require(plan['schema']==SCHEMA and plan['order']==list(ORDER) and tuple(plan['rows'])==ORDER,'96_order')
    require(plan['case_order']==list(CASES) and plan['group_order']==list(GROUP_ORDER) and tuple(plan['groups'])==GROUP_ORDER,'48_order')
    require(plan['hard_application_seconds']==LIMIT and plan['maximum_initial_engines']==48
        and plan['maximum_future_suffixes']==96 and plan['maximum_prefix_cuts_per_group']==4,'fixed_bounds')
    for case in CASES:
        actions=[plan['rows'][case+f'/vector_{i:02d}']['action'] for i in range(32)]
        partition=domain.partition(actions)
        for group in partition['groups']:
            saved=plan['groups'][case+f'/prefix_{group["prefix_index"]:02d}']
            require(bytes_of(saved['group'])==bytes_of(group),'group_action_binding')
            require(saved['candidate_keys']==[case+f'/vector_{i:02d}' for i in group['candidate_indices']],'group_row_binding')


def prepare(output):
    from . import validate_live_communication_projection as initial
    partition=domain.partition_original_domain();pure_gate();files=source_files()
    require(sha(PRIOR/'plan.json')=='afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497'
        and sha(PRIOR/'rows.json')=='7753bc2c9731ded83300435814f5b9c033197237cbaaa0c33721fe09c1a74a3e'
        and sha(PRIOR/'final_receipt.json')=='07b26e476cd5ab328498e919a88503aa2ee64ef73ed21d6c02eb9af0f01c36b0','lazy96_identity')
    require(read(SIX/'receipt.json')['status']=='exact_six_paired_future_suffixes'
        and sha(SIX/'rows.json')=='3b6b8d066c60c51fcbcef28b4420d66131175009daa42546eed0d7a0f9f69be1','actual_six_scope')
    old=read(PRIOR/'rows.json');require(tuple(old)==ORDER,'prior96_order')
    output.mkdir(exist_ok=False);rows={};groups={};evidence={}
    for case in CASES:
        for group in partition['groups']:
            publics=[];keys=[]
            for i,action in zip(group['candidate_indices'],group['actions'],strict=True):
                key=case+f'/vector_{i:02d}';saved=old[key];keys.append(key)
                require(saved['status']=='exact_conformance' and bytes_of(saved['action'])==bytes_of(action),'prior_row_action')
                for name in ('actual_raw','prediction'):
                    item=saved[name];require(sha(item['path'])==item['sha256'],'prior_artifact');evidence[item['path']]=item['sha256']
                # Only initial endpoints plus its immutable at<=.11 publication
                # leave the raw record; outcomes/late data never enter inputs.
                raw=json.loads(gzip.decompress(Path(saved['actual_raw']['path']).read_bytes()))
                public={'initial_owners':{o:initial.public_initial(raw,o) for o in ('A','B')},'action':copy.deepcopy(action)}
                publics.append(public);path=(output/'inputs'/key).with_suffix('.json');path.parent.mkdir(parents=True,exist_ok=True);write(path,public)
                evidence[str(path)]=sha(path)
                rows[key]={'status':'unknown_unexecuted','action':copy.deepcopy(action),'initial_input':ref(path),
                    'comparison_only_prediction':copy.deepcopy(saved['prediction']),'comparison_only_actual_raw':copy.deepcopy(saved['actual_raw'])}
            qualify_pair(publics,group['actions'])
            groups[case+f'/prefix_{group["prefix_index"]:02d}']={'status':'unknown_unexecuted','candidate_keys':keys,'group':copy.deepcopy(group)}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    for folder,names in ((PRIOR,('plan.json','rows.json','final_receipt.json')),
        (SIX,('plan.json','rows.json','receipt.json','external_application_wall.json')),
        (PURE,('plan.json','receipt.json','tests.xml','bounded_parent_receipt.json','external_application_wall.json'))):
        for name in names:evidence[str(folder/name)]=sha(folder/name)
    plan={'schema':SCHEMA,'case_order':list(CASES),'order':list(ORDER),'group_order':list(GROUP_ORDER),'rows':rows,'groups':groups,
        'source_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()},'source_archive':{n:'source/'+n for n in files},
        'evidence_sha256':evidence,'source_proof':partition['source_proof'],
        'environment':{'python':sys.executable,'sha256':sha(sys.executable)},'hard_application_seconds':LIMIT,
        'maximum_initial_engines':48,'maximum_future_suffixes':96,'maximum_prefix_cuts_per_group':4,
        'budget_basis':{'same_source_six_prefix_twelve_suffix_actual_seconds':28.1187678,'linear_eightfold_reference_seconds':224.9501424,
            'fixed_seconds':LIMIT,'scope':'Offline diagnostic budget including all imports/pins/48 fresh initial context pairs/graph cloning/output/96 targets; not a product100ms claim or speed measurement.'},
        'rules':['All original32 Cartesian actions per fixed3 cases; every sibling counts toward its32 budget.16 prefixes include return_delay, never8.',
            '48 fresh A/B supplied-context pairs, same initial endpoints exactly within each action pair; no context cache/scoped model optimization.',
            'Only initial supplied context and fixed action enter each prefix. Source/saved future outcomes are audit-only and cannot select a cut.',
            'Reuse unchanged four-frame same-action and future-only APIs. First known B cut is selected once; invalid/absent cut keeps two unknowns, without restart or adaptive replacement.',
            'Both children fork untouched parent before either resumes. All graph/alias/order/count/guard/output checks retained, no new native queries.',
            'Returned whole prediction saved before any target decoding. Exact full JSON bytes, float bits/types/order and all chronology required; no epsilon.',
            'Targets are retrospective semantic-regression comparands. No hidden-state coverage, actual opaque-ID relation, native authority, online utility, novelty or100ms certification.'],
        'native_calls':0,'model_runs_during_preparation':0}
    check_plan(plan);write(output/'plan.json',plan);write(output/'rows.json',rows);write(output/'groups.json',groups)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan':ref(output/'plan.json'),'source_count':len(files),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')],
        'native_calls':0,'model_predictions':0})


def worker(output,expected):
    from . import live_obligation_future_later_fork as future
    from . import validate_live_communication_projection as initial
    started=time.perf_counter();require(sha(output/'plan.json')==expected,'plan_hash');plan=read(output/'plan.json');check_plan(plan)
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'interpreter')
    paired.no_native_or_C_load();paired.source_ready();pure_gate();require(future.source_proof()==plan['source_proof'],'source_proof')
    pins={str(ROOT/n):d for n,d in plan['source_sha256'].items()};pins.update(plan['evidence_sha256'])
    pins.update({str(output/plan['source_archive'][n]):d for n,d in plan['source_sha256'].items()})
    entry={p:sha(p) for p in pins};write(output/'entry_pins.json',entry);require(entry==pins,'entry_pins')
    write(output/'loaded_entry.json',paired.loaded_sources(plan['source_sha256']))
    rows=copy.deepcopy(plan['rows']);groups=copy.deepcopy(plan['groups'])
    for group_key in GROUP_ORDER:
        record=groups[group_key];keys=record['candidate_keys'];group=record['group'];record['status']='unknown_in_progress'
        write(output/'groups.json',groups)
        try:
            begin=time.perf_counter();publics=[read(rows[k]['initial_input']['path']) for k in keys];qualify_pair(publics,group['actions'])
            def make_context(index,action):
                require(index==group['prefix_index'] and bytes_of(action)==bytes_of(publics[0]['action']),'factory_action')
                contexts={o:initial.context.initial_context(**publics[0]['initial_owners'][o]) for o in ('A','B')}
                require(all(type(v) is initial.context.SuppliedContext for v in contexts.values()),'initial_dynamic_guards')
                facts={o:initial.context.initial_projection_bundle(v) for o,v in contexts.items()}
                require(all(initial.context.encoded({'v':facts['A'][f]})==initial.context.encoded({'v':facts['B'][f]})
                    for f in ('jobs','trays','contract','now')),'initial_independent_facts')
                return contexts['A']
            def save(label,value):
                path=output/'predictions'/group_key/(label+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(gzip.compress(bytes_of(value),compresslevel=1,mtime=0));artifact=ref(path)
                if label in domain.LATER:
                    rows[keys[domain.LATER.index(label)]].update(status='unknown_prediction_returned_audit_pending',prediction=artifact)
                else:record['prefix_terminal']=artifact
                write(output/'rows.json',rows);write(output/'groups.json',groups);return artifact
            result=evaluator.execute_group(group,make_context,save,model=future.core,future=future)
            record.update(context_and_execution_seconds=time.perf_counter()-begin,result=result)
            # Durable complete result precedes target decompression/audit.
            write(output/'groups.json',groups)
            try:
                targets={choice:gzip.decompress(Path(rows[key]['comparison_only_prediction']['path']).read_bytes())
                    for choice,key in zip(domain.LATER,keys,strict=True)}
                evaluator.audit_group(result,targets)
                record['status']='exact_two_future_suffixes'
            except Exception:record.update(status='unknown_audit_or_unsupported',error=traceback.format_exc())
            for key,local in zip(keys,result['rows'].values(),strict=True):rows[key].update(copy.deepcopy(local))
            write(output/'groups.json',groups)
        except Exception:
            record.update(status='unknown_group_error',error=traceback.format_exc())
            for key in keys:rows[key]['status']='unknown_group_error'
        write(output/'rows.json',rows);write(output/'groups.json',groups)
    after={p:sha(p) for p in pins};write(output/'exit_pins.json',after);require(after==entry,'exit_drift')
    paired.no_native_or_C_load();write(output/'loaded_exit.json',paired.loaded_sources(plan['source_sha256']))
    exact=sum(row['status']=='exact_conformance' for row in rows.values());gexact=sum(g['status']=='exact_two_future_suffixes' for g in groups.values())
    counts={k:sum(g.get('result',{}).get('detail',{}).get('counts',{}).get(k,0) for g in groups.values() if g.get('result',{}).get('detail') is not None)
        for k in ('initial_engines','initial_advances','prefix_same_resumes','future_forks','future_resumes')}
    constructs=sum(g.get('result',{}).get('context_constructions',0) for g in groups.values())
    require(counts['initial_engines']<=48 and counts['future_forks']<=96 and counts['future_resumes']<=96 and constructs<=48,'execution_bounds')
    all_exact=exact==96 and gexact==48 and constructs==48 and counts['initial_engines']==counts['initial_advances']==48 and counts['future_forks']==counts['future_resumes']==96
    write(output/'receipt.json',{'schema':SCHEMA,'status':'exact_full96_future_suffixes' if all_exact else 'completed_unknowns_preserved',
        'exact_rows':exact,'unknown_rows':96-exact,'exact_groups':gexact,'unknown_groups':48-gexact,'context_constructions':constructs,'counts':counts,
        'plan':ref(output/'plan.json'),'rows':ref(output/'rows.json'),'groups':ref(output/'groups.json'),
        'entry_pins':ref(output/'entry_pins.json'),'exit_pins':ref(output/'exit_pins.json'),
        'loaded_entry':ref(output/'loaded_entry.json'),'loaded_exit':ref(output/'loaded_exit.json'),'source_changed':[],
        'worker_seconds':time.perf_counter()-started,'native_calls':0,'hidden_state_coverage':False,'online_protection_certified':False})


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
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan');a=p.parse_args();output=a.output.resolve()
    if a.prepare:prepare(output);return 0
    if a.worker:
        require(a.expected_plan and sys.stdin.readline()==a.expected_plan+'\n','owned_admission')
        try:worker(output,a.expected_plan)
        except BaseException:write(output/'worker_failure.json',{'status':'unknown_worker_failure','error':traceback.format_exc()});raise
        return 0
    require(a.execute,'explicit_action');return execute(output,a.expected_plan)


if __name__=='__main__':raise SystemExit(main())
