"""Fresh scoped-input96 conformance with unchanged original worker checks.

The model facade takes only the original context/action. Every returned complete
prediction is saved before the original worker can inspect future targets. Early
files have invocation ordinals, not guessed branch keys; only a complete96 run
can bind all ordinals to the fixed order. No native or request100ms claim.
"""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
import copy
import gc
import gzip
import hashlib
import json
from pathlib import Path
import sys
import traceback
from types import FunctionType,SimpleNamespace
import xml.etree.ElementTree as ET
from . import bounded_windows_job,initial_owner_route_image as image
from . import validate_live_communication_projection as original
from . import public_live_obligation_scoped_inputs as candidate
from . import review_scoped_public_inputs_saved as strict

ROOT,OUT,ORDER=original.ROOT,original.OUT,original.ORDER
OLD=OUT/'live_communication_lazy_prepare_001'
SCOPED=OUT/'scoped_public_inputs_six_cost_prepare_001'
PURE=OUT/'live_communication_scoped_inputs_pure_001'
MODULE='scripts.experiments.g31_ics_circulation.validate_live_communication_scoped_inputs'
TEST='tests/test_g31_circulation_live_communication_scoped_inputs.py'
PURE_MODULE='scripts.experiments.g31_ics_circulation.run_live_communication_scoped_inputs_pure'
OLD_PLAN='afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497'
OLD_ROWS='7753bc2c9731ded83300435814f5b9c033197237cbaaa0c33721fe09c1a74a3e'
SCOPED_PLAN='d4c69fe70c5c6bd567677f9a04c2b024b47f1a6e25a9e671a932ef8e938b6d04'
SCHEMA='g31.live_communication_scoped_inputs_conformance.v1'
LIMIT=360.
PURE_COUNT=53
sha,read,ref=original.sha,original.read,original.reference


def require(value,reason):
    if not value:raise ValueError('scoped96:'+reason)


def write(path,value):
    with Path(path).open('x',encoding='utf8') as stream:stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')


def no_execution_extensions():
    require(not any('czr005_circulation' in k or '_g31_complete_tree_normalizer' in k for k in sys.modules),'forbidden_extension')


class SaveBeforeReturn:
    """Data-only original predictor wrapper, exact invocation denominator."""
    def __init__(self,output,predict):
        self.output=Path(output);self.predict=predict;self.records=[];self.journal_errors=[]
        (self.output/'early_predictions').mkdir(exist_ok=False)
        self.journal=(self.output/'early_prediction_events.jsonl').open('xb')

    def append(self,event):
        data=json.dumps(event,allow_nan=False).encode()+b'\n'
        require(self.journal.write(data)==len(data),'journal_short_write');self.journal.flush()

    def __call__(self,context,action):
        require(len(self.records)<96,'maximum_model_calls')
        require(gc.isenabled(),'default_GC_disabled')
        ordinal=len(self.records);record={'ordinal':ordinal,'status':'unknown_in_progress',
            'started_ns':time.perf_counter_ns(),'input_action':copy.deepcopy(action)}
        self.records.append(record)
        try:
            self.append({'event':'attempt_started','ordinal':ordinal,'at_ns':record['started_ns']})
            value=self.predict(context,action)
            record['predict_returned_ns']=time.perf_counter_ns()
            encoded=json.dumps(value,allow_nan=False).encode()
            path=self.output/'early_predictions'/f'{ordinal:03d}.json.gz'
            with path.open('xb') as stream:
                data=gzip.compress(encoded,compresslevel=1,mtime=0)
                require(stream.write(data)==len(data),'prediction_short_write')
            require(gc.isenabled(),'default_GC_disabled')
            record.update(status='complete_prediction_saved_before_return',prediction=ref(path),
                full_json_sha256=hashlib.sha256(encoded).hexdigest(),full_json_bytes=len(encoded),
                saved_ns=time.perf_counter_ns())
            self.append({'event':'prediction_saved_before_return',**record})
            return value
        except BaseException as error:
            record.update(status='unknown_prediction_or_export_error',error_type=type(error).__name__,
                error=str(error),failed_ns=time.perf_counter_ns())
            try:self.append({'event':'attempt_failed',**record})
            except BaseException as journal_error:self.journal_errors.append(repr(journal_error))
            raise

    def close(self):self.journal.close()


