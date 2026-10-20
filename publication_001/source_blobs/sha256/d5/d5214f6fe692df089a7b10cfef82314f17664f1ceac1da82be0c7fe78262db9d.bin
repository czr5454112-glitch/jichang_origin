"""Saved-only diagnosis of a terminal fixed96 communication conformance run.

No predictor/native imports or execution. Existing receipts/statuses are never
rewritten. The producer's entry/exit pin ledger is checked as saved evidence;
this small diagnosis does not claim another complete source/native audit.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

JOBS=('loaded','receiver','reuse1','reuse2','blocker')
CASES=('mechanism','no_overlap','insufficient_advance')
ORDER=[case+f'/vector_{i:02d}' for case in CASES for i in range(32)]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def require(ok,why):
    if not ok:raise ValueError('communication_diagnosis:'+why)
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')

def exact(a,b):
    if type(a) is not type(b):return False
    if type(a) is float:return math.isfinite(a) and math.isfinite(b) and a.hex()==b.hex()
    if type(a) is dict:return list(a)==list(b) and all(exact(a[k],b[k]) for k in a)
    if type(a) is list:return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b,strict=True))
    return a==b

def first_difference(a,b,path=''):
    if type(a) is not type(b):return {'field':path,'reason':'scalar_or_container_type','projected':a,'actual':b}
    if type(a) is dict:
        if list(a)!=list(b):return {'field':path,'reason':'mapping_key_order','projected':list(a),'actual':list(b)}
        for key in a:
            difference=first_difference(a[key],b[key],path+'.'+key if path else key)
            if difference:return difference
    elif type(a) is list:
        for index in range(min(len(a),len(b))):
            difference=first_difference(a[index],b[index],f'{path}[{index}]')
            if difference:return difference
        if len(a)!=len(b):return {'field':path,'reason':'list_count','projected':len(a),'actual':len(b)}
    elif not exact(a,b):
        difference={'field':path,'reason':'exact_value','projected':a,'actual':b}
        if type(a) is float and type(b) is float:
            difference.update(projected_hex=a.hex(),actual_hex=b.hex(),delta=a-b)
        return difference
    return None

def diagnose(source,output,expected_receipt,expected_bounded):
    started=time.perf_counter();output.mkdir(parents=True,exist_ok=False)
    metadata={name:ref(source/name) for name in ('plan.json','rows.json','receipt.json','bounded_execution.json',
        'entry_pins.json','exit_pins.json')}
    require(metadata['receipt.json']['sha256']==expected_receipt and
        metadata['bounded_execution.json']['sha256']==expected_bounded,'terminal_identities')
    plan=read(source/'plan.json');rows=read(source/'rows.json');receipt=read(source/'receipt.json')
    bounded=read(source/'bounded_execution.json')
    require(bounded['process']['status']=='exited' and bounded['process']['exitcode']==0 and
        bounded['status']=='bounded_worker_completed','terminal_worker')
    require(plan['order']==ORDER and list(rows)==ORDER and len(rows)==96,'full96_order')
    require(receipt['rows']==metadata['rows.json'] and receipt['plan']==metadata['plan.json'] and
        receipt['entry_pins']==metadata['entry_pins.json'] and receipt['exit_pins']==metadata['exit_pins.json'] and
        bounded['worker_receipt']==metadata['receipt.json'],'receipt_bindings')
    pins={**plan['source_sha256'],**plan['fixed_evidence_sha256']}
    for path,digest in plan['source_sha256'].items():pins[str(source/plan['source_archive'][path])]=digest
    require(read(source/'entry_pins.json')==read(source/'exit_pins.json')==pins and receipt['source_changed']==[],
        'saved_producer_pin_ledgers')
    reports={};first_rows={};statuses=Counter();prediction_statuses=Counter();reasons=Counter();first_fields=Counter()
    for index,key in enumerate(ORDER):
        row=rows[key];require(row['execution_index']==index,'execution_order')
        statuses[row['status']]+=1
        value={'status':row['status'],'action':plan['rows'][key]['action'],'error':row.get('error'),
            'five_endpoints_exact':row.get('five_endpoints_exact'),
            'ordered_information_attempts_exact':row.get('ordered_information_attempts_exact'),
            'actual_collection_contexts':row.get('actual_collection_contexts',[]),
            'predictor_status':row.get('predictor_status'),'reasons':row.get('errors',[])}
        if 'prediction' in row:
            prediction=row['prediction'];require(sha(prediction['path'])==prediction['sha256'],'prediction_artifact')
            data=json.loads(gzip.decompress(Path(prediction['path']).read_bytes()))
            require(data['status']==row['predictor_status'] and exact(data.get('completion'),row.get('predicted_completion')),
                'prediction_row_binding')
            prediction_statuses[data['status']]+=1
            value['prediction']=prediction
            value['projected_collection_count']=len(row['projected_collection_rows'])
            value['actual_collection_count']=len(row['actual_collection_rows'])
            value['first_information_difference']=first_difference(row['projected_collection_rows'],row['actual_collection_rows'])
            completion=row.get('predicted_completion')
            value['completion_differences']={job:first_difference(completion.get(job),row['actual_completion'][job],job)
                for job in JOBS} if type(completion) is dict else {'missing_prediction':True}
            for reason in row.get('errors',[]):reasons[str(reason)]+=1
            for phase in data.get('unknown_information_phases',[]):
                for reason in (*phase.get('reasons',[]),*phase.get('bundle_reasons',[])):
                    reasons[str(reason)]+=1
            difference=value['first_information_difference']
            if difference:first_fields[difference['field']]+=1
        case=key.split('/')[0]
        if row['status']!='exact_conformance':first_rows.setdefault(case,{'key':key,'details':value})
        reports[key]=value
    require(dict(statuses)==receipt['counts'],'receipt_counts')
    require(all(sha(source/name)==reference['sha256'] for name,reference in metadata.items()),'terminal_metadata_changed')
    report={'schema':'g31.live_communication.saved_diagnosis.v1','status':'saved_diagnosis_no_status_promotion',
        'producer_status':receipt['status'],'producer_metadata':metadata,'source':ref(__file__),
        'rows':reports,'counts':dict(statuses),'predictor_statuses':dict(prediction_statuses),
        'reason_counts':dict(reasons),'first_information_field_counts':dict(first_fields),
        'first_nonconforming_per_case':first_rows,'native_calls':0,'model_evaluations':0,
        'actual_results_used_only_as_comparison_targets':True,'saved_pin_ledger_scope':'Producer entry/exit ledgers bound; no independent full source scan in this diagnosis.',
        'limits':['Unknowns remain unknown. No action-specific timing correction, float tolerance or fitted future clock is applied.',
                  'Information trace and five endpoints are separate checks; a difference is a diagnostic, not a protection result.'],
        'wall_seconds':time.perf_counter()-started}
    write(output/'report.json',report)
    write(output/'summary.json',{k:report[k] for k in ('status','producer_status','counts','predictor_statuses','reason_counts',
        'first_information_field_counts','native_calls','model_evaluations','wall_seconds')} | {'report':ref(output/'report.json')})
    print(json.dumps(read(output/'summary.json')))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--receipt-sha',required=True)
    parser.add_argument('--bounded-sha',required=True);args=parser.parse_args()
    diagnose(args.source.resolve(),args.output.resolve(),args.receipt_sha,args.bounded_sha)
