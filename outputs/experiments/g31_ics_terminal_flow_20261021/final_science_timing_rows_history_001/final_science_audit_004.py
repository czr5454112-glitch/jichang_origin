"""Offline final DEV audit. Default is check-only; --execute requires all 28 closed.

No native constructor, budget mutation, ACK export read, or policy dispatch.
The historical filename is retained; source/workflow are explicit CLI bindings.
Imports audited helpers only from that workflow's frozen source tree.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import copy
import gzip
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import re
import sys

PARENTS = (2201, 2202, 2203, 2204)
PHASES = {'bridge': ('C00','C10','TF-current','TF-B1-60'), 'bins': ('TF-B1-300',),
    'period': ('TF-B1-300-replan300',), 'predictor': ('TF-predictor',)}
PAIRS = (('C00','C10'), ('C00','TF-current'), ('TF-current','TF-B1-60'),
    ('TF-B1-60','TF-B1-300'), ('TF-B1-300','TF-B1-300-replan300'), ('TF-B1-300','TF-predictor'))
AXES = (('demand_information',), ('selector_algorithm','allocator'), ('demand_information',),
    ('forecast_bin_edges_seconds',), ('recompute_period_seconds',), ('demand_model',))
PUBLICATION_LIMIT_BYTES = 95_000_000
RUN_EVIDENCE_FILES = ('plan.json','receipt.json','worker_report.json','trajectory.json.gz',
    'terminal_evidence.json.gz','decisions.json.gz','calls.json.gz','observations.json.gz',
    'arrival_support_contract.json','arrival_support_receipts.json')

def need(ok, reason):
    if not ok: raise ValueError('final_science:'+reason)

def read(path):
    path=Path(path)
    with (gzip.open(path,'rt',encoding='utf8') if path.suffix=='.gz' else path.open(encoding='utf8')) as f:
        return json.load(f)

def bind(path):
    path=Path(path).resolve(); h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return dict(path=str(path),sha256=h.hexdigest())

def bound_read(ref):
    need(set(('path','sha256'))<=set(ref),'binding_fields_missing')
    need(bind(ref['path'])['sha256']==ref['sha256'],'bound_file_changed:'+ref['path'])
    return read(ref['path'])

def verify_bindings(refs, reason):
    for ref in refs:
        need(bind(ref['path'])['sha256']==ref['sha256'],reason+':'+ref['path'])

def fresh(path, value):
    path=Path(path)
    need(not path.exists(),'fresh_output_required:'+str(path))
    if path.suffix=='.gz':
        with path.open('xb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed:
            with io.TextIOWrapper(compressed,encoding='utf8',newline='\n') as f:
                json.dump(value,f,ensure_ascii=False,allow_nan=False,separators=(',',':'));f.write('\n')
    else:
        with path.open('x',encoding='utf8') as f:
            json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')
    size=path.stat().st_size
    need(size<PUBLICATION_LIMIT_BYTES,'artifact_over_publication_limit_keep_local_hash_only:'+str(path))
    return dict(bind(path),bytes=size,publication_size_limit_bytes=PUBLICATION_LIMIT_BYTES)

def verify_sources(source_ref):
    manifest=bound_read(source_ref); root=Path(source_ref['path']).resolve().parent
    need(re.fullmatch(r'terminal_flow_runtime_\d+',root.name) is not None,'terminal_flow_runtime_source_required')
    need(Path(manifest['root']).resolve()==root,'manifest_root_mismatch')
    need(bool(manifest['files']),'empty_source_manifest')
    for relative,sha in manifest['files'].items():
        path=(root/relative).resolve()
        need(path.is_relative_to(root),'source_path_escape')
        need(bind(path)['sha256']==sha,'frozen_source_changed:'+relative)
    return root

def workflow_blocks(path, source_ref):
    """Only declared full DEV phases; predecessor, export gate and TRAIN excluded."""
    path=Path(path).resolve();workflow_ref=bind(path);workflow=bound_read(workflow_ref)
    need(workflow['schema']=='g31.terminal_flow.finite_development_workflow.v1','workflow_schema')
    need(workflow['source_bundle']==source_ref,'workflow_source_binding')
    need(workflow['TEST_unlocked'] is False and workflow['R1_enabled'] is False,'locked_workflow_required')
    phases={};root=path.parent.parent
    need(root.name=='terminal_flow','workflow_terminal_flow_location')
    for stage in workflow['stages']:
        if stage['phase'] not in PHASES:continue
        phase=stage['phase'];need(phase not in phases,'duplicate_workflow_phase')
        need(set(stage['parents'])==set(PARENTS) and len(stage['parents'])==4,'workflow_four_dev_parents')
        destination=(root/stage['name']/'block.json').resolve()
        need(destination.parent.parent==root,'workflow_stage_path_escape')
        phases[phase]=destination
    need(set(phases)==set(PHASES),'workflow_full_phases_missing')
    return [phases[p] for p in PHASES],workflow_ref

def load_helpers(root):
    # An existing scripts import from the working tree would silently undermine freezing.
    need(not any(k=='scripts' or k.startswith('scripts.') for k in sys.modules),'run_driver_in_fresh_python_process')
    sys.path.insert(0,str(root))
    package='scripts.experiments.g31_ics_circulation.'
    names=dict(service='foundation_airport_terminal_service_audit',behavior='foundation_airport_terminal_behavior_summary',
        flow='foundation_airport_terminal_flow_audit',timing='foundation_airport_transport_timing_audit',
        campaign='foundation_airport_transport_campaign',stream='foundation_airport_json_stream',
        projection='foundation_airport_inventory_projection',allocation='foundation_airport_transport_allocation',
        digest='foundation_airport_batch_patch')
    helpers={k:importlib.import_module(package+name) for k,name in names.items()}
    for name,module in list(sys.modules.items()):
        if name.startswith('scripts.') and getattr(module,'__file__',None):
            need(Path(module.__file__).resolve().is_relative_to(root),'nonfrozen_import:'+name)
    return helpers

def pair_contract(a,b,allowed, contract_fn):
    left,right=contract_fn(a),contract_fn(b)
    need(left.keys()==right.keys(),'comparison_fields_missing')
    changed={k:dict(reference=left[k],candidate=right[k]) for k in left if left[k]!=right[k]}
    need(set(changed)<=set(allowed),'unregistered_pair_axis:'+','.join(sorted(set(changed)-set(allowed))))
    return dict(allowed_differences=list(allowed),observed_differences=changed)

def inspect_blocks(paths, source_ref, h):
    need(len(paths)==4 and len({str(Path(p).resolve()) for p in paths})==4,'exactly_four_unique_blocks_required')
    rows={}; phases=set(); refs=[]; pending=[]
    for path in paths:
        if not Path(path).exists():
            pending.append(dict(block=str(path),status='not_registered'));continue
        block_ref=bind(path);block=bound_read(block_ref);refs.append(block_ref);phase=block['phase']
        need(phase in PHASES and phase not in phases,'duplicate_or_nonfull_phase')
        phases.add(phase)
        need(block['source_bundle']==source_ref,'block_source_binding')
        need(set(block['parents'])==set(PARENTS) and len(block['parents'])==4,'all_four_dev_parents_required')
        need(tuple(block['methods'])==PHASES[phase],'registered_method_set')
        h['campaign']._validate_block_manifest(block)
        for ref in block['task_plans']:
            p=bound_read(ref); key=(p['parent']['parent_seed'],p['method']); directory=Path(ref['path']).parent
            need(key not in rows,'duplicate_parent_method')
            need(p['source_bundle']==source_ref and p['horizon']==59400. and p['activation']==7200.,'full_same_source_plan_required')
            need(p['parent']['split']=='dev' and p['parent']['synthetic'] is True,'synthetic_dev_only')
            need(not h['campaign'].method_contract_errors(p),'method_contract_error')
            rows[key]=dict(plan=p,directory=directory,plan_binding=ref)
            receipt_path=directory/'receipt.json'
            if not receipt_path.exists(): pending.append(dict(task_id=p['task_id'],status='receipt_missing'));continue
            receipt=read(receipt_path)
            if receipt.get('worker',{}).get('scientific_status')!='closed':
                pending.append(dict(task_id=p['task_id'],status=receipt.get('worker',{}).get('scientific_status','unknown')));continue
            h['flow'].closed_run(directory)  # receipt, worker equality, exact clock and trajectory completeness
            timing=receipt['worker']['policy_timing']
            need(all(k in timing for k in ('count','total_seconds','scope','stages','stage_scope','complete_request_100ms_certified')),
                'segmented_callback_timing_fields_missing')
            need('excluded' in timing['stage_scope'] and timing['complete_request_100ms_certified'] is False,'timing_scope_missing')
    expected={(p,m) for p in PARENTS for methods in PHASES.values() for m in methods}
    if not pending:
        need(phases==set(PHASES) and set(rows)==expected,'all_28_registered_runs_required')
        need(len({r['plan']['parent']['common_historical_template_sha256'] for r in rows.values()})==1,
            'declared_shared_historical_template_binding')
    axes=[]
    for parent in PARENTS:
        for (a,b),allow in zip(PAIRS,AXES):
            if (parent,a) in rows and (parent,b) in rows:
                axes.append(dict(parent=parent,reference_method=a,candidate_method=b,
                    **pair_contract(rows[(parent,a)]['plan'],rows[(parent,b)]['plan'],allow,h['campaign'].comparison_contract)))
    return rows,dict(status='pending' if pending else 'ready',pending=pending,registered_runs=len(rows),
        expected_runs=28,expected_scientific_pairs=24,blocks=refs,pair_contracts=axes,
        all_four_parents_share_one_historical_template=True if not pending else None,independent_airport_days=False)

def finite_nonnegative(value, name):
    need(type(value) in (int,float) and math.isfinite(value) and value>=0,name)
    return value

def unique_solve_cost(decisions):
    values={}
    for d in decisions:
        plan=d['selection'].get('flow_plan')
        if plan is None: continue
        seconds=finite_nonnegative(plan['solve_seconds'],'finite_solve_seconds_required')
        pid=plan['plan_id']
        need(pid not in values or values[pid]==seconds,'same_plan_changed_original_solve_time')
        values[pid]=seconds
    return dict(unique_plans=len(values),total_original_solve_seconds=sum(values.values()),
        original_solve_seconds=list(values.values()),cache_hits_are_not_new_solve_time=True,
        not_total_callback_time=True)

class ObservationJoin:
    """Monotone two-owner stream join; only current-time observations retained."""
    def __init__(self, directory, selected, h, cutoff):
        self.h=h;self.iterator=h['stream'].iter_json_array_gz(directory/'observations.json.gz')
        self.now=-1.;self.cache={};self.count=0;self.samples=defaultdict(list);self.windows=defaultdict(list)
        for row in selected:
            self.windows[row['requested_action']['source']].append((row['decision_time'],min(cutoff,row['decision_time']+600.)))
        self.until=max((b for v in self.windows.values() for _,b in v),default=-1.)
    def next(self):
        record=next(self.iterator);obs=record['observation'];now=obs['now']
        need(now>=self.now,'observation_order_reversed')
        if now!=self.now:self.cache={}
        self.now=now;self.count+=1
        digest=record['digest']
        need(self.h['digest'].digest(obs)==digest,'observation_digest_mismatch')
        self.cache[digest]=obs
        nodes={n for n,windows in self.windows.items() if any(a<now<=b for a,b in windows)}
        if nodes:
            prepared=self.h['projection'].prepare_inventory_projection(obs)
            for node in nodes:
                state=prepared.nodes[node]
                if state['local']:self.samples[node].append(dict(at=now,
                    stock=state['stock'] if state['inventory_known'] else None,
                    waiting=state['waiting'] if state['waiting_known'] else None))
        return obs
    def get(self,decision):
        digest=decision['public_observation_ref'];time=decision['decision_time']
        while digest not in self.cache:
            need(self.now<=time,'decision_observation_not_in_same_time_group')
            try:self.next()
            except StopIteration:raise ValueError('final_science:bound_observation_missing')
        obs=self.cache[digest]
        need(obs['now']==time and obs['owner_id']==decision['owner_id'],'decision_observation_time_owner_mismatch')
        return obs
    def finish(self):
        while self.now<=self.until:
            try:self.next()
            except StopIteration:break
        self.iterator.close()

class DecisionJoin:
    """Cross-bind every in-window decision to its immutable exported trajectory."""
    def __init__(self, trajectory_rows, start, end):
        self.rows={};self.seen=set();self.start=start;self.end=end;calendar=set()
        for row in trajectory_rows:
            identity=row['decision_id'];key=(row['owner_id'],row['decision_time'])
            need(identity not in self.rows,'duplicate_trajectory_decision_id')
            need(key not in calendar,'duplicate_trajectory_owner_time')
            self.rows[identity]=row;calendar.add(key)
    def accept(self, decision):
        identity=decision['decision_id']
        if identity not in self.rows:
            need(not self.start<=decision['decision_time']<self.end,'in_window_decision_missing_from_trajectory')
            return False
        need(identity not in self.seen,'duplicate_selected_decision_id')
        row=self.rows[identity]
        for key in ('owner_id','decision_time','public_observation_ref','legal_catalog_ref','requested_action'):
            need(decision[key]==row[key],'decision_trajectory_mismatch:'+key)
        need(decision['catalog']['catalog_id']==row['legal_catalog_ref'],'decision_catalog_binding_mismatch')
        self.seen.add(identity)
        return True
    def finish(self):
        need(self.seen==set(self.rows),'selected_trajectory_decision_missing')

def timing_decision(d, h, join, support, support_receipts, stats):
    """Frozen timing-audit ranking equations, with streamed bound current state."""
    plan=d['selection'].get('flow_plan')
    if plan is None:return
    counts=stats['counts'];counts['valid_flow_decisions']+=1
    verification=d['flow_verification'];stats['invalid'].update(r['reason'] for r in verification.get('invalid',[]))
    action=d['requested_action']
    if action['kind']=='transfer':
        counts['selected_transfers']+=1
        if verification.get('exact_net_gain') is not None:
            stats['gain_gaps'].append(plan['objective']['net_proxy_gain']-verification['exact_net_gain'])
    if any(plan['receiver_claims_deducted'].values()):
        counts['excluded_pending_claims_no_counterfactual_reconstruction']+=1;return
    receivers={r['node']:r['receiver'] for r in plan['station_table']}
    candidates=[r for r in d['catalog']['candidates'] if r['action_type']=='transfer'
        and receivers[r['destination']]['known'] and receivers[r['destination']]['available_slots']>0]
    if any(r['source_category']=='ordinary_return' for r in candidates):
        candidates=[r for r in candidates if r['source_category']=='ordinary_return']
    if len({(r['source'],r['destination']) for r in candidates})<2:
        counts['fewer_than_two_eligible_od_candidates']+=1;return
    obs=join.get(d);forecast=(d.get('forecast_binding') or {}).get('forecast')
    projection=h['projection'].prepare_inventory_projection(obs,forecast=forecast,
        horizon_seconds=plan['projection_horizon_seconds'],supply_mode=plan['supply_mode'],
        arrival_support_contract=support,arrival_support_receipt=support_receipts[d['owner_id']])
    scores=[]
    for candidate in candidates:
        common=copy.copy(candidate)
        common['nominal_arrival_time']=projection.now+plan['config']['marginal_reference_available_offset_seconds']
        common['earliest_departure']=min(common['earliest_departure'],common['nominal_arrival_time'])
        ref=h['projection'].project_action(projection,common);exact=h['projection'].project_action(projection,candidate)
        feature=d['candidate_features'][candidate['action_id']]
        recorded=feature['features_forecast']['forecast_proxy_gain'] if forecast is not None else feature['features_current']['current_proxy_gain']
        need((recorded is None)==(exact['proxy_gain'] is None),'timing_reconstruction_knownness_differs')
        need(recorded is None or abs(recorded-exact['proxy_gain'])<=1e-7,'timing_reconstruction_differs_from_saved_feature')
        counts['reconstructed_candidate_checks']+=1
        if not ref['known'] or not exact['known']:continue
        cost=h['allocation'].transport_cost(candidate,plan['config'])
        scores.append((candidate,ref['proxy_gain']-cost,exact['proxy_gain']-cost,
            exact['proxy_gain']-plan['config']['transport_penalty_weight']*candidate['static_travel_time']))
    counts['known_multi_source_ranking_opportunities']+=len({r[0]['source'] for r in scores})>1
    if len({(r[0]['source'],r[0]['destination']) for r in scores})<2:
        counts['fewer_than_two_known_scored_od_candidates']+=1;return
    counts['known_multi_od_ranking_opportunities']+=1
    ordinary=scores[0][0]['source_category']=='ordinary_return'
    def best(index):
        ranked=sorted(scores,key=lambda r:(-r[index],r[0]['nominal_arrival_time'],r[0]['source'],r[0]['destination'],str(r[0]['tray_id'])))
        return ranked[0] if ordinary or ranked[0][index]>plan['config']['minimum_net_gain'] else None
    reference,exact,actualcost=best(1),best(2),best(3)
    identity=lambda r:h['timing']._identity(None if r is None else r[0])
    changed=identity(reference)!=identity(exact)
    counts['eta_only_best_first_changes_including_hold']+=changed
    counts['eta_only_source_or_destination_ranking_changes']+=changed and reference is not None and exact is not None
    actual=h['timing']._identity(action if action['kind']=='transfer' else None)
    counts['full_exact_menu_best_differs_from_selected']+=identity(actualcost)!=actual
    if (changed or identity(actualcost)!=actual) and len(stats['examples'])<30:
        stats['examples'].append(dict(decision_id=d['decision_id'],decision_time=d['decision_time'],owner=d['owner_id'],
            common_time_best=identity(reference),exact_same_cost_best=identity(exact),exact_actual_cost_best=identity(actualcost),
            selected=actual))

def selected_lifecycle(trajectory,terminal):
    native={r['request_id']:r for r in terminal['transfers']};rows=[];seen=set()
    for d in trajectory['rows']:
        action=d['requested_action']
        if action['kind']!='transfer':continue
        rid=d.get('request_id')
        if rid is not None:
            need(rid not in seen,'unique_selected_native_request_required');seen.add(rid)
            need(rid in native,'selected_request_missing_terminal')
        actual=native[rid] if rid is not None else None
        received=actual is not None and actual['status']=='received' and actual['received_at']>=0
        failed=actual is not None and actual['status'] in ('failed','rejected','expired','cancelled')
        need(bool(d.get('received_event'))==received,'trajectory_native_received_join_disagrees')
        rows.append(dict(decision_id=d['decision_id'],owner_id=d['owner_id'],selected_at=d['decision_time'],
            source=action['source'],destination=action['destination'],tray_id=action['tray_id'],request_id=rid,
            classification='ordinary_return' if action['source_category']=='ordinary_return' else 'extra_reposition',
            accepted=any(a.get('status') in ('accepted','granted','dispatching','departed','in_transit','received') for a in d['ack'] or []),
            actual_submission=d['actual_submission'],first_edge_event=d.get('first_edge_event'),received_event=d.get('received_event'),
            nominal_arrival=action['nominal_arrival_time'],final_native=actual,
            received=received,failed=failed,missing_execution=rid is None or d['actual_submission'] is None,
            right_censored=actual is not None and not received and not failed,
            eta_error_seconds=actual['received_at']-action['nominal_arrival_time'] if received else None,
            unreceived_eta_lateness_lower_bound_seconds=max(0,trajectory['physical_clock']-action['nominal_arrival_time']) if actual is not None and not received and not failed else None))
    return rows

def run_audit(row,h):
    directory=row['directory']
    # Bind before consumption. The final marker rechecks these exact bytes, including
    # the two support inputs used in reconstruction; no owner ACK export is opened.
    evidence={name:bind(directory/name) for name in RUN_EVIDENCE_FILES}
    plan,receipt,trajectory=h['flow'].closed_run(directory)
    terminal=read(directory/'terminal_evidence.json.gz')
    selected=[r for r in trajectory['rows'] if r['requested_action']['kind']=='transfer']
    decisions_join=DecisionJoin(trajectory['rows'],plan['activation'],plan['horizon']);compact=[]
    join=ObservationJoin(directory,selected,h,plan['horizon'])
    support=read(directory/'arrival_support_contract.json');support_receipts=read(directory/'arrival_support_receipts.json')
    stats=dict(counts=Counter(),invalid=Counter(),gain_gaps=[],examples=[])
    def stream():
        for d in h['stream'].iter_json_array_gz(directory/'decisions.json.gz'):
            if decisions_join.accept(d):
                join.get(d)  # Validate every selected observation, including HOLD and C00.
                timing_decision(d,h,join,support,support_receipts,stats)
                # Drop bulky candidate-feature/forecast copies; frozen chain audit keeps original plan/order fields.
                compact.append(dict(decision_id=d['decision_id'],selection={k:d['selection'][k]
                    for k in ('flow_plan','empty_transport_order','fallback_reason','flow_verification') if k in d['selection']}))
            yield d
    behavior=h['behavior'].decision_coverage(stream(),trajectory['rows'])
    decisions_join.finish()
    join.finish()
    need(behavior['decision_counts']['valid_decisions']==len(trajectory['rows']),'complete_decision_denominator')
    chain=h['flow'].audit_records(compact,trajectory['rows'],terminal)
    need(not chain['violations'],'plan_order_chain_violation')
    for p in chain['plans']:
        p.pop('station_table',None)  # Counts/order links/source proposals remain; full station tables stay in immutable decisions.
    lifecycle=selected_lifecycle(trajectory,terminal)
    behavior['source_followup']=h['behavior'].source_windows(selected,join.samples,cutoff=plan['horizon'])
    behavior['reverse_moves']=h['behavior'].reverse_requests(h['stream'].iter_json_array_gz(directory/'calls.json.gz'),terminal,
        selected_request_ids=[r['request_id'] for r in selected])
    solves=unique_solve_cost(compact);solves['distribution']=h['timing']._summary(solves.pop('original_solve_seconds'))
    timing=dict(counts=dict(stats['counts']),verification_invalid_reasons=dict(stats['invalid']),
        proxy_minus_exact_selected_gain=h['timing']._summary(stats['gain_gaps']),examples=stats['examples'],
        unique_plan_solve=solves,measured_callback=receipt['worker']['policy_timing'],
        observations_read=join.count,whole_observation_file_bound=True,observation_tail_not_reparsed=join.now<plan['horizon'],
        all_trajectory_decisions_bound_to_digest_time_owner=True,validated_decision_observation_count=len(decisions_join.seen),
        excluded_pending_claims_are_not_reconstructed=True,
        reconstruction_scope='same frozen timing equations on bound current observations; at least two eligible OD candidates; no ACK file',
        counters_are_decisions_not_independent_scenes=True)
    decisions=[dict(owner_id=r['owner_id'],at=r['decision_time'],public_state=r['public_observation_ref'],catalog=r['legal_catalog_ref'],
        action=[r['requested_action'].get(k) for k in ('kind','tray_id','source','destination')]) for r in trajectory['rows']]
    return dict(task_id=plan['task_id'],method=plan['method'],parent=plan['parent']['parent_seed'],behavior=behavior,
        plan_order_chain=chain,selected_transfer_lifecycle=lifecycle,timing=timing,decision_choices=decisions,
        runtime=dict(worker_wall_seconds=receipt['worker']['wall_seconds'],peak_memory_bytes=receipt['worker']['peak_memory_bytes'],
            scope='whole worker including native and exports; distinct from callback policy_timing'),
        all_native_status_counts=dict(Counter(r['status'] for r in terminal['transfers'])),
        plan_station_tables_omitted_from_summary_but_retained_in_bound_decisions=True,
        full_owner_ack_export_opened=False,native_starts=0,
        evidence_bound_before_consumption=True,evidence=evidence)

def compare_choices(reference,candidate):
    def calendar(run):
        result={(r['owner_id'],r['at']):r for r in run['decision_choices']}
        need(len(result)==len(run['decision_choices']),'duplicate_comparison_owner_time')
        return result
    a,b=calendar(reference),calendar(candidate)
    need(a.keys()==b.keys(),'same_controller_decision_calendar_required')
    same=[];different=[]
    for key,x in a.items():
        y=b[key];same_input=(x['public_state'],x['catalog'])==(y['public_state'],y['catalog'])
        row=dict(owner=key[0],at=key[1],reference=x['action'],candidate=y['action'],same_public_state_and_catalog=same_input)
        if x['action']!=y['action']:different.append(row)
        if same_input:same.append(row)
    def signatures(run):
        rows=[r for r in run['selected_transfer_lifecycle'] if r['actual_submission'] is not None]
        result={(r['owner_id'],r['selected_at'],r['tray_id'],r['source'],r['destination']):r for r in rows}
        need(len(result)==len(rows),'duplicate_submitted_order_signature')
        return result
    x,y=signatures(reference),signatures(candidate)
    return dict(all_paired_decisions=len(a),same_public_state_catalog_decisions=len(same),
        actual_action_changes=len(different),same_state_action_changes=sum(r['reference']!=r['candidate'] for r in same),
        changed_actions=different,reference_only_actual_selected_orders=[x[k] for k in sorted(x.keys()-y.keys())],
        candidate_only_actual_selected_orders=[y[k] for k in sorted(y.keys()-x.keys())],
        same_schedule_different_state_is_closed_loop_outcome_not_isolated_prediction_effect=True)

def local_service(per_bag,specs):
    by_id={r['business_bag_id']:r for r in specs};groups={}
    for row in per_bag:
        origin=by_id[row['business_bag_id']]['origin'];bucket=groups.setdefault(origin,dict(population=0,reference=Counter(),candidate=Counter(),completion=Counter(),lateness=Counter()))
        bucket['population']+=1
        bucket['reference'][row['reference']['status']]+=1;bucket['candidate'][row['candidate']['status']]+=1
        bucket['completion'][row['category']]+=1;bucket['lateness'][row['lateness_direction']]+=1
    return {str(k):{name:dict(v) if isinstance(v,Counter) else v for name,v in b.items()} for k,b in groups.items()}

def aggregate_pairs(rows):
    need(len(rows)==4 and {r['parent'] for r in rows}==set(PARENTS),'four_parent_pair_aggregate_required')
    return dict(parent_count=4,mean_gain_bag_seconds=sum(r['gain_bag_seconds'] for r in rows)/4,
        minimum_gain_bag_seconds=min(r['gain_bag_seconds'] for r in rows),maximum_gain_bag_seconds=max(r['gain_bag_seconds'] for r in rows),
        known_completion_harm_parent_bag_cases=sum(r['completion_direction']['known_direction_harm'] for r in rows),
        known_lateness_harm_parent_bag_cases=sum(r['known_lateness_harm'] for r in rows),
        completed_delta_sum=sum(r['completed_delta'] for r in rows),on_time_delta_sum=sum(r['on_time_delta'] for r in rows),
        all_parent_observed_service_gates_passed=all(r['existing_observed_service_gate_passed'] for r in rows),
        any_parent_service_rejection=any(not r['existing_observed_service_gate_passed'] for r in rows),
        mean_gain_does_not_override_any_service_rejection=True,strict_per_bag_nonharm_certified=False,
        promotion_approved=False,test_unlocked=False,
        sampling_scope='four same-historical-template derived DEV parents; not independent real airport days',
        repeated_business_ids_counted_as_parent_bag_cases_not_unique_real_bags=True)

def execute(rows,status,source_ref,workflow_ref,h,output,producer_ref=None):
    producer_ref=bind(Path(__file__)) if producer_ref is None else producer_ref
    verify_bindings([producer_ref],'analysis_driver_changed_before_execution')
    need(status['status']=='ready','pending_runs_prohibit_science_execution')
    output=Path(output);need(not output.exists(),'fresh_output_directory_required')
    # Revalidate bound source bytes immediately before any science artifact is created.
    verify_sources(source_ref);bound_read(workflow_ref);output.mkdir(parents=True)
    fresh(output/'pending.json',dict(status='in_progress',source_bundle=source_ref,analysis_driver=producer_ref,
        not_a_completed_science_report=True))
    run_reports={};run_refs={}
    for key,row in sorted(rows.items()):
        print(json.dumps(dict(stage='run_audit',parent=key[0],method=key[1])),flush=True)
        report=run_audit(row,h)
        run_refs[key]=fresh(output/f'P{key[0]}_{key[1]}_behavior_timing.json.gz',report)
        # Only compact choices and selected lifecycles are needed for subsequent comparisons.
        run_reports[key]={k:report[k] for k in ('decision_choices','selected_transfer_lifecycle')}
        del report
    evaluated=h['campaign'].evaluate([r['path'] for r in status['blocks']])
    need(evaluated['all_registered_closed'] and evaluated['paired_comparison_complete'] and len(evaluated['paired'])==24,
        'campaign_structural_comparisons_incomplete')
    campaign_ref=fresh(output/'campaign_structural_comparisons_24.json',evaluated)
    pair_rows=[];pair_refs=[]
    for (a,b),allowed in zip(PAIRS,AXES):
        for parent in PARENTS:
            left,right=rows[(parent,a)],rows[(parent,b)]
            print(json.dumps(dict(stage='per_bag_pair',parent=parent,reference=a,candidate=b)),flush=True)
            result=h['service'].compare_runs(left['directory'],right['directory'])
            need(result['population']==28506 and result['population_exclusions']==0,'full_28506_population_required')
            result['parent']=parent
            result['registered_pair_axis']=pair_contract(left['plan'],right['plan'],allowed,h['campaign'].comparison_contract)
            result['actual_order_and_decision_changes']=compare_choices(run_reports[(parent,a)],run_reports[(parent,b)])
            result['local_service_by_original_input_node']=local_service(result['per_bag'],bound_read(left['plan']['input'])['jobs'])
            result['predictor_upgrade_pair']=b=='TF-predictor'
            result['independent_airport_day_claim']=False
            pair_refs.append(fresh(output/f'P{parent}_{a}_to_{b}_per_bag.json.gz',result))
            pair_rows.append({k:v for k,v in result.items() if k not in ('per_bag','physical_contract','evidence','physical_progress')})
            del result
    aggregates=[]
    for a,b in PAIRS:
        chosen=[r for r in pair_rows if r['reference_method']==a and r['candidate_method']==b]
        aggregates.append(dict(reference_method=a,candidate_method=b,**aggregate_pairs(chosen)))
    # Changed source bytes or receipts invalidate the entire final marker, even if partial files exist.
    verify_sources(source_ref);bound_read(workflow_ref)
    end_rows,end_status=inspect_blocks([r['path'] for r in status['blocks']],source_ref,h)
    need(end_status==status and set(end_rows)==set(rows),'registration_or_closure_changed_during_audit')
    for key,row in rows.items():
        for ref in row['plan'].values():
            if isinstance(ref,dict) and set(('path','sha256'))<=set(ref):
                need(bind(ref['path'])['sha256']==ref['sha256'],'bound_plan_dependency_changed_during_audit')
        saved=bound_read(run_refs[key])
        for name,ref in saved['evidence'].items():need(bind(ref['path'])==ref,'evidence_changed_during_audit:'+name)
    verify_bindings(pair_refs+[campaign_ref],'generated_evidence_changed_during_audit')
    verify_bindings([producer_ref],'analysis_driver_changed_during_audit')
    final=dict(schema='g31.terminal_flow.final_science.v1',status='complete',source_bundle=source_ref,workflow=workflow_ref,
        registered_runs=28,scientific_per_bag_pairs=24,scientific_pair_definitions=PAIRS,
        campaign_structural_comparisons_are_separate=True,campaign_structural_comparisons=campaign_ref,
        runs=[dict(parent=k[0],method=k[1],evidence=v) for k,v in sorted(run_refs.items())],
        per_bag_pair_evidence=pair_refs,pair_summaries=pair_rows,aggregates=aggregates,
        native_starts=0,full_owner_ack_export_opened=False,strict_per_bag_nonharm_certified=False,
        promotion_approved=False,test_unlocked=False,R1_enabled=False,
        sampling_scope='four same-template-derived DEV parents, not four independent airport days',
        all_unfinished_and_not_yet_arrived_bags_retained=True,analysis_driver=producer_ref,
        producer_bound_at_entry_and_rechecked=True,producer_scope='this driver; imported helpers bound by frozen source manifest')
    final_ref=fresh(output/'final_science_report.json',final)
    fresh(output/'COMPLETE.json',dict(status='complete',final_report=final_ref,
        completed_marker_supersedes_pending_marker=True,source_bytes_checked_at_start_and_end=True,
        producer_bytes_checked_at_start_and_end=True,evidence_bytes_bound_before_consumption=True))
    print(json.dumps(dict(final_report=final_ref,scientific_pairs=24,native_starts=0)),flush=True)

def main():
    producer_ref=bind(Path(__file__))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-manifest',required=True,type=Path)
    parser.add_argument('--workflow',required=True,type=Path)
    parser.add_argument('--block',action='append',type=Path,help='Optional exact cross-check against four paths resolved from workflow')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args();source_ref=bind(args.source_manifest)
    paths,workflow_ref=workflow_blocks(args.workflow,source_ref)
    if args.block is not None:
        need({p.resolve() for p in args.block}==set(paths) and len(args.block)==4,'explicit_blocks_differ_from_workflow')
    root=verify_sources(source_ref);h=load_helpers(root)
    rows,status=inspect_blocks(paths,source_ref,h)
    if not args.execute:
        verify_bindings([producer_ref],'analysis_driver_changed_during_check')
        print(json.dumps(dict(status,science_executed=False,native_starts=0,analysis_driver=producer_ref),ensure_ascii=False,indent=2));return
    need(args.output_dir is not None,'execute_requires_fresh_output_dir')
    execute(rows,status,source_ref,workflow_ref,h,args.output_dir,producer_ref)

if __name__=='__main__':main()