def bind_worker(saver):
    facade=SimpleNamespace(physics=original.model.physics,predict=saver)
    namespace={**original.worker.__globals__,'model':facade}
    function=FunctionType(original.worker.__code__,namespace,original.worker.__name__,
        original.worker.__defaults__,original.worker.__closure__)
    function.__kwdefaults__=original.worker.__kwdefaults__
    require(function.__code__ is original.worker.__code__ and function.__closure__ is original.worker.__closure__
        and function.__defaults__ is original.worker.__defaults__ and function.__kwdefaults__ is original.worker.__kwdefaults__
        and set(namespace)==set(original.worker.__globals__)
        and all(namespace[k] is v for k,v in original.worker.__globals__.items() if k!='model'),
        'worker_only_model_facade')
    return function


def source_proof():
    sentinel=lambda *args:None
    worker=bind_worker(sentinel)
    require(candidate.predict.__code__.co_names==('PublicInputScope','predict'),'fresh_candidate_scope')
    return {'same_worker_code_defaults_closure_and_all_other_globals':True,
        'model_physics_identity_unchanged':worker.__globals__['model'].physics is original.model.physics,
        'model_predict_is_only_facade_replacement':worker.__globals__['model'].predict is sentinel,
        'candidate_fresh_scope_each_call':True,
        'early_save_has_no_target_argument':True,'ordinal_to_branch_only_after_complete96':True,
        'original_dynamic_initial_later_and_history_guards_retained':True,
        'native_calls':0,'online_authority':False}


def early_inventory(records,events):
    require(type(records) is list and len(records)<=96,'early_count')
    require([r['ordinal'] for r in records]==list(range(len(records))),'early_ordinal_order')
    expected=[];last=-1
    for row in records:
        start=row['started_ns'];require(type(start) is int and start>=last>=-1,'early_clock')
        expected.append({'event':'attempt_started','ordinal':row['ordinal'],'at_ns':start})
        if row['status']=='complete_prediction_saved_before_return':
            require(all(type(row[k]) is int and row[k]>=0 for k in ('predict_returned_ns','saved_ns','full_json_bytes'))
                and start<=row['predict_returned_ns']<=row['saved_ns'],'save_clock')
            expected.append({'event':'prediction_saved_before_return',**row});last=row['saved_ns']
        elif row['status']=='unknown_prediction_or_export_error':
            require(type(row['failed_ns']) is int and row['failed_ns']>=start,'failed_clock')
            expected.append({'event':'attempt_failed',**row});last=row['failed_ns']
        else:raise ValueError('scoped96:unfinished_early_record')
    require(strict.exact(events,expected),'early_journal_binding')
    return len(records)


def mapping_allowed(receipt,rows,records):
    return (receipt.get('status')=='exact_all96_conformance' and receipt.get('model_evaluations')==96
        and receipt.get('actual_collection_data_checks')==226 and receipt.get('actual_known_collection_data')==192
        and receipt.get('complete_actual_collection_conformance') is True and list(rows)==ORDER
        and all(r.get('status')=='exact_conformance' for r in rows.values()) and len(records)==96
        and all(r.get('status')=='complete_prediction_saved_before_return' for r in records))


def exact_predictions(first,second):
    a,b=gzip.decompress(first),gzip.decompress(second)
    require(a==b and strict.exact(strict.loads(a),strict.loads(b)),'full_prediction_bytes_type_order_floathex')
    return a


def run_original(saver,output,expected):
    """Keep an original failure primary even if evidence finalization fails."""
    primary=None;cleanup=[]
    try:return bind_worker(saver)(output,expected)
    except BaseException as error:
        primary=error;raise
    finally:
        try:saver.close()
        except BaseException as error:
            cleanup.append(error);saver.journal_errors.append('close:'+repr(error))
        try:write(output/'early_prediction_inventory.json',{'records':saver.records,'journal_errors':saver.journal_errors})
        except BaseException as error:cleanup.append(error)
        if primary is None and cleanup:raise cleanup[0]


