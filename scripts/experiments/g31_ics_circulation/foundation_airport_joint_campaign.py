"""Budgeted joint-post-priority experiments; one native constructor per task.

Workers execute frozen Python sources. Native outcomes remain evaluator-only.
Resume reuses closed tasks and never pretends JSON restores physical state.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import gzip
import json
from pathlib import Path
import secrets
import shutil
import sys
import time
import traceback

from . import foundation_airport_action_campaign as common
from . import foundation_airport_joint_budget as budget
from .foundation_airport_evidence_export import write_gzip_json
from .foundation_airport_inventory_spi_campaign import JsonArrayStream, bound, read_bound

ROOT=Path(__file__).resolve().parents[3]
CYCLE=ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
MODULE='scripts.experiments.g31_ics_circulation.foundation_airport_joint_campaign'
SCHEMA='g31.airport_joint_campaign.v1'
BINARY=ROOT/'build_lt_session_030_inventory_spi/python/czr005_circulation.cp311-win_amd64.pyd'
BINARY_SHA='aa2f115d68f4f2c2a3d1df64192ebb33f8468ed6ce1248d14ebbc5955e4ddd82'
METHODS=('R0_legacy','R0_joint_bridge','C00','R_forecast_prior','C10','C01','C11','explore')

def verify_calibration(plan):
    """A non-gate run must use exactly its pretraining registered limits."""
    if plan.get('batch')=='gates': return
    if not plan.get('calibration'):
        raise ValueError('joint_campaign:pretraining_calibration_required')
    calibrated=read_bound(plan['calibration'])
    if calibrated.get('before_training') is not True or any(
            plan.get(key)!=calibrated.get(key) for key in
            ('horizon','soft_seconds','hard_seconds','estimated_evidence_bytes')):
        raise ValueError('joint_campaign:calibration_limits_binding')
    if type(calibrated.get('estimated_evidence_bytes')) is not int or calibrated['estimated_evidence_bytes']<=0:
        raise ValueError('joint_campaign:positive_evidence_estimate_required')

def freeze_sources(name):
    directory=CYCLE/'sources'/name
    if directory.exists(): raise ValueError('joint_campaign:fresh_source_bundle')
    from .foundation_airport_campaign import source_dependency_closure
    from .foundation_airport_joint_parents import SOURCE
    files=set(ROOT.joinpath('scripts/experiments/g31_ics_circulation').glob('*.py'))
    files.update(source_dependency_closure(roots=(MODULE,)).values())
    files.update(ROOT.joinpath('src').rglob('*.py'))
    files.add(SOURCE/'public/static_flight_plan.json')
    pins={}
    for path in sorted(files):
        relative=path.relative_to(ROOT); target=directory/relative
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,target)
        pins[relative.as_posix()]=common.sha(target)
    common.write(directory/'source_manifest.json',dict(schema=SCHEMA+'.sources',root=str(directory),
        files=pins,source_manifest_sha256=common.digest(pins),historical_private_tapes_included=False))
    return bound(directory/'source_manifest.json')

def prepare(task_id, *, method, seed, batch, source_bundle, horizon=59400., soft_seconds=2280.,
            hard_seconds=2400., rollout_round=0, mapping=None, model=None, root_branch=None,
            estimated_evidence_bytes=0, calibration=None):
    from .foundation_airport_joint_parents import make_parent, SPLITS
    from .foundation_airport_joint_calendar import load_calendar_binding
    if method not in METHODS or seed not in SPLITS: raise ValueError('joint_campaign:registered_method_parent')
    if SPLITS[seed]=='test': raise ValueError('joint_campaign:formal_locked_pending_freeze')
    if method in ('C01','C11') and model is None: raise ValueError('joint_campaign:model_required')
    if method=='C10' and mapping is None: raise ValueError('joint_campaign:explicit_train_mapping_required')
    if not 7200.<horizon<=59400. or not 0<soft_seconds<hard_seconds:
        raise ValueError('joint_campaign:finite_public_horizon_timeout')
    directory=CYCLE/'runs'/task_id
    if directory.exists(): raise ValueError('joint_campaign:fresh_task_id')
    if common.sha(BINARY)!=BINARY_SHA: raise ValueError('joint_campaign:accepted_native030_required')
    read_bound(source_bundle)
    parent_dir=CYCLE/'parents'/f'P{seed}_r{rollout_round}'
    if not parent_dir.exists():
        data,parent,generation=make_parent(seed,rollout_round=rollout_round)
        data['options']['max_events']=750000
        parent_dir.mkdir(parents=True)
        common.write(parent_dir/'input.json',data); common.write(parent_dir/'parent.json',parent)
        common.gz(parent_dir/'offline_generation.json.gz',generation)
    parent=common.read(parent_dir/'parent.json')
    directory.mkdir(parents=True)
    from . import foundation_airport_arrival_support as arrival_support
    from .foundation_airport_feasible_domain import ACTIVE_LOADERS, BUSINESS_SHA
    data=common.read(parent_dir/'input.json')
    if any(job['origin'] not in ACTIVE_LOADERS for job in data['jobs']):
        raise ValueError('joint_campaign:input_outside_fixed_public_arrival_support')
    audit=dict(schema=SCHEMA+'.input_origin_support_audit',input=bound(parent_dir/'input.json'),
        registered_business_sha256=BUSINESS_SHA,fixed_external_origin_nodes=list(ACTIVE_LOADERS),
        all_origins_within_predeclared_support=True,number_checked=len(data['jobs']),
        runtime_actor_reads_this_private_audit=False,origin_preserving_time_only_generator_sha256=arrival_support.generator_source_sha256())
    common.write(directory/'offline_origin_support_audit.json',audit)
    support=arrival_support.build_arrival_support_contract(parent=parent,
        input_origin_support_audit_sha256=common.sha(directory/'offline_origin_support_audit.json'))
    common.write(directory/'arrival_support_contract.json',support)
    binding=load_calendar_binding(parent)
    common.write(directory/'calendar_binding.json',binding)
    plan=dict(schema=SCHEMA,task_id=task_id,method=method,batch=batch,cycle=str(CYCLE),output=str(directory),
        parent=parent,input=bound(parent_dir/'input.json'),binary=bound(BINARY),source_bundle=source_bundle,
        forecast_binding=bound(directory/'calendar_binding.json'),mapping=mapping,model=model,
        arrival_support_contract=bound(directory/'arrival_support_contract.json'),
        origin_support_audit=bound(directory/'offline_origin_support_audit.json'),
        root_branch=root_branch,behavior_seed=17,activation=7200.,horizon=float(horizon),
        soft_seconds=soft_seconds,hard_seconds=hard_seconds,event_budget=100000,global_event_budget=750000,
        estimated_evidence_bytes=estimated_evidence_bytes,calibration=calibration,
        projection_horizon_seconds=600.,transport_penalty=.01,minimum_gain=0.,supply_mode='committed_only',
        controller=dict(common.CONTROLLER,inventory_snapshots=True,inventory_snapshot_validity=120.,
            inventory_snapshot_refresh_period=60.,recover_failed_empty=True,_consume_state=True,
            stock_return=True,stock_return_activate_at=7200.,actual_only_activate_at=7200.),
        policy_version='joint_v1:'+method+':'+(read_bound(model)['model_id'] if model else 'rule'),
        cost_scope='full_offered_population_integral_over_registered_window',strict_nonharm_certified=False)
    common.write(directory/'plan.json',plan)
    return directory

def verify(plan):
    from .foundation_airport_joint_parents import validate_public_parent, SPLITS
    if plan.get('schema')!=SCHEMA or plan.get('method') not in METHODS:
        raise ValueError('joint_campaign:plan_contract')
    parent=plan['parent']; validate_public_parent(parent)
    if parent['split']=='test' or plan.get('batch')=='formal':
        raise ValueError('joint_campaign:formal_locked_pending_freeze')
    if plan.get('batch') not in budget.ALLOCATIONS:
        raise ValueError('joint_campaign:registered_batch')
    if plan['method'] in ('C01','C11') and not plan.get('model'):
        raise ValueError('joint_campaign:explicit_model')
    if plan['method']=='C10' and not plan.get('mapping'):
        raise ValueError('joint_campaign:explicit_mapping')
    if not 7200.<plan['horizon']<=59400. or not 0<plan['soft_seconds']<plan['hard_seconds']:
        raise ValueError('joint_campaign:finite_physical_and_wall_limits')
    verify_calibration(plan)
    if common.sha(plan['binary']['path'])!=BINARY_SHA or plan['binary']['sha256']!=BINARY_SHA:
        raise ValueError('joint_campaign:native_changed')
    for key in ('input','source_bundle','forecast_binding','mapping','model','arrival_support_contract','origin_support_audit','calibration'):
        if plan.get(key): read_bound(plan[key])
    data=read_bound(plan['input'])
    if common.digest(data['jobs'])!=parent['jobs_digest'] or data['options']['max_events']!=plan['global_event_budget']:
        raise ValueError('joint_campaign:parent_input_binding')
    if plan.get('arrival_support_contract'):
        from . import foundation_airport_arrival_support as arrival_support
        support=read_bound(plan['arrival_support_contract']); nodes=arrival_support.validate_contract(support)
        audit=read_bound(plan['origin_support_audit'])
        if (audit['input']!=plan['input'] or not audit['all_origins_within_predeclared_support']
                or any(job['origin'] not in nodes for job in data['jobs'])
                or support['input_origin_support_audit_sha256']!=plan['origin_support_audit']['sha256']):
            raise ValueError('joint_campaign:public_arrival_support_offline_proof')
    binding=read_bound(plan['forecast_binding'])
    from .foundation_airport_joint_calendar import _validate_binding
    _validate_binding(binding)
    if binding['producer_manifest']['target_parent']['parent_group']!=parent['parent_group']:
        raise ValueError('joint_campaign:forecast_parent_binding')
    source=read_bound(plan['source_bundle'])
    if source['source_manifest_sha256']!=common.digest(source['files']): raise ValueError('joint_campaign:source_manifest')
    for name,expected in source['files'].items():
        if common.sha(Path(source['root'])/name)!=expected: raise ValueError('joint_campaign:frozen_source_changed:'+name)

class RecordingPolicy:
    def __init__(self,plan,forecast_at,decision_stream,observation_stream,arrival_receipts=None):
        self.plan=plan; self.forecast_at=forecast_at; self.decision_stream=decision_stream
        self.observation_stream=observation_stream; self.pending={}; self.counts=Counter(); self.rows=[]
        self.mapping=read_bound(plan['mapping']) if plan.get('mapping') else None
        self.model=read_bound(plan['model']) if plan.get('model') else None
        if self.model is not None:
            from .foundation_airport_joint_learning import prepare_predictor
            self.predictor=prepare_predictor(self.model)
        self.root=None
        self.root_prefix=None
        self.arrival_support=read_bound(plan['arrival_support_contract']) if plan.get('arrival_support_contract') else None
        self.arrival_receipts=arrival_receipts or {}
        self.policy_seconds=[]

    def __call__(self,prepared,catalog,*,policy_state,decision_context):
        policy_began=time.perf_counter()
        from .foundation_airport_joint_control import select_joint_bridge
        from .foundation_airport_inventory_projection import prepare_inventory_projection
        from .foundation_airport_joint_rules import select_joint_action, joint_candidate_features
        obs=prepared.observation; method=self.plan['method']; forecast=None
        support_options=(dict(arrival_support_contract=self.arrival_support,
            arrival_support_receipt=self.arrival_receipts[obs['owner_id']]) if self.arrival_support else {})
        current=prepare_inventory_projection(obs,prepared_current=prepared,
            horizon_seconds=self.plan['projection_horizon_seconds'],**support_options)
        reference=select_joint_action(current,catalog,information_variant='C00',
            transport_penalty=self.plan['transport_penalty'],minimum_gain=self.plan['minimum_gain'])
        choice=select_joint_bridge(prepared,catalog) if method=='R0_joint_bridge' else reference
        # Selection of a C00 action above precedes all B1 evaluation below.
        if method in ('C10','C11','R_forecast_prior','explore'):
            forecast=self.forecast_at(observation=obs,parent=self.plan['parent'])
            projected=forecast['forecast']
            forecast_projection=prepare_inventory_projection(obs,forecast=projected,prepared_current=prepared,
                horizon_seconds=self.plan['projection_horizon_seconds'],**support_options)
            if method in ('C10','C11','R_forecast_prior'):
                reference=select_joint_action(forecast_projection,catalog,information_variant='C10',
                    transport_penalty=self.plan['transport_penalty'],minimum_gain=self.plan['minimum_gain'])
                choice=reference
        else: forecast_projection=current
        features=joint_candidate_features(forecast_projection,catalog)
        if forecast is not None:
            for feature in features.values():
                feature['model_available_at']=max(forecast['model_available_at_epoch_seconds'],
                    (self.mapping or {}).get('model_available_at_epoch_seconds',0.))
        mechanism='deterministic'; probability=1.
        if method=='explore':
            alternatives=[a for a in catalog['candidates'] if a['action_id']!=reference['action_id']]
            decision_key=f"{self.plan['behavior_seed']}:{obs['owner_id']}:{decision_context['tick']}"
            integer=int(common.digest(decision_key)[:16],16); u=integer/2**64
            if alternatives and u>=.8:
                index=min(len(alternatives)-1,int((u-.8)/.2*len(alternatives)))
                choice=dict(reference,action_id=alternatives[index]['action_id'],reason='registered_uniform_exploration')
                probability=.2/len(alternatives)
            else: probability=.8 if alternatives else 1.
            mechanism='randomized'
            # Deterministic replay of an actual registered pseudorandom draw,
            # keyed independently of inventory and future outcomes.
        if self.plan.get('root_branch') is not None and self.root is None and self.root_prefix is not None:
            root_moves=sorted((a for a in catalog['candidates'] if a['action_type']=='transfer'),
                key=lambda a:(a['static_arrival_estimate'],a['action_id']))
            ref=next(a for a in catalog['candidates'] if a['action_id']==reference['action_id'])
            other=[a for a in root_moves if a['source']!=ref.get('source')]
            options=[ref]
            if other: options.append(other[0])
            options.extend(a for a in catalog['candidates'] if a['action_id'] not in {r['action_id'] for r in options})
            if len(options)<3: raise ValueError('joint_campaign:matched_root_three_distinct_choices')
            selected=options[self.plan['root_branch']]
            choice=dict(reference,action_id=selected['action_id'],reason='preregistered_matched_root_branch')
            probability=1.; mechanism='deterministic'
            self.root=dict(owner_id=obs['owner_id'],at=obs['now'],public_state_digest=prepared.public_state_digest,
                catalog_id=catalog['catalog_id'],reference_candidate_id=reference['action_id'],
                branch=self.plan['root_branch'],selected_action_id=selected['action_id'],prefix_pending=True)
            policy_state['matched_root_executed']=True
        if self.model is not None:
            from .foundation_airport_joint_learning import select_supported_action
            choice=select_supported_action(self.model,features,reference_candidate_id=reference['action_id'],
                calendar_time=self.plan['parent']['calendar_start_epoch_seconds']+obs['now'],predictor=self.predictor)
        selected=next(a for a in catalog['candidates'] if a['action_id']==choice['action_id'])
        choice=dict(choice,selection_probability=probability,policy=method)
        chosen_features=features[selected['action_id']]
        decision_id=common.digest([self.plan['task_id'],obs['owner_id'],decision_context['tick']])
        action={**selected,'kind':selected['action_type']}
        row=dict(decision_id=decision_id,owner_id=obs['owner_id'],decision_time=obs['now'],
            phase='post_priority',current_version=obs.get('version',0),
            public_observation_ref=prepared.public_state_digest,legal_catalog_ref=catalog['catalog_id'],
            reference_candidate_id=reference['action_id'],requested_action=action,
            joint_policy_version=self.plan['policy_version'],selection_probability=probability,
            execution_probability=None,selection_mechanism=mechanism,
            actual_submission=None,fallback_reason=choice.get('fallback_reason'),physical_failure=False,
            **chosen_features)
        self.rows.append(row); self.pending[(obs['owner_id'],obs['now'])]=row
        self.decision_stream.extend([dict(row,candidate_features=features,catalog=catalog,
            reference=reference,selection=choice,forecast_binding=forecast)])
        # Observations are streamed separately once, not copied into every action.
        self.observation_stream.extend([dict(digest=prepared.public_state_digest,observation=obs)])
        self.counts['legal_decisions']+=1; self.counts['multiple_source_nodes']+=catalog['candidate_source_node_count']>=2
        self.counts['nonreference']+=selected['action_id']!=reference['action_id']
        self.counts['proposal_'+selected['action_type']]+=1
        self.policy_seconds.append(time.perf_counter()-policy_began)
        return choice

    def before_choice(self,**kwargs):
        if self.root_prefix is not None: return
        from .foundation_airport_joint_opportunities import prepare_current,build_joint_catalog
        obs=kwargs['observation']
        prepared=prepare_current(obs,kwargs['decision'],message_delay=self.plan['controller']['command_delay'])
        catalog=build_joint_catalog(prepared)
        if catalog['candidate_source_node_count']<2 or len(catalog['candidates'])<3: return
        state={**kwargs['controller_state'],'client':kwargs['client_state']}
        self.root_prefix=dict(at=obs['now'],owner_id=obs['owner_id'],
            native_state_sha256=kwargs['session'].offline_state_sha256(),controller_state_sha256=common.digest(state),
            delivered_messages_sha256=common.digest(obs.get('delivered_messages',[])),
            exogenous_input_sha256=self.plan['input']['sha256'],stage='before_joint_selector_and_submission')

    def bind_prefix(self,**kwargs):
        if self.root is not None and self.root.get('prefix_pending'):
            if self.root_prefix is None: raise ValueError('joint_campaign:actual_prechoice_prefix_required')
            self.root.update(prefix=self.root_prefix,prefix_pending=False)

def worker(path,expected):
    plan=common.read(path); output=Path(plan['output']); began=time.monotonic()
    report=dict(schema=SCHEMA,task_id=plan['task_id'],process_status='failed',scientific_status='unknown',native_constructor_attempts=0)
    streams={}; session=None; recording=None; final=None; calls=[]; state=None
    try:
        if common.sha(path)!=expected: raise ValueError('joint_campaign:plan_changed')
        verify(plan)
        from .native_host import load_native
        from .foundation_airport_protocol_v2 import run_airport_bounded_protocol_control
        from .foundation_airport_inventory_rule import make_r0_priority_planner
        from .foundation_airport_joint_control import JointPostPrioritySelector
        from .foundation_airport_joint_calendar import record_controller_preload
        from .foundation_airport_joint_calendar_prepared import prepare_forecast_provider
        data=read_bound(plan['input']); owners=sorted({r['resource_owner'] for r in data['node_contracts']})
        report['native_constructor_attempts']=1
        session=load_native(plan['binary']['path']).NativeSession(data)
        binding=read_bound(plan['forecast_binding'])
        receipts=record_controller_preload(binding,session,owners=owners)
        common.write(output/'plan_preload_receipts.json',receipts)
        forecast_at=prepare_forecast_provider(binding,receipts,
            loader_mapping=read_bound(plan['mapping']) if plan.get('mapping') else None)
        arrival_receipts={}
        if plan.get('arrival_support_contract'):
            from .foundation_airport_arrival_support import record_controller_preload as record_support_preload
            arrival_receipts=record_support_preload(read_bound(plan['arrival_support_contract']),session,owners=owners)
            common.write(output/'arrival_support_receipts.json',arrival_receipts)
        streams={name:JsonArrayStream(output/(name+'.json.gz')) for name in ('decisions','observations','control_trace','calls')}
        recording=RecordingPolicy(plan,forecast_at,streams['decisions'],streams['observations'],arrival_receipts)
        options=copy.deepcopy(plan['controller'])
        if plan['method']!='R0_legacy':
            options.update(stock_return_selector=JointPostPrioritySelector(recording),
                stock_return_selector_identity=plan['policy_version'],post_decision_observer=recording.bind_prefix)
            if plan.get('root_branch') is not None: options['pre_stock_return_observer']=recording.before_choice
        target=min(3600.,plan['horizon'])
        with (output/'progress.jsonl').open('x',encoding='utf8') as progress:
            while True:
                run=run_airport_bounded_protocol_control(session,owners,horizon=target,state=state,
                    event_budget=plan['event_budget'],planner=make_r0_priority_planner(activate_at=7200.),
                    planner_identity='joint_shared_actual_priority_v1',soft_deadline=began+plan['soft_seconds'],**options)
                state=run['controller_state']; calls.extend(run['client_calls'])
                streams['calls'].extend(run['client_calls'])
                # Keep funnel/actual submit replies and timings; bulky original
                # observations have their own immutable stream.
                for row in run['control_records']:
                    compact=copy.copy(row)
                    compact['owner_decisions']=[]
                    for d in row.get('owner_decisions',[]):
                        item={k:v for k,v in d.items() if k not in ('decision','residual_decision','inventory_return')}
                        post=d.get('inventory_return')
                        if post is not None:
                            item['inventory_return']={k:v for k,v in post.items() if k!='decision'}
                            joint=(post.get('decision') or {}).get('joint_selection')
                            if joint is not None:
                                item['inventory_return']['joint_summary']={k:joint[k] for k in ('K',
                                    'candidate_source_tray_count','candidate_source_node_count','candidate_destination_count','exclusions')}
                            recording.counts['post_priority_visits']+=1
                            recording.counts['post_reason:'+str(post.get('reason'))]+=1
                        compact['owner_decisions'].append(item)
                    streams['control_trace'].extend([compact])
                if run['result'] is not None: final=run['result']
                progress.write(json.dumps(dict(at=session.physical_time,target=target,status=run['status'],
                    elapsed=time.monotonic()-began,decisions=len(recording.rows)))+'\n'); progress.flush()
                if run['status']!='reached':
                    report.update(process_status='completed',scientific_status='censored_'+run['status']); break
                if session.physical_time>=plan['horizon']:
                    report.update(process_status='completed',scientific_status='closed'); break
                target=min(target+3600.,plan['horizon'])
        for s in streams.values(): s.close()
        common.write(output/'controller_checkpoint_scope.json',dict(physical_time=session.physical_time,
            native_state_sha256=session.offline_state_sha256(),
            controller_state_sha256=common.digest(state),physical_restore_supported=False,
            resume_semantics='completed tasks reused; any physical prefix replay consumes another native start',
            quota=state.get('inventory_return_quota'),policy_state=state.get('joint_post_priority',{}).get('policy_state')))
        state=None; run=None
        if final is not None:
            # Keep physical execution evidence, avoid duplicating enormous full
            # snapshots of protocol histories already captured by call streams.
            terminal={k:final[k] for k in ('schema','physical_clock','advance','population','jobs','trays','transfers',
                'leg_identities','receipts','events_processed','status') if k in final}
            report['terminal_evidence']=write_gzip_json(output/'terminal_evidence.json.gz',terminal)
            from .foundation_airport_service_metrics import physical_progress_intervals
            report['physical_progress']=physical_progress_intervals(final,start=7200.,end=session.physical_time)
            diagnostics=session.offline_diagnostics()
            report['offline_diagnostics']=write_gzip_json(output/'offline_diagnostics.json.gz',diagnostics)
            if report['scientific_status']=='closed':
                from .foundation_airport_wait_graph import analyze_wait_graph
                report['wait_graph']=write_gzip_json(output/'wait_graph.json.gz',
                    analyze_wait_graph(data,final,diagnostics,client_calls=calls))
            from .foundation_airport_pair_dataset import window_cost
            if report['scientific_status']=='closed':
                report['cost']=window_cost(data,final,start=7200.,end=plan['horizon'])
            by_request={}
            for call in calls:
                if call.get('kind')=='transfer' and not call.get('retry'):
                    request=call['request']; key=(request['owner_id'],call['at'],request['tray_id'])
                    by_request[key]=call
            transfers={r['request_id']:r for r in final.get('transfers',[])}
            ack_views={owner:session.observe_protocol(owner) for owner in owners}
            write_gzip_json(output/'delivered_ack_evidence.json.gz',ack_views)
            legs_by_request={}
            for leg in final.get('leg_identities',[]):
                if leg.get('kind')=='empty_return':
                    identity=leg['transport_leg_id'].rsplit(':empty_return:',1)[0]
                    legs_by_request.setdefault(identity,[]).append(leg)
            events_by_leg={}
            for event in final.get('receipts',[]):
                if event.get('transport_leg_id'):
                    events_by_leg.setdefault(event['transport_leg_id'],[]).append(event)
            acks_by_request={}
            for view in ack_views.values():
                for ack in view.get('delivered_transfer_acks',[]):
                    acks_by_request.setdefault(ack['request_id'],[]).append(ack)
            for row in recording.rows:
                if row['requested_action']['kind']=='noop': continue
                call=by_request.get((row['owner_id'],row['decision_time'],row['requested_action']['tray_id']))
                if call:
                    request=call['request']; row.update(actual_submission=request,request_id=request['request_id'],reply_or_rejection=call['reply'])
                    transfer=transfers.get(request['request_id']); row['native_transfer_at_export']=transfer
                    acks=acks_by_request.get(request['request_id'],[]); row['ack']=acks
                    legs=legs_by_request.get(request['request_id'],[]); row['first_leg']=legs[0] if legs else None
                    events=[event for leg in legs for event in events_by_leg.get(leg['transport_leg_id'],[])]
                    row['first_edge_event']=next((e for e in events if e['event']=='EDGE_ENTER'),None)
                    row['received_event']=next((e for e in events if e['event']=='EMPTY_RECEIVED'),None)
                    row['physical_failure']=bool(call['reply'].get('status') in ('rejected','failed','expired')
                        or transfer and transfer.get('status') in ('rejected','failed','expired')
                        or any(a.get('status') in ('rejected','failed','expired') for a in acks))
            from .foundation_airport_joint_dataset import build_trajectory
            jobs={r['business_bag_id']:r for r in final['jobs']}
            cost_events=[dict(business_bag_id=j['business_bag_id'],arrival=j['arrival'],
                completion=jobs[j['business_bag_id']]['completed_at'] if jobs[j['business_bag_id']]['completed_at']>=0 else None)
                for j in data['jobs']]
            manifest=dict(trajectory_id=plan['task_id'],parent_uid=plan['parent']['parent_group'].rsplit(':r',1)[0],
                episode_parent_group=plan['parent']['parent_group'],rollout_round=plan['parent']['rollout_round'],
                lineage_family='joint_group_shift_plan_v1',template_family=plan['parent']['common_historical_template_sha256'],
                split=plan['parent']['split'],environment_seed=plan['parent']['parent_seed'],behavior_seed=plan['behavior_seed'],
                execution_source_id=plan['source_bundle']['sha256'],native_domain_id=plan['binary']['sha256'],
                joint_policy_version=plan['policy_version'],physical_start=7200.,physical_end=plan['horizon'],
                calendar_start_epoch_seconds=plan['parent']['calendar_start_epoch_seconds'])
            if recording.root is not None:
                prefix=recording.root['prefix']
                manifest['pairing']=dict(root_id=common.digest([prefix['owner_id'],prefix['at'],recording.root['catalog_id']]),
                    physical_control_prefix_sha256=common.digest([prefix['native_state_sha256'],prefix['controller_state_sha256']]),
                    delivered_messages_sha256=prefix['delivered_messages_sha256'],
                    exogenous_input_sha256=prefix['exogenous_input_sha256'],continuation_policy_version=plan['policy_version'])
            if recording.model is not None: manifest['deployed_model_id']=recording.model['model_id']
            manifest['recording_semantics']='decision stream before submit; trajectory joins actual requests and physical outcome evidence'
            rows=[r for r in recording.rows if r['decision_time']<plan['horizon']]
            trajectory=build_trajectory(manifest,rows,cost_events,physical_clock=session.physical_time,
                process_status='completed' if report['scientific_status']=='closed' else 'timeout',
                business_population_complete=True,logs_complete=True)
            write_gzip_json(output/'trajectory.json.gz',trajectory)
            common.write(output/'cost_events.json',dict(events=cost_events,physical_clock=session.physical_time))
        report.update(final_physical_time=session.physical_time,decisions=len(recording.rows),
            funnel=dict(recording.counts),root=recording.root,strict_nonharm_certified=False)
        timings=sorted(recording.policy_seconds)
        report['policy_timing']=dict(count=len(timings),total_seconds=sum(timings),
            p50_seconds=timings[len(timings)//2] if timings else None,
            p95_seconds=timings[min(len(timings)-1,int(.95*len(timings)))] if timings else None,
            maximum_seconds=max(timings,default=None),
            scope='selector scoring plus evidence stream writes; excludes catalogue, protocol, native and final export',
            complete_request_100ms_certified=False)
        verify(plan)
    except Exception:
        report.update(process_status='failed',scientific_status='unknown_error',exception=traceback.format_exc())
    finally:
        for s in streams.values(): s.close()
    import psutil
    process=psutil.Process(); mem=process.memory_info(); cpu=process.cpu_times()
    report.update(wall_seconds=time.monotonic()-began,peak_memory_bytes=getattr(mem,'peak_wset',mem.rss),
        cpu_seconds=cpu.user+cpu.system)
    common.write(output/'worker_report.json',report)
    return report

def launch(directory):
    from .bounded_windows_job import run
    directory=Path(directory).resolve(); plan=common.read(directory/'plan.json'); verify(plan)
    receipt=directory/'receipt.json'
    plan_sha=common.sha(directory/'plan.json')
    if receipt.exists():
        cached=common.read(receipt)
        if cached.get('plan_sha256')!=plan_sha or cached.get('task_id')!=plan['task_id']:
            raise ValueError('joint_campaign:cached_receipt_binding')
        return cached
    budget.admit(plan['cycle'],dict(plan,plan_sha256=plan_sha))
    admission=secrets.token_hex(24); source=read_bound(plan['source_bundle'])
    with (directory/'stdout.log').open('xb') as stdout,(directory/'stderr.log').open('xb') as stderr:
        result=run([sys.executable,'-m',MODULE,'worker',str(directory/'plan.json'),
            '--expected',plan_sha,'--admission',admission],timeout=plan['hard_seconds'],stdout=stdout,stderr=stderr,
            admission=admission,cwd=source['root'])
    report=common.read(directory/'worker_report.json') if (directory/'worker_report.json').exists() else dict(
        process_status='timeout' if result['status']=='hard_timeout' else 'failed',scientific_status='unknown_missing_export')
    receipt_data=dict(schema=SCHEMA,task_id=plan['task_id'],process=result,worker=report,plan_sha256=plan_sha)
    common.write(receipt,receipt_data); budget.append(plan['cycle'],'native_finish',task_id=plan['task_id'],
        process_status=report['process_status'],scientific_status=report['scientific_status'])
    return receipt_data

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status'); frozen=sub.add_parser('freeze'); frozen.add_argument('name')
    prep=sub.add_parser('prepare'); prep.add_argument('task_id'); prep.add_argument('--method',choices=METHODS,required=True)
    prep.add_argument('--seed',type=int,required=True); prep.add_argument('--batch',choices=tuple(budget.ALLOCATIONS),required=True)
    prep.add_argument('--source',type=Path,required=True); prep.add_argument('--horizon',type=float,default=59400.)
    prep.add_argument('--mapping',type=Path); prep.add_argument('--model',type=Path)
    for cmd in ('run','resume'):
        p=sub.add_parser(cmd); p.add_argument('directories',nargs='+',type=Path)
    p=sub.add_parser('worker'); p.add_argument('plan',type=Path); p.add_argument('--expected',required=True); p.add_argument('--admission',required=True)
    args=parser.parse_args()
    if args.command=='worker':
        if sys.stdin.readline().strip()!=args.admission: raise SystemExit('joint_campaign:parent_admission_required')
        result=worker(args.plan,args.expected); raise SystemExit(0 if result['process_status']=='completed' else 1)
    if args.command=='status': print(json.dumps(budget.status(CYCLE),indent=2)); return
    if args.command=='freeze': print(json.dumps(freeze_sources(args.name))); return
    if args.command=='prepare':
        print(prepare(args.task_id,method=args.method,seed=args.seed,batch=args.batch,source_bundle=bound(args.source),
            horizon=args.horizon,mapping=bound(args.mapping) if args.mapping else None,model=bound(args.model) if args.model else None)); return
    if args.command in ('run','resume'):
        runner_id=secrets.token_hex(12)
        if budget.status(CYCLE)['open_runners']: raise ValueError('joint_campaign:recover_existing_runner_first')
        budget.append(CYCLE,'runner_open',runner_id=runner_id)
        try:
            for directory in args.directories:
                result=launch(directory); print(json.dumps(result),flush=True)
                if result['worker']['scientific_status']!='closed': break
        finally: budget.append(CYCLE,'runner_close',runner_id=runner_id)

if __name__=='__main__': main()
