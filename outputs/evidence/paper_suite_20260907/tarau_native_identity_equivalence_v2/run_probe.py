"""Bounded real-map Tarau native identity controls; never a population campaign."""
from pathlib import Path
import argparse,gzip,hashlib,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[4]
for p in (ROOT,ROOT/'src'):sys.path.insert(0,str(p))
from scripts.eval import run_g31_tarau_paper_suite as encoding
from scripts.eval import g4irsf31_map_adapter as adapter
from scripts.eval import run_cie_component_activation as activation

OUT=Path(__file__).parent
BINARIES={
 'b00':(ROOT/'build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd','b00fd178dca5b3f201d50ddfc6446959272baa4cc45b4ee01a2f08e0c85a91f5'),
 'final38b':(ROOT/'build/g31_fault_potential_repair_20260907/python/Release/czr005_cpp.cp311-win_amd64.pyd','38b07ddfbc661c5243ab62a4963d84514405a87b11afa41538a94a42d2665b20')}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):p.write_bytes(encoding._bytes(value))
def archive(p,value):p.write_bytes(gzip.compress(encoding._bytes(value),mtime=0))
def read(p):return encoding._decode(json.loads(gzip.decompress(p.read_bytes())))
def scientific(value):
    if isinstance(value,dict):return {k:scientific(v) for k,v in value.items() if k not in {'inference_time_us','model_inference_us','decision_latency_us','runtime_seconds','loaded_cpp_binary_path','loaded_cpp_binary_sha256'}}
    if isinstance(value,list):return [scientific(x) for x in value]
    return value

