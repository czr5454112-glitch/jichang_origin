"""Record closed evidence without upgrading still-running experiments."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC = ROOT / 'docs/g31_ics_circulation'
HERE = Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())

backup = HERE / 'before_milestone_016'
report = HERE / 'milestone_016.json'
assert not backup.exists() and not report.exists()
pins = {
 'route_native027_saved_audit_001/audit/report.json': 'fbb2cff19d93a02416aa54067d98ec714c901cd600fa447242f3ee3b2481cae7',
 'route_native027_saved_audit_001/report_review_001.json': '445c5e683b713e47a15bac3b4f574d70c7b6982e2f5a176128c2fde849a9290e',
 'preference_request_context_summary_001.json': '9b6d612e3288ebd61fec5326557fc0471df619e9c9154bb4413fc093f71514dc',
 'public_interaction_discovery_001_saved_audit.json': '52fd212a0b30063e33bc2034a1bf4ab6ecfbccbbd3ab7158488d947ea998c12b',
 'public_projection_prefix_feasibility_001.json': '2c499cf2d4bdb492a5f03f5fdfd3366fce84ada584c729f872c6120eb8ac9956',
 'user_resume_20261015_001/terminated_chain_002_process_observation.json': 'f14041c5ed92001378fd1f03b28875a4bfd12970dc26e76c471d529ed9d735db',
 'user_resume_20261015_001/chained_audit_launcher_002_independent_source_review.json': '14b3090e131df5ba8787abea974396b8491e2fc73223d7266fe4cff644b1c852',
}
for n, h in pins.items(): assert sha(OUT / n) == h, n
producer = read(OUT / 'full024_chained_2x_20261015_002/receipt.json')
assert producer['status'] == 'hard_timeout' and producer['source_changed'] == []
for n in ('full024_chained_2x_20261015_002/receipt.json',
          'full024_chained_2x_20261015_002/run_shards.json',
          'original_low_wip_quiescent_prepare_001/cap3/independent_verification.json'):
    pins[n] = sha(OUT / n)
backup.mkdir()
files = ['RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md']
for n in files: (backup / n).write_bytes((DOC / n).read_bytes())
for n in ('branch_ledger.json', 'cap8/heartbeat.json'):
    source = OUT / 'original_low_wip_quiescent_prepare_001' / n
    target = backup / ('quiescent_' + n.replace('/', '_'))
    target.write_bytes(source.read_bytes())
    pins[str(target.relative_to(OUT))] = sha(target)
s = read(DOC / 'RESEARCH_STATE.json')
a = s['active_experiment']
a['full2x_latest_status'] = 'Actual H86400 all57012/526shards/256756owners/final producer seal a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826 and complete manifest retained. Producer hard_timeout7200.6285888 source_changed[]; exact19316/21344 absence confirmed. Pure saved audit98526 now running with3600s owned child bound and external whole Python wall; no native rerun, no success claim yet. Initial ancestor drift-finalization remains unknown.'
a['route_phase_status'] = 'Separate saved audit passed all6cells/actual026reference and3plain-timed orderedAPI+H9900seal parity,4closed2open; external399.9602518s under1800s ownedJob. Original600.1512597s timeout preserved. Plain normal89.0496ms/drop1599.3227ms/openprefix32676.3501ms; timed103.1931/1586.0818/38375.0117ms. Exclusive charges retain native whole+Python remainder+unclassified, no physics subtraction; complete computation unavailable and100ms not certified.'
a['request_context_status'] = 'New per-request immutable guarded context:41pure/24paired32candidate batches full orderedoutputs exact; reference median391.913ms vscontext247.6586ms,total36.7985% reduction. All24context batches182.2296-269.0302ms still>100 before actual protocol. Full external28.5237203s,0native. Static guard caching and separately verified prefix sharing remain new source work; no online authority or timing certificate.'
a['interaction_discovery_status'] = 'Independent preregistered public discovery256/256 projected,64cubes,0barriers,0projected chain candidates; all4searchmethods identical8cases and optima reachable by strict coordinate moves. All16 initial-only regressions damage an already-completed job which later R1 cannot repair. Validation256 remains unknown_unexecuted; no adaptive grid expansion/native run.'
a['repeating_low_wip_status'] += ' Latest quiescent001 cap3 actual worker1157s+saved verification432.078s bothexit0;cap8 stillinprogress at frozen snapshot. Shared2400s unchanged; pair not yet accepted.'
s['next_actions'] = [
 'Finish already-running saved full2x audit98526 within its3600s child budget; preserve producer timeout, ancestor unknowns, full source/cost lineage and all57012 denominator.',
 'Finish quiescent001 shared2400s without extension; cap3 passed actual+saved, cap8/pair still unknown. Preserve incomplete arm before deciding any new separately bounded experiment.',
 'PendingACK-only actual3fault600s package under independent review; preserve actual query chronology, exact permitted observation deletions, all background API/commonH seals and full request root costs.',
 'Implement separately source-pinned static guard reuse and public projection prefix sharing; full32/4 candidate outputs, guards, dynamic alias isolation, cold/warm accounting and paired pure validation before native.',
 'Keep negative interaction discovery, original6cases and strong baselines; validation256 remains unexecuted. Joint independent benefit remains unproved.',
 'Keep every failure/unknown and source pin; relevant coherent zero-skip regression remains required. No commit,push or GPTPro send without instruction.',
]
a['pending'] = s['next_actions']
(DOC / 'RESEARCH_STATE.json').write_text(json.dumps(s, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')
note = '''

## milestone016：全天记录进入独立核验；性能改进和联合机制负结论分别保留

2倍原流已到H86400，57012件全部进入统计口径，526分片与最终实际producer封印完整保存；原生产进程在保存核验阶段达到7200.629秒硬限，source_changed为空。精确父子进程退出已确认。单独3600秒owned Job保存审计已启动，外层完整Python启动至退出另计；不重跑native、不把producer超时改成成功，早期祖先缺少最终漂移记录仍未知。

六格计时的独立保存核验完成，全部真实API顺序、026参考和三组plain/timed共同H9900封印一致，外层399.960秒；原600秒整组超时仍保留。未插桩正常请求89.050ms，丢首次ACK约1599.323ms，缺ACK前缀约32676.350ms且未闭合。计时分区保留全部原生成本、Python余项和未分类项，未扣所谓物理耗时，完整计算口径仍未全部识别，100ms不通过。

新请求上下文的24组成对32候选纯测试输出逐字一致，总计算约减少36.8%，中位391.913降至247.659ms；全部新批次仍超过100ms，且尚未包含实际协议成本。前缀共享只读可行性核查显示可省约22%总事件、37%非tick事件，但朴素整图复制可能抵消收益；后续只共享证明只读的静态内容，动态对象与日志仍隔离，暂不混入静默尾段批处理。

独立预登记交互发现256项全部完成，64个交互立方没有严格保护障碍或目标因果链候选，普通坐标步骤可达所有最优值。16个初始单独动作回归发生在已经完成的件，后续改路无法修复；这是模型结构负证据。另256项验证仍未执行，未扩大网格寻找有利结果。低投放quiescent cap3实际与保存核验均通过，cap8仍在原共享2400秒内进行，整组未放行。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f: f.write(note)
with (DOC/'NEXT_ACTION.md').open('a',encoding='utf8') as f:
    f.write('\n\n## 最新执行次序（milestone016）\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(s['next_actions']))+'\n')
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:
    f.write('\n\n## 46. 独立交互发现负结果与性能改进分开\n\n新256发现项没有目标交互障碍，四方法均可由普通坐标解释；256验证项未执行。请求上下文约36.8%的纯计算改进属于实现优化，不能作为联合方法必要性证据，也未达到100ms完整请求标准。\n')
with report.open('x',encoding='utf8') as f:
    json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
      'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in files},
      'after_sha256':{n:sha(DOC/n) for n in files},'active_native_sessions':[43312],
      'active_pure_audit_sessions':[98526],'overall_goal_achieved':False},f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
