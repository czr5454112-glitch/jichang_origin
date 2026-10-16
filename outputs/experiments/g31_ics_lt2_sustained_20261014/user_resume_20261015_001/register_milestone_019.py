"""Close fair protection timing and actual diagnostic pipeline; keep goals open."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
pins={
 'preference_protection_context_pair_001_independent_review.json':'7c0a6c783ceadedccd4669f8d411f758728b9b67bdb69ac5f9987f6d19012bc4',
 'preference_protection_context_pair_001/external_application_wall.json':'44aa4aae455fa9b6690e241f4f6665010824299bb36586f87f57e42866eae1fd',
 'original_route_spool_actual_review_001.json':'d055065953b287f48f70e1314b5843948a83e33f093daaa94c34f61534e4262f',
 'original_route_spool_cold_comparison_001.json':'1c985420703d140c5fb7169f356756e40a5c2e8941032c4e891d8ea927e71c4e',
 'original_route_spool_prepare_002/powershell_launch_receipt.json':'3bf7cc9d174b6241103961fd1e2e4befc75af1a10a53ac6bd0a2e5736b502773',
 'live_obligation_interval_001/receipt.json':'71f45f3c17fbaafac1f9fd2f1551ab99ebb767ebe365f5b1351dcc9724e3cf77',
}
for name,digest in pins.items():assert sha(OUT/name)==digest,name
pair=read(OUT/'preference_protection_context_pair_001/receipt.json')
assert pair['status']=='completed_pure_ABBA_with_validated_partial_suffixes'
assert pair['source_changed']==pair['input_changed']==[]
assert pair['candidate_queries']==768 and pair['full_baselines']==24
spool=read(OUT/'original_route_spool_prepare_002/independent_verification.json')
assert spool['status']=='passed_saved_spool_candidate' and spool['closed_roots']==2 and spool['open_roots']==1
assert [v['all_warm_native_api_rows'] for v in spool['cases'].values()]==[1272,6197,147171]
assert read(OUT/'original_route_spool_prepare_002/receipt.json')['source_changed']==[]
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup,receipt=HERE/'before_milestone_019',HERE/'milestone_019.json'
assert not backup.exists() and not receipt.exists()
backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');a=state['active_experiment']
state['current_stage']='Fully resumed. Full1x/2x physical horizons audited but business0; separate original caprelay completes8/28506 with3 ontime, all-job protection unknown. Fair protection-cut context total improves6.956% but every32-query batch>100ms. Spool actual3faults and exact saved replay passed, mixed warm results and slower whole campaign, no promotion. Earlier receiver bound and fixed new joint mechanism remain independently gated research, no overall success.'
state['working_tree_identity']='codex/g31-ics-v3-circulation at c3fba566; uncommitted local research. Production89c2935 and parent user PIBT hash preserved. Actual native campaigns currently closed; accepted026 binary/67 archived sources remain distinct from current opt-in027 source.'
state['last_verified_checkpoint']='Accepted026 build/acceptance and actual route/caprelay saved verifiers remain bound to026 archived sources and binary c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943. Separate027 phase campaign has its own authority. Producer seals are not newly reconstructed by small reviews; arbitrary cross-process persistence remains unproved.'
a['request_context_status']='Historical context improvement retained: original391.913ms->247.6586ms median. Latest fair full-baseline ABBA adds conditional protection cuts to that faster context:24batches/768queries/24baselines; total2804.1019->2609.0202ms(-6.956%), median240.7895->229.5407ms. B152.8675-272.8738ms,0/12<=100; two of six cases slower. All43sources unchanged,384Afull outputs,198Bexactfull+186Bstrict prefix counterexamples;0native. Complete source/check/copy/potential/baseline/32queries/encoding charged. External10.6764766s includes saved-output readback.'
a['protection_cut_status']='Logic and fair timing closed.93 distinct strict completed-job counterexamples remain valid in initial model; unknown suffix explicit. Modest6.956% total measured gain, no100ms certificate. New independent receiver lower bound targets48 of93 by sole-carrier reachability and optimistic forward floating arrivals; same full baseline and original guards retained. Initial pure31pass/192candidate+four-method parity; final strengthened pure gate and A=combined/B=receiver-bound ABBA preparation pending, not benchmarked.'
a['diagnostic_spool_status']='Spool002 actual3fault+fullsaved verification closed in203.8276189s<600;95Python/67compiled026 pins unchanged, same1272/6197/147171APIrows with zero omissions, all background/controller boundaries and commonH9900producerseals exact. Normalwarm64.3337->81.6111ms(slower),drop970.5869->928.7724ms,missingACKopen27365.3727->22030.004ms(still5attempts/open). Closegzip238.5426/343.7109/1637.4657ms plushash58.0072/79.9513/366.4023ms retained. Wholecampaign199.1382522->203.8276189s(slower); childcold normal10920.8852->14547.9666ms,drop12840.3533->15642.1305ms,openprefix50562.6842->46753.6521ms. Single nonisolated comparison with concurrent pure work; not algorithmic acceleration or net improvement, no promotion. Preparation001 and small-review precheck schema errors preserved,0native in those failures.'
a['joint_protection_design_status']='Frozen source-only live_obligation_interval001:19pure,42source pins, exactly3 synthetic11node/14edge/5job/3tray inputs. Isolated D1.2,HQ=HX1.1,s1.5,detour1.3 gives safe timing-only advance<=.1 and bypass.2; two negatives fail. All native/all-job/online embedding unknown. Separate new predictor retains best-ranked waiting, extends generic Storage and absolute-return rule;24pure plus old6x32 full-output regression exact. Unique new3x32 fixed screen and full16 fixed-initial/16later-default references being prepared; original immediate-return baseline must not be weakened to analytic not-before b. No new-case screen or native executed yet.'
state['next_actions']=[
 'Review/execute one fixed receiver-bound ABBA versus current combinedProtectionRequestContext under120s owned job; fullbaseline,32queries,allpreparation/encoding and savedreadback charged. No native protection or100ms upgrade.',
 'Review/execute unique3x32 new live-obligation pure model under120s; keep exact frozen three inputs,all5jobs,all directed alternatives,complete strong reference families and strict comparisons. If failed, retain failure without parameter tuning; original airport map and validation256 unchanged.',
 'Close spool hypothesis as mixed engineering evidence; no further reruns or default promotion. Preserve deferred compression/cold/wholecampaign costs and open ACK denominator.',
 'Source-only evaluate dedicated closed JSON-only prediction worker with one startup guard compilation; prove no cached prior snapshot/outcomes and full dynamic per-request validation. Existing staticfactory negative remains; cold/RPC costs cannot be amortized into a100ms claim.',
 'Retain original28506/57012 denominators,cap0 edge97->98,original permissions/FIFO/capacity/mandatoryStorage. Full-day business throughput, strict per-job protection, actual final revalidation/timing and independently useful joint method remain open.',
 'Record problems/solutions and exact continuation; do not commit,push or sendGPTPro without instruction.',
]
a['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
next_text='''# 当前执行入口 — milestone019

用户“全面恢复”仍有效。所有验收标准不变；当前没有运行中的 native worker。完整请求100ms、全天业务吞吐、严格逐件保护和联合方法有效性仍未完成。

最近闭合结果：

- 原图caprelay保留全天28506件与22盘，同一盘8次业务循环完整核验；完成8、按时3、未完成28498。两owner终态发布/ACK修复通过，不能推出全业务保护。
- 较快RequestContext加条件保护剪枝：公平24批、768查询、24个完整baseline，总计算降6.956%；所有B批次仍152.868—272.874ms，两个场景更慢。完整结果与严格反证已独立复核。
- spool002三故障实际和完整保存核验通过，共203.828秒。正常暖请求变慢到81.611ms，丢首ACK928.772ms，缺ACK开放前缀22030.004ms；全部API与背景轨迹保持。close压缩和冷启动费用保留，不推广为净算法加速。
- 新联合机制仍是独立合成模型：原机场图未改。解析正例和两负例冻结；通用Storage模型旧192候选精确回归通过，新96候选尚未执行，未来信息仍是假设。

按序推进：

'''+ '\n'.join(f'{i+1}. {value}' for i,value in enumerate(state['next_actions']))+'''

证据根：`outputs/experiments/g31_ics_lt2_sustained_20261014`。最新绑定见 `user_resume_20261015_001/milestone_019.json`；历史顺序与失败原因见 `RESUMPTION_20261015.md`，旧执行入口原件保存在各milestone备份中。不要重跑已封存的一次性注册/launch脚本，也不要把live027源要求等同于已接受026归档。
'''
(DOC/'NEXT_ACTION.md').write_text(next_text,encoding='utf8')
note='''

## milestone019：保护剪枝有限正收益，诊断流水线实际混合结果

首次公平保护剪枝ABBA已执行且独立复核：每臂每批都计完整context初始化、同输入完整baseline、32查询和编码，24批合计768查询与24baseline。A总2804.1019ms，B总2609.0202ms，下降6.956%；中位240.7895降至229.5407ms。B范围152.8675—272.8738ms，0/12达到100ms，两个case中位反而更慢。93个不同反例各重复两次，186个条件前缀拒绝及198个完整B输出均核验；未执行后缀始终unknown。整Python10.6764766秒含完整保存读回。下一条更早receiver下界保留全guard与baseline，不把偏好当强制路径；仅在L/P不可能更早供盘的固定continuation内研究48个可提前拒绝案例，其余45不夸大。

spool002完成三故障实际+完整保存核验，整应用203.8276189秒，低于600秒。95个Python源、67个026编译归档与binary均绑定；1272/6197/147171条API全部保留，背景controller、请求重试、实体语义和H9900封印相同。暖正常64.3337→81.6111ms变慢，丢首ACK970.5869→928.7724ms，缺ACK开放前缀27365.3727→22030.004ms，仍5次尝试且未闭合。close压缩分别238.5426/343.7109/1637.4657ms，hash58.0072/79.9513/366.4023ms也保留。整campaign由199.1382522增至203.8276189秒，正常/丢ACK冷界更慢，开放前缀冷界较快；单次非隔离且有并发纯工作，不能归因为算法净加速。结束这条微调，不推广默认策略，也不从旧费用扣除假想收益。

准备001曾误把旧prepare返回的campaign当完整plan，启动前校验阻止，0native；002改读实际保存的完整plan后通过。小结果复核曾用错receipt字段名，在产出前停止并留下记录，未改实验原件。精确进程身份012只覆盖wrapper/launcher/campaign命令族，不是全后代清单；600秒起点只可给creation/BOOT bracket，不伪造精确UTC。

新联合模型的解析输入冻结为一正两负。正例孤立资源不等式只说明潜在0.2秒绕行收益可以大于0.1秒安全纯timing界，未证明E占用、默认路由、全5件保护或消息交付。新预测器已通过旧六场景×32完整输出回归，之后唯一固定96候选必须包含完整16个固定初始路线和16个后续default参考；不得把更强的立即返盘baseline改成较弱not-before窗口。新原生验证尚未启动。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 49. 计算改进与机制构造均不替代联合创新证据\n\n保护剪枝公平总计算下降6.956%，所有样本仍超100ms；这是条件模型中的效率进展。spool仅改变诊断存储且整campaign更慢，不属于联合方法收益。解析资源例子仍需完整场景证伪与强参考，普通pair repair/LNS若同样达到结果必须如实归因。\n')
with receipt.open('x',encoding='utf8') as f:json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'new_native_dispatched_here':0},f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
