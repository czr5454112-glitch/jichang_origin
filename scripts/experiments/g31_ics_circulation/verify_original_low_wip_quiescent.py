"""Saved-only quiescent/reference comparison; incomplete old arms remain unknown."""
from __future__ import annotations
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path

from . import research_original_low_wip_quiescent as r
from . import verify_original_low_wip_repeat as frozen
from . import diagnose_repeat_postcap_saved as diagnostic
from .review_original_low_wip_repeat_saved import terminal_inventory, independent_outcomes, require, ordered, verify_case_corrected

p=r.reference


def verified_counter(directory,*,quiescent):
    """One exact saved replay provides validation and passive proof counting."""
    plan=p.base.read(directory/'preregistered_protocol.json')
    counter=diagnostic.ProofCounter(plan['supply_cap'],plan['parking_plan']['token_tray_id'])
    old_tape=p.base.ReplayTape;old_barrier=p.physical_barrier;old_candidate=r.candidate.physical_barrier
    class ObservedTape(old_tape):
        def __getattr__(self,name):
            method=super().__getattr__(name)
            def call(*args,**kwargs):
                at=self.physical_time;ordinal=self.index;value=method(*args,**kwargs)
                if name in {'observe_protocol_control_policy_recent','protocol_planning_snapshots_v2'}:
                    counter.read(name,args[0],at,ordinal,value)
                return value
            return call
    def barrier(outbox,owner,peer,parking):
        value=old_barrier(outbox,owner,peer,parking);counter.barrier(owner,value);return value
    try:
        p.base.ReplayTape=ObservedTape;p.physical_barrier=barrier;r.candidate.physical_barrier=barrier
        with (r.installed() if quiescent else nullcontext()): result=verify_case_corrected(directory)
    finally:
        p.base.ReplayTape=old_tape;p.physical_barrier=old_barrier;r.candidate.physical_barrier=old_candidate
    result['cap_proof_read_diagnostic']={'status':'passed_identical_saved_policy_with_read_counter',
        'api_rows':result['replay']['api_rows'],'first_cap_proofs_and_later_reads':counter.summary(),
        'native_executions':0,'seconds_saved':None,'scope':'Passive counter during the exact full saved-policy replay, never an additional native call or changed response.'}
    return result


def verify_case(directory):
    terminal_inventory(r.REFERENCE)
    result=verified_counter(directory,quiescent=True)
    result['candidate_ast_proof']=r.candidate.prove_only_cap_check_moved()
    data=p.base.gzread(directory/'input.json.gz');raw=p.base.gzread(directory/'raw_final.json.gz')
    result['independent_outcomes']=independent_outcomes(data,raw,p.base.read(directory/'preregistered_protocol.json'))
    result['variant_verifier_sha256']=p.base.sha(__file__)
    return result


def prefix_rows(directory, *,partial=False):
    """Only complete, hash-verified manifest rows count; expose any tail gap."""
    rows=[];error=None;manifest=directory/'api/manifest.jsonl'
    if not manifest.is_file(): return rows,{'reason':'no_manifest','excluded_files':[]}
    for ordinal,line in enumerate(manifest.read_bytes().splitlines()):
        try:
            row=json.loads(line)
            require(row['path']==f'{ordinal:06d}.json.gz' and p.base.sha(directory/'api'/row['path'])==row['sha256'],'prefix_manifest_identity')
            rows.append(row)
        except (ValueError,KeyError,OSError,TypeError) as failure:
            if not partial: raise
            error={'reason':repr(failure),'first_unverified_ordinal':ordinal};break
    listed={row['path'] for row in rows}
    extra=sorted(path.name for path in (directory/'api').glob('*.json.gz') if path.name not in listed)
    if not partial: require(not extra,'prefix_unmanifested_payload')
    if error is not None or extra: error={**(error or {}),'excluded_files':extra}
    return rows,error


def compare_prefix(left,right,count, *,partial_left=False):
    a,tail=prefix_rows(left,partial=partial_left);b,_=prefix_rows(right)
    require(type(count) is int and count>=0 and count<=min(len(a),len(b)),'prefix_row_count')
    last=None
    for x,y in zip(a[:count],b[:count],strict=True):
        left_row=p.base.gzread(left/'api'/x['path']);right_row=p.base.gzread(right/'api'/y['path'])
        require(frozen.semantic(left_row)==frozen.semantic(right_row),'cap_prefix_changed')
        last={'physical_time':left_row['after'],'endpoint':left_row['endpoint'],'ordinal':left_row['ordinal']}
    return {'verified_rows':count,'last_verified':last,'left_verified_manifest_rows':len(a),
        'right_verified_manifest_rows':len(b),'left_unverified_tail':tail,
        'only_excluded':'advance_to.result.wall_seconds after finite nonnegative numeric validation'}


def first_proof_count(diagnostic_result, fallback):
    proofs=diagnostic_result['first_cap_proofs_and_later_reads']
    return min((x['after_api_ordinal']+1 for x in proofs.values()),default=fallback)


def physical_call_rows(directory):
    rows,_=prefix_rows(directory);result=[]
    for item in rows:
        row=p.base.gzread(directory/'api'/item['path'])
        if row['endpoint'] in {'submit_protocol_transfer','protocol_request'}:
            result.append({key:row[key] for key in ('endpoint','args','kwargs','before','after','result')})
    return result


def compare_physical(old,new):
    require(old['physical_time']==new['physical_time']==p.HORIZON,'physical_horizon_difference')
    checks={key:ordered(old['result'][key])==ordered(new['result'][key]) for key in ('jobs','trays','receipts')}
    checks['physical_audit']=ordered(old['physical_audit'])==ordered(new['physical_audit'])
    require(all(checks.values()),'physical_result_difference')
    return checks


