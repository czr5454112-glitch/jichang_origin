"""Fixed saved18 complete C publisher attribution, not request performance.

The accepted complete publisher is unchanged. cProfile encloses fresh mock
root construction through append/return. Every full result is saved before
comparison; all old source/toolchain/runtime/input checks remain in owned120.
"""
import time
BOOT=time.monotonic()
import argparse,cProfile,gc,gzip,hashlib,json,pstats,sys,traceback
from pathlib import Path
from . import measure_complete_root_c_normalizer as base

ROOT,OUT=base.ROOT,base.OUT
MODULE='scripts.experiments.g31_ics_circulation.profile_complete_c_publisher_saved18'
PURE_MODULE='scripts.experiments.g31_ics_circulation.run_complete_c_publisher_profile_pure'
TEST='tests/test_g31_circulation_complete_c_publisher_profile.py'
REFERENCE=OUT/'C_publisher_pair_prepare_001'
REFERENCE_SHA='840329a5c7eaf928f92b7c6d9a4bbfaf08bdf12260141e41f2863746e2df4072'
LIMIT=120.
SCHEMA='g31.complete_C_publisher.saved18_profile.v1'
require,sha,read,write=base.require,base.sha,base.read,base.write


def profile_call(record,method,publish,root_factory):
    profiler=cProfile.Profile();start=time.perf_counter_ns()
    profiler.enable()
    try:
        root=root_factory(record,method);holder=[];result=publish(root,holder)
        require(len(holder)==1 and holder[0] is result,'profile_append_identity')
    finally:profiler.disable()
    end=time.perf_counter_ns()
    return result,profiler,start,end


def profile_rows(profiler):
    stats=pstats.Stats(profiler)
    rows=[]
    for (filename,line,function),(primitive,total,self_seconds,cumulative,callers) in stats.stats.items():
        rows.append(dict(filename=filename,line=line,function=function,primitive_calls=primitive,
            total_calls=total,self_seconds=self_seconds,cumulative_seconds=cumulative))
    return sorted(rows,key=lambda r:(-r['self_seconds'],r['filename'],r['line'],r['function']))


def validate_inventory(rows,order):
    require(type(rows) is list and len(rows)==18 and [r['key'] for r in rows]==order,'profile_fixed18')
    require(all(r['status']=='exact_profiled' for r in rows),'profile_unknowns_retained')
    require(all(type(r['started_ns']) is int and type(r['finished_ns']) is int
        and 0<=r['started_ns']<=r['finished_ns'] and type(r['elapsed_ns']) is int
        and r['elapsed_ns']==r['finished_ns']-r['started_ns'] for r in rows),'profile_clocks')
    require(all(a['finished_ns']<=b['started_ns'] for a,b in zip(rows,rows[1:])),'profile_serial_clocks')
    return {'fixed_roots':18,'profiled_publishers':18,'exact':18,'unknown':0}


def source_files():
    files=base.source_files()
    files.update(base.image.source_closure(ROOT,(MODULE,PURE_MODULE,TEST[:-3].replace('/','.'))))
    return dict(sorted(files.items()))


