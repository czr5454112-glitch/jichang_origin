"""Independently reconstruct every bag's shared-D THT for the selected V5 comparison."""
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/runtime/feng_dh_v5_shared_D_20260905'
V5=ROOT/'outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5'
HISTORY=ROOT/'outputs/runtime/feng_dh_historical_signatures_20260905/paired_segments.csv.gz'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def stats(values):
    v=sorted(values)
    def q(p):
        x=(len(v)-1)*p;i=int(x)
        return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(x-i)
    return dict(count=len(v),min=v[0],mean=sum(v)/len(v),median=q(.5),p95=q(.95),p99=q(.99),max=v[-1])


def main():
    identity=json.loads((OUT/'run_identity.json').read_text(encoding='utf-8'))
    assert identity['status']=='COMPLETE'
    for filename,value in identity['outputs'].items():
        if filename.endswith('.jsonl'):
            data=gzip.decompress((OUT/(filename+'.gz')).read_bytes())
            assert hashlib.sha256(data).hexdigest()==value
        else: assert sha(OUT/filename)==value
    payload_bytes=gzip.decompress((OUT/'g31_native_payload.json.gz').read_bytes())
    assert hashlib.sha256(payload_bytes).hexdigest()==identity['native_payload_uncompressed_sha256']
    payload=json.loads(payload_bytes)
    canonical=[json.loads(x) for x in gzip.decompress((OUT/'g31_exact_historical_D.jsonl.gz').read_bytes()).decode().splitlines()]
    inputs={r['segment_id']:r for r in canonical}
    native={r['segment_id']:r for r in payload['bags']}
    assert len(native)==len(payload['bags'])==len(inputs)==43603
    assert set(native)==set(inputs)
    assert payload['loaded_cpp_binary_sha256']==identity['binary_sha256']
    with gzip.open(V5/'segments.csv.gz','rt',encoding='utf-8',newline='') as f:
        dh={(int(r['raw_bag_id']),int(r['segment_id'])):r for r in csv.DictReader(f)}
    with gzip.open(HISTORY,'rt',encoding='utf-8',newline='') as f:
        historical={(int(r['raw_bag_id']),int(r['segment_id'])):r for r in csv.DictReader(f)}
    assert len(dh)==len(historical)==43603 and set(dh)==set(historical)
    totals={name:defaultdict(float) for name in ('historical_DH','historical_HCA','V5_DH','G31')}
    segments=[]
    for segment_id,row in inputs.items():
        key=int(row['task_id']),1 if row['leg']=='storage_out' else 0
        old=historical[key];v5=dh[key];actual=native[segment_id]
        release=float(old['release_seconds'])
        assert row['pass_time']==release==float(v5['release_seconds'])
        assert actual['release_time']==release==actual['arrival_time']
        assert actual['completed'] and v5['status']=='COMPLETED'
        assert all(int(actual[k])==int(row[k])==int(old[k])==int(v5[k]) for k in ('start','goal'))
        assert actual['final_node']==int(old['goal'])
        values={'historical_DH':float(old['historical_dh_seconds']),
                'historical_HCA':float(old['historical_hca_seconds']),
                'V5_DH':float(v5['completion_time_seconds'])-release,
                'G31':float(actual['finish_time'])-release}
        assert all(v>=0 for v in values.values())
        for name,value in values.items():totals[name][key[0]]+=value
        segments.append(dict(raw_bag_id=key[0],segment_id=key[1],start=row['start'],goal=row['goal'],shared_D=release,**values))
    assert all(set(v)==set(range(28506)) for v in totals.values())
    summaries={name:stats(list(v.values())) for name,v in totals.items()}
    comparisons={base:{k:100*(1-summaries['G31'][k]/summaries[base][k]) for k in ('min','mean','p95','p99','max')}
                 for base in ('historical_DH','historical_HCA','V5_DH')}
    rows=[dict(method=k,**v) for k,v in summaries.items()]
    table=ROOT/'outputs/tables/feng_dh_v5_shared_D_20260905.csv'
    with table.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=list(segments[0]));w.writeheader();w.writerows(segments)
    (OUT/'paired_segments.csv.gz').write_bytes(gzip.compress(stream.getvalue().encode(),mtime=0))
    result={'schema':'feng.dh.v5.shared_D_pairing.v1','pass':True,'raw_bags':28506,'segments':43603,
            'every_D_OD_and_identity_matched':True,'timing_definition':'Per raw bag sum of each segment finish minus identical historical D',
            'summaries_seconds':summaries,'G31_reduction_percent':comparisons,
            'historical_rows_are_archived_measurements':True,'V5_row_is_user_selected_reconstruction':True,
            'inputs':{p.relative_to(ROOT).as_posix():sha(p) for p in [OUT/'run_identity.json',HISTORY,V5/'segments.csv.gz']},
            'outputs':{p.relative_to(ROOT).as_posix():sha(p) for p in [table,OUT/'paired_segments.csv.gz']}}
    (OUT/'comparison_and_audit.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__=='__main__':main()