def completed_reference_case(entry):
    # Native closed0 may have the frozen verifier's independently diagnosed
    # payload-ID KeyError. Never relabel that original verification success:
    # a separate corrected full saved replay below must pass first.
    return entry.get('execution',{}).get('exit_code')==0


def compare(output):
    outer,old_ledger=terminal_inventory(r.REFERENCE)
    with r.installed(): r.verify_campaign(output)
    evidence={name:p.base.read(output/name/'independent_verification.json') for name in p.CAPS}
    newraw={name:p.base.gzread(output/name/'raw_final.json.gz') for name in p.CAPS}
    for name,item in evidence.items():
        require(item['status']=='passed_saved_policy_replay' and item['variant_verifier_sha256']==p.base.sha(__file__),'new_case_unverified')
        for path,digest in item['evidence_sha256'].items(): require(p.base.sha(path)==digest,'new_case_changed')
    comparisons={}
    for name in p.CAPS:
        old_dir=r.REFERENCE/name;new_dir=output/name
        new_diag=evidence[name]['cap_proof_read_diagnostic'];new_manifest,_=prefix_rows(new_dir)
        if completed_reference_case(old_ledger[name]):
            old_replay=verified_counter(old_dir,quiescent=False);old_diag=old_replay['cap_proof_read_diagnostic']
            oldraw=p.base.gzread(old_dir/'raw_final.json.gz')
            old_manifest,_=prefix_rows(old_dir)
            count=min(first_proof_count(old_diag,len(old_manifest)),first_proof_count(new_diag,len(new_manifest)))
            prefix=compare_prefix(old_dir,new_dir,count)
            a,b=old_diag['first_cap_proofs_and_later_reads'],new_diag['first_cap_proofs_and_later_reads']
            require(set(a)==set(b),'owner_cap_proof_domain_changed')
            per_owner={}
            for owner in a:
                fields=('at','current_token_locally_empty','physical_barrier')
                require(ordered({k:a[owner][k] for k in fields})==ordered({k:b[owner][k] for k in fields}), 'owner_cap_proof_facts_changed')
                per_owner[owner]={'same_public_cap_facts':True,'reference':a[owner],'candidate':b[owner]}
            physical=compare_physical(oldraw,newraw[name])
            require(ordered(physical_call_rows(old_dir))==ordered(physical_call_rows(new_dir)),'physical_protocol_tape_changed')
            comparisons[name]={'status':'passed_completed_reference_physical_parity','reference_replay':old_replay,
                'original_reference_ledger_unchanged':old_ledger[name],
                'common_prefix':prefix,'per_owner_actual_cap_proofs':per_owner,'physical_exact':physical,
                'ordered_physical_submit_and_query_tape_exact':True,
                'reference_native_seal':oldraw['native_state_sha256'],'candidate_native_seal':newraw[name]['native_state_sha256'],
                'native_seal_equality_required':False,'whole_api_equality_required':False,
                'reference_raw_sha256':p.base.sha(old_dir/'raw_final.json.gz'),
                'reference_manifest_sha256':p.base.sha(old_dir/'api/manifest.jsonl')}
        else:
            old_manifest,tail=prefix_rows(old_dir,partial=True)
            count=min(len(old_manifest),first_proof_count(new_diag,len(new_manifest)))
            prefix=compare_prefix(old_dir,new_dir,count,partial_left=True)
            comparisons[name]={'status':'unknown_incomplete_reference_arm','reference_ledger':old_ledger[name],
                'common_verified_prefix':prefix,'unverified_tail':tail,'completed_arm_parity':False,
                'reference_manifest_sha256':p.base.sha(old_dir/'api/manifest.jsonl') if (old_dir/'api/manifest.jsonl').is_file() else None}
    # The new cap3/cap8 may diverge immediately after the first cap3 proof,
    # before its third job completes. Never use the old third-HOLD cutoff.
    count=first_proof_count(evidence['cap3']['cap_proof_read_diagnostic'],len(prefix_rows(output/'cap3')[0]))
    pair_prefix=compare_prefix(output/'cap3',output/'cap8',min(count,len(prefix_rows(output/'cap8')[0])))
    assessed=all(item['assessment']['status']=='complete_finite_policy_evidence' for item in evidence.values())
    counts={name:len(item['independent_outcomes']['completed']) for name,item in evidence.items()}
    return {'schema':r.SCHEMA,'status':'assessed_finite_pair' if assessed else 'unknown_incomplete_policy_pair',
        'cases':{name:item['assessment'] for name,item in evidence.items()},'completion_counts':counts,
        'extra_observed_completions':counts['cap8']-counts['cap3'] if assessed else None,
        'cap3_cap8_common_prefix_to_first_cap3_proof':pair_prefix,'reference_comparisons':comparisons,
        'reference_external_receipt_sha256':p.base.sha(r.REFERENCE/'external_launch_receipt.json'),
        'reference_ready_sha256':r.READY_SHA,'all_offered_each':28506,'total_trays_each':22,'other_parked_trays':21,
        'strict_protection':'unknown_unfinished_offered_jobs','complete_100ms_certified':False,
        'scope':'Same original data/physical policy and fullH. Only post-cap new admission/publication reads stop; immutable refresh/retry/ACK relay continues. Native/API/protocol history equality is not assumed after proof. Incomplete old arm is retained without a completed physical parity certificate.'}
