"""Offline request-tape reconstruction; only read-only calls are profiled."""
import argparse, cProfile, gzip, hashlib, io, json, os, pstats, statistics, time
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[4]
os.chdir(ROOT)
import sys
sys.path[:0]=[str(ROOT), str(ROOT/'src')]
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.analytic_control import transfer_candidates

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def dist(values):
    values=sorted(values)
    return dict(n=len(values),sum_ms=sum(values),mean_ms=statistics.mean(values) if values else 0,
        p50_ms=values[len(values)//2] if values else 0,p95_ms=values[int(.95*(len(values)-1))] if values else 0,
        max_ms=max(values,default=0),over100=sum(v>100 for v in values))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args(); out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'outputs/experiments/g31_ics_long_term_20261013/event_protocol_original24_015_001/original24'
    with gzip.open(base/'event_predictive/run.json.gz','rt',encoding='utf-8') as f:run=json.load(f)
    scene=json.loads((base/'input.json').read_text(encoding='utf-8'))
    runtime_paths=[*ROOT.glob('cpp/ics_core/runtime/*.hpp'),*ROOT.glob('cpp/ics_core/bindings/circulation*'),
        ROOT/'scripts/experiments/g31_ics_circulation/analytic_control.py',
        ROOT/'scripts/experiments/g31_ics_circulation/protocol_control.py',
        ROOT/'scripts/experiments/g31_ics_circulation/event_protocol_control.py']
    source=lambda:{p.relative_to(ROOT).as_posix():sha(p) for p in runtime_paths if p.is_file()}
    before=source();native=load_native(args.binary);s=native.NativeSession(scene)
    started=time.perf_counter(); position=0; samples=[]; replies=[]
    owners=sorted({r['request']['owner_id'] for r in run['client_calls']})
    for horizon in [24000.,36000.,45000.]:
        while position<len(run['client_calls']) and run['client_calls'][position]['at']<=horizon:
            if time.perf_counter()-started>20: raise RuntimeError('independent_profile_wall_budget')
            call=run['client_calls'][position]
            assert s.advance_to(call['at'])['horizon_complete']
            reply=(s.submit_protocol_transfer(call['request']) if call['kind']=='transfer' else s.submit_protocol_command(call['request']))
            assert reply==call['reply'],(position,reply,call['reply'])
            replies.append(reply);position+=1
        assert s.advance_to(horizon)['horizon_complete']
        state_before=s.offline_state_sha256(); output={}
        for owner in owners:
            initial=s.observe_protocol_control(owner)
            command_ids=[r['request_id'] for r in initial['client_commands']]
            rows={k:len(initial[k]) for k in ['client_commands','delivered_command_acks','delivered_messages','client_requests','delivered_transfer_acks']}
            timings={name:[] for name in ['observe_protocol_control','demand_signature','query_all_own_commands','matching_on_cached_observation']}
            profile=cProfile.Profile(); profile.enable()
            for _ in range(12):
                t=time.perf_counter();value=s.observe_protocol_control(owner);timings['observe_protocol_control'].append(1000*(time.perf_counter()-t))
                assert value==initial
                t=time.perf_counter();s.protocol_demand_signature(owner);timings['demand_signature'].append(1000*(time.perf_counter()-t))
                t=time.perf_counter();[s.protocol_command(owner, identity) for identity in command_ids];timings['query_all_own_commands'].append(1000*(time.perf_counter()-t))
                value['transfers']=value['client_transfer_ledger']
                t=time.perf_counter();transfer_candidates(value,predictive=True,message_delay=2.,respect_service_forecasts=True,request_prefix='readonly-probe');timings['matching_on_cached_observation'].append(1000*(time.perf_counter()-t))
            profile.disable();profile.dump_stats(str(out/f'{int(horizon)}_{owner.split(":")[-1]}.prof'))
            stream=io.StringIO();pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(24)
            (out/f'{int(horizon)}_{owner.split(":")[-1]}.txt').write_text(stream.getvalue(),encoding='utf-8')
            output[owner]=dict(payload_counts=rows,timings={k:dist(v) for k,v in timings.items()},observation_sha256=digest(initial))
        state_after=s.offline_state_sha256();assert state_before==state_after
        result=s.result_at(horizon)
        expected=[r for r in run['result']['receipts'] if r['time']<=horizon]
        assert result['receipts']==expected,'request-tape physical/protocol receipt prefix mismatch'
        samples.append(dict(horizon=horizon,replayed_requests=position,owners=output,state_sha256=state_after,
            all_receipts_exact_original_prefix=True,receipt_sha256=digest(result['receipts']),receipt_count=len(expected)))
    after=source();changed=[p for p in before if before[p]!=after[p]]
    receipt=dict(schema='g31.event_control_readonly_profile.v1',status='passed' if not changed else 'source_changed',
        binary=str(Path(args.binary).resolve()),binary_sha256=sha(args.binary),source_before=before,source_after=after,
        source_changed=changed,request_reply_exact_match=True,samples=samples,wall_seconds=time.perf_counter()-started,
        scope='offline exact request-tape reconstruction to H45000; cProfile overhead present, no SLA or fair end-to-end comparison')
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['status','wall_seconds','source_changed','samples']},indent=2))

if __name__=='__main__':main()
