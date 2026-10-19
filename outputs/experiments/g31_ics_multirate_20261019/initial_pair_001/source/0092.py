"""Independent saved-only partial96 audit. Never predicts or calls native."""
from __future__ import annotations
import time
BOOT=time.monotonic()
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys
import traceback
from . import bounded_windows_job
from . import diagnose_live_communication_conformance as comparison

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
SOURCE=OUT/'live_communication_conformance_prepare_002'
EXPECTED={'bounded_execution.json':'77f7afc19212b9fcb39cd916b3eb2c95c172225429fa400fc8a2698b9f6fcab4',
    'rows.json':'11831be39a3a225a2fde2489a797fb71313485d1c75c1b0719d665215c431397',
    'external_application_wall.json':'76787446c51c08b327adc8fa9f5441cc9bc68eaac27beddffac58d111eb20502',
    'plan.json':'029d5c97114651e348a2b66a4c3509e5d4bd10f5bbdd576cf738620100c2d08f'}
LIMIT=180.
MODULE='scripts.experiments.g31_ics_circulation.diagnose_live_communication_partial'
sha,read,ref,require,write=(getattr(comparison,k) for k in ('sha','read','ref','require','write'))


def classify(rows):
    require(list(rows)==comparison.ORDER and len(rows)==96,'partial96_order')
    known=[k for k,r in rows.items() if r['status']=='exact_conformance']
    unknown=[k for k,r in rows.items() if r['status']!='exact_conformance']
    return known,unknown


def cost_summary(rows,whole_seconds):
    values=[r['model_wall_seconds'] for r in rows.values() if 'model_wall_seconds' in r]
    require(values and all(type(v) is float and v>=0 for v in values),'saved_model_costs')
    total=sum(values);other=whole_seconds-total
    require(other>=0,'model_cost_within_application')
    return {'saved_model_calls':len(values),'saved_model_seconds':total,'median_model_seconds':statistics.median(values),
        'min_model_seconds':min(values),'max_model_seconds':max(values),'whole_python_seconds':whole_seconds,
        'unpartitioned_seconds':other,
        'unpartitioned_scope':'Imports, hashes, actual data guard replay, gzip/JSON and output, plus any in-flight74th work. No exclusive per-stage attribution.',
        'linear_full96_seconds':whole_seconds*96/len(values),
        'conservative_observed_max_model_plus_scaled_residual_seconds':max(values)*96+other*96/len(values),
        'estimate_limits':'Descriptive extrapolations, not timing guarantees or completed-request100ms results.',
        'minimum_32_model_seconds_at_observed_min':32*min(values)}


