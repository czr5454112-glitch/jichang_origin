"""Record actual native feedback closure and retained failed attempts."""
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]; OUT=HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
pins={
 'live_obligation_native_failed_readback_001.json':'f1293ec057f1bd543081bcafd2a76353a0fbe468caf724d6491ef950ade60fdd',
 'live_obligation_native_saved_review_003.json':'a9c157e23459f95f53dad15ea5690d6c81aaabb0516cebb76af0c7f36b04579c',
 'live_obligation_native_probe_prepare_004/preregistered_protocol.json':'7f5b1937a44efb2c7fe9b376765a1b9ddb44a9ad93575cadf48f6e0dc06acabc',
 'live_obligation_native_probe_prepare_004/receipt.json':'75021a527186f35879a94e45bcfdabc8dd5c882524c181c1ed48a4086244b0ab',
 'live_obligation_native_probe_prepare_004/branch_ledger.json':'1e584b5a526b460acdd1e8dee18c6b55a98c7b8116858479d20ff7fae33d4834',
 'live_obligation_native_probe_prepare_004/external_application_wall.json':'414e43bc136d24d225b82b6c62e2f0efbf8fb05a79b22d0e9688dc7d59a7f781',
 'live_obligation_native_probe_prepare_004/independent_source_review_001.json':'66819359281206f3d91bbe92c9df80faff01f810af8ba220b88b680bda190a82',
 'live_obligation_native_saved_review_004.json':'d4c8614b945d50fb7eea66838a80e028c0565810977568caf37d8ac85e23b35c',
 'cooperative_bridge_policy_prepare_002/preregistered_protocol.json':'eb3975a6cb7528bfadd147d9f0079af32160e40627e885e9b4d001bb4c39fe81',
 'json_prediction_shards_RPC_prepare_001/external_application_wall.json':'cfe090e3409c0f43481772a88e84f363a21f5aeffd0d1c39934e4bcb09d5bf32',
}
for name,digest in pins.items():assert sha(OUT/name)==digest,name
report=read(OUT/'live_obligation_native_probe_prepare_004/receipt.json')
review=read(OUT/'live_obligation_native_saved_review_004.json')
assert report['status']=='complete3_assessed' and report['source_changed']==[]
assert report['run_acceptance_status']=='closed_run_acceptance_passed'
assert review['assessed']==3 and review['unknown']==0 and review['all_per_job_times_exactly_match_corresponding_saved_pure003']
assert report['comparisons']['mechanism/vector_25']['strict_protected'] is True
assert report['comparisons']['mechanism/vector_24']['strict_protected'] is False
assert read(OUT/'live_obligation_native_probe_prepare_003/receipt.json')['status']!='complete3_assessed'
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_022';receipt=HERE/'milestone_022.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. Fixed three native027 branches now assessed with zero fallbacks, exact15 per-job agreement to saved pure model, actual ACK/return/later-route feedback. Vector25 is strictly nonworsening versus12; vector24 harms blocker. Full96 strong references not yet executed. Original bridge91pure source package frozen, full28506/H86400 runner in preparation. Two-shard attempt001 failed before any prediction due Path subscription; failed evidence retained and narrow wiring fix in preparation. Full-day effectiveness, complete100ms and general joint-method effectiveness remain unmet.'
active['joint_protection_design_status']='Native004 independently closed3/3assessed,0fallback,73Python/557closure pins and44+21 entry/exit accepted027. All15 completion times exactly match frozen pure003. Vector12 sum60.061;24 sum55.961 harms blocker+.8;25 sum57.761 protects all5 with deltas loaded-1,receiver-1.1,reuse1-.1,reuse2-.1,blocker0. Actual returnACK8.60<unionfloor8.66,route8.69,execution8.70,ACK8.72,EDGE7->8 at8.75. This establishes a small fixed-action actual feedback mechanism, not online optimization, full96 reference advantage, originality, original-map applicability or100ms. Full96 preparation must explicitly correct absolute return-not-before7.84 versus inherited now+.5 mismatch;004 allreturn0 unaffected.'
active['native_probe_failure_history']='001 allunknown owner_notifications_not_enabled; missing raw prefix cannot be reconstructed.002 notification overlay andpartialcapture prepared unexecuted after private-capability deepcopy risk.003 JSON-only exception capture executed; all15 physicaltimes exact but3unknown because first-return E loading available_at misread as past epoch.004 typed correction matches actual native observed LOAD_START+load_seconds, preserves readykind/knownbit/current identity/derivedstart/ACKunion/occupancy;67pure then3actualassessed.003 statuses remainunknown, not retroactively promoted. Inputs/actions/physical clocks and accepted027 binary unchanged except declared001->003 notification overlay.'
active['json_prediction_sharding_status']='Fixed2 disjoint0..15/16..31 plan with duplicated freshfullguards/baselines and exact ordered merge; new common pipeline adds isolation/codec/ledger to bothA/B, so onlywithin-new A/B timing comparable.001 external18.7216475s exited1 before worker construction: output[directory] on WindowsPath.0 logicalRPC/0fullbaseline/0candidate, all4roundunknown_unexecuted. Preservefailure/ledger/external; one-expression path fix and actualcampaign-to-first-constructor test required, then freshimmutable002. No parallel performance evidence yet.'
active['original_bridge_status']='Source package002 frozen73Python+67compiled026,91purepass, no native. Root caught compact view.jobs contains only carried jobs, not waiting heads; corrected current source-owned control_projection FIFOhead identities joined to actually delivered own selfcopy fullcontracts. Actual20840 fixture used; missing/stale/mismatched head failsclosed.001 prepare tuple/list JSON boundary mismatch retained; canonical orderedJSON equality narrowfix. Fresh singlecase full28506/H86400 runner under preparation, shared2400s budget declared,39completion/78postparkingempty/100physical/8722publicationsperowner.39 is only necessary conditional bound. Global failure halt is experimentmanagement, not distributed coordination. Oldcap8 unchanged; actualoriginal remains8complete3ontime.'
state['next_actions']=[
 'Complete new full96 native runner and source/pure review using unchanged3cases/32actions/strong16references. Bind absolute not-before7.84 action semantics explicitly, preserve unknowns, and dispatch only from a fresh fixed plan; keep native0043branch evidence unchanged.',
 'Finish narrow shard001 launch-path fix and functional wiring gate, freeze002 and execute one fixedABBA. Count every failure, fullbaseline, query, duplicated work, codec/merge, cold/close and caller tail; compare onlywithinnewpipeline.',
 'Prepare, review and execute fresh original bridge trial with full28506/H86400, accepted026 archived authority, fullAPI tape and independentpolicy/physicalaudit, shared2400s ownedJob. No resume of oldterminalcap8 and no graph/FIFO/Storage/capacity/R1 changes.',
 'Allthree top-level targets remain unmet: fulloriginal workload effectiveness, complete100ms and strong-method joint validity. Native smallcase improvement is not algorithm novelty; known pairrepair already explains frozen pure mechanism.',
 'Preserve problem/solution chronology and allfailed/unexecuted artifacts for future user-commanded review. No commit, push, external message orGPTPro transmission authorized.'
]
active['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone022\n\n“全面恢复”继续有效。三条固定原生反馈分支已全部通过；完整96、全天原流新策略和完整100ms仍待验证。\n\n联合分支五件逐件非劣，总完成时间60.061→57.761；单独前段优化使blocker晚0.8。真实ACK8.60、route8.69、EDGE8.75已闭合。原图仍以8件完成/3件按时为已执行结果。双进程001在创建worker前失败，性能尚未测得。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n',encoding='utf8')
note='''

## milestone022：实际原生反馈链通过，严格保留失败史和未覆盖范围

固定native027探针004实际3/3 assessed，0fallback；整Python28.684526秒，worker27.447272秒。独立保存审计核73源码与557闭包/证据pin、44+21入出门、所有初始与later端点、全五件物理过程，15逐件完成时刻与纯003精确相同。12基线总60.061；24前段优化总55.961但blocker+0.8，严格保护失败；25联合总57.761，逐件delta为-1、-1.1、-0.1、-0.1、0，严格保护通过。总数求和的7e-15表示顺序差异不用于逐件保护；无epsilon。实际loading预检8.55→已收ACK8.60<unionfloor8.66→route提交8.69→执行8.70/ACK8.72→EDGE7到8在8.75，解决了纯模型8.89周期重试与实际8.60触发的混淆。仍只有三条固定分支，完整96强参考、在线选择、原图适用性与求解器新颖性未成立。

001因未启owner_notifications三条unknown，旧runner无raw prefix，不能事后重建。002启显式observer overlay，物理输入不改，但deepcopy可能复制NativeCollectedV3私有不可序列化能力，准备后未执行。003改为JSON数据捕获并完成三条物理过程；首次return仍因guard将E loading未来装载完成界误读为过去available事件而fallback，全部unknown保留。004只按accepted027实际LOAD_START语义校正stationary E loading available==load_complete==service_ready>now，同时保留knownkind/owner/identity/derivedstart<=floor/currentstate/ACKunion/occupancy；67纯测试含实际003三份哈希绑定形状和13负例，随后真实004全部通过。旧003不追认。

扩展96前另发现旧父return_tray把delay=.5解释为now+.5，而冻结纯域定义绝对not-before7.84。004均delay0不受影响；新runner必须显式绑定原动作语义，不能只把三条循环扩成96，更不能据事后结果调时钟。

双进程固定分片001共18.7216475秒后exit1：campaign将WindowsPath误用下标，发生于第一预测worker构造之前，0逻辑请求/基线/候选，四round均unknown_unexecuted。失败trace、ledger和外部计时保留；窄修路径连接并补真实campaign接线测试，再冻结002。不能把启动代码失败当作并行性能失败或过滤掉。两组新增caller复制/codec/ledger相同，只能本次A/B内比较，不能和旧207.71ms直接对比。

原图bridge源码门发现compact view.jobs只含当前承载作业，不能当完整waiting队列。改为当前source-owned control_projection FIFO首件身份与已真实送达自身副本全合同连接；实际20840输入回归及篡改负例纳入91通过。准备001 tuple/list持久JSON边界失败原样保留，002源包已冻结73Python+67compiled026。完整28506/H86400新trial、全API保存和独立审计正在准备，预声明单native/shared2400秒，不延续旧cap8终态，不改变R1false/FIFO/Storage/零容量边。全局故障halt只属实验管理，不能冒充消息协调；39只是条件必要上界。全天原流、完整100ms和强方法联合效果总体仍未达标。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 52. 三分支真实反馈闭合，但强参考与算法差异尚未成立\n\n实际027五件逐件与纯模型吻合，联合分支减少总完成时间2.3并消除前段优化造成的blocker+.8。该机制仍可由已知pair repair解释，三条不是完整96或在线算法优势。原图bridge与双进程分片仍处开发/验证阶段；不以局部结果宣称总体达标。\n')
with receipt.open('x',encoding='utf8') as f:json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'new_native_dispatched_here':0},f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
