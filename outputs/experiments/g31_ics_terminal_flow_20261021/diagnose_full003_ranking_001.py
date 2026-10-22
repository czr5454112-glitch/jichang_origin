"""Read saved public decision inputs, never realized future labels, for ranking."""
import json
from pathlib import Path
from scripts.experiments.g31_ics_circulation.foundation_airport_json_stream import iter_json_array_gz
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_projection import prepare_inventory_projection, demand_mass
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_rule import inventory_view
from scripts.experiments.g31_ics_circulation.foundation_airport_transport_evidence import read, binding
from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import digest

ROOT=Path('outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001/runs/TF_bridge_P2201_003_C10_P2201')
OUT=Path('outputs/experiments/g31_ics_terminal_flow_20261021/full003_C10_9600_ranking_001.json')
plan=read(ROOT/'plan.json'); manifest=read(plan['source_bundle']['path'])
for helper in ('foundation_airport_inventory_projection.py','foundation_airport_inventory_rule.py'):
    path='scripts/experiments/g31_ics_circulation/'+helper
    assert binding(path)['sha256']==manifest['files'][path], 'projection helper changed from source003'
decision=None
for row in iter_json_array_gz(ROOT/'decisions.json.gz'):
    if row['decision_time']>9600: break
    if row['decision_time']==9600 and row['owner_id']=='owner:system_domestic': decision=row
assert decision is not None
observations={}
for record in iter_json_array_gz(ROOT/'observations.json.gz'):
    o=record['observation']
    if o['now']>10020: break
    if o['now'] in (9600,10020): observations[(o['now'],o['owner_id'])]=o
o=observations[(9600,'owner:system_domestic')]
assert digest(o)==decision['public_observation_ref']
forecast=decision['forecast_binding']['forecast']
prepared=prepare_inventory_projection(o,forecast=forecast)
view=inventory_view(o)
scored={r['action_id']:r for r in decision['selection']['score_report']['scores']}
options=[]
for action in decision['catalog']['candidates']:
    if action.get('tray_id')!='initial:138:0' or action.get('destination') not in (24,149): continue
    node=action['destination']; feature=decision['candidate_features'][action['action_id']]
    state=prepared.nodes[node]
    assert state['stock']==feature['features_current']['destination_stock']
    assert state['inventory_known']==bool(feature['features_current']['destination_inventory_known'])
    assert state['waiting']==feature['features_current']['destination_waiting']
    assert abs(demand_mass(prepared,node,0,300)-feature['features_forecast']['destination_demand_300s'])<1e-12
    options.append(dict(candidate=action,saved_features=feature,saved_score=scored[action['action_id']],
        public_inventory_view=view['nodes'][node],public_projection_state=state,
        public_supply_events=[e for e in prepared.supply_events if e['location']==node],
        public_ledger_inbound=[r for r in o['client_transfer_ledger'] if r['destination']==node],
        public_transfer_rows_inbound=[r for r in o['transfers'] if r.get('destination')==node],
        forecast_demand_600_seconds=demand_mass(prepared,node,0,600),
        forecast_bin_edges_seconds=forecast['bin_edges_seconds'][:11],
        forecast_first_ten_bin_means=forecast['new_demand_mean_by_region']['airport_node_'+str(node)][:10],
        forecast_missing_mask=forecast['missing_mask_by_region']['airport_node_'+str(node)],
        eta_outside_fixed_proxy_horizon=action['nominal_arrival_time']-9600>600))
assert len(options)==2
priority=[]
for call in iter_json_array_gz(ROOT/'calls.json.gz'):
    if call.get('kind')=='transfer' and not call.get('retry') and call['at']==10020 and call['request']['tray_id']=='initial:24:1': priority.append(call)
assert len(priority)==1 and priority[0]['request']['control_reason']=='observed_source_queue'
own=observations[(10020,'owner:system_international')]
own_prepared=prepare_inventory_projection(own)
priority_public=dict(observation_time=own['now'],owner_id=own['owner_id'],observation_sha256=digest(own),
    waiting_groups=own['control_projection']['waiting_groups'],
    source_state_post_priority=own_prepared.nodes[24],target_state_post_priority=own_prepared.nodes[0],
    matching_request_ledger=[r for r in own['client_transfer_ledger'] if r['request_id']==priority[0]['request']['request_id']],
    source_tray_public=[r for r in own['trays'] if r.get('tray_id')=='initial:24:1'],
    post_priority_observation_does_not_reconstruct_unrecorded_pre_priority_selector_scores=True)
owner9600=prepare_inventory_projection(observations[(9600,'owner:system_international')])
result=dict(schema='g31.terminal_flow.source003.saved_public_ranking_explanation.v1',
    task_id=plan['task_id'],decision_time=9600,owner_id=decision['owner_id'],decision_id=decision['decision_id'],
    source_bundle=plan['source_bundle'],decision_public_state_sha256=decision['public_observation_ref'],
    legal_catalog_id=decision['catalog']['catalog_id'],catalog_candidate_count=len(decision['catalog']['candidates']),
    selected_action_id=decision['selection']['action_id'],selection_reason=decision['selection']['reason'],
    source_actual_unpledged=2,source_138_hard_reserve=1,source_138_cap=1,
    options=options,forecast_binding=decision['forecast_binding'],
    priority_24_to_0_call=priority[0],priority_visible_input=priority_public,
    separately_observed_24_owner_state_at9600=dict(owner_id='owner:system_international',state=owner9600.nodes[24],
        not_available_to_domestic_decision_as_its_own_local_sensor=True),
    facts=['138→24 is legal but destination stock and waiting are unknown in the selecting domestic owner view.',
       'Its saved proxy gain and score are null, never a zero or negative forecast benefit.',
       'Its static arrival offset is 632.409 seconds, outside the fixed 600-second inventory proxy.',
       'The selected 138→149 has known current inventory and a positive saved net proxy score.',
       'The later 24→0 request is separately tagged observed_source_queue and sees an already-arrived waiting bag at node0.'],
    causal_limits=['This saved-input ranking explanation does not use actual future BAG_ARRIVAL counts or completion labels.',
       'Unknown target accounts and the proxy horizon are distinct limits; this evidence cannot identify which modification alone is sufficient.',
       'Priority observed-demand dispatch is a separate contract, not the optional selection at9600.',
       'Changing horizon, message coverage or priority contract requires a separate preregistered comparison; none was changed.'],
    actual_future_arrivals_used_in_ranking=False,native_starts=0,full_owner_ack_export_opened=False,
    observations_prefix_through=10020,full_observation_json_tail_reparsed=False,
    evidence={name:binding(ROOT/name) for name in ('plan.json','receipt.json','decisions.json.gz','calls.json.gz','observations.json.gz')},
    analysis_source=binding(Path(__file__)))
assert not OUT.exists()
with OUT.open('x',encoding='utf8') as f:
    json.dump(result,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')
print(json.dumps(dict(output=str(OUT),options=[dict(destination=r['candidate']['destination'],
    forecast_600=r['forecast_demand_600_seconds'],proxy=r['saved_score']['proxy_gain'],cost=r['saved_score']['transport_cost'],
    score=r['saved_score']['score'],view=r['public_inventory_view'],supply_events=r['public_supply_events']) for r in options],
    priority=priority_public),ensure_ascii=False))