def worker(output):
    started=time.perf_counter()
    # Imported only inside the owned child. No call to model.predict/Projection.
    from . import validate_live_communication_projection as verifier
    from . import live_obligation_delivered_context as context
    metadata={name:ref(SOURCE/name) for name in (*EXPECTED,'entry_pins.json')}
    require(all(metadata[n]['sha256']==d for n,d in EXPECTED.items()),'partial_terminal_binding')
    require(not (SOURCE/'receipt.json').exists() and not (SOURCE/'exit_pins.json').exists(),'missing_finalization_preserved')
    bounded=read(SOURCE/'bounded_execution.json');external=read(SOURCE/'external_application_wall.json')
    require(bounded['process']['status']=='hard_timeout' and bounded['status']=='unknown_failed_or_budget_exceeded'
        and external['exit_code']==1 and bounded['worker_receipt'] is None,'actual_timeout')
    plan=read(SOURCE/'plan.json');rows=read(SOURCE/'rows.json');known,unknown=classify(rows)
    require(known==comparison.ORDER[:73] and unknown==comparison.ORDER[73:],'actual73_prefix')
    pins={**plan['source_sha256'],**plan['fixed_evidence_sha256']}
    for p,d in plan['source_sha256'].items():pins[str(SOURCE/plan['source_archive'][p])]=d
    require(read(SOURCE/'entry_pins.json')==pins,'producer_entry_pin_ledger')
    original=verifier.ACTUAL;original_plan=read(original/'preregistered_protocol.json')
    require(len(original_plan['source_sha256'])==93,'original93_domain')
    for p,d in original_plan['source_sha256'].items():
        pins[p]=d;pins[str(original/original_plan['source_archive'][p])]=d
    auditor={str(Path(m.__file__).resolve()):sha(m.__file__) for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).suffix=='.py' and Path(m.__file__).resolve().is_relative_to(ROOT)}
    test=ROOT/'tests/test_g31_circulation_live_communication_partial.py'
    auditor[str(test)]=sha(test)
    xml=OUT/'live_communication_partial_pure_001.xml';auditor[str(xml)]=sha(xml)
    pins.update(auditor);entry={p:sha(p) for p in pins};require(entry==pins,'independent_current_archive_entry')
    write(output/'entry_pins.json',entry)
    checks={};context_count=0;known_context_count=0;prediction_pins={}
    for index,key in enumerate(known):
        saved=rows[key];require(saved['execution_index']==index,'partial_execution_order')
        prediction=saved['prediction'];prediction_pins[prediction['path']]=prediction['sha256']
        require(sha(prediction['path'])==prediction['sha256'],'partial_prediction_hash')
        projected=json.loads(gzip.decompress(Path(prediction['path']).read_bytes()))
        rawref=plan['rows'][key]['actual_raw'];require(sha(rawref['path'])==rawref['sha256'],'partial_actual_hash')
        raw=json.loads(gzip.decompress(Path(rawref['path']).read_bytes()))
        require(raw['specification']['case']==key.split('/')[0] and
            comparison.exact(raw['specification']['vector'],plan['rows'][key]['action']),'partial_case_action')
        contexts={owner:context.initial_context(**verifier.public_initial(raw,owner)) for owner in ('A','B')}
        require(all(type(v) is context.SuppliedContext for v in contexts.values()),'partial_actual_initial_guard')
        future=[]
        for owner in ('A','B'):
            for attempt in raw['collection_attempts'][owner]:
                rebuilt=verifier.future_context(raw,owner,attempt)
                valid=type(rebuilt) is context.SuppliedContext
                require(valid==(attempt['information'].get('native_delivery_verified') is True),'partial_later_guard_replay')
                future.append({'owner':owner,'at':attempt['at'],'known':valid,'matches_saved':True})
        require(comparison.exact(future,saved['actual_collection_contexts']),'partial_context_rows')
        context_count+=len(future);known_context_count+=sum(v['known'] for v in future)
        actual_rows=verifier.actual_collection_rows(raw);projected_rows=verifier.projected_collection_rows(projected)
        require(comparison.exact(actual_rows,saved['actual_collection_rows']) and
            comparison.exact(projected_rows,saved['projected_collection_rows']) and
            comparison.exact(projected_rows,actual_rows),'partial_chronology_exact')
        actual=raw['summary']['completion']
        require(comparison.exact(actual,saved['actual_completion']) and
            comparison.exact(projected.get('completion'),saved.get('predicted_completion')) and
            verifier.exact_completion(projected.get('completion'),actual) and
            projected['status']==saved['predictor_status']=='conditional_prediction','partial_five_endpoints_exact')
        checks[key]={'status':'saved_exact_rechecked','prediction':prediction,'actual':rawref,
            'five_endpoints_exact':True,'chronology_exact':True,'initial_owner_checks':2,'actual_attempts':len(future),
            'actual_known_attempts':sum(v['known'] for v in future),'completion':actual,
            'model_wall_seconds':saved['model_wall_seconds'],'projection_event_count':projected.get('event_count')}
        write(output/'checked_rows.json',checks)
    for key in unknown:
        checks[key]={'status':'unknown_not_closed','producer_label':rows[key]['status'],
            'reason':'No committed row result. The first missing row may have been in flight; absence is not proof of never started.'}
    exitpins={p:sha(p) for p in pins};require(exitpins==entry,'independent_current_archive_exit')
    require(all(sha(p)==d for p,d in prediction_pins.items()),'prediction_exit_hash')
    require(all(sha(SOURCE/n)==r['sha256'] for n,r in metadata.items()) and
        not (SOURCE/'receipt.json').exists() and not (SOURCE/'exit_pins.json').exists(),'terminal_artifacts_unchanged')
    write(output/'exit_pins.json',exitpins)
    artifact_paths={str(p.resolve()) for case in comparison.CASES for p in (SOURCE/case).glob('*.json.gz')}
    extra=sorted(artifact_paths-set(prediction_pins))
    report={'schema':'g31.live_communication.partial_saved_review.v1','status':'partial73_rechecked_full96_unknown',
        'producer_status':'hard_timeout_preserved','producer_process_exitcode':bounded['process']['exitcode'],
        'producer_application_exitcode':external['exit_code'],'producer_final_receipt':'missing_not_created',
        'producer_exit_pin_proof':'missing_unknown_even_if_independent_current_hashes_match',
        'producer_metadata':metadata,'all96_rows':checks,'saved_exact_count':len(known),'not_closed_count':len(unknown),
        'first_not_closed':unknown[0],'first_not_closed_may_have_been_in_flight':True,
        'uncommitted_prediction_artifacts':extra,'initial_owner_guard_checks':2*len(known),
        'actual_later_guard_checks':context_count,'actual_known_attempts':known_context_count,
        'independent_entry_pins':ref(output/'entry_pins.json'),'independent_exit_pins':ref(output/'exit_pins.json'),
        'original93_current_and_archive_match':True,'producer96_current_and_archive_match':True,
        'new_native_calls':0,'new_model_evaluations':0,'source':ref(__file__),
        'costs':cost_summary(rows,external['whole_python_application_seconds']),
        'full96_conformance':False,'product100ms_certified':False,
        'wall_seconds':time.perf_counter()-started}
    write(output/'report.json',report)
    small={k:report[k] for k in ('status','producer_status','saved_exact_count','not_closed_count','first_not_closed',
        'first_not_closed_may_have_been_in_flight','uncommitted_prediction_artifacts','initial_owner_guard_checks',
        'actual_later_guard_checks','actual_known_attempts','original93_current_and_archive_match',
        'producer96_current_and_archive_match','new_native_calls','new_model_evaluations','costs','full96_conformance',
        'product100ms_certified','wall_seconds')}
    write(output/'summary.json',{**small,'report':ref(output/'report.json')});print(json.dumps(small))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--worker',action='store_true')
    p.add_argument('--execute',action='store_true');args=p.parse_args();output=args.output.resolve()
    if args.worker:
        require(sys.stdin.readline()=='partial73\n','partial_job_admission')
        try:worker(output)
        except BaseException:
            write(output/'failure.json',{'status':'partial_audit_failed','error':traceback.format_exc()});raise
        return 0
    require(args.execute,'explicit_partial_action');output.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,'-m',MODULE,'--worker','--output',str(output)]
    with (output/'stdout.log').open('x',encoding='utf8') as out,(output/'stderr.log').open('x',encoding='utf8') as err:
        remaining=LIMIT-(time.monotonic()-BOOT)-1
        require(remaining>0,'partial_budget_before_worker')
        result=bounded_windows_job.run(command,timeout=remaining,admission='partial73',stdout=out,stderr=err,cwd=str(ROOT))
    elapsed=time.monotonic()-BOOT
    write(output/'bounded_execution.json',{'status':'completed' if result['status']=='exited' and result['exitcode']==0 and elapsed<LIMIT else 'unknown',
        'process':result,'command':command,'fixed_application_seconds':LIMIT,'application_seconds_before_receipt':elapsed,
        'report':ref(output/'report.json') if (output/'report.json').exists() else None,'new_native_calls':0,'new_model_evaluations':0})
    return 0 if result['status']=='exited' and result['exitcode']==0 and time.monotonic()-BOOT<LIMIT else 1

if __name__=='__main__':raise SystemExit(main())
