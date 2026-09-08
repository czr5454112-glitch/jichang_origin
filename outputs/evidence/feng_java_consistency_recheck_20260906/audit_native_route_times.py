from pathlib import Path
import csv,gzip,hashlib,io,json,sys,math
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'.git').exists())
RUNTIME=ROOT/'outputs/runtime/hca_segment_identity_20260906_fast_cleanup'
HERE=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def native(cell,name):
    m=json.loads((cell/'native_archive/manifest.json').read_text())
    item=next(i for i in m['files'] if i['source_name']==name)
    z=(cell/item['path']).read_bytes()
    assert sha(z)==item['sha256'],(cell,name,'gzip sha')
    b=gzip.decompress(z)
    assert sha(b)==item['uncompressed_sha256'],(cell,name,'source sha')
    if (cell/name).exists(): assert (cell/name).read_bytes()==b
    return b,{'path':str(cell/item['path']),'compressed_sha256':sha(z),'uncompressed_sha256':sha(b)}
def rows(b):return list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
results=[]
paths=sorted(RUNTIME.glob('*x/seed_*/hca_segment_identity/runner_status.json'))
if '--all' not in sys.argv: paths=[p for p in paths if p.parents[1].name=='seed_104729' and p.parents[2].name.endswith('1p00x')]
for p in paths:
    s=json.loads(p.read_text())
    if s['status']!='complete':continue
    cell=p.parent
    summary=rows(native(cell,'summary.csv')[0])[0]
    assert int(summary['fault_event_count'])==int(summary['repair_event_count'])==0
    speed=float(summary['speed_mps'])
    mapfile=Path(s['inputs']['map']['path']); mb=mapfile.read_bytes();assert sha(mb)==s['inputs']['map']['sha256']
    lines=[l.split() for l in mb.decode('utf-8-sig').splitlines() if l.strip()];n=int(lines[0][0]);dwell={int(r[0]):float(r[2]) for r in lines[1:n+1]};edge={(int(r[0]),int(r[1])):float(r[2]) for r in lines[1+2*n:]}
    rb,ref=native(cell,'routes.csv'); rr=rows(rb)
    defects=[];maxgap=0.;mingap=0.;sumgap=0.
    for r in rr:
        ns=list(map(int,r['path'].split(';')))
        expected=sum(dwell[u] for u in ns)+sum(edge[u,v]/speed for u,v in zip(ns,ns[1:]))
        elapsed=float(r['finish_time'])-float(r['epoch']);gap=elapsed-expected
        if abs(gap)>1e-7:
            defects.append({'execution_id':int(r['task_id']),'planned_epoch':float(r['epoch']),'recorded_finish_time':float(r['finish_time']),'route':ns,'sum_all_node_through_seconds':sum(dwell[u] for u in ns),'goal_through_seconds':dwell[ns[-1]],'sum_edge_travel_seconds':sum(edge[u,v]/speed for u,v in zip(ns,ns[1:])),'expected_finish_time':float(r['epoch'])+expected,'excess_seconds':gap})
            maxgap=max(maxgap,gap);mingap=min(mingap,gap);sumgap+=gap
    examples=defects[:3]
    if examples:
        identities={int(r['execution_id']):r for r in rows(native(cell,'segment_execution_identity.csv')[0])}
        for ex in examples:ex['execution_mapping']=identities[ex['execution_id']]
    result={'cell':str(cell.relative_to(ROOT)),'source_sha256':s['source_sha256'],'class_sha256':s['class_sha256'],'build_identity_sha256':s['build_identity_sha256'],'map_sha256':sha(mb),'route_evidence':ref,'speed_mps':speed,'no_faults':True,'goal_through_values_seconds':sorted({dwell[int(r['goal'])] for r in rr}),'planned_route_count':len(rr),'route_formula_mismatch_count':len(defects),'max_excess_seconds':maxgap,'min_excess_seconds':mingap,'sum_excess_seconds':sumgap,'examples':examples}
    results.append(result)
    print(json.dumps({'cell':cell.parents[1].name+'/'+cell.parent.name,'routes':len(rr),'mismatches':len(defects),'max_excess_seconds':maxgap}),flush=True)
out={'schema':'czr005.original_hca_route_time_formula_diagnostic.v1','status':'MISMATCH_DETECTED' if any(x['route_formula_mismatch_count'] for x in results) else 'NO_TOTAL_ROUTE_TIME_MISMATCH_DETECTED','scope':'read-only native full planned path vs original no-fault Astar recurrence including wrapper-exported goal T2; no reservation collision proof; no intermediate node timestamps available','equation':'expected_goal_T2 = planned_epoch + sum(all path node through times INCLUDING source and goal) + sum(edge lengths / configured speed)','auditor_sha256':sha(Path(__file__).read_bytes()),'corrected_formula_note':'Goal T2 is the exported route finish; includes goal dwell. Initial tmp diagnostic omitted it and is superseded. This report recomputes every count.','audited_cell_count':len(results),'mismatch_cell_count':sum(bool(x['route_formula_mismatch_count']) for x in results),'planned_route_count':sum(x['planned_route_count'] for x in results),'route_formula_mismatch_count':sum(x['route_formula_mismatch_count'] for x in results),'cells':results}
(HERE/('native_route_time_audit_all.json' if '--all' in sys.argv else 'native_route_time_audit_sample.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
