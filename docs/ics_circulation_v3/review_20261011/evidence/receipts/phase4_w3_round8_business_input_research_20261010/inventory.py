"""Read-only source/projection audit. No simulator/controller imports or calls.

Emit one *business* bag per raw ID, preserving source provenance. This is an
input-design artifact, not an executable physical scenario: operational policy
fields deliberately remain unresolved. Root can implement the declared stage
interface later without treating the old independent legs as real tray reuse.
"""
from pathlib import Path
from collections import Counter, defaultdict
from hashlib import sha256
from time import process_time, perf_counter
import gzip, heapq, json, math, zipfile
import xml.etree.ElementTree as ET

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'scripts/experiments/ics_circulation_v3').is_dir())
HERE = Path(__file__).parent
HIST = ROOT/'.g4irsf24_worktree'
TASKS = HIST/'artifacts/tasks/g4irsf31_nanning'
SOURCE = ROOT/'legacy/jichang_origin_readonly/inputdata.txt'
PROFILE = ROOT/'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'
DOCX = Path(r'C:/Users/38908/xwechat_files/wxid_4820408204312_a0d1/msg/file/2026-09/ICS调度研究方向梳理.docx')
SUPPLEMENT = Path(r'C:/Users/38908/xwechat_files/wxid_4820408204312_a0d1/msg/file/2026-10/研究问题的说明/问题及约束说明.docx')