def source_union():
    files=image.source_closure(ROOT,(MODULE,PURE_MODULE,TEST[:-3].replace('/','.')))
    for folder,expected,count in ((OLD,OLD_PLAN,100),(SCOPED,SCOPED_PLAN,151)):
        require(sha(folder/'plan.json')==expected,'prior_plan')
        plan=read(folder/'plan.json');require(len(plan['source_sha256'])==count,'prior_source_count')
        for path,digest in plan['source_sha256'].items():
            require(sha(path)==digest==sha(folder/plan['source_archive'][path]),'prior_source_or_archive')
            files[str(Path(path).relative_to(ROOT)).replace('\\','/')]=Path(path).read_bytes()
    return files


def pure_gate():
    receipt=read(PURE/'receipt.json');rows=ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(receipt['status']=='passed' and receipt['source_changed']==[] and len(rows)==receipt['tests']
        and len(rows)==PURE_COUNT>0 and receipt['XML_sha256']==sha(PURE/'tests.xml')
        and not any(x.tag in ('failure','error','skipped') for row in rows for x in row),'focused_pure')
    return receipt


def prepare(output):
    no_execution_extensions();pure=pure_gate();files=source_union()
    require(sha(OLD/'rows.json')==OLD_ROWS,'old96_rows')
    previous=read(OLD/'plan.json');oldrows=read(OLD/'rows.json');oldreceipt=read(OLD/'receipt.json')
    require(list(oldrows)==ORDER and len(oldrows)==96 and all(r['status']=='exact_conformance' for r in oldrows.values())
        and oldreceipt['status']=='exact_all96_conformance','closed_old96')
    output.mkdir(exist_ok=False);pins={};archives={}
    for name,data in files.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        pins[str(ROOT/name)]=hashlib.sha256(data).hexdigest();archives[str(ROOT/name)]=str(path.relative_to(output))
    for name,digest in pure['source_sha256'].items():require(pins[str(ROOT/name)]==digest,'tested_source')
    fixed=dict(previous['fixed_evidence_sha256'])
    for folder,names in ((OLD,('plan.json','rows.json','receipt.json','final_receipt.json','bounded_execution.json','external_application_wall.json')),
        (SCOPED,('plan.json','receipt.json','report.json','external_application_wall.json')),
        (PURE,('receipt.json','tests.xml'))):
        for name in names:fixed[str(folder/name)]=sha(folder/name)
    oldpredictions={k:oldrows[k]['prediction'] for k in ORDER}
    for refvalue in oldpredictions.values():fixed[refvalue['path']]=refvalue['sha256']
    for row in previous['rows'].values():fixed[row['actual_raw']['path']]=row['actual_raw']['sha256']
    for folder in (OLD,SCOPED):
        prior=read(folder/'plan.json')
        for path,digest in prior['source_sha256'].items():fixed[str(folder/prior['source_archive'][path])]=digest
    inherited=copy.deepcopy(previous)
    inherited.pop('saved73_equivalence')
    plan={**inherited,'schema':SCHEMA,'hard_timeout_seconds':LIMIT,
        'model_variant':'fresh_scoped_public_inputs_per_prediction',
        'complete_gate_requires':['receipt.json exact_all96_conformance',
            'equivalence96.json 96 exact_full_old_prediction',
            'final_receipt.json exact_all96_original_checks_and_full_outputs',
            'bounded_execution.json bounded_worker_completed within shared360'],
        'source_sha256':pins,'source_archive':archives,'fixed_evidence_sha256':fixed,
        'old96_predictions':oldpredictions,'old96_source_count':100,'scoped_source_count':151,
        'source_proof':source_proof(),'environment':{'python':sys.executable,'sha256':sha(sys.executable)},
        'rules':[r for r in previous['rules'] if 'saved73 complete-output' not in r]+[
            'Original complete worker code/globals and every initial/future-target guard retained; only private model facade changes.',
            'Each candidate.predict creates a fresh PublicInputScope. No global input/result/observation cache.',
            'Returned complete prediction gzip/hash/journal written before return to original worker; this cost is inside old model span.',
            'Invocation ordinal is bound to fixedORDER only if original receipt96/226/192 and all96 returned early records are complete.',
            'All96 early/late/full old output bytes, ordered types, floathex and chronology must agree; partial failure remains unknown.',
            'No ABBA/full-request100ms conclusion; model_wall includes early-save overhead. DefaultGC and whole process cleanup retained.'],
        'budget':{**previous['budget'],'fixed_application_seconds':LIMIT,
            'basis':'Original fixed96 lazy conformance whole about100s; new candidate scope cuts six-case component cost but early-save adds work.360 remains failure bound, not guarantee.'},
        'prediction_saved_before_target_validation':True,'preparation_model_calls':0,'preparation_raw_decodes':0}
    write(output/'plan.json',plan);write(output/'rows.json',copy.deepcopy(plan['rows']))
    write(output/'ready.json',{'status':'prepared_source_review_pending','plan':ref(output/'plan.json'),
        'source_count':len(pins),'fixed_application_seconds':LIMIT,'native_calls':0,'model_calls':0,
        'execute_command':[sys.executable,'-m',MODULE,'--execute','--output',str(output),'--expected-plan',sha(output/'plan.json')]})


