"""Refine saved census binding: raw generator pool can exceed authorized prefix pool."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import process_time,perf_counter
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent

def main():
    cpu,wall=process_time(),perf_counter();source=OUT/'census.json';target=OUT/'census_repaired.json'
    if target.exists():raise FileExistsError(target)
    data=source.read_bytes();s=json.loads(data);checks=[];filtered=[]
    for q in s['queries']:
        if q['bag_id']is not None:
            # Initial pass only populated keys/version when exactly one actual
            # query signature matched; no weakening of uniqueness is needed.
            valid='version'in q and 'actual_action_keys'in q
            n=len(q.get('actual_action_keys',[]))
            checks.append({'query':[q['case_id'],q['query_ordinal']],
                           'okay':valid and n<=q['candidate_count']})
            q['authorized_candidate_count']=n if valid else None
            if valid and n<q['candidate_count']:filtered.append(q)
    for q in s['truncated_queries']:
        if q['bag_id']is None:
            matches=q['same_tick_slow_rejection_matches']
            q['slow_site_evidence']='unique same tick/tray exhaustion rejection'if len(matches)==1 else 'ambiguous'
            if len(matches)==1:q['inferred_slow_domain']=matches[0].get('domain','not_logged')
    unchanged=all(sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in s['bound_file_sha256'].items())
    initial_other=[e for e in s['failures']if e['kind']!='loaded_query_opportunity_binding']
    result={**s,'schema':'ics_round7_search_truncation_census_repaired_v1',
        'initial_failed_analysis':{'file':str(source.relative_to(ROOT)),'sha256':sha256(data).hexdigest(),
            'failed_checks':s['failed_checks'],'reason':'Invalid analyzer assumption raw generator K equals post-next_edge validator authorized K; original runtime explicitly filters.'},
        'authorized_pool_filtered_queries':filtered,
        'filtered_query_count':len(filtered),
        'truncated_domain_counts':dict(Counter(q.get('inferred_slow_domain','loaded')for q in s['truncated_queries'])),
        'checks':len(checks)+1,'failed_checks':sum(not c['okay']for c in checks)+bool(initial_other)+int(not unchanged),
        'failures':[c for c in checks if not c['okay']]+initial_other,'changed_inputs':[]if unchanged else ['source raw SHA changed'],
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'initial_analysis_cpu_nested_metadata_not_added':s['cpu_seconds'],
        'resource_scope':'Pure-file correction of already extracted query bindings and raw SHA revalidation; no repeated generation or simulation. Prior failed analyzer is separate CPU.',
        'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k]for k in ('query_count','truncated_count','filtered_query_count','truncated_domain_counts','checks','failed_checks','cpu_seconds','wall_seconds')}))
    if result['failed_checks']:raise SystemExit(1)
if __name__=='__main__':main()
