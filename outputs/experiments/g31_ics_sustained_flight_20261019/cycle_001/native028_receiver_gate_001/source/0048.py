"""Nine-constructor finite receiver gate. Prepare/verify never execute native."""
from __future__ import annotations
import sys
if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv or sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission')+1]:
        raise SystemExit('native028_gate:missing_job_admission')
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import secrets
import traceback
from . import bounded_windows_job
from . import native028_receiver_fixture as fixture
from .foundation_airport_campaign import source_dependency_closure

ROOT=Path(__file__).resolve().parents[3]
MODULE='scripts.experiments.g31_ics_circulation.native028_receiver_gate'
SCHEMA='g31.native028_receiver_admission_gate.v1'
OLD_SHA='845486b745bc6e65a9988d1ef5429336b60fd472eb73c39e133e19ec93a7e7be'
INVALID={'negative':-1,'capacity':4,'fraction':1.5,'boolean':True}
ARMS={'native027':{'default':None},'native028':{'default':None,'explicit_zero':0,'reserve1':1,'reserve2':2}}

def require(value,reason):
    if not value:raise ValueError('native028_gate:'+reason)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    path=Path(path)
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes())
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,indent=2,allow_nan=False).encode()
    if path.suffix=='.gz':data=gzip.compress(data,compresslevel=1,mtime=0)
    with path.open('xb')as stream:stream.write(data)
def source_pins():
    return {str(path):sha(path) for path in sorted(set(source_dependency_closure(roots=(MODULE,)).values()))}


def build_pins(receipt,binary):
    receipt=Path(receipt).resolve();binary=Path(binary).resolve();data=read(receipt)
    require(data['schema']=='g31.circulation.receiver_admission_build_only.v1'
        and data['status']=='build_passed_tests_held' and not data['source_changed']
        and data['source_before']==data['source_after'] and not data['ctest_executed']
        and not data['native_session_executed'],'closed_build')
    require(data['binary_sha256'].get(str(binary))==sha(binary),'built_binary')
    pins={str(receipt):sha(receipt),str(binary):sha(binary)}
    builder=receipt.parent/'build_native_receiver_admission.py'
    require(builder.is_file() and sha(builder)==sha(Path(__file__).with_name(builder.name)),'build_script_archive')
    pins[str(builder)]=sha(builder)
    for relative,digest in data['source_after'].items():
        part=Path(relative)
        require(not part.is_absolute() and '..'not in part.parts,'build_archive_path')
        path=receipt.parent/'source'/part
        require(sha(path)==digest,'build_archive_bytes')
        pins[str(path)]=digest
    for path,digest in data['binary_sha256'].items():
        require(sha(path)==digest,'built_outputs');pins[path]=digest
    return pins


def prepare(directory,old_binary,binary,build_receipt):
    directory=Path(directory).resolve()
    require(directory.is_relative_to(ROOT) and not directory.exists(),'fresh_output')
    require(sha(old_binary)==OLD_SHA,'historical027_binary')
    pins=source_pins();built=build_pins(build_receipt,binary)
    directory.mkdir(parents=True)
    input_refs={}
    values={**ARMS['native028'],**{'invalid_'+k:v for k,v in INVALID.items()}}
    for case,value in values.items():
        path=directory/'inputs'/(case+'.json.gz');write(path,fixture.scene(value));input_refs[case]=ref(path)
    archives={}
    for index,(path,digest)in enumerate(pins.items()):
        target=directory/'source'/f'{index:04d}.py';target.parent.mkdir(exist_ok=True)
        target.write_bytes(Path(path).read_bytes());archives[path]=str(target.relative_to(directory))
    plan={'schema':SCHEMA,'output':str(directory),'status':'prepared_not_executed','arms':ARMS,
        'invalid_values':INVALID,'maximum_native_constructor_attempts':9,'native_session_fork_count':0,
        'arm_attempt_limits':{'native027':1,'native028':8},'arm_timeout_seconds':60,
        'automatic_retries':0,'maximum_parallel_workers':1,
        'old_binary':ref(old_binary),'binary':ref(binary),'build_receipt':ref(build_receipt),
        'build_pins':built,'source_sha256':pins,'source_archive':archives,
        'inputs':input_refs,
        'interpreter':ref(sys.executable),'policy_version':fixture.POLICY,
        'legacy44plus21_reexecuted':False,'complete_request_100ms_certified':False}
    write(directory/'plan.json',plan);check_plan(directory,plan)
    return plan