def audit():
    cpu, wall = process_time(), perf_counter()
    if (HERE/'analysis.json').exists():
        raise FileExistsError('Retain each independent audit invocation; never overwrite evidence.')
    bindings, checks = {}, Counter()
    def read(path):
        path = Path(path); data = path.read_bytes()
        bindings[str(path.resolve())] = sha256(data).hexdigest()
        return data
    def obj(path): return json.loads(read(path).decode('utf-8-sig'))
    def check(name, condition):
        checks[name] += 1
        if not condition: raise AssertionError(name)
    def raw(path):
        lines = read(path).decode('utf-8-sig').splitlines()
        check('seven-field raw header', lines[0].split() == ['ID','EntryTime(s)','STD(s)','star','end','Unloader','Loader'])
        rows = {}
        for n, line in enumerate(lines[1:], 2):
            if not line.strip(): continue
            x = line.split(); check('raw field count', len(x)==7)
            r = dict(id=int(x[0]), arrival=float(x[1]), std=float(x[2]), start=int(x[3]), end=int(x[4]), unloader=x[5], loader=x[6], source_line=n)
            check('identity and finite clock', r['id'] not in rows and all(math.isfinite(r[k]) for k in ('arrival','std')) and r['std']>=r['arrival'])
            rows[r['id']] = r
        return rows
    profile = obj(PROFILE); nodes = {n['location']:n for n in profile['nodes']}
    historical_profile = obj(HIST/'data/processed/maps/nanning_airport_profile.json')
    check('profile semantic equality', profile==historical_profile)
    source = raw(SOURCE)
    historical_source = read(HIST/'legacy/jichang_origin_readonly/inputdata.txt')
    check('original timetable byte equality across root/historical checkout', historical_source==read(SOURCE))
    # Independent reproduction of deterministic atomic projection, without
    # importing a historical script which could alter sys.path or run physics.
    lanes, flights, transfers = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in source.values():
        f=(r['std'],r['end'],r['unloader']); flights[f].append(r)
        if r['loader']=='T': transfers[f].append(r)
        else: lanes[(r['loader'],r['start'])].append(r)
    def assign(groups, targets):
        loads={n:0 for n in targets}; mapping={}
        for key, rows in sorted(groups.items(),key=lambda kv:(-len(kv[1]),repr(kv[0]))):
            node=min(loads,key=lambda n:(loads[n],n));mapping[key]=node;loads[node]+=len(rows)
        return mapping
    roles=profile['business_roles']
    lane_map=assign(lanes,roles['standard_loader_nodes'])
    flight_map=assign(flights,roles['unloader_nodes'])
    transfer_map=assign(transfers,roles['transfer_loader_nodes'])
    streams=defaultdict(list)
    for std,end,unloader in flights: streams[(end,unloader)].append(std)
    shifts={}
    for key,times in streams.items():
        times.sort(); gaps=sorted(b-a for a,b in zip(times,times[1:]))
        check('densification stream headways', len(gaps)>0 and min(gaps)>0)
        terminal=gaps[(len(gaps)-1)//2]/2
        for i,t in enumerate(times): shifts[(t,*key)]=(times[i+1]-t)/2 if i+1<len(times) else terminal
    adjacency=defaultdict(list)
    cross=set()
    for e in profile['edges']:
        if e['capacity']>0:adjacency[e['start']].append((e['end'], e['length']/e['speed']))
        if nodes[e['start']]['system_key']!=nodes[e['end']]['system_key']:cross.add((e['start'],e['end']))
    def shortest(start):
        d={start:0.}; paths={start:()}; q=[(0.,start)]
        while q:
            value,node=heapq.heappop(q)
            if value!=d[node]:continue
            for target,cost in sorted(adjacency[node]):
                candidate=value+cost
                if candidate<d.get(target,math.inf):
                    d[target]=candidate;paths[target]=paths[node]+((node,target),);heapq.heappush(q,(candidate,target))
        return d,paths
    all_paths={n:shortest(n) for n in nodes}
    def od(a,b):
        return 'outbound_unreachable' if b not in all_paths[a][0] else 'return_unreachable' if a not in all_paths[b][0] else 'directed_cycle_available'
    od_all=Counter(od(a,b) for a in roles['source_candidate_ids'] for b in roles['sink_candidate_ids'])
    summaries=[]; offset=max(source)+1; ordered_source=list(source.values())
    for scale in (1,2):
        prefix=TASKS/f'nanning_{scale}x'
        raw_path=prefix.with_name(prefix.name+'_raw.txt')
        rows=raw(raw_path); manifest=obj(prefix.with_name(prefix.name+'_manifest.json'))
        canonical=read(prefix.with_name(prefix.name+'_canonical.jsonl')).decode('utf-8-sig')
        legs=defaultdict(list); segment_ids=set()
        for line in canonical.splitlines():
            if not line.strip(): continue
            s=json.loads(line); r=rows[s['task_id']]
            check('canonical unique segment',s['segment_id'] not in segment_ids);segment_ids.add(s['segment_id']);legs[r['id']].append(s)
            check('canonical original attributes', (s['original_start'],s['original_goal'],s['original_entry_time'],s['std'],s['source_line'])==(r['start'],r['end'],r['arrival'],r['std'],r['source_line']))
            check('legacy pallet identity is task identity',s['pallet_id']==r['id'])
        counts=Counter(); link_use=Counter(); origins=Counter(); destinations=Counter(); hour_counts=Counter(); normalized=[]
        for r in rows.values():
            inserted=r['id'] not in source
            check('inserted source rank',not inserted or (scale==2 and 0<=r['id']-offset<len(ordered_source)))
            parent=ordered_source[r['id']-offset] if inserted else source[r['id']]
            f=(parent['std'],parent['end'],parent['unloader']); shift=shifts[f] if inserted else 0
            expected_start=transfer_map[f] if parent['loader']=='T' else lane_map[(parent['loader'],parent['start'])]
            check('atomic projection rebuilt', (r['start'],r['end'])==(expected_start,flight_map[f]))
            check('source timing or complete-manifest shift preserved',abs(r['arrival']-parent['arrival']-shift)<1e-8 and r['std']==parent['std']+shift)
            check('projected aliases',r['loader']==nodes[r['start']]['alias'] and r['unloader']==nodes[r['end']]['alias'])
            early=r['std']-r['arrival']>=4800; byleg={s['leg']:s for s in legs[r['id']]}
            check('one original bag complete lifecycle', sorted(byleg)==(['storage_in','storage_out'] if early else ['direct']) and len(byleg)==len(legs[r['id']]))
            release=r['std']-2700 if early else None
            expected={'storage_in':(r['start'],53,r['arrival']),'storage_out':(53,r['end'],release)} if early else {'direct':(r['start'],r['end'],r['arrival'])}
            for leg,key in expected.items():
                s=byleg[leg];check('legacy independent stage release rule',(s['start'],s['goal'],s['pass_time'])==key)
            counts['early' if early else 'direct']+=1;counts[od(r['start'],r['end'])]+=1
            counts['inserted' if inserted else 'original']+=1
            origins[str(r['start'])]+=1;destinations[str(r['end'])]+=1;hour_counts[int(r['arrival']//3600)]+=1
            stages=((r['start'],53),(53,r['end'])) if early else ((r['start'],r['end']),)
            missing_stage=any(b not in all_paths[a][0] for a,b in stages)
            counts['stage_route_unreachable' if missing_stage else 'stage_routes_available']+=1
            if early and 53 in all_paths[r['start']][0]:
                counts['earliest_travel_only_ingress_after_scheduled_release']+=int(r['arrival']+all_paths[r['start']][0][53]>release)
            for a,b in stages:
                for edge in all_paths[a][1].get(b,()):
                    if edge in cross:link_use[f'{edge[0]}->{edge[1]}']+=1
            normalized.append({'business_bag_id':f'projected:{scale}x:{r["id"]}',
                'source':{'raw_sha256':bindings[str(raw_path.resolve())],'source_line':r['source_line'],'raw_task_id':r['id'],
                    'parent_timetable_sha256':bindings[str(SOURCE.resolve())],'parent_task_id':parent['id'],'parent_source_line':parent['source_line'],
                    'flight_surrogate':list(f),'synthetic_inserted':inserted,'time_shift_seconds':shift},
                'arrival_seconds':r['arrival'],'std_seconds':r['std'],'origin':str(r['start']),'final_destination':str(r['end']),
                'lifecycle':'early_storage' if early else 'direct','storage_node_proxy':str(53) if early else None,
                'scheduled_release_seconds':release,'old_segment_ids':[s['segment_id'] for s in legs[r['id']]],
                'physical_tray_id':None,'deadline_contract':None,'protected_contract':None,'storage_carrier_policy':None,
                'status':'normalized_input_only_operational_contract_required'})
        check('manifest full counts',(len(rows),len(segment_ids),counts['direct'],counts['early'])==(manifest['raw_task_count'],manifest['expanded_segment_count'],manifest['direct_raw_task_count'],manifest['early_split_raw_task_count']))
        check('manifest origin marginal',dict(origins)==manifest['raw_by_start']);check('manifest goal marginal',dict(destinations)==manifest['raw_by_goal'])
        check('scale exact source denominator',len(rows)==len(source)*scale and counts['original']==len(source) and counts['inserted']==len(source)*(scale-1))
        output=HERE/f'business_tasks_{scale}x.jsonl.gz'
        with output.open('wb') as stream:
            with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as gz:
                for row in sorted(normalized,key=lambda r:(r['arrival_seconds'],r['business_bag_id'])):
                    gz.write((json.dumps(row,separators=(',',':'),sort_keys=True)+'\n').encode())
        summaries.append({'scale':scale,'raw_count':len(rows),'segment_count':len(segment_ids),'counts':dict(counts),
            'flight_groups':manifest['flight_count'],'source_flight_groups':manifest['source_flight_count'],
            'hour_arrival_counts':dict(sorted(hour_counts.items())),
            'static_shortest_stage_cross_edge_use':dict(sorted(link_use.items())),
            'normalized_artifact':output.name,'normalized_sha256':sha256(output.read_bytes()).hexdigest(),
            'qualification':'All rows retained. Static travel-only directed witnesses are not reservations, admitted trajectories, dynamic feasibility, expected load, or simulation.'})
    source_files=[ROOT/'src/czr005/io/legacy_tasks.py',HIST/'src/czr005/io/legacy_tasks.py',
        HIST/'scripts/eval/run_g4irsf31_nanning_workload.py',HIST/'scripts/eval/run_g4irsf29_workload.py',
        ROOT/'docs/ics_circulation_v3/ICS_plan_revision_and_learning_20261006.md',
        ROOT/'docs/ics_circulation_v3/phase4_external_review_20261009/ICS_V3_030493_audit_and_phase4_plan_20261009.md',
        ROOT/'outputs/reports/ics_new_requirements_research_plan_20261006.md',
        ROOT/'outputs/reports/ics_new_requirements_joint_plan_v2_20261006.md',
        ROOT/'outputs/reports/ics_new_requirements_map_gap_audit_20260929.md',
        ROOT/'outputs/reports/ics_new_requirements_decision_checklist_20260929.md',
        ROOT/'cpp/ics_core/runtime/bounded_local_pibt.hpp',Path(__file__),HERE/'BUSINESS_INPUT_DESIGN.md']
    for name in ('phase4_network_workloads.py','nanning_routing_benchmark.py','model.py','runtime.py','distributed_local.py','same_zone_supply.py','distributed.py','phase4_control.py','learning.py'):
        source_files.append(ROOT/'scripts/experiments/ics_circulation_v3'/name)
    source_files+=list((ROOT/'map_nanning').glob('*.xlsx'))
    note=ROOT/'outputs/experiments/ics_circulation_v3/phase4_w3_round8_stability_analysis_20261010/EBS_CARRIER_SEMANTICS_SOURCES.md'
    if note.exists():source_files.append(note)
    for path in source_files:read(path)
    attachment_equality={}
    for path,name in ((DOCX,'original_requirement_text.txt'),(SUPPLEMENT,'supplement_requirement_text.txt')):
        read(path)
        with zipfile.ZipFile(path) as z:doc=ET.fromstring(z.read('word/document.xml'))
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        paras=[''.join(t.text or '' for t in p.iter(ns+'t')) for p in doc.iter(ns+'p')]
        (HERE/name).write_text('\n'.join(paras),encoding='utf8')
    for n in (1,2):
        name=f'附件：拓扑结构示例{n}.xlsx'
        attachment_equality[name]=read(SUPPLEMENT.parent/name)==read(ROOT/'map_nanning'/name)
        check('supplement topology attachment exact root copy',attachment_equality[name])
    stable=all(sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in bindings.items())
    check('all bound inputs unchanged',stable)
    result={'schema':'ics_round8_business_input_inventory_v1','physical_calls':0,'routing_queries':0,
        'source_original_bags':len(source),'source_flight_surrogates':len(flights),'source_streams':len(streams),
        'profiles_semantically_equal':True,'profile_bytes_equal':bindings[str(PROFILE.resolve())]==bindings[str((HIST/'data/processed/maps/nanning_airport_profile.json').resolve())],
        'supplement_attachment_byte_equal':attachment_equality,
        'topology_counts':profile['counts'],'loader_unloader_od_classes':dict(od_all),
        'cross_edges':[{'source':a,'destination':b,'source_alias':nodes[a]['external_id'],'destination_alias':nodes[b]['external_id'],
            'length_m':next(e['length'] for e in profile['edges'] if(e['start'],e['end'])==(a,b)),
            'capacity_recorded':next(e['capacity'] for e in profile['edges'] if(e['start'],e['end'])==(a,b))} for a,b in sorted(cross)],
        'datasets':summaries,'checks_by_family':dict(checks),'checks':sum(checks.values()),'failed_checks':0,
        'bound_inputs':bindings,'all_bound_inputs_unchanged':stable,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Pure-file parse, independent mapping/time/lifecycle/static graph audit and normalized gzip writes after Python imports through input rehash. Final analysis/manifest writes and prior manual reads excluded; no engine, routing generator or physical rollout imported/invoked.'}
    (HERE/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    manifest={'input_sha256':bindings,'physical_calls':0,'outputs':{p.name:sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.is_file() and p.name!='manifest.json'}}
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('checks','failed_checks','physical_calls','cpu_seconds','wall_seconds')}))


if __name__=='__main__':
    started_cpu,started_wall=process_time(),perf_counter()
    try:audit()
    except Exception as exc:
        failure={'status':'failed','error':{'type':type(exc).__name__,'message':str(exc)},
            'cpu_seconds':process_time()-started_cpu,'wall_seconds':perf_counter()-started_wall,
            'physical_calls':0,'resource_scope':'Failed pure-file audit after imports; partial artifacts retained. No simulation.'}
        target=HERE/'failure.json'
        if not target.exists():target.write_text(json.dumps(failure,indent=2),encoding='utf8')
        raise
