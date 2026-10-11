"""Independent static domain recomputation from ORIGINAL raw + canonical.

Does not read normalized business records for group or lifecycle construction,
does not assign destinations, call a route generator, or advance physics.
"""
from pathlib import Path
from collections import defaultdict
from hashlib import sha256
from time import process_time,perf_counter
import json

HERE=Path(__file__).parent
ROOT=next(p for p in HERE.parents if(p/'scripts/experiments/ics_circulation_v3').is_dir())
BASE=HERE.parent

if __name__=='__main__':
    cpu,wall=process_time(),perf_counter();bindings={};checks=0
    if(HERE/'analysis.json').exists():raise FileExistsError('retain independent invocations')
    def read(p):
        data=p.read_bytes();bindings[str(p.resolve())]=sha256(data).hexdigest();return data
    def obj(p):return json.loads(read(p).decode('utf-8-sig'))
    def check(condition):
        global checks
        checks+=1
        if not condition:raise AssertionError(f'check {checks}')
    def raw(p):
        lines=read(p).decode('utf-8-sig').splitlines();check(lines[0].split()==['ID','EntryTime(s)','STD(s)','star','end','Unloader','Loader'])
        rows={}
        for line in lines[1:]:
            if not line.strip():continue
            f=line.split();check(len(f)==7)
            key=int(f[0]);check(key not in rows)
            rows[key]=(float(f[1]),float(f[2]),int(f[3]),int(f[4]),f[5],f[6])
        return rows
    prior=obj(BASE/'phase4_w3_round8_business_input_research_repaired_20261010/analysis.json')
    target=BASE/'phase4_w3_round8_stability_analysis_20261010/projection_domains'
    target_manifest=obj(target/'manifest.json')
    for name,digest in target_manifest.items():check(sha256(read(target/name)).hexdigest()==digest)
    reference=obj(target/'analysis.json');resource=obj(target/'resource.json')
    check(sha256(read(target.parent/'projection_domains.py')).hexdigest()==resource['source_sha256'])
    for name,digest in reference['input_sha256'].items():check(sha256(read(Path(name))).hexdigest()==digest)
    source=raw(ROOT/'legacy/jichang_origin_readonly/inputdata.txt')
    tasks=ROOT/'.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning'
    projected=raw(tasks/'nanning_1x_raw.txt');manifest=obj(tasks/'nanning_1x_manifest.json')
    canonical=read(tasks/'nanning_1x_canonical.jsonl').decode('utf-8-sig')
    profile=obj(ROOT/'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json')
    for p in(ROOT/'legacy/jichang_origin_readonly/inputdata.txt',tasks/'nanning_1x_raw.txt',tasks/'nanning_1x_canonical.jsonl',tasks/'nanning_1x_manifest.json',ROOT/'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'):
        check(bindings[str(p.resolve())]==prior['bound_inputs'][str(p.resolve())])
    check(set(source)==set(projected)and len(source)==manifest['raw_task_count']==28506)
    nodes={n['location']for n in profile['nodes']};reverse=defaultdict(set)
    for edge in profile['edges']:
        check(edge['capacity']>=0)
        if edge['capacity']>0:reverse[edge['end']].add(edge['start'])
    # Traverse reverse graph separately for each target. This directly answers
    # "which origins can reach this target?", without normalized forward rows.
    ancestors={}
    for node in nodes:
        seen={node};stack=[node]
        while stack:
            for predecessor in reverse[stack.pop()]:
                if predecessor not in seen:seen.add(predecessor);stack.append(predecessor)
        ancestors[node]=seen
    loaders=set(profile['business_roles']['source_candidate_ids']);sinks=set(profile['business_roles']['sink_candidate_ids'])
    can_return={sink for sink in sinks if any(sink in ancestors[loader]for loader in loaders)}
    legs=defaultdict(dict);seen_segments=set()
    for line in canonical.splitlines():
        if not line.strip():continue
        leg=json.loads(line);tid=leg['task_id'];row=projected[tid]
        check(leg['segment_id']not in seen_segments);seen_segments.add(leg['segment_id'])
        check(leg['leg']not in legs[tid]);legs[tid][leg['leg']]=leg
        check((leg['original_entry_time'],leg['std'],leg['original_start'],leg['original_goal'])==row[:4])
    groups=defaultdict(list);domains={};unreachable_old=0
    for tid,original in source.items():
        row=projected[tid];check(row[:2]==original[:2]);check(row[2]in loaders and row[3]in sinks)
        key=(original[1],original[3],original[4]);groups[key].append(tid)
        if sorted(legs[tid])==['direct']:
            check(row[1]-row[0]<4800)
            domains[tid]={goal for goal in can_return if row[2]in ancestors[goal]}
        else:
            check(sorted(legs[tid])==['storage_in','storage_out']and row[1]-row[0]>=4800)
            incoming,outgoing=legs[tid]['storage_in'],legs[tid]['storage_out']
            check(incoming['goal']==outgoing['start']==53 and incoming['start']==row[2]and outgoing['goal']==row[3])
            check(outgoing['pass_time']==row[1]-2700)
            waypoint=incoming['goal']
            domains[tid]={goal for goal in can_return if row[2]in ancestors[waypoint]and waypoint in ancestors[goal]}
        unreachable_old+=row[2]not in ancestors[row[3]]
    reference_rows={tuple(r['flight_surrogate']):r for r in reference['groups']}
    check(set(groups)==set(reference_rows)and len(groups)==360)
    rows=[]
    for key,members in sorted(groups.items()):
        domain=set(sinks)
        for tid in members:domain&=domains[tid]
        old_goals={projected[tid][3]for tid in members};check(len(old_goals)==1)
        old_goal=next(iter(old_goals));r=reference_rows[key]
        check(r['bag_count']==len(members)and r['old_destination']==old_goal and r['feasible_destination_domain']==sorted(domain))
        empty_individual=sum(not domains[tid]for tid in members)
        check(sum(x['bag_count']for x in r['individual_empty_domains'])==empty_individual)
        check(r['joint_empty_without_individual_empty']==(not domain and not empty_individual))
        rows.append({'flight_surrogate':list(key),'bag_count':len(members),'old_destination':old_goal,'feasible_destination_domain':sorted(domain)})
    totals={'business_bags':sum(r['bag_count']for r in rows),'atomic_flight_groups':len(rows),
        'nonempty_flight_domains':sum(bool(r['feasible_destination_domain'])for r in rows),
        'old_destination_outside_nonempty_domain_groups':sum(bool(r['feasible_destination_domain'])and r['old_destination']not in r['feasible_destination_domain']for r in rows),
        'old_outbound_unreachable':unreachable_old,'all_unloaders_with_any_loader_return':len(can_return)}
    for key,value in totals.items():check(reference['totals'][key]==value)
    check(all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in bindings.items()))
    result={'schema':'ics_round8_projection_domains_independent_v1','checks':checks,'failed_checks':0,'totals':totals,'rows':rows,
        'physical_calls':0,'assignment_changes':0,'discarded_bags':0,'bound_inputs':bindings,
        'source_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Independent original-timetable/projected-raw/canonical parsing, reverse reachability and 360 full domain equality checks, after imports before final output writes. Reference normalized artifact is SHA-bound but never used to build groups/lifecycles/domains. Static proxy permissions only; no scheduling/capacity/source-reassignment guarantee or physical work.'}
    (HERE/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    lines=['# 原始 raw/canonical 对完整航班组目的域的独立交叉核验','',
        f"{checks:,} checks / 0 errors；28,506 件袋、360 个完整原航班代理组，360 个域均非空，48 组旧目的地不在共同域，旧去程不可达 4,001 件。逐组全部候选目的集合与 root 库存相等。",'',
        '独立构造来自原 timetable 的 (STD,end,Unloader)、投射 raw 的固定源/旧目的、旧 canonical 的 direct/storage_in/storage_out；未用规范化 business rows 构造分组或生命周期。用正容量图的反向遍历重算每一目标的前驱集合，与 root 的正向 BFS/bitset 构造交叉核对。','',
        '只有现行正容量共网模式代理下的静态必要条件；真实 empty/owner/EBS 权限未获得，未分配新目的、未删除袋、未证明动态容量或供盘可持续。48 组是整体原子组赋值不合条件，不是要丢掉 48 个航班。','',
        f"本次独立 CPU {result['cpu_seconds']}s / wall {result['wall_seconds']:.6f}s，0 physical calls；imports 与末尾输出不在计时。"]
    (HERE/'CROSSCHECK.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (HERE/'manifest.json').write_text(json.dumps({'input_sha256':bindings,'output_sha256':{p.name:sha256(p.read_bytes()).hexdigest()for p in HERE.iterdir()if p.is_file()and p.name!='manifest.json'}},indent=2),encoding='utf8')
    print(json.dumps({'checks':checks,'totals':totals,'cpu_seconds':result['cpu_seconds'],'wall_seconds':result['wall_seconds']}))
