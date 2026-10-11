"""Pure positive-directed-graph inventory to ANY of the 11 loader roles."""
from pathlib import Path
from collections import defaultdict,deque
from hashlib import sha256
from time import process_time,perf_counter
import json

HERE=Path(__file__).parent
ROOT=next(p for p in HERE.parents if(p/'scripts/experiments/ics_circulation_v3').is_dir())

if __name__=='__main__':
    cpu,wall=process_time(),perf_counter();bound={};checks=[]
    if(HERE/'return_reachability.json').exists():raise FileExistsError('new invocation required')
    def read(p):
        b=p.read_bytes();bound[str(p.resolve())]=sha256(b).hexdigest();return json.loads(b.decode('utf-8-sig'))
    def check(name,value):
        checks.append({'name':name,'okay':bool(value)})
        if not value:raise AssertionError(name)
    previous=read(HERE/'analysis.json');read(HERE/'review_manifest.json')
    path=ROOT/'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'
    profile=read(path)
    check('profile is exactly previously audited input',bound[str(path.resolve())]==previous['bound_inputs'][str(path.resolve())])
    roles=profile['business_roles'];loaders=set(roles['source_candidate_ids']);sinks=roles['sink_candidate_ids']
    check('complete role denominator',len(loaders)==11 and len(sinks)==42)
    edges=defaultdict(list)
    for edge in profile['edges']:
        if edge['capacity']>0:edges[edge['start']].append(edge['end'])
    all_return={}
    for goal in sorted(sinks):
        queue=deque([goal]);visited={goal}
        while queue:
            for target in edges[queue.popleft()]:
                if target not in visited:visited.add(target);queue.append(target)
        all_return[goal]=sorted(visited&loaders)
    datasets=[]
    for n in(1,2):
        path=ROOT/f'.g4irsf24_worktree/artifacts/tasks/g4irsf31_nanning/nanning_{n}x_manifest.json'
        m=read(path)
        check(f'{n}x manifest is exactly previously audited source',bound[str(path.resolve())]==previous['bound_inputs'][str(path.resolve())])
        check(f'{n}x all bags retained in destination weights',sum(m['raw_by_goal'].values())==m['raw_task_count'])
        check(f'{n}x destination roles complete',set(map(int,m['raw_by_goal']))==set(sinks))
        rows=[{'unloader':goal,'reachable_loaders':all_return[goal],'reachable_loader_count':len(all_return[goal]),
            'original_bag_weight':m['raw_by_goal'][str(goal)]}for goal in sorted(sinks)]
        datasets.append({'scale':n,'original_bags':m['raw_task_count'],'zero_return_loader_set_bag_weight':sum(r['original_bag_weight']for r in rows if not r['reachable_loaders']),
            'nonzero_return_loader_set_bag_weight':sum(r['original_bag_weight']for r in rows if r['reachable_loaders']),
            'rows':rows})
    read(HERE/'analysis.json')
    check('all inputs unchanged',all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in bound.items()))
    result={'schema':'ics_round8_any_loader_return_inventory_v1','physical_calls':0,'routing_generator_calls':0,
        'all_loaders':sorted(loaders),'all_unloaders':sorted(sinks),'unloader_with_no_reachable_loader':[g for g in sorted(sinks)if not all_return[g]],
        'datasets':datasets,'source_scope':'Positive-capacity directed topology and current proxy shared loaded/empty mode assumption only. Actual empty-mode permissions and receiving/export authorization are absent. Reaching any loader is a static necessary possibility, not a dynamic/global sustainable-service guarantee.',
        'distinct_diagnostic':'Returning to the bag original source is stricter than reaching any allowed loader; prior return_unreachable count is NOT a count of no legal return destination.',
        'checks':checks,'failed_checks':sum(not c['okay']for c in checks),'bound_inputs':bound,
        'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Independent static BFS and all-bag destination-weight inventory after imports through input rehash; final JSON/Markdown/manifest writes excluded. No physical or route-generator calls.'}
    (HERE/'return_reachability.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    lines=['# 回到任一装载点：完整静态回流集合','',result['source_scope'],'',
        '**全部 42 个卸载节点逐个计算到 11 个装载点的可达集合，按全部原业务袋加权；没有按去程是否成功过滤分母。**',
        '', '| 数据 | 全业务袋 | 回流集合为空的袋权重 | 至少一个可回流装载点的袋权重 |','|---|---:|---:|---:|']
    for d in datasets:lines.append(f"| {d['scale']}× | {d['original_bags']} | {d['zero_return_loader_set_bag_weight']} | {d['nonzero_return_loader_set_bag_weight']} |")
    lines+=['','上述静态到达仍须遵守真实 empty 权限、接收回压、old transit/承诺与有限盘守恒。相同 source 的双向要求不是持续业务的必要条件；有一个可达 loader 也不证明对所有需求源的可持续供给。原去程不可达袋仍是另一项完整分母缺口，不能因回流集合非空而当其已可服务。','',
        '| 卸载节点 | 可达装载节点集合 | 1×袋权重 | 2×袋权重 |','|---|---|---:|---:|']
    for a,b in zip(datasets[0]['rows'],datasets[1]['rows']):lines.append(f"| {a['unloader']} | {', '.join(map(str,a['reachable_loaders'])) or 'empty'} | {a['original_bag_weight']} | {b['original_bag_weight']} |")
    (HERE/'ANY_LOADER_RETURN.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    (HERE/'return_reachability_manifest.json').write_text(json.dumps({'bound_inputs':bound,'outputs':{p.name:sha256(p.read_bytes()).hexdigest()for p in(HERE/'return_reachability.py',HERE/'return_reachability.json',HERE/'ANY_LOADER_RETURN.md')}},indent=2),encoding='utf8')
    print(json.dumps({'zero_return_unloaders':result['unloader_with_no_reachable_loader'],'zero_return_bag_weights':[d['zero_return_loader_set_bag_weight']for d in datasets],'cpu_seconds':result['cpu_seconds'],'wall_seconds':result['wall_seconds'],'failed_checks':result['failed_checks']}))