def worker(label,map_name,speed,horizon,target):
    from czr005 import cpp_backend
    binary,expected=BINARIES[label]
    assert sha(binary)==expected
    profile=activation._profile_for_map(map_name,activation.DEFAULT_NANNING_PROFILE)
    rows=[dict(segment_id='1001:direct',task_id=1001,start=0,goal=47 if map_name=='map2' else 16,
               pass_time=0.0,std=5000.0,original_entry_time=0.0)]
    request,contract=adapter.build_s4_request(profile,rows,binary=binary,
        scenario='TARAU_BOUNDED_NATIVE_IDENTITY_CONTROL_NOT_FULL_POPULATION',max_events=30000,max_simulation_time=horizon,
        trace_limit=5000,event_trace_limit=5000,summary_only=False,edge_speed_mps=speed,
        enable_s4_local_potential_descent_guard=False,enable_s4_direct_neighbor_merge_calendar_visibility=False,complete_on_goal_arrival=True)
    request.update(scorer_mode='TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY',merge_grant_rule='M1',
                   merge_grant_timing_mode='jit_fifo',enable_cie_component_activation=False)
    if label=='final38b':request['enable_s4_advertised_fault_potential_repair']=False
    payload=cpp_backend.g4irsf11_event_runtime_from_records(**request)
    assert payload['summary']['loaded_cpp_binary_sha256']==expected
    target.mkdir(parents=True,exist_ok=False)
    archive(target/'request.json.gz',request);archive(target/'native.json.gz',payload)
    save(target/'identity.json',dict(map=map_name,speed_mps=speed,horizon=horizon,method='TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY',
        binary_sha256=expected,profile_sha256=sha(profile.source_path),source_prefilter=False,new_g31_repair_enabled=False,
        request_sha256=sha(target/'request.json.gz'),native_sha256=sha(target/'native.json.gz'),potential_contract=contract,
        tools=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in
               (Path(__file__),ROOT/'src/czr005/cpp_backend.py',ROOT/'scripts/eval/g4irsf31_map_adapter.py')]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true');parser.add_argument('--label');parser.add_argument('--map');parser.add_argument('--speed',type=float);parser.add_argument('--horizon',type=float);parser.add_argument('--target',type=Path)
    args=parser.parse_args()
    if args.worker:return worker(args.label,args.map,args.speed,args.horizon,args.target)
    assert not (OUT/'verification.json').exists(),'frozen evidence exists'
    cases=[(m,s,1000.0) for m in ('map2','nanning') for s in (1.5,2.5,3.0)]+[('map2',2.5,10.0),('nanning',2.5,13.0)]
    records=[]
    for map_name,speed,horizon in cases:
        name=f'{map_name}_v{speed:g}_h{horizon:g}';payloads={}
        for label in BINARIES:
            target=(OUT.parent/'tarau_native_identity_equivalence_v1' if horizon==1000 else OUT)/'native'/name/label
            command=[sys.executable,str(Path(__file__)), '--worker','--label',label,'--map',map_name,'--speed',str(speed),'--horizon',str(horizon),'--target',str(target)]
            if not (target/'native.json.gz').exists():
                done=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=90)
                assert done.returncode==0,(done.stdout+done.stderr).decode(errors='replace')
            identity=json.loads((target/'identity.json').read_text())
            assert identity['binary_sha256']==BINARIES[label][1] and identity['map']==map_name and identity['speed_mps']==speed and identity['horizon']==horizon
            assert identity['native_sha256']==sha(target/'native.json.gz') and identity['request_sha256']==sha(target/'request.json.gz')
            payloads[label]=read(target/'native.json.gz')
        old,new=payloads['b00'],payloads['final38b']
        equality={field:encoding._encode(scientific(old[field]))==encoding._encode(scientific(new[field])) for field in ('bags','decisions','hold_attempts','events','merge_grant_lifecycle')}
        assert all(equality.values()),(name,equality)
        assert len(new['bags'])==1 and new['bags'][0]['goal']==(47 if map_name=='map2' else 16)
        summary=new['summary']
        assert summary['merge_grant_conservation_holds'] is True
        assert summary['merge_grant_runtime_owned_capability'] is True and summary['merge_grant_exact_slot_no_future_shift'] is True
        assert summary['merge_grant_post_commit_capacity_compensation_pass'] is True
        assert summary['merge_grant_rule']=='M1' and summary['merge_grant_timing_mode']=='jit_fifo'
        assert summary['merge_grant_active_bijection_holds'] is True
        assert summary['reservation_conflicts']==0 and summary['physical_fault_edge_entry_violation_count']==0
        assert not summary.get('s4_advertised_fault_potential_repair_enabled',False)
        if horizon==1000:
            assert new['bags'][0]['completed'] and new['bags'][0]['final_node']==new['bags'][0]['goal']
            assert summary['merge_grant_final_active_unconsumed']==0 and summary['merge_grant_outstanding_request_count']==0
        else:
            assert not new['bags'][0]['completed']
            assert summary['merge_grant_final_active_unconsumed'] > 0
            assert len(new['merge_grant_lifecycle']) > 0
        records.append(dict(case=name,map=map_name,speed_mps=speed,horizon_seconds=horizon,equality=equality,
            completed=new['bags'][0]['completed'],finish_time=new['bags'][0]['finish_time'],primitive_invariants={k:summary[k] for k in ('merge_grant_runtime_owned_capability','merge_grant_exact_slot_no_future_shift','merge_grant_conservation_holds','merge_grant_active_bijection_holds','merge_grant_final_active_unconsumed','merge_grant_outstanding_request_count','merge_grant_queue_capacity_block_count','merge_grant_post_commit_capacity_compensation_pass','merge_grant_post_commit_revoked_count','merge_grant_post_commit_expired_count','merge_grant_post_commit_rollback_count','merge_grant_lifecycle_dropped_count')},
            old_active_bijection=old['summary']['merge_grant_active_bijection_holds'],new_active_bijection=summary['merge_grant_active_bijection_holds'],
            old_protocol_integrity=old['summary']['merge_grant_protocol_integrity_pass'],new_protocol_integrity=summary['merge_grant_protocol_integrity_pass']))
    save(OUT/'verification.json',dict(status='PASS',scope=__doc__,case_count=len(cases),native_runs=2*len(cases),
        binary_identities={k:v[1] for k,v in BINARIES.items()},source_sha256=sha(Path(__file__)),cases=records,new_native_runs=4,reused_full_duration_native_runs=12,reused_source_namespace='../tarau_native_identity_equivalence_v1/native',
        limits='One real native bag per case. Same records/request clocks. Not full population, original Tarau implementation, or continuous collision proof. Horizon diagnostic changes are not routing changes.'))
    print(json.dumps(dict(status='PASS',case_count=len(cases),native_runs=2*len(cases),records=records)))

if __name__=='__main__':main()
