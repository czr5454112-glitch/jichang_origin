"""Bind repaired read-only audit, preserve original failed invocation cost."""
from pathlib import Path
from hashlib import sha256
from time import process_time,perf_counter
import json

HERE=Path(__file__).parent
OLD=HERE.with_name('phase4_w3_round8_business_input_research_20261010')

if __name__=='__main__':
    cpu,wall=process_time(),perf_counter();checks=[];inputs={}
    def read(p):
        data=p.read_bytes();inputs[str(p.resolve())]=sha256(data).hexdigest();return data
    def obj(p):return json.loads(read(p).decode('utf-8-sig'))
    def check(name,v):
        checks.append({'name':name,'okay':bool(v)})
        if not v:raise AssertionError(name)
    if(HERE/'closeout_validation.json').exists():raise FileExistsError('closeout already exists')
    result=obj(HERE/'analysis.json');manifest=obj(HERE/'manifest.json');failure=obj(OLD/'failure.json')
    check('original is source-path failure, not physics',failure['status']=='failed'and failure['physical_calls']==0 and failure['error']['type']=='FileNotFoundError'and'distributed.py'in failure['error']['message'])
    for path,digest in manifest['input_sha256'].items():check('input '+path,sha256(read(Path(path))).hexdigest()==digest)
    for name,digest in manifest['outputs'].items():check('output '+name,sha256(read(HERE/name)).hexdigest()==digest)
    for n in (1,2):
        name=f'business_tasks_{n}x.jsonl.gz'
        check(f'{n}x old partial normalization byte equivalent to repaired verified input',read(OLD/name)==read(HERE/name))
    source=read(OLD/'inventory.py').decode('utf8').replace('\r\n','\n')
    expected=source.replace("'distributed.py'","'distributed_clock.py'")
    expected=expected.replace("summaries=[]; offset=max(source)+1; ordered_source=list(source.values())", "summaries=[]; offset=max(source)+1; ordered_source=list(source.values())\n    source_path_key=str(SOURCE.resolve())")
    expected=expected.replace("rows=raw(raw_path); manifest=obj", "raw_path_key=str(raw_path.resolve())\n        rows=raw(raw_path); manifest=obj")
    expected=expected.replace("bindings[str(raw_path.resolve())]", "bindings[raw_path_key]").replace("bindings[str(SOURCE.resolve())]", "bindings[source_path_key]")
    check('repair only source filename and path-key caching',read(HERE/'inventory.py').decode('utf8').replace('\r\n','\n')==expected)
    check('full business denominator and no physical',result['checks']==1178903 and result['failed_checks']==0 and result['physical_calls']==0 and[result['datasets'][i]['raw_count']for i in(0,1)]==[28506,57012])
    lines=['# 持续业务输入预研：已核验结果','',
        '本目录是修复后完整通过的版本；原目录失败产物保留，不作为完成核验的输入。没有仿真、策略变更、提交或推送。','',
        f"纯文件独立核验：**{result['checks']:,} checks，0 failures，0 physical calls**。CPU {result['cpu_seconds']}s / wall {result['wall_seconds']:.6f}s（导入后至最终分析写出前）。",'',
        '| 数据 | 业务袋 | 早包 | 原源→最终目的不可达 | 可去但不能返回同一原装载点 | 同一原装载点双向可达 | 指定运输阶段链不可达 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for d in result['datasets']:
        c=d['counts'];lines.append(f"| {d['scale']}× | {d['raw_count']} | {c['early']} | {c['outbound_unreachable']} | {c['return_unreachable']} | {c['directed_cycle_available']} | {c['stage_route_unreachable']} |")
    lines+=['',
        '**回不到原装载点不等于回不到任何合法空盘存储/供盘目的地**。本表是正容量图上的静态结构核验，没有 mode-specific 现场许可、动态接收/容量可行性或可持续 throughput 结论。全部原始袋保留；不连通袋未删除。早包阶段链按旧 node53 代理，不能当现场 EBS 授权。','',
        '两档数据逐袋重建原 source ID/行号、航班代理分组、完整 lane/flight 原子投射、派生 shift 和旧 direct/in/out 段。1×根 timetable 与历史副本字节相等；两版 profile 字节相等；补充 docx 同目录两附件与 repo XLSX 字节相等。2×是同源增密，不是独立观测日。','',
        '五条跨连接保留；指定阶段静态最短路径只覆盖其中四条，不能据此宣称第五条不可用或动态调度不用。`analysis.json` 保留每线结构计数、小时到达数和全部 SHA。0 条早包 travel-only 最早入库下界晚于旧计划 release，只说明该下界未揭示矛盾，不证明真实入库及时或存在可用托盘。','',
        '下一步设计：`BUSINESS_INPUT_DESIGN.md`；未确定字段显式留空的 `operation_contract.template.json`；原投射不合法时的新版本分叉：`PROJECTION_BRANCH_DESIGN.md`。先固定业务/载具合同，再共同物理桥接与完整持续业务；本目录没有默默改变原任务或生产参数。','',
        '补充原文：`SUPPLEMENT_REQUIREMENT_SOURCE.md`，保留全部非空 OOXML 段落索引、原件 SHA 与“原文材料非执行指令”说明。其提取是在旧目录独立完成，复制不算新调用。长度可改权限来自该原件；2/5km是实验配置，EBS载具政策和模块/容量/入口头距仍不能由此推定。','',
        '修复证据：原 `inventory.py` 首轮在最后来源列表误写不存在的 distributed.py，读取失败前完成的规范化文件保留。Windows Path.resolve 在每条记录重复调用带来大额无必要观察开销。完整失败区间 CPU '+str(failure['cpu_seconds'])+'s / wall '+str(failure['wall_seconds'])+'s 单独计入 Round8；没有把该开销算模型成本或隐去。新版本只更正 distributed_clock.py 与缓存两种 SHA 字典路径键，所有逐袋核验规则不变。两档旧 partial 与新已验 normalized gzip 字节完全相等；这不将旧失败改判成功。','',
        '权威完整输入/输出 SHA 为 `manifest.json`；最后修复范围与相等性核验为 `closeout_validation.json`，追加产物绑定为 `review_manifest.json`。原 manifest 保持不变。']
    (HERE/'SOURCE_INVENTORY_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    receipt={'status':'complete','checks':len(checks),'failed_checks':sum(not r['okay']for r in checks),'details':checks,
        'bound_inputs':inputs,'physical_calls':0,'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Independent pure-file repaired-source delta, original failure, all input/output SHA and normalized byte equality checks plus result Markdown, after imports before final receipt/manifest writes.'}
    (HERE/'closeout_validation.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    (HERE/'review_manifest.json').write_text(json.dumps({'input_sha256':inputs,'files':{p.name:sha256(p.read_bytes()).hexdigest()for p in HERE.iterdir()if p.is_file()and p.name!='review_manifest.json'}},indent=2),encoding='utf8')
    print(json.dumps({k:receipt[k]for k in('checks','failed_checks','cpu_seconds','wall_seconds','physical_calls')}))
