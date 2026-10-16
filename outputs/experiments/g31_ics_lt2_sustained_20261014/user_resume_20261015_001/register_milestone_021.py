"""Close fixed JSON RPC audit and register strict native/bridge next steps."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DOC = ROOT / 'docs/g31_ics_circulation'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
pins = {
 'json_prediction_RPC_independent_actual_review_001.json':'e8fae8dd5772fab81a3906733c2532fc6607a46de533b242d64d9289f01d8c5e',
 'json_prediction_RPC_prepare_002/external_application_wall.json':'83124d5bdb8ad337d78f4eb6d4070b4891e6b51f0ee54d0372a485ce8511504c',
 'preference_receiver_vector_pair_001_independent_review.json':'14073a0b122e565af05acc304ff446aaa39309ae1172d1613d6680ff16884555',
 'original_recirculation_screen_001_independent_review.json':'82194f2094d765636cc93af95192a4ff3c99e4230018f93c01d8441864759ef2',
 'current_possession_permit_independent_source_review_001.json':'3e8a16a608a52788f1f2f1b5e82937a1bbcdf09140958abcff24306aa0689d6a',
 'possession_gate_pure_001/receipt.json':'5e3440842ccd249aa450b3dc459172bdea60111beedbd012d6afa7ae2bd05f43',
 'live_obligation_native_version_binding_001.json':'10357700ccd61e6c265a013014966ca89720c3e5806ea36f6d15ea72eed25df6',
 'live_obligation_native_probe_prepare_001/preregistered_protocol.json':'d747b33656d712f1942456374ddcf68f3edab4fc09d5cec1e4f3fe51c734ec89',
}
for name, digest in pins.items(): assert sha(OUT/name)==digest, name
rpc=read(OUT/'json_prediction_RPC_prepare_002/report.json')
assert rpc['status']=='saved_24_RPC_ordered_exact' and rpc['source_changed']==[]
assert (rpc['requests'],rpc['full_baselines'],rpc['candidate_queries'])==(24,24,768)
assert rpc['native_calls']==0 and rpc['complete_100ms_certified'] is False
assert all(r['complete_caller_ns']>100_000_000 for r in rpc['request_costs'])
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup, receipt=HERE/'before_milestone_021',HERE/'milestone_021.json'
assert not backup.exists() and not receipt.exists()
backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. JSON fixed-source RPC completed and independently verified: all24 exact, median warm207.71145ms, no100ms success; cold and close retained. New three-branch actual027 feasibility probe prepared, not dispatched at this milestone. Current-possession gate24pure reviewed; original single-token bridge policy separate source work. Full-day performance, complete100ms and joint method effectiveness remain unmet.'
active['json_prediction_worker_status']='Closed fixed002 ABBA:85sources,4owned isolated workers,24fresh contexts/fullbaselines,768queries,396full+372partial exact. A total2848.7007->B2423.8229ms; median241.81015->207.71145ms. B139.5668-248.8636ms,0/12<=100; nestedcompute116.5222-160.4127ms already exceeds100. ColdB launch-through-first-return1007.3225/1008.446ms; close222.8972/224.8415ms unamortized. External31.270883s. Puregate80passed; earlier failures and unexecutedprepare001 retained. Independent audit runs0newpredictor/0native. No complete-business100ms claim.'
active['receiver_vector_status']='Independently closed45source/24request/768query/fullbaseline exact comparison; total-2.287%, median worsens177.77965->179.15925ms, all12B115.503-247.1064ms>100. Stop mixed receiver micro-optimization line; no new profile/case gating.'
active['joint_protection_design_status']='Fixed96 conditional model and complete reference families remain unchanged. CORRECTION to020:8.89 is modeled periodic-retry ACK, not proof actual8.69 decision is impossible; source loading preflight may retry earlier (source-derived8.60). No actual timing established yet. Fixed native12/24/25 probe prepared,31pure/73Pythonpins/shared120s, all5jobs/Storage/ACK/actualedge/savedendpoint audits required. Actualruntime is accepted027(845486b7...), because026 lacks v3 endpoint/observedEDGE_ENTER extension;026 immutable protocol file matches but does not certify027 behavior. Three branches cannot establish full96 references or algorithm novelty.'
active['original_recirculation_screen']='Independent screen checked original28506/all22/zero-capacityedge/21parked. Offline path relaxation adds31 using12bridges, not time/capacity/native feasibility. Clarification: all39safeprefix jobs had already arrived by actualtoken26367.778; global offline selection still lacks online delivered authority. Oldcap8 terminal is immutable. Current-possession gate24pure reviewed under cooperative2owners/oneunresolved/onlytoken scope: actualownempty+selfcopy+freshpeercompleteACK+strictactionIDwatermark. It is NOT authenticated empty-arrival payload causality. New bridge policy source work fixed39completion/78postparkingempty/100physicalbudget, no native yet; bridges require unconsumed actual same-token UNLOAD and anewcurrent capture eacharrival.'
state['next_actions']=[
 'Finish independent source review of fixed native02712/24/25 probe, then one owned120s run with actual44+21 entry/exit and complete saved audit. Preserve unknowns/ACK timing deviations; no new parameters, retiming or extra branches.',
 'Close JSON RPC as partial speed progress with warm/cold/full costs. Source-only evaluate deadline-owned native finalization or fixed pure parallelism; do not add blind codec/profile/microbenchmarks, hide cold cost, or claim unexecuted candidates complete.',
 'Complete separate original bridge policy pure gate and source review with unchanged full28506/H86400/FIFO/Storage/capacity0/R1false. Preserve consumed-action and receipt watermarks, one live token, finite cap handshake; new native experiment needs fresh frozen plan.',
 'Original completed8/28506 and3ontime remains actual limited result. 39zero-bad and371conditional upper bounds are not achieved schedules; strict all-job protection and R1/R2/joint effectiveness remain open.',
 'Preserve all failures, evidence and review material; user has not authorized commit, push, external messaging or GPTPro transmission.'
]
active['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone021\n\n用户“全面恢复”有效，整体标准不降低。当前登记时所有native已关闭，新三分支探针仅准备。\n\nJSON固定对照及独立审计完成：24请求/24完整基线/768候选精确一致，中位241.81→207.71ms；12次B全部>100，首请求冷成本约1秒，关闭约223–225ms，整Python31.27秒。\n\n纠正上一登记：模型8.89 ACK不等于实际拒绝证明，原生loading预检可能更早重试；将以独立验收的027和固定三分支验证。原图仍是8件完成、3件按时，桥接策略尚未实跑。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n',encoding='utf8')
note='''

## milestone021：JSON请求优化闭合，修正ACK推断，准备真实可行性检查

JSON002固定A/B/B/A首次实际执行exit0，整Python31.270883秒。85源码、四个拥有独立Job的worker、24新请求上下文/完整基线、768查询独立复核，396完整和372严格前缀拒绝标签逐项精确。总caller2848.7007→2423.8229ms，中位241.81015→207.71145ms；B139.5668–248.8636ms，0/12达100。B纯动态compute已116.5222–160.4127ms，所以仅压缩通信无法过100。冷启动至首返回约1007–1008ms，关闭223–225ms保留不摊薄，未声称完整业务请求过线。80纯测通过；深路径/src遗漏、2MiB帧误用总artifact、blocked-write watchdog、计时尾部和READY完整loaded-map等修复及原失败均保留。

纠正020的ACK结论：8.89只是纯模型周期重试的received时间；原生控制器还有loading阶段预检，静态源码推算可能8.60获得ACK，尚无实际测量。固定12/24/25、共享120秒的探针已准备，31纯测、73Python绑定，实际必须通过五件全完成、强制Storage、目标边/ACK、完整源状态与保存端点重放。该探针使用独立验收027（binary845486b7…a7e7be），026缺v3端点和实际EDGE_ENTER扩展；两版仅immutable protocol实现相同，不能把026历史证据写成027运行事实。三条不能证明96条强参考或求解器创新。

原图离线路径筛查和current-possession gate已分别独立源审。24项纯门通过，约束实际当前本地空盘、自送达副本、新peer完整已收动作及严格增长的精确action-ID watermark；非空盘到达的payload/因果认证，也未集成native。新单token桥接策略单独开发，固定39完成/78停车后空转/100物理操作预算，39仅条件必要上界用作停止预算。桥接必须消费未用过的实际同盘UNLOAD，桥点到盘再次捕获判断，不允许桥→桥循环。补充筛查口径：39个安全前缀任务在26367.778前都已释放，问题是offline全局选择未经送达授权，不能笼统称这些任务尚未到达。全天原流、100ms与联合有效性仍未达标。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 51. 固定代码进程复用降低请求时间，但不是完整100ms或算法新颖性\n\nJSON对照24精确、中位207.71ms仍超线；不能摊薄冷启动。联合机制的8.69/8.89疑点是模型与实际触发差异，等待固定027实测，不能提前否决或认证。新原图桥接是受限单盘策略探索，当前只有路径松弛与权限纯门，无新增吞吐证书。\n')
with receipt.open('x',encoding='utf8') as f:json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'new_native_dispatched_here':0},f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
