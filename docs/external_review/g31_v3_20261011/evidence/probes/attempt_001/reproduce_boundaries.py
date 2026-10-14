"""Independent deterministic probes. Reads frozen checkout; never edits production.
An observed defect is reported separately from the existing release regressions.
"""
from pathlib import Path
import sys,json,time
from dataclasses import asdict, replace
D=Path(__file__).resolve().parents[1]
ROOT=Path((D/'root.txt').read_text().strip()); sys.path.insert(0,str(ROOT))
from scripts.experiments.ics_circulation_v3.model import *
from scripts.experiments.ics_circulation_v3.runtime import *
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator,clear_static_cache
from scripts.experiments.ics_circulation_v3.routing_reference import FullGraphReferenceGenerator
from scripts.experiments.ics_circulation_v3.routing_cache_contract import ReplayRegionalFactory
from scripts.experiments.ics_circulation_v3.storage_contracts import *
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator
from scripts.experiments.ics_circulation_v3.terminal_capacity_screen import *
from scripts.experiments.ics_circulation_v3.partition_observation import observe_partition
from scripts.experiments.ics_circulation_v3.joint_reference import solve_joint,JointDomain


def regional(horizon=10):
    return RegionalCandidateGenerator(horizon=horizon,expansion_limit=200000,static_path_limit=20,
              deadline_ms=None,cache_contract='isolated_replay_v1')

def storage_merge_state():
    nodes={n:Node(n,'Z','P',capacity=4) for n in ('S','A','W','X','G')}
    edges=[Edge('a-SA','S','A',1),Edge('b-SW','S','W',1),Edge('c-AX','A','X',1),Edge('d-WX','W','X',1),Edge('e-XG','X','G',1)]
    bag=StorageBag('b','S','G',0,10,True,StorageWaypointContract('W',0,0))
    return StorageSnapshot(0,Network(nodes,{e.edge_id:e for e in edges}),{'t':Tray('t','S','loaded','b')},{'b':bag})

def four_paths_state():
    nodes={n:Node(n,'Z','P') for n in ('S','A','B','C','D','G')}
    edges=[e for n in 'ABCD' for e in (Edge('S'+n,'S',n,1),Edge(n+'G',n,'G',1))]
    return Snapshot(0,Network(nodes,{e.edge_id:e for e in edges}),{'t':Tray('t','S','loaded','b')},{'b':Bag('b','S','G',0,20)})

start=time.perf_counter();cpu=time.process_time(); rows={}
s=storage_merge_state();clear_static_cache()
g=FullGraphReferenceGenerator(horizon=5,expansion_limit=200000,deadline_ms=None,integer_ticks=True)
a=g.generate(s,'b','t',k=1)
w=RouteCandidate('known-feasible','b','t',(Leg('b-SW',0,1),Leg('d-WX',1,2),Leg('e-XG',2,3)),4,4,s.version,'known-feasible',True,'G')
v=ExecutionValidator().validate(s,w)
sg=StorageCandidateGenerator(regional(5)); b=sg.generate(s,'b','t',k=1)
rows['P01_storage_integer_oracle']={'returned_count':len(a),'search_status':g.last_search_status,
    'diagnostics':g.last_diagnostics,'independent_hand_witness':asdict(w),'witness_validation':asdict(v),
    'storage_generator_count':len(b),'storage_candidates':[asdict(x) for x in b],
    'defect_observed':not a and v.accepted and g.last_diagnostics.get('finite_horizon_exhausted',False),
    'scope':'Direct FullGraphReferenceGenerator Storage call. Not claiming latest business runner calls this oracle.'}
s=four_paths_state();orig=regional();wrapped=TerminalScreenGenerator(regional())
a=orig.generate(s,'b','t');b=wrapped.generate(s,'b','t')
rows['P02_ordinary_screen_default_k']={'unwrapped_count':len(a),'wrapped_count':len(b),
    'unwrapped':[asdict(x) for x in a],'wrapped':[asdict(x) for x in b],
    'defect_observed':a!=b,'scope':'omitted-k API only; latest explicit-k1 Storage result is not invalidated.'}
