"""Independent saved60 audit after terminal execution; never runs native.

Replays source-data validation and pure search, then compares actual immutable
commands/ACKs/edges and complete five-job physical outcomes. Measured proposal
durations remain in raw evidence and are excluded only from semantic equality.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace
from . import research_native_public_preference as runner
from . import public_native_preference_search as search
from . import native_public_preference_policy as policy
from .public_owned_action_state import bind_supplied_bundle
from .validate_public_native_preference_projection import imported_source_pins


def require(value,reason):
    if not value:raise ValueError('saved_public_preference:'+reason)


def json_value(value):return json.loads(json.dumps(value,allow_nan=False))


def semantic_proposal(proposal):
    """Remove only newly measured envelopes, never physical model times."""
    value=copy.deepcopy(proposal)
    def duration(row,key):
        if key in row:
            measured=row.pop(key)
            require(type(measured) in (int,float) and math.isfinite(measured) and measured>=0,'invalid_measured_duration')
    duration(value,'proposal_wall_seconds')
    for row in value.get('rows',[]):duration(row,'model_call_wall_seconds')
    return json_value(value)


def verify_transport(raw):
    prior=-1.;first={};seen=set()
    for call in raw['calls']:
        now=call['at'];req=call['request'];key=req['request_id']
        require(type(now) in (int,float) and math.isfinite(now) and prior<=now<=40.,'call_chronology')
        require(req['owner_id'] in ('A','B') and type(call['retry']) is bool,'call_owner_or_retry')
        prior=now
        if key in seen:require(call['retry'] and req==first[key]['request'] and call['kind']==first[key]['kind'],'changed_immutable_retry')
        else:
            require(call['retry'] is False,'retry_without_original')
            first[key]=call;seen.add(key)
        require(key in raw['outbox'] and req==raw['outbox'][key]['request'] and call['kind']==raw['outbox'][key]['kind'],'outbox_payload_binding')
    require(seen==set(raw['outbox']),'outbox_call_denominator')
    last={};previous=-1.
    for handled in raw.get('ack_handling',[]):
        key=handled['request_id'];ack=handled['ack'];at=handled['at']
        require(key in first and handled['owner']==first[key]['request']['owner_id'],'ack_owner_binding')
        require(type(at) in (int,float) and previous<=at<=40. and type(ack.get('delivered_at')) in (int,float)
            and first[key]['at']<=ack['delivered_at']<=at,'ack_causal_time')
        require(type(ack.get('sequence')) is int and ack['sequence']>0,'ack_sequence')
        if key in last:require(ack['sequence']>=last[key]['sequence'],'ack_sequence_reversed')
        previous=at;last[key]=ack
    if 'ack_handling' in raw:
        for key,row in raw['outbox'].items():require(row.get('ack',{})==last.get(key,{}),'outbox_latest_handled_ack')
    at=.11;cursors={'A':0,'B':0}
    for batch in raw.get('native_batches',[]):
        response=batch['response'];now=response['physical_time']
        require(response['status'] in ('notified','horizon_reached') and response['timestamp_complete'] is True
            and type(now) in (int,float) and at<=now<=batch['deadline']<=40.,'undrained_or_reversed_native_boundary')
        for owner,notice in response.get('notifications',{}).items():
            require(owner in cursors and type(notice['sequence']) is int and notice['sequence']>cursors[owner]
                and notice['observed_at']<=now,'native_notification_cursor')
            cursors[owner]=notice['sequence']
        at=now


def verify_retained_ledgers(raw):
    for owner,ledger in raw.get('retained_ledgers',{}).items():
        initial=raw['initial_owners'][owner]['information'];contracts={};sources={};digests=set()
        fields=runner.adapter.previous.CONTRACT_FIELDS
        for source,envelope in initial['envelopes'].items():
            body=envelope['capture'];digests.add(body['static_contract_sha256'])
            for job in body['jobs']:
                key=job['business_bag_id'];require(key not in contracts,'duplicate_initial_ledger_job')
                contracts[key]={field:job[field] for field in fields}
                sources[key]={'source_owner':source,'message_id':body['message_id'],'payload_sha256':envelope['payload_sha256'],
                    'captured_at':body['captured_at'],'delivered_at':initial['own_delivered_ack']['delivered_at'] if source==owner else envelope['delivered_at']}
        require(len(digests)==1 and set(contracts)==runner.model.JOBS,'incomplete_initial_ledger')
        require(ledger['owner']==owner and ledger['retained_at']==.11 and ledger['contracts']==contracts
            and ledger['sources']==sources and ledger['static_contract_sha256']==next(iter(digests))
            and ledger['native_binary']==initial['native_read']['native_binary'],'retained_ledger_not_derived_from_initial_capture')


def replay_proposals(raw):
    method=raw['specification']['method'];evaluations=0;states=[]
    for owner,row in raw['initial_owners'].items():
        info=row['information'];known=info.get('native_delivery_verified') is True
        proposed=(search.initial_proposal(info['bundle'],**policy.method_parameters(method)) if known else
                  {'status':'unknown_unverified_initial_input','selected_action':None})
        require(semantic_proposal(proposed)==semantic_proposal(row['proposal']),'initial_search_replay:'+owner)
        evaluations+=proposed.get('evaluations',0)
        selected=row['decision'].get('selected_action')
        require(selected is None or selected==proposed.get('selected_action'),'initial_selected_action_not_proposed')
        if selected is not None:
            request=row['native_request_id']
            if owner=='A' and selected['initial_action']=='native_default':
                require(request is None and row['decision'].get('native_default_no_command') is True,'default_misrepresented_as_request')
            else:
                require(request in raw['outbox'],'initial_selected_action_has_no_request')
                issued=raw['outbox'][request]['request'];view=row['local_action_view']
                if owner=='A':
                    tray=next(t for t in view['trays'] if t['tray_id']=='L')
                    fields={'owner_id':'A','tray_id':'L','business_bag_id':'loaded','from':0,'next':2,
                        'expected_generation':tray['generation'],'expected_traversal':tray['traversal_id'],
                        'expiry':5.,'message_delay':.01}
                else:fields={'owner_id':'B','tray_id':'E','source':5,'destination':1,'expiry':39.,
                    'message_delay':.01,'earliest_departure':selected['empty_departure']}
                require(all(issued.get(k)==v for k,v in fields.items()),'initial_request_does_not_match_owned_proposal')
                calls=[c for c in raw['calls'] if c['request']['request_id']==request and c['retry'] is False]
                require(len(calls)==1 and calls[0]['at']==view['now']==.11,'initial_request_epoch')
        states.append({'owner':owner,'phase':'initial','status':proposed['status'],'evaluations':proposed.get('evaluations'),
            'selected_action':proposed.get('selected_action'),'proposal_wall_seconds':row['proposal'].get('proposal_wall_seconds')})
    for owner,sequence in raw.get('decisions',{}).items():
        for row in sequence:
            info=row['information']
            if info.get('native_delivery_verified') is True:
                try:
                    bundle=bind_supplied_bundle(info['bundle'],info['raw_endpoints']['view'])
                    proposed=search.later_proposal(bundle,**policy.method_parameters(method,later=True))
                    proposed['current_owned_action_facts']=bundle['owner_current_action_facts']
                except (ValueError,KeyError,TypeError,AttributeError):
                    proposed={'status':'unknown_current_owned_action_scope','selected_action':None}
            else:proposed={'status':'unknown_unverified_or_unsupported_input','selected_action':None}
            require(semantic_proposal(proposed)==semantic_proposal(row['decision']),'later_search_replay:'+owner)
            selected=proposed.get('selected_action');expected=({'reuse_next':8 if selected['later_action']=='prefer_8' else None,
                'return_delay':selected['return_delay']} if selected else {'reuse_next':None,'return_delay':0.})
            require(row['executed_first_action']==expected and row['fallback_used']==(selected is None),'later_action_or_fallback_not_proposed')
            # PhaseB never submits the already executed first return again.
            if row['phase']=='first_reuse_route' and row['native_request_id'] is not None:
                require(raw['outbox'][row['native_request_id']]['kind']=='route','phaseB_changes_first_return_prefix')
            if row['phase']=='first_return' and row['native_request_id'] is not None:
                operation=raw['outbox'][row['native_request_id']]
                fields={'owner_id':'A','tray_id':'L','source':6,'destination':7,'expiry':39.,'message_delay':.01,
                        'earliest_departure':row['at']+expected['return_delay']}
                require(operation['kind']=='transfer' and all(operation['request'].get(k)==v for k,v in fields.items()),
                        'first_return_not_bound_to_current_action')
            evaluations+=proposed.get('evaluations',0)
            states.append({'owner':owner,'phase':row['phase'],'status':proposed['status'],'evaluations':proposed.get('evaluations'),
                'selected_action':selected,'fallback':row['fallback_used'],'proposal_wall_seconds':row['decision'].get('proposal_wall_seconds')})
    return {'pure_projection_evaluations':evaluations,'decisions':states,'measured_durations_recharged_or_subtracted':False}


def audit(directory):
    directory=Path(directory).resolve();sources=imported_source_pins();pins=dict(sources)
    def pin(path,expected=None):
        path=Path(path).resolve();digest=runner.sha(path)
        require(expected is None or digest==expected,'evidence_hash:'+str(path))
        require(str(path) not in pins or pins[str(path)]==digest,'conflicting_evidence_pin')
        pins[str(path)]=digest
        return json.loads(path.read_bytes()) if path.suffix=='.json' else None
    parent=pin(directory/'bounded_parent_receipt.json');receipt=pin(directory/'receipt.json')
    require(parent['status']=='exited' and parent['exitcode']==0 and parent['windows_job_kill_on_close'] is True
        and parent['wall_seconds']<180. and receipt['status'] in ('executed','completed_with_unknowns')
        and receipt['source_changed']==receipt['source_closure_changed']==[],'campaign_not_terminal_and_evidence_closed')
    plan=pin(directory/'preregistered_protocol.json',parent['expected_plan_sha256']);rows=pin(directory/'branch_ledger.json')
    declared=runner.protocol('business')
    require(plan['phase']=='business' and plan['rows']==declared['rows'] and set(rows)==set(plan['rows'])
        and len(rows)==receipt['branch_count']==60,'full60_domain')
    for source,digest in plan['source_sha256'].items():
        pin(source,digest);pin(directory/plan['source_archive'][source],digest)
    admission=pin(directory/'run_acceptance.json',receipt['run_acceptance']['sha256'])
    require(receipt['run_acceptance']['status']==admission['status']=='closed_run_acceptance_passed'
        and admission['active'] is False and admission['invalid']==[]
        and admission['run_reference']=={'path':str(directory/'preregistered_protocol.json'),'sha256':runner.sha(directory/'preregistered_protocol.json')}
        and admission['contract_reference']==receipt['native027_contract_reference']
        and admission['semantic_reference']==receipt['native027_semantic_gate']['reference'],'run_acceptance_not_closed_or_bound')
    require(admission['evidence_sha256']==runner.run_admission.inventory(admission['contract_reference'],admission['semantic_reference'],admission['run_reference']),
        'run_acceptance_evidence_changed')
    for path,digest in admission['evidence_sha256'].items():pin(path,digest)
    delivery=pin(directory/'delivery_gate_binding.json')
    require(runner.require_delivery_gate(delivery['path'],receipt['binary_sha256'],plan)==delivery,'initial_delivery_gate_changed')
    phases=[row['phase'] for row in admission['costs']]
    require(phases.count('run_entry_closed_verifiers')==phases.count('run_exit_closed_verifiers')==1,'missing_entry_exit_acceptance')
    require(len(admission['branch_keys'])==len(set(admission['branch_keys'])) and set(admission['branch_keys'])<=set(rows),'admission_branch_domain')
    native_contract=pin(admission['contract_reference']['path'],admission['contract_reference']['sha256'])
    require(native_contract['binary_sha256']==receipt['binary_sha256'],'actual_binary_binding')
    result={};counts=Counter();evaluations=0
    for key,row in rows.items():
        require(all(row[field]==plan['rows'][key][field] for field in ('case','method','fault')),'row_misbound')
        item=row.get('raw_artifact')
        if item is None:
            require(row['status'].startswith('unknown') and 'summary' not in row,'assessed_without_raw')
            result[key]={'status_retained':row['status'],'physical_assessment':'unknown_no_raw'};counts[row['status']]+=1;continue
        expected={'path':key+'.json.gz','input_path':'inputs/'+key+'.json','input_sha256':plan['input_file_sha256'][key],
                  'sha256':runner.sha(directory/(key+'.json.gz'))}
        require(item==expected==receipt['raw_artifacts'][key] and key in admission['branch_keys'],'raw_artifact_binding')
        require(phases.count('branch_entry:'+key)==phases.count('branch_exit:'+key)==1,'branch_not_closed')
        path=directory/item['path'];pin(path,item['sha256']);data=pin(directory/item['input_path'],item['input_sha256'])
        raw=json.loads(gzip.decompress(path.read_bytes()))
        require(raw['input']==data and runner.config_sha(data)==plan['row_configuration_sha256'][key],'raw_input_changed')
        require(all(raw['specification'][f]==row[f] for f in ('case','method','fault')),'raw_policy_identity')
        verify_transport(raw);runner.matrix_runner.verify_saved_inputs(raw);verify_retained_ledgers(raw)
        for owner,initial in raw['initial_owners'].items():
            runner.delivery_evidence._local_shape(initial['raw_endpoints']['view'],data,owner)
            native=initial['information']['native_read']['native_binary']
            require(native['sha256']==receipt['binary_sha256']
                and Path(native['resolved_path']).resolve()==Path(native_contract['binary']).resolve(),'saved_endpoint_binary_mismatch')
        proposals=replay_proposals(raw);evaluations+=proposals['pure_projection_evaluations']
        if 'continuation' in raw:
            summary=runner.completed_summary(data,raw['result'],SimpleNamespace(rows=raw['outbox'],calls=raw['calls']),raw['continuation'],
                raw['initial_owners']['A']['decision']['selected_action'],raw['initial_owners'],raw['decisions'])
        else:
            require(raw['summary']['status']=='unknown_initial_asymmetry_or_missing_ledger','missing_unclassified_continuation')
            summary={'status':'unknown_initial_asymmetry_or_missing_ledger','business_metrics':None}
        require(json_value(summary)==row['summary']==raw['summary'] and row['status']==summary['status'],'physical_summary_replay')
        counts[row['status']]+=1
        result[key]={'status_retained':row['status'],'completion':summary.get('completion'),'completion_sum':summary.get('completion_sum'),
            'initial_actual_next':summary.get('initial_actual_next'),'first_reuse_actual_next':summary.get('first_reuse_actual_next'),
            'physical_audit':summary.get('audit'),'fallback_count':summary.get('rolling_fallback_count'),
            'policy_replay':proposals,'raw_artifact':str(path),'raw_sha256':item['sha256'],'unknown_promoted':False}
    comparisons=runner.assess(rows,'business')
    require(receipt['branch_status_counts']==dict(counts) and receipt['comparisons']==comparisons,'summary_counts_or_comparisons_changed')
    require(set(receipt['raw_artifacts'])=={k for k,r in rows.items() if 'raw_artifact' in r},'receipt_raw_denominator')
    require(imported_source_pins()==sources and all(runner.sha(p)==h for p,h in pins.items()),'audit_source_or_evidence_drift')
    return {'schema':'g31.native_public_preference.saved_audit.v1','status':'terminal_saved60_revalidated_no_native',
        'rows':result,'comparisons':comparisons,'counts':dict(counts),'evidence_sha256':pins,
        'pure_projection_evaluations':evaluations,'native_calls':0,'unknown_promoted':False,
        'limits':['Saved endpoint provenance and immutable compiled-source/receipt bindings are rechecked; no hidden native replay or new authority token is created.',
            'All five actual jobs and full four fixed-initial arms are required for their strict comparisons; incomplete references remain unknown.',
            'Pure search timing is newly measured only for replay equality. Original timing remains charged and no complete-request100ms certificate is produced.',
            'Exact point model and saved actual protection do not establish unseen error bounds, atomic agreement, original-map usefulness or algorithm novelty.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    require(not args.output.exists(),'output_already_exists');result=audit(args.directory)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'counts':result['counts'],'pure_evaluations':result['pure_projection_evaluations']}))


if __name__=='__main__':main()
