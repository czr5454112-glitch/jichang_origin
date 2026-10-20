"""All238 saved collections through a new pure guard; no simulation or native."""
from __future__ import annotations
import copy,gzip,hashlib,json,time
from collections import Counter
from pathlib import Path
from . import domain_guard_historical_service as candidate
from . import verify_live_obligation_recollection as saved

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
RUN=OUT/'live_obligation_recollection_native_v2_prepare_001'
TARGET=OUT/'historical_goal_service_saved_replay_001.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def require(v,why):
    if not v:raise ValueError(why)
def normalized(v):return json.loads(json.dumps(v,allow_nan=False,sort_keys=True))

def arguments(raw,owner,entry):
    requests=saved.prefix_requests(raw,owner,entry);pending=entry['collection']
    ep=copy.deepcopy(entry['information']['raw_endpoints'])
    for field in ('node_records','edge_records'):ep['view'][field]=[tuple(row) for row in ep['view'][field]]
    return ep,{'retained':raw['retained_ledgers'][owner],
        'own_actions':sorted((k,kind) for k,(kind,_) in requests.items() if kind in saved.policy.PHYSICAL_KINDS),
        'phase':entry['phase'],'own_request_id':pending['request_id'],'peer_message_id':pending['peer_message'],
        'collection_started_at':pending['at'],'policy_quiet_since':pending['policy_quiet_since'],
        'own_request':requests[pending['request_id']][1],
        'own_publication_requests':{k:r for k,(kind,r) in requests.items() if kind=='planning_snapshot_v3'}}

def main():
    start=time.perf_counter();require(not TARGET.exists(),'immutable_report')
    prior=OUT/'live_obligation_recollection_native_v2_saved_review_001.json'
    require(sha(prior)=='c21c9e90c92fb12ccf846fe2072f81c7b43531e969aa3ff031a8ea0d733e88af','prior_independent_review')
    audit=read(prior);plan=read(RUN/'preregistered_protocol.json')
    pins={};archives={}
    for key,digest in plan['source_sha256'].items():
        p=Path(key);p=p if p.is_absolute() else ROOT/p
        require(sha(p)==digest,'old_source_pin');pins[str(p)]=digest
    for key,item in plan['source_archive'].items():
        p=RUN/item;digest=plan['source_sha256'][key]
        require(sha(p)==digest,'old_source_archive_pin');archives[str(p)]=digest
    new_sources=[Path(candidate.__file__),Path(candidate.history.__file__),Path(__file__),
                 ROOT/'tests/test_g31_circulation_historical_goal_service.py']
    newpins={str(p):sha(p) for p in new_sources}
    rows={};transitions=Counter();reasons=Counter();final_counts=Counter();total=0
    for key in plan['branch_order']:
        p=RUN/(key+'.json.gz');require(sha(p)==audit['rows'][key]['raw']['sha256'],'all_raw_pins')
        raw=json.loads(gzip.decompress(p.read_bytes()));attempts=[];final={}
        for owner in ('A','B'):
            for index,entry in enumerate(raw['collection_attempts'][owner]):
                ep,kwargs=arguments(raw,owner,entry);before=copy.deepcopy(ep)
                output=candidate.validate_collected_endpoints(ep['view'],ep['command'],ep['received'],**kwargs)
                require(ep==before,'input_mutation')
                known=output['status']=='conditional_validated_later_v3_data'
                old_known=entry['information']['status']=='conditional_native_delivered_later_v3_model_input'
                require(not old_known or known,'old_supported_input_regression')
                derived=output.get('bundle',{}).get('derived_goal_service_bounds',{})
                if derived:
                    require(not old_known and owner=='B','narrow_extension_only')
                    require(output['native_delivery_verified'] is False and output['online_information_delivered'] is False,'no_authority_minted')
                    for tray,proof in derived.items():
                        require(output['bundle']['trays'][tray]['service_ready_at']==proof['raw_service_ready_at'],'raw_epoch_preserved')
                else:
                    # Confirm every unaffected supplied-data output is identical
                    # to the frozen original guard, including all unknown reasons.
                    oldkwargs={k:v for k,v in kwargs.items() if k!='own_publication_requests'}
                    previous=candidate.old.validate_collected_endpoints(ep['view'],ep['command'],ep['received'],**oldkwargs)
                    require(normalized(output)==normalized(previous),'unchanged_guard_output')
                transitions[(old_known,known)]+=1;total+=1
                if not known:reasons.update(output.get('reasons',[])+output.get('bundle',{}).get('reasons',[]))
                attempts.append({'owner':owner,'index':index,'at':entry['at'],'phase':entry['phase'],
                    'old_actual_information_status':entry['information']['status'],'new_pure_guard_status':output['status'],
                    'reasons':output.get('reasons',[]),'bundle_reasons':output.get('bundle',{}).get('reasons',[]),
                    'derived_goal_service_bounds':derived,
                    'raw_endpoints_unchanged':True,'native_authority_minted':False})
                final[owner]=known
        final_counts['both_final_saved_inputs_supported' if all(final.values()) else 'at_least_one_final_input_unknown']+=1
        rows[key]={'raw':ref(p),'original_actual_status':raw['summary']['status'],
            'original_selected_actions_executed':raw['summary']['selected_actions_executed'],
            'final_saved_input_support':final,'attempts':attempts,'actual_status_not_promoted':True}
    require(len(rows)==96 and total==238,'complete_saved_attempt_denominator')
    for p,digest in {**pins,**archives,**newpins}.items():require(sha(p)==digest,'source_drift_during_replay')
    report={'schema':'g31.historical_goal_service_saved_replay.v1','status':'complete_pure_saved_replay_no_native_claim',
        'prior_independent_native_review':ref(prior),'native_plan':ref(RUN/'preregistered_protocol.json'),
        'old_source_pins':pins,'old_archive_pins':archives,'new_source_pins':newpins,
        'pure_tests':ref(OUT/'historical_goal_service_pure_001.xml'),'branches':96,'attempts':total,
        'transitions':[{'old_known':a,'new_pure_supported':b,'count':n} for (a,b),n in transitions.items()],
        'remaining_pure_unknown_reasons':dict(reasons),'final_saved_input_support_counts':dict(final_counts),'rows':rows,
        'limits':['All original actual80assessed/16unknown and six incomplete families remain immutable.',
            'Pure supplied-data acceptance grants no native endpoint authority and does not demonstrate a newly executed action.',
            'Some first failed attempts now have enough retained history. A future policy may act before the old fresh-pair exchange, changing subsequent physical/communication timing; these saved outcomes cannot stand in for that counterfactual.',
            'The two actual unloading transitions lack delivered completion receipts and remain unknown. No retry, clock, wire, physics, tolerance or family standard changed.',
            'No model evaluations or new trajectory outcomes were computed; the same saved cases are retrospective interface regression material, not held-out validation.'],
        'native_executions':0,'model_evaluations':0,'wall_seconds':time.perf_counter()-start}
    TARGET.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':ref(TARGET),'transitions':report['transitions'],'final':dict(final_counts),'wall_seconds':report['wall_seconds']}))

if __name__=='__main__':main()
