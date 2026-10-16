"""Retrospective current-capture conformance; never a policy outcome input."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import time
from . import public_native_later_preference_projection as model
from .validate_public_native_preference_projection import sha, imported_source_pins
from .public_owned_action_state import bind_supplied_bundle


def validate(audit_path):
    audit_path=Path(audit_path).resolve(); audit=json.loads(audit_path.read_bytes())
    assert audit['status']=='saved192_revalidated_no_new_native' and len(audit['rows'])==192
    sources=imported_source_pins(); pins={str(audit_path):sha(audit_path),**sources}
    rows={}; counts=Counter()
    for key,saved in audit['rows'].items():
        path=Path(saved['raw_artifact']);assert sha(path)==saved['raw_sha256'];pins[str(path)]=saved['raw_sha256']
        raw=json.loads(gzip.decompress(path.read_bytes()))
        decisions=[r for owner in ('A','B') for r in raw['decisions'][owner]]
        assert len(decisions)==2 and {r['phase'] for r in decisions}=={'first_return','first_reuse_route'}
        for decision in decisions:
            phase=decision['phase']; information=decision['information'];bundle=information.get('bundle',{})
            if bundle.get('status') == 'conditional_model_input':
                bundle = bind_supplied_bundle(bundle, information['raw_endpoints']['view'])
            action={name:saved['vector'][name] for name in ('return_delay','later_action')}
            # Exactly the current supplied public bundle + declared action.
            # Actual suffixes/completions are first read after predict returns.
            start=time.perf_counter();prediction=model.predict(bundle,action);elapsed=time.perf_counter()-start
            admitted=saved['status_retained']=='assessed' and information.get('native_delivery_verified') is True
            complete=prediction['status']=='conditional_prediction' and set(prediction['completion'])==model.contract.JOBS
            errors={job:prediction['completion'][job]-saved['completion'][job] for job in model.contract.JOBS} if complete else None
            projected=[(r['tray'],r.get('job') or '',r['source'],r['target'],r['at'])
                       for r in prediction.get('physical_projection',[]) if r['event']=='EDGE_ENTER']
            actual=[(r['tray_id'],r['business_bag_id'],r['from'],r['to'],r['time'])
                    for r in raw['result']['receipts'] if r['event']=='EDGE_ENTER' and r['time']>=decision['at']]
            row={'phase':phase,'now':decision['at'],'action':action,'native_status_retained':saved['status_retained'],
                 'source_input_verified':information.get('native_delivery_verified') is True,
                 'authority_valid_counterfactual_comparison':admitted,'unknown_promoted':False,
                 'prediction':prediction,'model_call_wall_seconds':elapsed,'prediction_minus_native_per_job':errors,
                 'all_five_completion_doubles_exact':complete and all(x==0 for x in errors.values()),
                 'all_ordered_future_edges_and_times_match':projected==actual,
                 'projected_future_edges':projected,'actual_future_edges':actual,'native_protection_certified':False}
            rows[key+'/'+phase]=row
            counts[phase,prediction['status']]+=1
            if admitted:
                counts[phase,'admitted_exact_completion:'+str(row['all_five_completion_doubles_exact'])]+=1
                counts[phase,'admitted_exact_future_edges:'+str(row['all_ordered_future_edges_and_times_match'])]+=1
            else: counts[phase,'unknown_native_comparison_retained']+=1
    assert all(sha(path)==value for path,value in pins.items()) and imported_source_pins()==sources
    return {'schema':'g31.public_native_later_preference_projection.validation.v1',
        'status':'retrospective384_source_capture_projection_comparisons_no_new_native','rows':rows,
        'counts':[{'phase':phase,'category':category,'count':count} for (phase,category),count in counts.items()],
        'pins':pins,'loaded_project_source_pins_before_and_after':sources,'native_executions':0,
        'projection_evaluations':len(rows),'used_for_semantic_debugging':True,'statistically_held_out':False,
        'online_method_execution':False,'native_protection_certified':False,
        'limits':['Current source-authored captures are inputs, subsequent physical outcomes are retrospective comparands.',
                  'Missing future collection/readiness cannot be promoted by a successful conditional point prediction.',
                  'Exact finite conformance does not prove unseen model-error bounds or strict native protection.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists();value=validate(args.audit)
    args.output.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(value['counts'],indent=2))


if __name__=='__main__':main()
