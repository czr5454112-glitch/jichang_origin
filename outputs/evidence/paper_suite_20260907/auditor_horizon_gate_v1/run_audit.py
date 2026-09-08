"""Read-only gate probes on saved real native horizon evidence; no simulation."""
from pathlib import Path
import copy,gzip,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from scripts.eval import run_g31_tarau_paper_suite as audit
OUT=Path(__file__).parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return audit._decode(json.loads(gzip.decompress(p.read_bytes())))
def main():
    assert not (OUT/'verification.json').exists(),'refuse to replace frozen gate evidence'
    results=[]
    structural=('merge_grant_conservation_holds','merge_grant_active_bijection_holds',
                'merge_grant_runtime_owned_capability','merge_grant_exact_slot_no_future_shift')
    for name in ('map2_v2.5_h10','nanning_v2.5_h13'):
        for label in ('b00','final38b'):
            source=OUT.parent/'tarau_native_identity_equivalence_v2/native'/name/label
            payload,request=load(source/'native.json.gz'),load(source/'request.json.gz')
            rec=request['bag_records'][0]
            rows=[dict(segment_id=rec[0],task_id=rec[1],pass_time=rec[2],std=rec[3],start=rec[4],goal=rec[5])]
            spec=dict(method='TARAU_DISTRIBUTED_2010_ADAPTED_ROUTE_ONLY',fixed_horizon_seconds=request['max_simulation_time'],
                      binary_sha256=payload['summary']['loaded_cpp_binary_sha256'],load_factor=1.0,timing_policy='full_population_only')
            prepared=audit.Prepared(spec,{'raw_bag_count':1,'segment_count':1},rows,request,{'scope':__doc__})
            result=audit.audit_payload(prepared,payload)
            assert result['status']=='PASS' and not result['full_population_complete']
            assert result['primary_timing'] is None and result['native_timing'] is None
            s=payload['summary'];assert s['merge_grant_final_active_unconsumed']==1 and s['merge_grant_outstanding_request_count']==0
            assert s['merge_grant_active_state_integrity_pass'] is False and s['merge_grant_protocol_integrity_pass'] is False
            rejected=[]
            for mutation in [*structural,'all_four_false']:
                corrupted=copy.deepcopy(payload)
                for field in structural if mutation=='all_four_false' else [mutation]:corrupted['summary'][field]=False
                try:audit.audit_payload(prepared,corrupted)
                except audit.SuiteError as error:rejected.append({'mutation':mutation,'rejection':str(error)})
                else:raise AssertionError('corrupt structural invariant was accepted: '+mutation)
            results.append(dict(case=name,binary=label,status='PASS',original_active_integrity=s['merge_grant_active_state_integrity_pass'],
                original_protocol_integrity=s['merge_grant_protocol_integrity_pass'],active=1,pending=0,full_population_complete=False,
                primary_timing=None,native_timing=None,negative_probes=rejected,
                native_path=str((source/'native.json.gz').relative_to(ROOT)),native_sha256=sha(source/'native.json.gz'),
                request_path=str((source/'request.json.gz').relative_to(ROOT)),request_sha256=sha(source/'request.json.gz')))
    value=dict(schema='czr005.paper_suite.horizon_gate_negative_controls.v1',status='PASS',scope=__doc__,
               positive_real_native_cases=4,rejected_structural_mutations=20,native_simulations_executed=0,
               auditor_path=str(Path(audit.__file__).relative_to(ROOT)),auditor_sha256=sha(Path(audit.__file__)),
               probe_source_sha256=sha(Path(__file__)),results=results)
    (OUT/'verification.json').write_bytes(audit._bytes(value))
    print(json.dumps({k:value[k] for k in ('status','positive_real_native_cases','rejected_structural_mutations','auditor_sha256','native_simulations_executed')}))
if __name__=='__main__':main()