factory=ReplayRegionalFactory.from_generator(regional())
engine=Simulation(s,generator_factory=factory)
install_terminal_screen(engine)
cp=engine.checkpoint()
before=(len(cp.generator.accounting.rows),len(cp.generator_factory.accounting.rows))
engine.generator_factory().generate(s,'b','t',k=1)
after=(len(cp.generator.accounting.rows),len(cp.generator_factory.accounting.rows))
restored=Simulation.from_checkpoint(cp)
rows['P03_ordinary_factory_checkpoint_alias']={'checkpoint_counts_before':before,'checkpoint_counts_after_original_factory_query':after,
    'restored_counts':(len(restored._generator.accounting.rows),len(restored.generator_factory.accounting.rows)),
    'checkpoint_factory_is_original_factory':cp.generator_factory is engine.generator_factory,
    'defect_observed':before!=after,'scope':'ordinary screen accounting checkpoint contamination, not evidence of physical trajectory contamination.'}
# Confirm intentional rejection is not an accidental implementation error.
s=storage_merge_state();small=Simulation(s,generator_factory=factory,slow_controller=lambda state:())
res=small.advance(6)
rows['P04_storage_can_have_slow_callback']={'completed':res.completed,'slow_calls':res.policy_stats['slow_calls'],
    'scope':'no-op slow callback compatibility only, not predictive balancing evidence.'}
for label,call in [('partition',lambda:observe_partition(s,'P')),('joint',lambda:solve_joint(s,domain=JointDomain(6)))]:
    try:call();value='unexpected_accept'
    except ValueError as e:value=str(e)
    rows['P05_'+label+'_storage_guard']={'observed':value}
# Stop at protected refusal, while an independently built compatible alternate exists.
s=four_paths_state();s.bags['b']=replace(s.bags['b'],protected=True);s.replaceable_trays=('t',)
old=RouteCandidate('old','b','t',(Leg('SA',2,3),Leg('AG',3,4)),5,5,s.version,'old',True,'G')
assert ExecutionValidator().commit(s,old).accepted
try:ExecutionValidator().prepare_replacement(s,'t'); refusal=None
except ValueError as e:refusal=str(e)
rows['P06_protected_replacement']={'refusal':refusal,'scope':'intentional contract limitation; no assertion of causality for 0/44.'}
# Verify that removing a completed plan is not deleting the physical empty tray.
s=Snapshot(0,Network({'S':Node('S','Z','P'),'G':Node('G','Z','P')},{'SG':Edge('SG','S','G',1)}),
    {'t':Tray('t','S','loaded','b')},{'b':Bag('b','S','G',0,10)})
e=Simulation(s,reactive_empty_dispatch=False);r=e.advance(3)
rows['P07_terminal_actual_empty_occupancy']={'completed':r.completed,'plans':list(e.state.plans),
    'tray':asdict(e.state.trays['t']),'effective_reservations':[asdict(x) for x in effective_reservations(e.state)]}
output={'production_sha':'defd79effe02ee13f1a5bbbbc5143f6d0dce2f63','uploaded_release_sha':'fccd4819532701ee4173ec598822450d962d4e61',
    'results':rows,'wall_seconds':time.perf_counter()-start,'process_cpu_seconds':time.process_time()-cpu,
    'interpretation':'Independent probes; observed defects do not retroactively change historical experiments.',
    'explicit_simulation_advance_calls':3,'full_business_replay':False}
(D/'probes/results.json').write_text(json.dumps(output,indent=2))
print(json.dumps({k:{a:b for a,b in v.items() if a in ('defect_observed','scope','unwrapped_count','wrapped_count','returned_count','search_status','witness_validation','checkpoint_counts_before','checkpoint_counts_after_original_factory_query','completed','slow_calls','refusal','observed')} for k,v in rows.items()},indent=2))