def loaded_sources(plan):
    no_execution_extensions();values={}
    for name,module in sorted(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve()
        if path.is_relative_to(ROOT):
            require(path.suffix=='.py' and plan['source_sha256'].get(str(path))==sha(path),'loaded_source:'+name)
            values[name]={'path':str(path),'sha256':sha(path)}
    return values


def worker(output,expected):
    require(sha(output/'plan.json')==expected,'plan');plan=read(output/'plan.json')
    require(plan['schema']==SCHEMA and plan['hard_timeout_seconds']==LIMIT and plan['maximum_model_evaluations']==96
        and plan['source_proof']==source_proof() and gc.isenabled(),'closed_scope')
    require(plan['environment']=={'python':sys.executable,'sha256':sha(sys.executable)},'interpreter');pure_gate()
    loaded_entry=loaded_sources(plan);write(output/'loaded_sources_entry.json',loaded_entry)
    saver=SaveBeforeReturn(output,candidate.predict)
    run_original(saver,output,expected)
    require(not saver.journal_errors,'journal_failure')
    events=[strict.loads(line) for line in (output/'early_prediction_events.jsonl').read_bytes().splitlines()]
    early_inventory(saver.records,events)
    rows=read(output/'rows.json');receipt=read(output/'receipt.json')
    require(list(rows)==ORDER and len(rows)==96,'new96_denominator')
    mapped=mapping_allowed(receipt,rows,saver.records);comparisons={}
    for index,key in enumerate(ORDER):
        current=rows[key].get('prediction');old=plan['old96_predictions'][key]
        result={'status':'unknown_missing_new_prediction','old':old,'new':current,'early_ordinal_bound':mapped}
        try:
            require(type(current) is dict and ref(current['path'])==current,'new_prediction_identity')
            require(ref(old['path'])==old,'old_prediction_identity')
            newbytes=Path(current['path']).read_bytes();oldbytes=Path(old['path']).read_bytes()
            decoded=exact_predictions(newbytes,oldbytes);value=strict.loads(decoded)
            require(strict.exact(original.projected_collection_rows(value),rows[key]['projected_collection_rows'])
                and strict.exact(rows[key]['projected_collection_rows'],rows[key]['actual_collection_rows']), 'all_information_chronology')
            if mapped:
                early=saver.records[index];require(ref(early['prediction']['path'])==early['prediction'],'early_identity')
                require(strict.exact(early['input_action'],plan['rows'][key]['action']),'early_action_binding')
                earlydecoded=exact_predictions(Path(early['prediction']['path']).read_bytes(),newbytes)
                require(hashlib.sha256(earlydecoded).hexdigest()==early['full_json_sha256']
                    and len(earlydecoded)==early['full_json_bytes'],'early_json_identity')
            result.update(status='exact_full_old_prediction',full_bytes_type_order_floathex_exact=True,chronology_exact=True)
        except Exception:result.update(status='unknown_comparison_error',error=traceback.format_exc())
        comparisons[key]=result
    write(output/'equivalence96.json',comparisons)
    entry=read(output/'entry_pins.json');exit={p:sha(p) for p in entry};require(entry==exit,'source_raw_final_exit')
    loaded_exit=loaded_sources(plan);require(all(loaded_exit.get(k)==v for k,v in loaded_entry.items()),'loaded_source_drift')
    require(gc.isenabled(),'default_GC_disabled');write(output/'final_exit_pins.json',exit);write(output/'loaded_sources_exit.json',loaded_exit)
    exact=sum(r['status']=='exact_full_old_prediction' for r in comparisons.values())
    final={'schema':SCHEMA,'status':'exact_all96_original_checks_and_full_outputs' if mapped and exact==96 else 'completed_unknowns_or_differences_preserved',
        'model_receipt':ref(output/'receipt.json'),'rows':ref(output/'rows.json'),'equivalence96':ref(output/'equivalence96.json'),
        'early_inventory':ref(output/'early_prediction_inventory.json'),'early_events':ref(output/'early_prediction_events.jsonl'),
        'early_invocations':len(saver.records),'early_ordinal_mapping_certified':mapped,
        'early_unbound_invocations':0 if mapped else len(saver.records),
        'full_output_exact':exact,'unknown_or_difference':96-exact,'all_original_checks':receipt['status'],
        'actual_collection_data_checks':receipt['actual_collection_data_checks'],'actual_known_collection_data':receipt['actual_known_collection_data'],
        'new_counts':receipt['counts'],'source_changed':[],'GC_enabled':True,'native_calls':0,
        'modelspan_includes_early_full_export_hash_journal':True,'sample_cleanup_certified':False,
        'complete_request_100ms_certified':False,'online_executable':False,'old_raw_future_values_only_offline_targets':True}
    write(output/'final_receipt.json',final)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--execute',action='store_true');p.add_argument('--worker',action='store_true');p.add_argument('--expected-plan')
    a=p.parse_args();output=a.output.resolve();no_execution_extensions()
    if a.prepare:prepare(output);return 0
    if a.worker:
        require(sys.stdin.readline()==a.expected_plan+'\n','owned_admission')
        try:worker(output,a.expected_plan)
        except BaseException:write(output/'worker_failure.json',{'status':'unknown_worker_failure','error':traceback.format_exc()});raise
        return 0
    require(a.execute and sha(output/'plan.json')==a.expected_plan,'reviewed_execute')
    with (output/'execution_claim').open('x'):pass
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output),'--expected-plan',a.expected_plan]
    remaining=LIMIT-(time.monotonic()-BOOT)-1.;require(remaining>0,'before_worker_budget')
    with (output/'stdout.log').open('x') as out,(output/'stderr.log').open('x') as err:
        process=bounded_windows_job.run(command,timeout=remaining,stdout=out,stderr=err,admission=a.expected_plan,cwd=ROOT)
    wall=time.monotonic()-BOOT;passed=process['status']=='exited' and process['exitcode']==0 and wall<=LIMIT
    write(output/'bounded_execution.json',{'status':'bounded_worker_completed' if passed else 'unknown_failed_or_timeout',
        'process':process,'command':command,'application_seconds_before_receipt':wall,'fixed_application_seconds':LIMIT,
        'plan_sha256':a.expected_plan,'source':ref(__file__),
        'final_receipt':ref(output/'final_receipt.json') if (output/'final_receipt.json').exists() else None,
        'external_python_launch_through_exit_required':True,'native_calls':0})
    return 0 if passed and time.monotonic()-BOOT<=LIMIT else 1


if __name__=='__main__':raise SystemExit(main())