def prepare(output,pure):
    require(sha(REFERENCE/'plan.json')==REFERENCE_SHA,'profile_reference_plan')
    receipt=read(pure/'receipt.json')
    require(receipt['status']=='passed' and receipt['tests']==8 and receipt['source_changed']==[],'profile_pure')
    require(receipt['XML_sha256']==sha(pure/'tests.xml'),'profile_pure_XML')
    files=source_files()
    require({str(ROOT/p):hashlib.sha256(b).hexdigest() for p,b in files.items()}==receipt['source_sha256'],'profile_tested_sources')
    original=read(REFERENCE/'plan.json');order=list(original['input_raw'])
    require(len(order)==18,'profile_original18')
    output.mkdir(exist_ok=False)
    for rel,data in files.items():
        path=output/'source'/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    plan={'schema':SCHEMA,'reference_plan_sha256':REFERENCE_SHA,'order':order,'hard_seconds':LIMIT,
        'source_sha256':receipt['source_sha256'],'sources':list(files),'pure':base.legacy.c.reference(pure/'receipt.json'),
        'pure_XML':base.legacy.c.reference(pure/'tests.xml'),'python':sys.executable,'python_sha256':sha(sys.executable),
        'profiled_publishers':18,'direct_support_preflight_publishers':18,'native_calls':0,'model_calls':0,
        'scope':'Original complete C publisher on all18 frozen entry-codec fixtures,16closed2unknown retained. All setup/C load/source6124toolchain/runtime/raw/direct18 support/full18profiles/output/readback/exit in120. Instrumented times only; cumulative overlaps, no uninstrumented gain or native100ms claim.'}
    write(output/'plan.json',plan)
    write(output/'ready.json',{'status':'prepared_unexecuted','plan_sha256':sha(output/'plan.json'),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def verify_pins(output,expected):
    require(sha(output/'plan.json')==expected,'profile_plan_pin');plan=read(output/'plan.json')
    require(plan['schema']==SCHEMA and plan['reference_plan_sha256']==REFERENCE_SHA
        and plan['hard_seconds']==LIMIT and plan['profiled_publishers']==plan['direct_support_preflight_publishers']==18,'profile_scope')
    require(sha(REFERENCE/'plan.json')==REFERENCE_SHA,'profile_original_plan')
    original=base.verify_pins(REFERENCE,REFERENCE_SHA)
    require(plan['order']==list(original['input_raw']),'profile_fixed_order')
    files=source_files()
    require(plan['sources']==list(files) and plan['source_sha256']=={str(ROOT/p):hashlib.sha256(b).hexdigest() for p,b in files.items()},'profile_sources')
    for rel in plan['sources']:require(sha(output/'source'/rel)==plan['source_sha256'][str(ROOT/rel)],'profile_archive')
    for key in ('pure','pure_XML'):require(sha(plan[key]['path'])==plan[key]['sha256'],'profile_pure_ref')
    require(plan['python']==sys.executable and plan['python_sha256']==sha(sys.executable),'profile_interpreter')
    return plan,{**original,'source_sha256':plan['source_sha256']}


def worker(output,expected):
    plan,loaded_plan=verify_pins(output,expected);require(gc.isenabled(),'profile_GC')
    rows=[{'key':key,'status':'unknown_unexecuted'} for key in plan['order']];write(output/'rows.json',rows)
    entry=base.loaded_sources(loaded_plan)
    try:
        provider=base.binding.provider
        source_expected={str(Path(m.__file__).resolve()):plan['source_sha256'][str(Path(m.__file__).resolve())]
            for m in (provider.original,provider.original.wire)}
        candidate=provider.load_candidate(loaded_plan['binary']['path'],loaded_plan['binary']['sha256'],source_expected)
        runtime=base.parity.loaded_runtime(loaded_plan);binding=base.binding.bind(candidate)
        method,publish=base.bindings('B',binding)
        inputs=base.load_inputs(loaded_plan);fingerprints={k:base.legacy._fixture_hash(v) for k,v in inputs.items()}
        support={k:base.direct_support(v,candidate) for k,v in inputs.items()}
        require(len(support)==18 and all(x['direct_C_supported'] and x['exact_and_new_owned_tree'] for x in support.values()),'profile_support18')
        write(output/'direct_support.json',support)
        for index,row in enumerate(rows):
            row['status']='unknown_in_progress';write(output/'rows.json',rows)
            result,profiler,start,end=profile_call(inputs[row['key']],method,publish,base.legacy.root_from_fixture)
            raw_path=output/f'{index:02d}.json.gz'
            with gzip.open(raw_path,'wt',encoding='utf8',compresslevel=1) as stream:
                json.dump(result,stream,ensure_ascii=False,allow_nan=False)
            row.update(status='saved_audit_pending',raw=base.legacy.c.reference(raw_path),started_ns=start,finished_ns=end,elapsed_ns=end-start)
            write(output/'rows.json',rows)
            profiler.dump_stats(str(output/f'{index:02d}.pstats'))
            write(output/f'{index:02d}.functions.json',profile_rows(profiler))
            base.mock.current_clock_bounds(result,start,end)
            require(base.legacy.candidate.single.exact_tree(base.mock.semantic_record(result),base.mock.semantic_record(inputs[row['key']])),'profile_complete_record')
            with gzip.open(raw_path,'rt',encoding='utf8') as stream:saved=json.load(stream,object_pairs_hook=base.image._pairs,parse_constant=base.image._constant)
            require(base.legacy.candidate.single.exact_tree(saved,result),'profile_saved_complete_bytes')
            row.update(status='exact_profiled',profile=base.legacy.c.reference(output/f'{index:02d}.pstats'),functions=base.legacy.c.reference(output/f'{index:02d}.functions.json'))
            write(output/'rows.json',rows)
            del result,saved,profiler
        counts=validate_inventory(rows,plan['order'])
        require(fingerprints=={k:base.legacy._fixture_hash(v) for k,v in inputs.items()},'profile_input_mutated')
        verify_pins(output,expected);exit_loaded=base.loaded_sources(loaded_plan)
        require(all(exit_loaded.get(k)==v for k,v in entry.items()) and gc.isenabled(),'profile_exit_state')
        write(output/'receipt.json',{'schema':SCHEMA,'status':'exact_all18_profiled_diagnostic','counts':counts,
            'rows':base.legacy.c.reference(output/'rows.json'),'runtime':runtime,'source_changed':[],
            'loaded_entry':entry,'loaded_exit':exit_loaded,'GC_enabled':True,'native_calls':0,'model_calls':0,
            'worker_seconds_before_receipt':time.monotonic()-BOOT,'scope':plan['scope']})
    except BaseException:
        write(output/'failure.json',{'status':'unknown_failure','error':traceback.format_exc()});write(output/'rows.json',rows);raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--pure',type=Path)
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan')
    a=p.parse_args();output=a.output.resolve()
    if a.prepare:prepare(output,a.pure.resolve());return 0
    if a.worker:
        require(sys.stdin.readline()==a.expected_plan+'\n','profile_admission');worker(output,a.expected_plan);return 0
    require(a.execute and sha(output/'plan.json')==a.expected_plan,'profile_execute')
    with (output/'execution_claim.json').open('x'):pass
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',a.expected_plan]
    remaining=LIMIT-(time.monotonic()-BOOT)-1;require(remaining>0,'profile_budget_before_worker')
    with (output/'stdout.log').open('x') as stdout,(output/'stderr.log').open('x') as stderr:
        process=base.bounded.run(command,timeout=remaining,stdout=stdout,stderr=stderr,admission=a.expected_plan,cwd=ROOT)
    elapsed=time.monotonic()-BOOT
    write(output/'bounded_execution.json',{'process':process,'shared_seconds':LIMIT,'elapsed_before_receipt':elapsed,'command':command})
    return 0 if process['status']=='exited' and process['exitcode']==0 and elapsed<=LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
