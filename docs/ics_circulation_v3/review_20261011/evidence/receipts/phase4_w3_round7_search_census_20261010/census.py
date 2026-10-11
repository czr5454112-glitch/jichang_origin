"""All round6 old32/new queries: pure-file, no routing or simulation import."""
from collections import Counter,defaultdict
from hashlib import sha256
import gzip,json
from pathlib import Path
from time import process_time,perf_counter
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/experiments/ics_circulation_v3'
RUN=BASE/'phase4_w3_same_zone_supply_repaired_20261010'

def main():
    cpu,wall=process_time(),perf_counter();dest=OUT/'census.json'
    if dest.exists():raise FileExistsError(dest)
    bound={};checks=[];all_queries=[];truncated=[];case_counts=[]
    def read(path):
        data=path.read_bytes();bound[str(path.relative_to(ROOT))]=sha256(data).hexdigest()
        return json.loads((gzip.decompress(data)if path.suffix=='.gz'else data).decode('utf-8-sig'))
    summary=read(RUN/'full/summary.json');manifest=read(RUN/'full/manifest.json')
    chosen=[r for r in summary['rows']if r['policy']in ('old32','same_zone32plus32')]
    checks.append({'kind':'full_denominator','okay':len(chosen)==54})
    for row in chosen:
        path=RUN/row['file'];raw=read(path);name=row['case_id']
        checks.append({'kind':'raw_sha','case':name,'okay':bound[str(path.relative_to(ROOT))]==row['sha256']==manifest[path.name]})
        searches=raw['searches'];opportunities=raw['opportunities'];by_signature=defaultdict(list)
        for op in opportunities:by_signature[(op['time'],op['node'],op['bag_id'],op['tray_id'])].append(op)
        calls={c['time']:c for c in raw['slow_calls']}
        slow_rejections=defaultdict(list)
        for c in raw['slow_calls']:
            for rejection in c['diagnostics'].get('candidate_rejections',[]):
                if rejection.get('search_status')=='expansion_budget_exhausted':
                    slow_rejections[c['time'],rejection['tray_id']].append(rejection)
        counts=Counter()
        for i,q in enumerate(searches):
            op=by_signature.get((q['time'],q['node'],q['bag_id'],q['tray_id']),[])
            loaded=q['bag_id']is not None
            if loaded:
                checks.append({'kind':'loaded_query_opportunity_binding','case':name,'query':i,
                               'okay':len(op)==1 and op[0]['candidate_count']==q['candidate_count']})
            site='engine_loaded'if loaded else 'empty_site_not_in_query_record'
            query={'case_id':name,'scene':row['scene'],'policy':row['policy'],'tape_id':row['tape_id'],
                   'query_ordinal':i,**q,'site':site,'requested_k':4 if loaded else 1,
                   'zero_or_partial':'zero'if q['candidate_count']==0 else 'partial'if q['candidate_count']<(4 if loaded else 1)else 'full',
                   'generator_family_from_frozen_contract':'RegionalCandidateGenerator(dynamic_local=True)',
                   'reference_fallback':False}
            if loaded and len(op)==1:
                o=op[0];bag=o['visible_state']['bags'][q['bag_id']]
                role='destination'if q['node']==bag['destination']else 'origin'if q['node']==bag['origin']else 'continuation'
                query.update(destination=bag['destination'],opportunity_sequence=o['sequence'],role=role,
                    protected=o['protected'],version=o['version'],
                    public_snapshot_sha256=sha256(json.dumps(o['visible_state'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                    actual_action_keys=o['candidate_keys'],
                    state_recovery='Exact public physical Snapshot from opportunity.visible_state + frozen original network. Cache-before-query and full resumable engine checkpoint not saved.')
            else:
                query['state_recovery']='Not exact from old query record: slow scratch/engine empty phase, destination, version and query cache are missing.'
            counts[(site,q['status'],query['zero_or_partial'])]+=1
            all_queries.append(query)
            if q['status']=='expansion_budget_exhausted':
                detail=dict(query)
                detail['same_tick_slow_rejection_matches']=slow_rejections.get((q['time'],q['tray_id']),[])
                detail['same_tick_slow_search_calls']=calls.get(q['time'],{}).get('diagnostics',{}).get('search_calls')
                if loaded and len(op)==1:
                    detail['opportunity']=op[0]
                truncated.append(detail)
        checks.append({'kind':'search_totals','case':name,'okay':len(searches)==row['search_calls']and sum(q['work']for q in searches)==row['search_work']})
        case_counts.append({'case_id':name,'search_calls':len(searches),'work':sum(q['work']for q in searches),
            'counts':[{'site':k[0],'status':k[1],'pool':k[2],'count':v}for k,v in sorted(counts.items())]})
        del raw
    aggregate=Counter((q['policy'],q['site'],q['status'],q['zero_or_partial'])for q in all_queries)
    # Stable predeclared coverage sample, independent of costs or branch values.
    # Exact old states presently recoverable only for loaded inputs. Empty sites
    # await collector-level query snapshots and are not silently substituted.
    selected=[];cells=defaultdict(list)
    for q in truncated:
        cell=(q['scene'],q['policy'],q['site'],q['zero_or_partial'],q.get('role','unknown'))
        cells[cell].append(q)
    for cell,values in sorted(cells.items()):
        for q in sorted(values,key=lambda x:(x['tape_id'],x['time'],x['query_ordinal']))[:2]:
            selected.append({'cell':cell,'case_id':q['case_id'],'query_ordinal':q['query_ordinal'],
                             'reason':'first two by fixed tape,time,query ordering; no outcome fields consulted'})
    changed=[p for p,h in bound.items()if sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    result={'schema':'ics_round7_search_truncation_census_v1','new_physical_simulations':0,
        'case_count':len(chosen),'query_count':len(all_queries),'truncated_count':len(truncated),
        'aggregate':[{'policy':k[0],'site':k[1],'status':k[2],'pool':k[3],'count':v}for k,v in sorted(aggregate.items())],
        'case_counts':case_counts,'queries':all_queries,'truncated_queries':truncated,
        'representative_selection':selected,'selection_scope':'fixed shape/chronology coverage diagnostic; not a performance confirmation subset',
        'checks':len(checks),'failed_checks':sum(not c['okay']for c in checks),
        'failures':[c for c in checks if not c['okay']],'bound_file_sha256':bound,'changed_inputs':changed,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Pure-file full54 read/hash/query-opportunity binding and summarization; excludes final serialization.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('case_count','query_count','truncated_count','aggregate','checks','failed_checks','changed_inputs','cpu_seconds','wall_seconds')},ensure_ascii=False))
    if changed or result['failed_checks']:raise SystemExit(1)

if __name__=='__main__':main()
