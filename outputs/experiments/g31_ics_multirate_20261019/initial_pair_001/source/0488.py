"""Independent saved24 reader. No producer imports, prediction or native call.

Source ordering is distinguishable from runtime I/O evidence: the producer did
not persist target-read timestamps or its intermediate ledger versions. This
reader verifies the frozen source ordering, not an invented temporal journal.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import argparse
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import traceback
import xml.etree.ElementTree as ET
from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
PRODUCER = OUT/'scoped_public_inputs_six_cost_prepare_001'
PURE = OUT/'scoped_inputs_saved_pure_001'
MODULE = 'scripts.experiments.g31_ics_circulation.review_scoped_public_inputs_saved'
TEST = 'tests/test_g31_circulation_scoped_inputs_saved.py'
PRODUCER_MODULE = ROOT/'scripts/experiments/g31_ics_circulation/measure_scoped_public_inputs_six.py'
PLAN_SHA = 'd4c69fe70c5c6bd567677f9a04c2b024b47f1a6e25a9e671a932ef8e938b6d04'
REPORT_SHA = 'f6c8c0ebda0a87d727196bd9afffda795b0267fd492a6e9679ea5a3204fd0f55'
MEASURE_SHA = '11e31125715adfb83f9f3501949adcdb7c5bb9d26597832e456902ae1f2d2b0a'
ORDER = ('mechanism/vector_00', 'mechanism/vector_25', 'no_overlap/vector_00',
    'no_overlap/vector_25', 'insufficient_advance/vector_00', 'insufficient_advance/vector_17')
METADATA = ('plan.json','report.json','receipt.json','ledger.json','bounded_execution.json',
    'external_application_wall.json','entry_pins.json','exit_pins.json',
    'loaded_sources_entry.json','loaded_sources_exit.json')
LIMIT = 120.
MAX_RAW = 128*1024*1024
SCHEMA = 'g31.scoped_inputs.saved24_independent.v1'


def require(value, reason):
    if not value: raise ValueError('scoped_inputs_saved:'+reason)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path): return {'path': str(Path(path).resolve()), 'sha256': sha(path)}
def finite(v): return type(v) in (int, float) and math.isfinite(v) and v >= 0


def pairs(values):
    value = {}
    for key, item in values:
        require(key not in value, 'duplicate_JSON_key'); value[key] = item
    return value


def loads(data):
    value = json.loads(data, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_JSON')))
    require(exact(value,value), 'not_finite_JSON'); return value


def read(path): return loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x',encoding='utf8') as stream:
        stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')


def exact(a,b):
    if type(a) is not type(b): return False
    if type(a) is dict:
        return all(type(k) is str for k in a) and list(a)==list(b) and all(exact(a[k],b[k]) for k in a)
    if type(a) is list: return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b,strict=True))
    if type(a) is float: return math.isfinite(a) and math.isfinite(b) and a.hex()==b.hex()
    require(type(a) in (str,int,bool,type(None)), 'non_builtin_JSON'); return a==b


def declaration(): return [{'key':k,'arm':arm,'position':i} for k in ORDER for i,arm in enumerate('ABBA')]


def source_order_proof(source):
    """Frozen AST/source observation, not a saved runtime read-event trace."""
    syntax=ast.parse(source)
    worker=next(n for n in syntax.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    call=next(n for n in ast.walk(worker) if isinstance(n,ast.Assign)
        and ast.unparse(n.targets[0])=='prediction')
    require(ast.unparse(call.value)=="function(context, public['action'])", 'prediction_inputs')
    candidates=[n for n in ast.walk(worker) if isinstance(n,ast.Try)
        and any(isinstance(x,ast.Assign) and ast.unparse(x.targets[0])=='target' for x in n.body)]
    require(len(candidates)==1,'unique_sample_scope'); body=candidates[0].body
    def index(text):
        matches=[i for i,n in enumerate(body) if ast.unparse(n)==text]
        require(len(matches)==1,'source_statement:'+text); return matches[0]
    saved=index('path.write_bytes(gzip.compress(encoded, compresslevel=1, mtime=0))')
    target=index("target = gzip.decompress(Path(row['comparison_only_saved_prediction']['path']).read_bytes())")
    sample=next(i for i,n in enumerate(body) if call in list(ast.walk(n)))
    ledger=index("write(output / 'ledger.json', ledger)")
    require(sample<saved<ledger<target,'source_save_before_target')
    update=body[saved+1]
    require(isinstance(update,ast.Expr) and isinstance(update.value,ast.Call)
        and any(k.arg=='status' and isinstance(k.value,ast.Constant) and k.value.value=='returned_audit_pending'
            for k in update.value.keywords),'saved_pending_status')
    require(not any(isinstance(n,ast.Constant) and n.value=='comparison_only_saved_prediction'
        for statement in body[:target] for n in ast.walk(statement)), 'preprediction_target_read')
    return {'source_save_and_pending_write_before_target_read':True,
        'prediction_arguments_only_supplied_context_and_action':True,
        'independent_runtime_target_read_order_proved':False,
        'limitation':'No persisted target-read timestamp/journal or intermediate ledger version; source-order proof only.'}


def row_clock(row, previous=None):
    require(all(type(row[k]) is int and row[k]>=0 for k in ('started_ns','finished_ns','elapsed_ns')), 'sample_clock_type')
    require(row['finished_ns']>=row['started_ns'] and row['elapsed_ns']==row['finished_ns']-row['started_ns'], 'sample_elapsed')
    if 'export_ns' in row: require(type(row['export_ns']) is int and row['export_ns']>=0,'export_clock')
    if previous is not None:
        require(row['started_ns']>=previous['finished_ns']+previous.get('export_ns',0),'sample_export_chronology')


def summarize(ledger):
    require(type(ledger) is list and len(ledger)==24,'sample_denominator')
    require(all(exact({k:r[k] for k in ('key','arm','position')},d)
        for r,d in zip(ledger,declaration(),strict=True)), 'ABBA_order')
    states={'unknown_unexecuted','unknown_setup_error','unknown_in_progress','unknown_error',
        'returned_audit_pending','exact_full_prediction'}
    previous=None; attempted=0; exact_count=0
    for row in ledger:
        require(row['status'] in states,'unknown_status')
        clocks=[k in row for k in ('started_ns','finished_ns','elapsed_ns')]
        require(all(clocks) or not any(clocks),'partial_clock_tuple')
        if all(clocks): row_clock(row,previous); previous=row; attempted+=1
        if row['status']=='exact_full_prediction':
            require(all(clocks) and 'raw' in row and 'export_ns' in row,'exact_without_complete_record');exact_count+=1
    summary={};paired={};negative=[]
    if exact_count==24:
        values={a:[r['elapsed_ns']/1e6 for r in ledger if r['arm']==a] for a in 'AB'}
        require(all(len(v)==12 for v in values.values()),'arm_denominator')
        summary={a:{'count':len(v),'min':min(v),'median':statistics.median(v),'max':max(v),'sum':sum(v)} for a,v in values.items()}
        paired={k:{a:statistics.median([r['elapsed_ns']/1e6 for r in ledger if r['key']==k and r['arm']==a]) for a in 'AB'} for k in ORDER}
        negative=[k for k,p in paired.items() if p['B']>=p['A']]
    return {'exact':exact_count,'unknown':24-exact_count,'observed_completed_call_clocks':attempted,
        'summary_ms':summary,'paired_median_ms':paired,'negative_or_equal_cases':negative}


def compare_prediction(saved,target,expected_collections):
    a,b=loads(saved),loads(target)
    require(saved==target and exact(a,b),'complete_prediction_changed')
    require(type(a) is dict and exact(a['projected_collections'],expected_collections),'collection_chronology')
    return {'full_bytes_exact':True,'full_ordered_types_floathex_exact':True,'chronology_exact':True}


def metadata_check(plan,report,receipt,bounded,outer):
    require(plan['order']==list(ORDER) and exact(plan['declaration'],declaration())
        and plan['maximum_model_calls']==24 and plan['hard_application_seconds']==LIMIT
        and plan['default_GC_required'] is True,'producer_fixed_scope')
    require(report['status'] in ('passed_fixed_six_ABBA24_complete_prediction','unknowns_preserved')
        and receipt['status']==report['status'] and report['GC_enabled'] is True
        and report['source_changed']==receipt['source_changed']==[]
        and report['native_calls']==report['C_extension_loads']==0
        and report['complete_request100ms_certified'] is False
        and report['all_method_setup_and_state_filtering_costed'] is False,'producer_report_scope')
    require(type(report['model_calls']) is int and 0<=report['model_calls']<=24,'model_call_bound')
    require(type(report['setup']) is list and [x['key'] for x in report['setup']]==list(ORDER),'setup_denominator')
    for item in report['setup']:
        require(item['status'] in ('initial_context_prepared','unknown_setup_error'),'setup_status')
        if item['status']=='initial_context_prepared':require(finite(item['seconds']),'setup_clock')
    p=bounded['process']
    require(bounded['status']=='completed' and p['status']=='exited' and type(p['exitcode']) is int
        and p['exitcode']==0 and type(p['pid']) is int and p['pid']>0
        and p['windows_job_kill_on_close'] is p['child_released_only_after_job_assignment'] is True,'owned_process')
    clocks=(report['worker_seconds'],p['wall_seconds'],bounded['whole_python_before_receipt_seconds'],outer['whole_python_application_seconds'])
    require(all(finite(v) for v in clocks) and list(clocks)==sorted(clocks) and clocks[-1]<=LIMIT
        and finite(p['hard_timeout_seconds']) and p['wall_seconds']<=p['hard_timeout_seconds']<=LIMIT
        and bounded['shared_limit_seconds']==LIMIT,'whole_clock')
    require(outer['status']=='application_exited_zero' and type(outer['exit_code']) is int and outer['exit_code']==0
        and outer['error'] is None and outer['evidence_unchanged'] is True
        and outer['whole_python_within_120_seconds'] is True and outer['shared_owned_seconds']==LIMIT
        and outer['plan_sha256']==PLAN_SHA and outer['python_sha256']==plan['environment']['sha256']
        and outer['fixed_inputs']==6 and outer['model_calls']==24
        and outer['C_extension_loads']==outer['native_simulation_calls']==0
        and outer['complete_native_request_100ms_certified'] is False,'external_terminal')
    expected=[plan['environment']['python'],'-m','scripts.experiments.g31_ics_circulation.measure_scoped_public_inputs_six',
        '--worker','--output',str(PRODUCER),'--expected-plan',PLAN_SHA]
    require(bounded['command']==expected,'producer_command')


def check_saved_sources(folder,plan,entry,exit,loaded_entry,loaded_exit):
    expected={}
    for path,digest in plan['source_sha256'].items():
        for p in (Path(path),folder/plan['source_archive'][path]):
            require(sha(p)==digest,'producer_source_changed');expected[str(p)]=digest
    for path,digest in plan['evidence_sha256'].items():
        require(sha(path)==digest,'producer_evidence_changed');expected[path]=digest
    require(exact(entry,expected) and exact(exit,expected),'producer_saved_entry_exit')
    require(type(loaded_entry) is dict and type(loaded_exit) is dict and loaded_entry
        and all(loaded_exit.get(p)==d for p,d in loaded_entry.items()),'loaded_entry_exit')
    for p,d in loaded_exit.items():require(plan['source_sha256'].get(p)==d,'loaded_source_outside_frozen_domain')
    return {'sources':len(plan['source_sha256']),'evidence_files':len(plan['evidence_sha256']),
        'loaded_entry':len(loaded_entry),'loaded_exit':len(loaded_exit)}


def uncompress(reference):
    path=Path(reference['path']);require(ref(path)==reference,'gzip_identity')
    require(path.stat().st_size<=MAX_RAW,'compressed_bound')
    with gzip.open(path,'rb') as stream:data=stream.read(MAX_RAW+1)
    require(len(data)<=MAX_RAW,'uncompressed_bound');return data


def no_execution_modules():
    require(not any('czr005_circulation' in k or '_g31_complete_tree_normalizer' in k for k in sys.modules),'execution_extension_loaded')
    require('scripts.experiments.g31_ics_circulation.public_live_obligation_scoped_inputs' not in sys.modules,'producer_model_imported')


def pure_gate():
    receipt=read(PURE/'receipt.json');rows=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[] and receipt['tests']==len(rows)
        and len(rows)>0 and receipt['XML_sha256']==sha(PURE/'tests.xml')
        and not any(x.tag in ('failure','error','skipped') for row in rows for x in row),'focused_pure')
    return receipt


def own_files():
    from . import initial_owner_route_image as image
    files=image.source_closure(ROOT,(MODULE,TEST[:-3].replace('/','.'),
        'scripts.experiments.g31_ics_circulation.run_scoped_inputs_saved_pure'))
    plan=read(PRODUCER/'plan.json')
    for path,digest in plan['source_sha256'].items():
        data=Path(path).read_bytes();require(hashlib.sha256(data).hexdigest()==digest,'prepare_producer_source')
        files[str(Path(path).relative_to(ROOT))]=data
    return files


def prepare(output):
    no_execution_modules();pure=pure_gate()
    require(sha(PRODUCER/'plan.json')==PLAN_SHA and sha(PRODUCER/'report.json')==REPORT_SHA
        and sha(PRODUCER_MODULE)==MEASURE_SHA,'fixed_producer_metadata')
    proof=source_order_proof(PRODUCER_MODULE.read_text(encoding='utf8'))
    output.mkdir(exist_ok=False);files=own_files();pins={};archives={}
    for rel,data in files.items():
        target=output/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        pins[str(ROOT/rel)]=hashlib.sha256(data).hexdigest();archives[str(ROOT/rel)]=str(target.relative_to(output))
    for rel,d in pure['source_sha256'].items(): require(pins.get(str(ROOT/rel))==d,'tested_auditor_source')
    outer=read(PRODUCER/'external_application_wall.json')
    # Wrapper file discovered from the explicit reviewed naming, never raw data.
    wrapper=OUT/'user_resume_20261015_001/invoke_scoped_inputs_six_cost_root_001_measured.ps1'
    require(sha(wrapper)==outer['wrapper_sha256'],'external_wrapper')
    metadata={str(PRODUCER/name):sha(PRODUCER/name) for name in METADATA}
    metadata.update({str(p):sha(p) for p in (wrapper,PURE/'receipt.json',PURE/'tests.xml')})
    ledger=read(PRODUCER/'ledger.json');producer=read(PRODUCER/'plan.json')
    plan={'schema':SCHEMA,'status':'prepared_unexecuted','hard_application_seconds':LIMIT,
        'source_sha256':pins,'source_archive':archives,'producer_metadata_sha256':metadata,
        'published_raw':[r['raw'] for r in ledger if 'raw' in r],
        'targets':[producer['rows'][k]['comparison_only_saved_prediction'] for k in ORDER],
        'source_order_proof':proof,'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'scope':'All24 saved complete predictions versus all6 original targets; no predictor/engine/alias graph regeneration.',
        'preparation_raw_reads':0,'native_calls':0,'model_calls':0,'C_loads':0,'performance_runs':0,
        'cost_basis':'Producer whole11.595s with24 model calls; readback omits calls. Fixed120 includes source/input hash,30 decompressions, complete comparisons and own shutdown; no runtime guarantee.',
        'cleanup_limit':'Default GC producer observation retained. Sample ends at prediction return; scope-cycle reclamation may occur later. No complete-request100ms inference.'}
    write(output/'plan.json',plan)
    write(output/'preparation.json',{'status':'prepared_source_review_pending','plan':ref(output/'plan.json'),
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def own_pins(output,plan):
    values={}
    for p,d in plan['source_sha256'].items():
        for path in (Path(p),output/plan['source_archive'][p]):
            values[str(path)]=sha(path);require(values[str(path)]==d,'auditor_source')
    for p,d in plan['producer_metadata_sha256'].items():values[p]=sha(p);require(values[p]==d,'producer_metadata')
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'auditor_interpreter')
    return values


def loaded_own(plan):
    no_execution_modules();values={}
    for name,module in sorted(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file:continue
        p=Path(file).resolve()
        if p.is_relative_to(ROOT):
            require(p.suffix=='.py' and plan['source_sha256'].get(str(p))==sha(p),'auditor_loaded')
            values[name]={'path':str(p),'sha256':sha(p)}
    return values


def worker(output,expected):
    require(sha(output/'plan.json')==expected,'auditor_plan');plan=read(output/'plan.json')
    require(plan['schema']==SCHEMA and plan['hard_application_seconds']==LIMIT,'auditor_scope')
    entry=own_pins(output,plan);loaded_entry=loaded_own(plan);write(output/'entry_pins.json',entry)
    producer=read(PRODUCER/'plan.json');report=read(PRODUCER/'report.json');receipt=read(PRODUCER/'receipt.json')
    ledger=read(PRODUCER/'ledger.json');outer=read(PRODUCER/'external_application_wall.json')
    metadata_check(producer,report,receipt,read(PRODUCER/'bounded_execution.json'),outer)
    require(receipt['report']==ref(PRODUCER/'report.json') and receipt['plan']==ref(PRODUCER/'plan.json')
        and report['ledger']==ref(PRODUCER/'ledger.json'),'producer_references')
    source_counts=check_saved_sources(PRODUCER,producer,*[read(PRODUCER/n) for n in
        ('entry_pins.json','exit_pins.json','loaded_sources_entry.json','loaded_sources_exit.json')])
    computed=summarize(ledger)
    for key in ('exact','unknown','summary_ms','paired_median_ms','negative_or_equal_cases'):
        require(exact(computed[key],report[key]),'saved_summary:'+key)
    require(receipt['exact']==computed['exact'] and receipt['unknown']==computed['unknown'],'receipt_counts')
    require((report['status']=='passed_fixed_six_ABBA24_complete_prediction')==(computed['exact']==24),'exact_status')
    targets={};target_errors={};public_inputs=[]
    for k in ORDER:
        row=producer['rows'][k]
        try:targets[k]=uncompress(row['comparison_only_saved_prediction'])
        except Exception as exc:target_errors[k]=repr(exc)
        require(ref(row['input']['path'])==row['input'],'public_input_identity')
        supplied=read(row['input']['path'])
        require(type(supplied) is dict and set(supplied)=={'initial_owners','action'}
            and type(supplied['initial_owners']) is dict and set(supplied['initial_owners'])=={'A','B'}
            and exact(supplied['action'],row['action']),'supplied_input_shape_or_action')
        public_inputs.append({'key':k,'minimal_input_shape_verified':True,'dynamic_guard_reexecuted':False})
    checks=[]
    for index,row in enumerate(ledger):
        if 'raw' not in row:
            checks.append({'index':index,'key':row['key'],'status':row['status'],'comparison':'unknown_missing_saved_raw'});continue
        require(Path(row['raw']['path']).resolve()==PRODUCER/'raw'/f'{index:03d}.json.gz','sample_path')
        try:
            require(row['key'] not in target_errors,'target_decode:'+target_errors.get(row['key'],''))
            check=compare_prediction(uncompress(row['raw']),targets[row['key']],producer['rows'][row['key']]['expected_collections'])
            checks.append({'index':index,'key':row['key'],'status':row['status'],**check})
        except Exception as exc:
            checks.append({'index':index,'key':row['key'],'status':'invalid_saved_comparison','error':repr(exc)})
    invalid=[x for x in checks if x['status']=='invalid_saved_comparison']
    write(output/'comparison_rows.json',checks)
    require(not invalid,'one_or_more_saved_predictions_invalid')
    require(report['model_calls']>=computed['observed_completed_call_clocks'],'reported_model_call_count')
    require(source_order_proof(PRODUCER_MODULE.read_text(encoding='utf8'))==plan['source_order_proof'],'source_order_changed')
    exit=own_pins(output,plan);require(entry==exit,'auditor_source_exit');loaded_exit=loaded_own(plan)
    write(output/'exit_pins.json',exit)
    require(all(loaded_exit.get(k)==v for k,v in loaded_entry.items()),'auditor_loaded_drift')
    result={'schema':SCHEMA,'status':'passed_saved24' if computed['exact']==24 else 'verified_saved_unknown_denominator',
        **computed,'comparisons':checks,'public_inputs':public_inputs,'producer_source_counts':source_counts,
        'loaded_sources_entry':loaded_entry,'loaded_sources_exit':loaded_exit,'source_changed':[],
        'source_order_proof':plan['source_order_proof'],'producer_whole_seconds':outer['whole_python_application_seconds'],
        'producer_gc_observation':report['GC_enabled'],'sample_cleanup_certified':False,
        'complete_request100ms_certified':False,'native_calls':0,'model_calls':0,'performance_runs':0,
        'elapsed_before_report_seconds':time.monotonic()-BOOT}
    write(output/'report.json',result);write(output/'receipt.json',{'status':result['status'],'report':ref(output/'report.json'),
        'plan':ref(output/'plan.json'),'source_changed':[],'native_calls':0,'model_calls':0})


def remaining(elapsed):
    require(finite(elapsed),'elapsed');value=LIMIT-elapsed-1.
    if value<=0:raise TimeoutError('scoped_inputs_saved:before_worker')
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true')
    p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan');a=p.parse_args();output=a.output.resolve()
    no_execution_modules()
    if a.prepare:prepare(output);return 0
    if a.worker:
        require(sys.stdin.readline()==a.expected_plan+'\n','owned_admission')
        try:worker(output,a.expected_plan)
        except BaseException:
            write(output/'failure.json',{'status':'unknown_failed_audit','error':traceback.format_exc()});raise
        return 0
    require(a.execute and sha(output/'plan.json')==a.expected_plan,'explicit_reviewed_execute')
    with (output/'execution_claim').open('x'):pass
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',a.expected_plan]
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        process=bounded_windows_job.run(command,timeout=remaining(time.monotonic()-BOOT),stdout=out,stderr=err,
            admission=a.expected_plan,cwd=ROOT)
    elapsed=time.monotonic()-BOOT
    passed=process['status']=='exited' and process['exitcode']==0 and elapsed<=LIMIT
    write(output/'bounded_execution.json',{'status':'completed' if passed else 'unknown_failed_or_timeout',
        'process':process,'command':command,'whole_python_before_receipt_seconds':elapsed,'shared_limit_seconds':LIMIT})
    return 0 if passed and time.monotonic()-BOOT<=LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
