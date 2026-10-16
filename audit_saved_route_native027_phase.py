"""Saved-only six-cell audit with bounded case lifetime and rowwise comparisons.

The original600s campaign remains timed out. No native object is constructed,
no original file is changed, and no timing field is reinterpreted as compute.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import gzip
import inspect
import json
from pathlib import Path
import time
import sys
from itertools import zip_longest

from scripts.experiments.g31_ics_circulation import verify_original_route_update_native027_phase as original
from scripts.experiments.g31_ics_circulation import route_update_phase_measurement as measurement

p=original.p
require=original.require
SCHEMA='g31.saved_route_native027_phase_audit.v1'
_MISSING=object()


def api_rows(path):
    with gzip.open(path,'rt',encoding='utf8') as stream:
        for line in stream:yield json.loads(line)


def compare_api_rows(left,right,reason):
    """Equivalent to the old ordered normalized list equality, one row at a time."""
    count=0
    for a,b in zip_longest(left,right,fillvalue=_MISSING):
        require(a is not _MISSING and b is not _MISSING,reason+':denominator')
        require(original.ordered(original.api_semantics(a))==original.ordered(original.api_semantics(b)),reason)
        count+=1
    return count


def phase_reference_stream(plan,name,raw,rows,folder):
    reference=Path(plan['phase_reference'])/name
    prior=p.old.gzread(reference/'raw.json.gz')
    require(raw['physical_time']==prior['physical_time']==p.HORIZON and
        raw['control_status']==prior['control_status']=='reached' and
        raw['native_state_sha256']==prior['native_state_sha256'],'native026_same_horizon_seal')
    count=compare_api_rows(iter(rows),api_rows(reference/'service_tape.jsonl.gz'),'native026_all_warm_api_changed')
    require(original.ordered(raw['root']['intent'])==original.ordered(prior['root']['intent']) and
        original.ordered(raw['root']['eligibility_schedule'])==original.ordered(prior['root']['eligibility_schedule']),
        'native026_intent_changed')
    current_parts=p.old.read(folder/'shards.json');prior_parts=p.old.read(reference/'shards.json')
    require(len(current_parts)==len(prior_parts),'native026_controller_part_count')
    for current,previous in zip(current_parts,prior_parts,strict=True):
        require({k:v for k,v in current.items() if k!='sha256'}=={k:v for k,v in previous.items() if k!='sha256'},
            'native026_controller_boundaries')
        reference_path=reference/previous['path']
        require(p.old.sha(reference_path)==previous['sha256'],'native026_controller_reference_hash')
        require(original.ordered(original.prefix_semantics(p.old.gzread(folder/current['path'])))==
            original.ordered(original.prefix_semantics(p.old.gzread(reference_path))),'native026_controller_parts_changed')
    return {'status':'all_ordered_api_controller_parts_and_common9900_producer_seal_exact',
        'api_rows':count,'controller_parts':len(current_parts),'producer_seal':raw['native_state_sha256'],
        'independent_native_replay':False,'comparison_algorithm':'rowwise exact original api_semantics; all controller parts unchanged',
        'clock_exclusions':['API outer start_ns/end_ns','advance_to/advance_until_owner_notification.result.wall_seconds when present',
            'result_at.result.advance.wall_seconds','controller prefix_semantics exact fixed clock list']}


def consume_verified_case(summary,raw,rows,directory,plan,name):
    """Run remaining old checks before the decoded case can leave this frame."""
    diag_path=directory/'phase_capture.json.gz';diagnostic=p.old.gzread(diag_path)
    timed=plan['phase_arm']=='timed'
    require(diagnostic['schema']=='g31.original_route_native027_phase_capture.v1' and
        diagnostic['timed'] is timed and diagnostic['capacity']==measurement.CAPACITY and
        diagnostic['complete_computation_available'] is False and type(diagnostic['physics_subtracted_ns']) is int and
        diagnostic['physics_subtracted_ns']==0,'phase_capture_scope')
    summary['native026_reference']=phase_reference_stream(plan,name,raw,rows,directory)
    if timed:
        summary['phase_diagnostics']=measurement.summarize(diagnostic,rows,raw['root'],raw['events'])
    else:
        require(diagnostic['capture_setup'] is None and diagnostic['capture_take'] is None and
            all(diagnostic[k]==[] for k in ('python_spans','native_batches','native_envelopes','capture_errors')),
            'plain_capture_not_empty')
        summary['phase_diagnostics']={'status':'disabled'}
    summary['phase_capture_sha256']=p.old.sha(diag_path)
    return summary


def verify_case_function():
    """All original case guards remain byte-for-AST; only wrap its final return."""
    source=inspect.getsource(original.verify_case)
    tree=ast.parse(source);function=tree.body[0]
    require(isinstance(function,ast.FunctionDef) and function.name=='verify_case' and
        isinstance(function.body[-1],ast.Return),'unexpected_original_case_ast')
    before=ast.dump(tree,include_attributes=False)
    old_return=function.body[-1].value
    function.body[-1].value=ast.Call(func=ast.Name(id='_consume_verified_case',ctx=ast.Load()),
        args=[old_return,*[ast.Name(id=name,ctx=ast.Load()) for name in ('raw','rows','directory','plan','name')]],keywords=[])
    restored=deepcopy(tree);restored.body[0].body[-1].value=deepcopy(old_return)
    require(ast.dump(restored,include_attributes=False)==before,'case_validation_ast_changed')
    ast.fix_missing_locations(tree)
    namespace={**original.verify_case.__globals__,'_consume_verified_case':consume_verified_case}
    exec(compile(tree,str(Path(__file__).resolve())+':original_case','exec'),namespace)
    return namespace['verify_case'],{'status':'original_case_AST_unchanged_except_final_return_callback',
        'original_source_sha256':p.old.sha(original.__file__),
        'unchanged':'raw/process/clock/API/request replay/shard/outbox/ACK/drain/owner/budget/lineage/prefix and split-reference checks'}


def original_inventory(folder):
    """Pin every actual produced row and stop receipt without decoding large API lists."""
    pins={}
    def add(path,expected=None):
        path=Path(path).resolve();digest=p.old.sha(path)
        require(expected is None or digest==expected,'saved_phase_hash_mismatch')
        require(str(path) not in pins or pins[str(path)]==digest,'saved_phase_pin_conflict')
        pins[str(path)]=digest
    outer=p.old.read(folder/'external_launch_receipt.json')
    require(outer['status']=='unknown_campaign_process' and outer['process']['status']=='hard_timeout' and
        outer['process']['windows_job_kill_on_close'] is True,'original_campaign_not_stopped_timeout')
    require(outer['campaign_sha256']==p.old.sha(folder/'campaign.json'),'saved_phase_campaign_binding')
    add(folder/'external_launch_receipt.json');add(folder/'campaign.json')
    for relative,digest in outer['artifact_sha256'].items():
        path=(folder/relative).resolve();require(path.is_relative_to(folder),'outer_path_escape');add(path,digest)
    ledger=p.old.read(folder/'branch_ledger.json')
    require(set(ledger)=={arm+'/'+case for arm in p.ARMS for case in p.CASES},'six_cell_denominator')
    for arm in p.ARMS:
        armfolder=folder/arm;receipt=p.old.read(armfolder/'receipt.json')
        add(armfolder/'receipt.json');add(armfolder/'preregistered_protocol.json')
        require(receipt['status']=='children_finished' and set(receipt['cases'])==set(p.CASES),'arm_execution_incomplete')
        for case in p.CASES:
            process=receipt['cases'][case];directory=armfolder/case
            require(process==ledger[arm+'/'+case] and process['status']=='child_finished' and process['exit_code']==0,
                'cell_worker_not_completed')
            require(set(process['artifact_sha256'])=={'raw.json.gz','service_tape.jsonl.gz','shards.json','phase_capture.json.gz'},
                'cell_artifact_denominator')
            for relative,digest in process['artifact_sha256'].items():add(directory/relative,digest)
            add(directory/'input.json.gz')
            for item in p.old.read(directory/'shards.json'):add(directory/item['path'],item['sha256'])
    return pins,outer


def verify(folder,progress=None):
    folder=Path(folder).resolve();started=time.perf_counter();events=[]
    def note(stage):
        events.append({'stage':stage,'elapsed_seconds':time.perf_counter()-started})
        if progress is not None:p.old.write(progress,{'schema':SCHEMA,'status':'running_saved_only','stages':events})
    source_before={str(Path(module.__file__).resolve()):p.old.sha(module.__file__) for module in (original,measurement,p)}
    source_before[str(Path(__file__).resolve())]=p.old.sha(__file__)
    pins,outer=original_inventory(folder);note('actual_six_cells_and_original_timeout_pinned')
    campaign=p.verify_campaign(folder);p.abi.verify_contract(p.CONTRACT,require_runtime=True);note('full_source_and_closed027_authority_verified')
    check,proof=verify_case_function()
    report={'schema':SCHEMA,'status':'passed_saved_six_cell_audit_after_original_timeout','cases':{},'parity':{},
        'declared_roots':6,'original_campaign_status':outer['status'],'original_timeout_preserved':True,
        'original_external_receipt_sha256':pins[str(folder/'external_launch_receipt.json')],
        'verification_AST_proof':proof,'native_timing_contract':p.CONTRACT,'native_executions':0,
        'complete_computation_available':False,'complete_100ms_certified':False,'physics_subtracted_ns':0}
    for arm in p.ARMS:
        directory=folder/arm;plan=p.old.read(directory/'preregistered_protocol.json');p.verify_pins(directory,plan)
        for name in p.CASES:
            report['cases'][arm+'/'+name]=check(directory,plan,name)
            note('verified:'+arm+'/'+name)
        p.verify_pins(directory,plan)
    for name in p.CASES:
        left=folder/'plain'/name;right=folder/'timed'/name
        count=compare_api_rows(api_rows(left/'service_tape.jsonl.gz'),api_rows(right/'service_tape.jsonl.gz'),'timing_changed_api')
        a=p.old.gzread(left/'raw.json.gz');b=p.old.gzread(right/'raw.json.gz')
        require(a['native_state_sha256']==b['native_state_sha256'],'timing_changed_seal')
        report['parity'][name]={'status':'ordered_all_warm_api_and_native_seal_exact','api_rows':count,
            'producer_native_seal':a['native_state_sha256']}
        note('plain_timed_parity:'+name)
    p.verify_campaign(folder);p.abi.verify_contract(p.CONTRACT,require_runtime=True)
    require(all(p.old.sha(path)==digest for path,digest in pins.items()),'actual_evidence_changed_during_audit')
    require(all(p.old.sha(path)==digest for path,digest in source_before.items()),'audit_source_changed')
    note('exit_all_evidence_sources_and_closed027_authority_verified')
    report.update(closed_roots=sum(v['status']=='closed_finite_request' for v in report['cases'].values()),
        source_before=campaign['source_before'],audit_source_pins=source_before,evidence_sha256=pins,
        stages=events,audit_wall_seconds=time.perf_counter()-started,
        scope='All original six-cell guards, exact request-policy replay, API/controller/native-seal comparisons and unchanged phase validator. Rowwise comparisons avoid full normalized API copies. Separate saved audit does not repair the original600s timeout, prove isolated compute or create a new native seal.')
    report['open_roots']=6-report['closed_roots']
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--admission',required=True)
    args=parser.parse_args();require(sys.stdin.readline().rstrip('\n')==args.admission,'saved_audit_job_admission')
    require(not args.output.exists(),'audit_output_exists')
    args.output.mkdir(parents=True)
    try:
        report=verify(args.source,args.output/'progress.json');p.old.write(args.output/'report.json',report)
        print(json.dumps({'status':report['status'],'closed_roots':report['closed_roots'],'open_roots':report['open_roots'],
            'audit_wall_seconds':report['audit_wall_seconds']}))
    except BaseException as error:
        p.old.write(args.output/'failure.json',{'schema':SCHEMA,'status':'unknown_saved_audit_failed',
            'error':repr(error),'source':str(args.source.resolve()),'native_executions':0})
        raise


if __name__=='__main__':main()