def check_plan(directory,plan,*,current_sources=True):
    directory=Path(directory).resolve()
    require(plan['schema']==SCHEMA and plan['arms']==ARMS and plan['invalid_values']==INVALID
        and plan['maximum_native_constructor_attempts']==9 and plan['arm_attempt_limits']=={'native027':1,'native028':8}
        and plan['arm_timeout_seconds']==60 and plan['automatic_retries']==0,'fixed_fixture_domain')
    for key in ('old_binary','binary','build_receipt','interpreter'):
        require(ref(plan[key]['path'])==plan[key],'reference:'+key)
    require(plan['old_binary']['sha256']==OLD_SHA,'old_binary_identity')
    values={**ARMS['native028'],**{'invalid_'+k:v for k,v in INVALID.items()}}
    require(set(plan['inputs'])==set(values),'input_domain')
    for case,value in values.items():
        path=directory/'inputs'/(case+'.json.gz')
        require(ref(path)==plan['inputs'][case] and read(path)==fixture.scene(value),'input_binding:'+case)
    require(build_pins(plan['build_receipt']['path'],plan['binary']['path'])==plan['build_pins'],'compiled_closure')
    require(set(plan['source_sha256'])==set(plan['source_archive']),'source_domain')
    if current_sources:require(source_pins()==plan['source_sha256'],'source_pins')
    for path,digest in plan['source_sha256'].items():
        archived=(directory/plan['source_archive'][path]).resolve()
        require(archived.is_relative_to(directory/'source') and sha(archived)==digest,'source_archive')


def worker(directory,arm,plan_sha):
    from .native_host import load_native
    directory=Path(directory);plan=read(directory/'plan.json');attempts=0
    result={'status':'failed','arm':arm,'plan_sha256':plan_sha,'raw':{},'invalid':{},'constructor_attempts':0}
    try:
        require(sha(directory/'plan.json')==plan_sha,'plan_binding');check_plan(directory,plan)
        native=load_native(plan['old_binary'if arm=='native027'else'binary']['path'])
        result['native_binary']=copy.deepcopy(native._g31_native_artifact_identity)
        for case,reserve in ARMS[arm].items():
            attempts+=1
            require(attempts<=plan['arm_attempt_limits'][arm],'constructor_budget')
            row=fixture.run(native,reserve,restore=case=='reserve1')
            require(row['input']==read(plan['inputs'][case]['path']),'executed_input')
            path=directory/arm/(case+'.json.gz');write(path,row);result['raw'][case]=ref(path)
            fixture.validate(row,reserve)
        if arm=='native028':
            for case,value in INVALID.items():
                attempts+=1
                require(attempts<=plan['arm_attempt_limits'][arm],'constructor_budget')
                error=None
                try:native.NativeSession(fixture.scene(value))
                except (ValueError,RuntimeError,TypeError)as exc:error={'type':type(exc).__name__,'message':str(exc)}
                result['invalid'][case]={'value':value,'exception':error}
                require(error is not None and 'invalid_receiver_transit_reserve'in error['message'],'invalid_value_accepted:'+case)
        check_plan(directory,plan);require(sha(directory/'plan.json')==plan_sha,'exit_plan_binding')
        result['status']='all_declared_fixtures_executed'
    except Exception:result['exception']=traceback.format_exc()
    result['constructor_attempts']=attempts;write(directory/arm/'completion.json',result)
    return result


