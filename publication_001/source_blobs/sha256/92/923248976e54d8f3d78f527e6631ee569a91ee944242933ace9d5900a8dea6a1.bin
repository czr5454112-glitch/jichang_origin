"""Fresh original-map bridge campaign. Preparation never loads a native module.

Frozen005 infrastructure is reused through private FunctionType namespaces,
not mutation of any imported module. Only this new campaign may dispatch its
single worker, under the separate owned-Job launcher.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import FunctionType, SimpleNamespace
from . import cooperative_bridge_policy as policy

base=policy.base
ROOT,OUT=base.ROOT,base.OUT
SCHEMA='g31.original_cooperative_bridge.campaign.v1'
MODULE='scripts.experiments.g31_ics_circulation.research_original_cooperative_bridge'
CASE='bridge'
LIMIT=2400.
PROTOTYPE=OUT/'cooperative_bridge_policy_prepare_002'
PROTOTYPE_SHA='eb3975a6cb7528bfadd147d9f0079af32160e40627e885e9b4d001bb4c39fe81'
require=base.require


def clone(function,namespace):
    value=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    value.__kwdefaults__=deepcopy(function.__kwdefaults__)
    value.__annotations__=dict(function.__annotations__)
    return value


def source_paths():
    pending=[Path(__file__),Path(__file__).with_name('verify_original_cooperative_bridge.py'),
        Path(__file__).with_name('launch_original_cooperative_bridge.py'),
        ROOT/'tests/test_g31_circulation_cooperative_bridge_campaign.py',
        ROOT/'tests/test_g31_circulation_cooperative_bridge_policy.py',
        ROOT/'tests/test_g31_circulation_current_possession_permit.py']
    found=set()
    def enqueue(target):
        for path in (target.with_suffix('.py'),target/'__init__.py'):
            if path.is_file() and path.resolve().is_relative_to(ROOT):
                pending.append(path)
                for parent in path.parents:
                    if parent==ROOT:break
                    if (parent/'__init__.py').is_file():pending.append(parent/'__init__.py')
    while pending:
        path=pending.pop().resolve()
        if path in found:continue
        require(path.is_file(),'bridge_source_missing');found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node,ast.ImportFrom):
                for prefix in ([path.parent] if node.level else [ROOT,ROOT/'src',ROOT/'tests']):
                    for _ in range(max(0,node.level-1)):prefix=prefix.parent
                    if node.module:prefix=prefix.joinpath(*node.module.split('.'));enqueue(prefix)
                    for item in node.names:
                        if item.name!='*':enqueue(prefix/item.name)
            elif isinstance(node,ast.Import):
                for item in node.names:
                    for prefix in (ROOT,ROOT/'src'):enqueue(prefix.joinpath(*item.name.split('.')))
    return sorted(found)


def contract():
    return {**policy.scope(),'status':'fresh_finite_native_candidate_unexecuted',
        'shared_parent_seconds':LIMIT,'native_workers_at_once':1,'native_branches':1,
        'no_original_contract_change':'All original28506 jobs/22 trays/R1false/FIFO/mandatoryStorage/cap0/input order retained.',
        'budget_basis':'Fixed39 completion necessary bound;78 postparking empty requests;100 total physical requests. Neither39 attainable nor all jobs successful is asserted.',
        'startup_reference_only':'Only original005 startup through first-supply next complete boundary is compared. Oldcap8 is not a same-policy performance/protection control.',
        'complete_evidence':'Exact wholeAPI replay using BridgeOwner; alloffered jobs,22 identities,21 stationary parked,actual EMPTY_RECEIVED perphysical request and token LOAD/UNLOAD/HOLD/FIFO/Storage receipts. Full-day observation is reported independently of whether39/78 cap was reached; cap certificate separately requires both actual cap proofs and delivered terminal relay ACKs.',
        'cost':'Whole2400 includes child setup/imports/native/codec/tape/diagnostics/one saved replay/export. External launch-to-exit additionally recorded; API and owner clocks are diagnostic scopes, not production business requests.',
        'failure':'Any policy failure keeps unknown while continuing immutable retries/nativeH. Timeout/nonzero retains manifested prefix and denominator; no retrying a prepared campaign.'}


def operations(raw):
    rows=[]
    for owner in raw['owners']:
        if owner.get('supply'):
            s=owner['supply'];rows.append({'request_id':s['request_id'],'at':s['at'],
                'kind':'direct_supply','job':s['choice']['job'],'source':s['choice']['tray']['node'],
                'destination':s['choice']['job']['origin'],'owner':owner['owner'],'first':True})
        for s in owner.get('operations',[]):
            rows.append({'request_id':s['request_id'],'at':s['at'],'kind':s['choice']['kind'],
                'job':s['choice']['selected_current_job'],'source':s['request']['source'],
                'destination':s['request']['destination'],'owner':owner['owner'],'first':False,
                'decision':s})
    return sorted(rows,key=lambda r:(r['at'],r['request_id']))


def assess(raw,plan):
    rows=operations(raw);token=plan['parking_plan']['token_tray_id']
    supplies=[r for r in rows if r['kind']=='direct_supply'];bridges=[r for r in rows if r['kind']=='bridge_empty']
    receipts=raw['result']['receipts'];unloads=[r for r in receipts if r['event']=='UNLOAD_COMPLETE' and r['tray_id']==token]
    physical=[r for o in raw['owners'] for r in o['outbox']['outbox'].values() if r['kind']=='transfer']
    received=(len(physical)==22+len(rows) and all(r['terminal'] and
        (r.get('client_view',{}).get('last_delivered_ack') or {}).get('status')=='received' for r in physical))
    full=(raw['status']=='horizon_complete' and raw['physical_time']==policy.HORIZON
        and raw['result']['advance']['horizon_complete'] is True and not any(o['failure'] for o in raw['owners']))
    relays={o['owner']:policy.cap_relay_evidence(o,plan['parking_plan'],plan['public_contract']) for o in raw['owners']}
    return {'schema':SCHEMA,'status':'candidate_full_horizon_pending_independent_audit' if full else 'unknown_incomplete_or_failed',
        'offered':28506,'horizon':raw['physical_time'],'full_horizon_without_policy_failure':full,
        'startup_parking_requests':22,'postparking_empty_requests':len(rows),'direct_supplies':len(supplies),
        'bridge_operations':len(bridges),'actual_token_unloads':len(unloads),'all_physical_received':received,
        'historical_cap_relays':relays,'strict_protection':'unknown_unfinished_offered_jobs',
        'alloffered_business_success':False,'complete_100ms_certified':False}


def verify_pins(output,plan,runtime=False):
    require(base.sha(base.__file__)==policy.reuse.BASE_SHA,'frozen005_changed')
    require(plan['schema']==SCHEMA and plan['horizon']==policy.HORIZON and plan['bridge_contract']==contract()
        and plan['max_physical_requests']==policy.MAX_PHYSICAL and plan['max_ticks']==policy.MAX_TICKS
        and plan['parent_timeout_seconds']==LIMIT,'bridge_scope_changed')
    require(set(plan['source_before'])=={str(p) for p in source_paths()},'bridge_complete_source_domain')
    base.verify_pins(output,plan,runtime)
    for name,h in plan['prototype_pins'].items():require(base.sha(PROTOTYPE/name)==h,'bridge_prototype_changed')
    for name,h in plan['bootstrap_pins'].items():require(base.sha(Path(plan['bootstrap_reference'])/name)==h,'bridge_bootstrap_changed')


class MeasuredTape(base.Tape):
    """Preserve the entire frozen tape row; extra clocks have their own file."""
    def __init__(self,session,directory):
        super().__init__(session,directory)
        self.clock_path=directory.parent/'service_clocks.jsonl'
        self.clock_path.open('x',encoding='utf-8').close()
        self.api_persisted_bytes=0
    def clock(self,row):
        with self.clock_path.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n');stream.flush()
    def __getattr__(self,name):
        method=super().__getattr__(name)
        def call(*args,**kwargs):
            ordinal=len(self.rows);start=time.perf_counter_ns()
            try:return method(*args,**kwargs)
            finally:
                if len(self.rows)>ordinal:
                    item=self.rows[ordinal]
                    self.api_persisted_bytes+=(self.directory/item['path']).stat().st_size+len((json.dumps(item)+'\n').encode('utf-8'))
                self.clock({'scope':'complete_frozen_api_and_tape_write','ordinal':ordinal,
                    'endpoint':name,'start_ns':start,'end_ns':time.perf_counter_ns()})
        return call


def measured_run(session,plan,progress=None):
    class MeasuredOwner(policy.BridgeOwner):
        def activate(self):
            start=time.perf_counter_ns();before=len(session.rows)
            try:return super().activate()
            finally:session.clock({'scope':'owner_activation_including_tape_clocks','owner':self.owner,
                'logical_time':session.physical_time,'first_api':before,'after_api':len(session.rows),
                'start_ns':start,'end_ns':time.perf_counter_ns()})
    return clone(policy.run_policy,{**policy.run_policy.__globals__,'BridgeOwner':MeasuredOwner})(session,plan,progress)


def isolated_base(**overrides):
    """Every copied base function resolves only private bindings; no setattr."""
    namespace=dict(vars(base))
    for name,value in vars(base).items():
        if isinstance(value,FunctionType) and value.__globals__ is vars(base):namespace[name]=clone(value,namespace)
    namespace.update(SCHEMA=SCHEMA,HORIZON=policy.HORIZON,MAX_TICKS=policy.MAX_TICKS,
        MAX_PHYSICAL=policy.MAX_PHYSICAL,source_paths=source_paths,verify_pins=verify_pins,
        run_policy=policy.run_policy,assess=assess,Tape=MeasuredTape)
    namespace.update(overrides)
    return SimpleNamespace(**namespace)


def worker(output):
    """Only enrich diagnostic progress; no diagnostic value reaches a policy."""
    started=time.perf_counter_ns();latest={}
    require(not (output/'worker_elapsed.json').exists(),'bridge_worker_measurement_exists')
    with (output/'worker_measurement_claim.json').open('x',encoding='utf-8') as stream:
        json.dump({'status':'claimed_never_reuse','started_perf_ns':started},stream)
    def write(path,value):
        if path.name=='heartbeat.json':
            value={**value,**latest,'available_disk_bytes':shutil.disk_usage(output).free,
                'progress_scope':'Public delivered completion receipts are a lower bound until final offline result. No diagnostic is supplied to the owner policy.'}
        base.write(path,value)
    def run(session,plan,progress):
        def update(tick,owners):
            physical=[c for o in owners for c in o.client.calls if c['kind']=='transfer' and not c['retry']]
            known={jid for o in owners for jid in (o.last_barrier or {}).get('token_completed_job_ids',[])}
            latest.update(delivered_actual_completed_count=len(known),completed_job_ids_from_delivered_facts=sorted(known),
                physical_requests_submitted=len(physical),postparking_empty_requests_submitted=max(0,len(physical)-22),
                bridge_requests_submitted=sum(s['choice']['kind']=='bridge_empty' for o in owners for s in o.operations),
                api_rows=len(session.rows),api_persisted_bytes=session.api_persisted_bytes,
                publication_counts={o.owner:o.publications for o in owners})
            progress(tick,owners)
        return measured_run(session,plan,update)
    try:isolated_base(run_policy=run,write=write).worker(output)
    finally:base.write(output/'worker_elapsed.json',{'elapsed_ns':time.perf_counter_ns()-started,
        'scope':'Worker function entry through all native/policy/tape/final raw and assessment export; child process record includes Python imports and this final export. No per-business100ms claim.'})


def prepare(output,tests_xml):
    require(not output.exists(),'bridge_output_exists')
    require(base.sha(PROTOTYPE/'preregistered_protocol.json')==PROTOTYPE_SHA,'bridge_source_prototype')
    import xml.etree.ElementTree as ET
    suites=list(ET.parse(tests_xml).getroot().iter('testsuite'))
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    require(counts['tests']>0 and all(counts[k]==0 for k in ('failures','errors','skipped')),'bridge_pure_gate')
    output.mkdir(parents=True)
    case=output/CASE;private=isolated_base()
    source=OUT/'original_low_wip_prepare_005/input.json.gz'
    binary=ROOT/'build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd'
    plan=private.prepare(case,source,binary)
    plan.update(parent_timeout_seconds=LIMIT,bridge_contract=contract(),
        execution_amendment='Fresh bridge policy; frozen prior005 and cap8 artifacts are not amended.',
        policy_contract=contract(),assessment='Actual whole-horizon finite evidence only; cap39 is not business success.',
        bootstrap_reference=str(OUT/'original_low_wip_prepare_005'),
        bootstrap_pins={n:base.sha(OUT/'original_low_wip_prepare_005'/n) for n in
            ('receipt.json','raw_final.json.gz','api/manifest.jsonl','input.json.gz')},
        prototype_pins={n:base.sha(PROTOTYPE/n) for n in ('preregistered_protocol.json','prepare_receipt.json')})
    base.write(case/'preregistered_protocol.json',plan);verify_pins(case,plan,runtime=True)
    campaign={'schema':SCHEMA,'contract':contract(),'case_plans':{CASE:base.sha(case/'preregistered_protocol.json')},
        'source_before':plan['source_before'],'interpreter':{'path':sys.executable,'sha256':base.sha(sys.executable)},
        'tests':{'path':str(tests_xml.resolve()),'sha256':base.sha(tests_xml),'counts':counts},
        'parent_seconds':LIMIT,'native_workers_at_once':1,'native_executions':0}
    base.write(output/'campaign.json',campaign);base.write(output/'branch_ledger.json',{CASE:{'status':'unknown_unexecuted'}})
    return campaign


def verify_campaign(output):
    value=base.read(output/'campaign.json')
    require(value['schema']==SCHEMA and value['contract']==contract() and set(value['case_plans'])=={CASE}
        and value['parent_seconds']==LIMIT and value['native_workers_at_once']==1,'bridge_campaign_scope')
    require(value['source_before']=={str(p):base.sha(p) for p in source_paths()},'bridge_campaign_sources')
    require(base.sha(value['interpreter']['path'])==value['interpreter']['sha256']
        and base.sha(value['tests']['path'])==value['tests']['sha256'],'bridge_campaign_tools')
    case=output/CASE;require(base.sha(case/'preregistered_protocol.json')==value['case_plans'][CASE],'bridge_case_changed')
    verify_pins(case,base.read(case/'preregistered_protocol.json'));return value


def campaign_worker(output,admission):
    require(sys.stdin.readline().rstrip('\n')==admission,'bridge_job_admission')
    require(base.sha(output/'campaign.json')==admission==base.read(output/'external_launch_claim.json')['campaign_sha256'],'bridge_campaign_identity')
    began=time.monotonic();verify_campaign(output);case=output/CASE
    isolated_base().claim_execution(case,base.read(case/'preregistered_protocol.json'))
    ledger={CASE:{'status':'unknown_in_progress'}};base.write(output/'branch_ledger.json',ledger)
    def child(flag,log):
        remaining=LIMIT-(time.monotonic()-began)
        if remaining<=0:return {'status':'unknown_shared_budget','exit_code':None}
        command=[sys.executable,'-m',MODULE,'--output',str(output),flag];start=time.monotonic()
        with log.open('xb') as stream:
            try:
                code=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=remaining).returncode
                status='child_finished' if code==0 else 'unknown_child_nonzero'
            except subprocess.TimeoutExpired:code=None;status='unknown_shared_timeout'
            except OSError as error:
                code=None;status='unknown_dispatch_error';stream.write(repr(error).encode('utf-8'));stream.flush()
        return {'status':status,'exit_code':code,'command':command,'wall_seconds':time.monotonic()-start,'allowed_seconds':remaining}
    execution=child('--worker',case/'worker.log')
    verification=child('--verify',case/'verification.log') if execution['exit_code']==0 else {'status':'unknown_worker_incomplete','exit_code':None}
    verified=base.read(case/'independent_verification.json') if verification['exit_code']==0 else None
    ledger[CASE]={'status':'saved_replay_passed' if verified else 'unknown_incomplete_case','execution':execution,'verification':verification}
    base.write(output/'branch_ledger.json',ledger);verify_campaign(output)
    complete=verified is not None and verified['status']=='complete_finite_bridge_observation'
    receipt={'schema':SCHEMA,
        'campaign_sha256':admission,'cases':ledger,'source_changed':[],
        'assessment':None if verified is None else verified['assessment'],'offered':28506,
        'strict_protection':'unknown_unfinished_offered_jobs','alloffered_business_success':False,'complete_100ms_certified':False}
    names=('raw_final.json.gz','assessment.json','api/manifest.jsonl','service_clocks.jsonl','all_job_states.json.gz',
        'independent_verification.json','worker.log','verification.log','worker_elapsed.json','error_prefix.json.gz')
    receipt['artifact_sha256']={str(p.relative_to(output)):base.sha(p) for p in [output/'branch_ledger.json',*[case/n for n in names]] if p.is_file()}
    elapsed=time.monotonic()-began
    receipt.update(status='completed_finite_campaign' if complete and elapsed<=LIMIT else 'unknown_incomplete_campaign',wall_seconds=elapsed)
    base.write(output/'receipt.json',receipt);return 0 if receipt['status']=='completed_finite_campaign' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--tests-xml',type=Path)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--verify',action='store_true')
    parser.add_argument('--campaign',action='store_true');parser.add_argument('--admission')
    args=parser.parse_args();output=args.output.resolve()
    require(sum((args.prepare,args.worker,args.verify,args.campaign))==1,'bridge_mode')
    if args.prepare:prepare(output,args.tests_xml);return
    if args.campaign:raise SystemExit(campaign_worker(output,args.admission))
    if args.worker:worker(output/CASE);return
    from .verify_original_cooperative_bridge import verify_case
    result=verify_case(output/CASE);target=output/CASE/'independent_verification.json'
    require(not target.exists(),'bridge_verification_exists');base.write(target,result)


if __name__=='__main__':main()
