"""Stream 010c/011 full parity, allowing only elapsed times and actual scan work."""
from pathlib import Path
import argparse, copy, hashlib, itertools, json
from micro import TIMES, first_difference

HERE=Path(__file__).resolve().parent
CORES=('01e3289e7934ae164fd0014c34878657027cff7811186384080cf885d68523e3',
       'c03b54db9ff7756ca90bbf5fe22fd64ea3117dde0493dd60850ed16162a1866c')
BINARIES=('493ffb54331e6f0010b1fea524a64d74d1fe8d04896f1d2e6927d92628c5c0f5',
          'e0b0d90a486b119cfcce70bf539501b96d08ac6d9d0a56aca21c72a7002f61c1')
AUDITS=('headway_audit','rolling_replay','source_policy_audit','tht_audit','business_audit')
SCAN='future_calendar_entries_scanned'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def normalized(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def without(v,keys):return {k:x for k,x in v.items() if k not in keys}
def require_same(a,b,label):
    d=first_difference(a,b)
    if d:raise ValueError(label+d)
def stream_bags(a,b):
    hashes=[hashlib.sha256(),hashlib.sha256()];logical=[hashlib.sha256(),hashlib.sha256()]
    sizes=[0,0];counts=[0,0];scans=[0,0];raw_exact=True;examples=[];changed=0
    with a.open('rb') as af,b.open('rb') as bf:
        for ordinal,pair in enumerate(itertools.zip_longest(af,bf),1):
            if None in pair:raise ValueError('bag file lengths differ')
            raw_exact &= pair[0]==pair[1];values=[]
            for i,line in enumerate(pair):
                hashes[i].update(line);sizes[i]+=len(line);counts[i]+=1
                v=json.loads(line)
                count=v.pop(SCAN)
                if type(count) is not int or count<0:raise ValueError('invalid scanned counter')
                scans[i]+=count;values.append((v,count));logical[i].update(normalized(v)+b'\n')
            if values[1][1]>values[0][1]:raise ValueError('candidate bag scans unexpectedly increase')
            d=first_difference(values[0][0],values[1][0])
            if d:
                changed+=1
                if len(examples)<10:examples.append(dict(ordinal=ordinal,segment_id=values[0][0].get('segment_id'),difference=d))
    return dict(passed=changed==0,records=counts[0],candidate_records=counts[1],changed_nonallowed_records=changed,
      examples=examples,serialized_bytes_exact=raw_exact,reference_sha256=hashes[0].hexdigest(),candidate_sha256=hashes[1].hexdigest(),
      reference_bytes=sizes[0],candidate_bytes=sizes[1],reference_logical_sha256=logical[0].hexdigest(),candidate_logical_sha256=logical[1].hexdigest(),
      reference_scan_sum=scans[0],candidate_scan_sum=scans[1])
def stream_exact(a,b):
    hashes=[hashlib.sha256(),hashlib.sha256()];sizes=[0,0];counts=[0,0];same=True
    with a.open('rb') as af,b.open('rb') as bf:
        while True:
            pair=(af.read(1<<20),bf.read(1<<20))
            if not any(pair):break
            same &= pair[0]==pair[1]
            for i,chunk in enumerate(pair):hashes[i].update(chunk);sizes[i]+=len(chunk);counts[i]+=chunk.count(b'\n')
    return dict(passed=same,serialized_bytes_exact=same,records=counts[0],candidate_records=counts[1],
      reference_sha256=hashes[0].hexdigest(),candidate_sha256=hashes[1].hexdigest(),reference_bytes=sizes[0],candidate_bytes=sizes[1])
def run(reference,candidate):
    dirs=[Path(reference).resolve(),Path(candidate).resolve()]
    if dirs[0]==dirs[1]:raise ValueError('distinct runs required')
    tracked={}
    def track(p):
        p=Path(p);tracked[p]=(p.stat().st_size,p.stat().st_mtime_ns);return p
    manifests=[read(track(d/'manifest.json')) for d in dirs]
    for i,m in enumerate(manifests):
        if m.get('status')!='complete' or m.get('audits_passed') is not True:raise ValueError('completed independent audit pipeline required')
        s=m['selection']
        if s['native_source']['sha256']!=CORES[i] or s['binary']['sha256']!=BINARIES[i]:raise ValueError('unexpected source/binary')
        if sha(track(s['binary']['path']))!=BINARIES[i]:raise ValueError('binary changed')
        for n,h in m['source_sha256'].items():
            if sha(track(dirs[i]/'standard_sources'/n))!=h:raise ValueError('saved evidence changed: '+n)
        if m['source_sha256']['core.cpp']!=CORES[i]:raise ValueError('saved core is not registered build')
    a,b=[m['selection'] for m in manifests]
    identity={'contract','binary','build_receipt','native_source','standard_id','selection_label','entrypoint','controls'}
    require_same(without(a,identity),without(b,identity),'selection policy ')
    require_same(without(a['controls'],{'path'}),without(b['controls'],{'path'}),'control bytes ')
    for i,s in enumerate((a,b)):
        for key in ('contract','controls','build_receipt','entrypoint'):
            if sha(track(s[key]['path']))!=s[key]['sha256']:raise ValueError('selection evidence changed: '+key)
    contracts=[read(d/'standard_sources/contract.json') for d in dirs]
    require_same(without(contracts[0],{'native_source','default_binary','candidate_id'}),
                 without(contracts[1],{'native_source','default_binary','candidate_id'}),'physical contract ')
    if contracts[0]['candidate_id']!='g31_continuous_010c_future_source_reservation' or contracts[1]['candidate_id']!='g31_continuous_011_future_source_reservation_calendar_index':
        raise ValueError('unexpected isolated contract identity')
    for c,s in zip(contracts,(a,b)):
        require_same(c['native_source'],s['native_source'],'contract source registration ')
        if c['default_binary']['sha256']!=s['binary']['sha256']:raise ValueError('contract binary registration changed')
    allowed_sources={'core.cpp','contract.json','build_receipt.json','g31_continuous_adapter.py'}
    require_same(without(manifests[0]['source_sha256'],allowed_sources),without(manifests[1]['source_sha256'],allowed_sources),'audit/input source hashes ')
    old_adapter=(dirs[0]/'standard_sources/g31_continuous_adapter.py').read_text(encoding='utf-8')
    expected=old_adapter.replace('candidate010','candidate011').replace('AUDITORS = Path(__file__).resolve().parent / "auditors"',
      'AUDITORS = Path(__file__).resolve().parent.parent / "candidate010" / "auditors"')
    if (dirs[1]/'standard_sources/g31_continuous_adapter.py').read_text(encoding='utf-8')!=expected:
        raise ValueError('adapter changes beyond isolated identity/path')
    old_entry=(dirs[0]/'standard_sources/run_candidate.py').read_text(encoding='utf-8')
    if (dirs[1]/'standard_sources/run_candidate.py').read_text(encoding='utf-8')!=old_entry.replace('candidate010','candidate011'):
        raise ValueError('entrypoint changed beyond candidate identity')
    configs=[read(track(d/'config.json')) for d in dirs];require_same(*configs,'effective controls ')
    if configs[0]['future_source_reservation_min_wait_seconds']!=2:raise ValueError('this registered comparison is minwait2')
    statuses=[]
    for d in dirs:
        result={n:read(track(d/(n+'.json'))).get('passed') for n in AUDITS}
        if not all(v is True for v in result.values()):raise ValueError('independent gate missing or failed')
        statuses.append(result)
    native=[read(track(d/'native_summary.json')) for d in dirs]
    for s,c in zip(native,configs):
        if s['event_budget_exhausted'] or s['executed_horizon']!=c['end_time']:raise ValueError('incomplete horizon execution')
    native_diff=first_difference(without(native[0],TIMES|{SCAN}),without(native[1],TIMES|{SCAN}))
    standard=[read(track(d/'summary.json')) for d in dirs]
    for s,n in zip(standard,native):require_same(s['native'],n,'native copy ')
    std_diff=first_difference(without(standard[0],{'native'}),without(standard[1],{'native'}))
    bags=stream_bags(track(dirs[0]/'bags.jsonl'),track(dirs[1]/'bags.jsonl'))
    ledger=stream_exact(track(dirs[0]/'rolling_events.jsonl'),track(dirs[1]/'rolling_events.jsonl'))
    for i,prefix in enumerate(('reference','candidate')):
        if bags[prefix+'_sha256']!=manifests[i]['bags_sha256']:raise ValueError('bag bytes changed since manifest')
        if bags[prefix+'_scan_sum']!=native[i][SCAN]:raise ValueError('bag/global scan counters do not conserve')
    if bags['records']!=a['segment_denominator'] or bags['candidate_records']!=b['segment_denominator']:raise ValueError('bag denominator mismatch')
    if ledger['records']!=native[0]['rolling_ledger_records'] or ledger['candidate_records']!=native[1]['rolling_ledger_records']:raise ValueError('ledger count mismatch')
    if any((p.stat().st_size,p.stat().st_mtime_ns)!=v for p,v in tracked.items()):raise ValueError('evidence changed during scan')
    return dict(schema='g31.candidate011.full_parity.v1',passed=bags['passed'] and ledger['passed'] and native_diff is None and std_diff is None,
      reference_run=str(dirs[0]),candidate_run=str(dirs[1]),bags=bags,rolling_events=ledger,
      native_nonallowed_difference=native_diff,standard_summary_difference=std_diff,independent_audits=statuses,
      allowed_time_fields=sorted(TIMES),allowed_work_fields=['summary.'+SCAN,'bags[*].'+SCAN],
      execution_identity_differences='Only registered source/binary/build, candidate/entrypoint labels, controls path with identical bytes, adapter candidate name/auditor path.',
      source_sha256=dict(reference=CORES[0],candidate=CORES[1],parity_tool=sha(__file__),micro_helper=sha(HERE/'micro.py')),
      manifest_sha256=dict(reference=sha(dirs[0]/'manifest.json'),candidate=sha(dirs[1]/'manifest.json')),
      timing={k:dict(reference=native[0].get(k),candidate=native[1].get(k)) for k in sorted(TIMES)},
      boundary='No full-run speed or parity conclusion until this actual receipt passes. Bag equality excludes only real scan count; ledger must be byte exact.')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    result=run(a.reference,a.candidate);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','native_nonallowed_difference','standard_summary_difference')}))
    return 0 if result['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