def validate_saved(directory,*,require_receipt=True):
    directory=Path(directory);plan=read(directory/'plan.json');check_plan(directory,plan)
    rows={};evidence={str(directory/'plan.json'):sha(directory/'plan.json')}
    evidence.update(plan['build_pins']);evidence.update(plan['source_sha256'])
    evidence[plan['old_binary']['path']]=OLD_SHA;evidence[plan['interpreter']['path']]=plan['interpreter']['sha256']
    for item in plan['inputs'].values():evidence[item['path']]=item['sha256']
    for source,archive in plan['source_archive'].items():evidence[str(directory/archive)]=plan['source_sha256'][source]
    results={}
    for arm,cases in ARMS.items():
        process=read(directory/(arm+'.process.json'));completion=read(directory/arm/'completion.json')
        require(process['status']=='exited' and process['exitcode']==0,'arm_process:'+arm)
        require(completion['status']=='all_declared_fixtures_executed'
            and completion['constructor_attempts']==plan['arm_attempt_limits'][arm]
            and completion['plan_sha256']==sha(directory/'plan.json') and set(completion['raw'])==set(cases),'complete_arm:'+arm)
        binary=plan['old_binary'if arm=='native027'else'binary']
        require(completion['native_binary']=={'resolved_path':binary['path'],'sha256':binary['sha256']},'executed_binary')
        for path in (directory/(arm+'.process.json'),directory/arm/'completion.json'):evidence[str(path)]=sha(path)
        rows[arm]={};results[arm]={}
        for case,reserve in cases.items():
            path=directory/arm/(case+'.json.gz');require(ref(path)==completion['raw'][case],'raw_identity')
            row=read(path);rows[arm][case]=row;results[arm][case]=fixture.validate(row,reserve);evidence[str(path)]=sha(path)
        if arm=='native028':
            require(set(completion['invalid'])==set(INVALID),'invalid_domain')
            for case,value in INVALID.items():
                row=completion['invalid'][case]
                require(type(row['value'])is type(value) and row['value']==value
                    and row['exception'] is not None and 'invalid_receiver_transit_reserve'in row['exception']['message'],'invalid_rejection')
    require(fixture.stable(rows['native027']['default'])==fixture.stable(rows['native028']['default']),'default027_exact_parity')
    zero=copy.deepcopy(rows['native028']['explicit_zero']);zero['input']=fixture.scene()
    require(fixture.stable(zero)==fixture.stable(rows['native028']['default']),'explicit_zero_semantic_parity')
    seals=[rows['native028'][case]['initial_seal']for case in ('default','reserve1','reserve2')]
    digests=[results['native028'][case]['static_contract_sha256']for case in ('default','reserve1','reserve2')]
    require(len(set(seals))==len(set(digests))==3,'nonzero_policy_digest_binding')
    result={'schema':SCHEMA,'status':'validated_native028_finite_receiver_admission',
        'plan_sha256':sha(directory/'plan.json'),'native_constructor_attempts':9,
        'binary':plan['binary'],'build_receipt':plan['build_receipt'],'evidence_sha256':evidence,
        'default027_exact_parity':True,'policy_version':fixture.POLICY,
        'legacy44plus21_reexecuted':False,'complete_request_100ms_certified':False,
        'global_deadlock_freedom_established':False}
    if require_receipt:require(read(directory/'receipt.json')==result,'receipt_recomputed')
    return result


def launch(directory):
    directory=Path(directory);plan=read(directory/'plan.json');check_plan(directory,plan)
    write(directory/'launch.json',{'plan':ref(directory/'plan.json'),'maximum_native_constructor_attempts':9,'automatic_retries':0})
    for arm in ARMS:
        (directory/arm).mkdir(exist_ok=False);admission=secrets.token_hex(24)
        with (directory/(arm+'.stdout.log')).open('x')as stdout,(directory/(arm+'.stderr.log')).open('x')as stderr:
            process=bounded_windows_job.run([sys.executable,'-m',MODULE,'--worker','--output',str(directory),
                '--arm',arm,'--plan-sha256',sha(directory/'plan.json'),'--admission',admission],
                timeout=60,stdout=stdout,stderr=stderr,admission=admission,cwd=ROOT)
        write(directory/(arm+'.process.json'),process)
        require(process['status']=='exited' and process['exitcode']==0,'worker_failed:'+arm)
    result=validate_saved(directory,require_receipt=False);write(directory/'receipt.json',result);return result


def main():
    sys.path.insert(0,str(ROOT/'src'))
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    for mode in ('prepare','launch','verify','worker','accept'):modes.add_argument('--'+mode,action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    for name in ('old-binary','binary','build-receipt'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--arm',choices=ARMS);parser.add_argument('--plan-sha256');parser.add_argument('--admission')
    parser.add_argument('--contract-output',type=Path)
    args=parser.parse_args()
    if args.prepare:result=prepare(args.output,args.old_binary,args.binary,args.build_receipt)
    elif args.launch:result=launch(args.output)
    elif args.verify:result=validate_saved(args.output)
    elif args.accept:
        from .native028_run_acceptance import accept
        result=accept(args.output,args.contract_output)
    else:result=worker(args.output,args.arm,args.plan_sha256)
    print(json.dumps({k:result[k]for k in ('status','native_constructor_attempts','constructor_attempts')if k in result}))
    return 1 if result.get('status')=='failed'else 0
if __name__=='__main__':raise SystemExit(main())
