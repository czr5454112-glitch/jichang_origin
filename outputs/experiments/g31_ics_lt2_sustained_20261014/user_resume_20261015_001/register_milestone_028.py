"""Record bridge timeout with complete raw retained and evidence ABBA result."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
pins={
 'original_bridge_serialize_once_prepare_001/external_application_wall.json':'95a682b80bb76d1788ae6c7f3ab522cfc44ca8a8d248308527b53bcc64b317a4',
 'bridge_serialize_once_terminal_partial_review_002/review.json':'f3ef1bf55bcde7e39b619ddaf928d25f7f7b628438905fc5b7cb5688717694b8',
 'single_root_evidence_pair_prepare_002/plan.json':'086dd891c9b60a2700045c5c75da0cd9d67776f541e1c8c9eb215f82d8ba36cf',
 'single_root_evidence_pair_prepare_002/report.json':'813215d1a5cc1be6361bf10c0a5c84e76cfe08234a5796c3fa12f6ee8fd93380',
 'single_root_evidence_pair_prepare_002/receipt.json':'d0c2826ccf7e7685da27c48047f9f841aa3dcf60da665ea59f5a827d4f34cd42',
 'single_root_evidence_pair_prepare_002/external_application_wall.json':'020ad158ecea9dbf49df247c41d53ecc6d446730726de0e3e579131df2f8e73a',
 'single_root_evidence_pair_independent_review_002/review.json':'e1b0106b74ac705518a87aebef23b69488d28d534f05de370ef108e4cafc1c60',
 'historical_goal_service_source_prepare_001/source_preparation.json':'93c8f76b701417f986688b550691dc71b1af831bd4fdd79e6620503e4c77540b',
 'historical_goal_service_saved_replay_001.json':'f716a5d4fca19769797af3fe7f8b4115df4d5810157488ce1a6298d8b86756a4',
 'live_obligation_recollection_v2_residual_001.json':'7d6a47bc13146096171c4f82cf7746d1f0ba6ba5d02a1f76b0e5f1225e56e98b',
 'initial_root_observation_source_diagnosis_001/report.json':'794e7076e2fccb9434a471429488519c4c9498b8f62087c870bc8e6810f2a81a',
 'initial_root_gate_actual_shape_replay_001/report.json':'843e8532e531673d2f7d0c01c7c3bab5a353455ac7ff0648de9729c1a9e9020d',
}
for p,h in pins.items():assert sha(OUT/p)==h,p
review=read(OUT/'single_root_evidence_pair_independent_review_002/review.json')
assert review['saved_calls']==72 and review['all_original_roots']==18 and review['source_unchanged']
assert review['summary_ms']['A']['count']==review['summary_ms']['B']['count']==36
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_028';receipt=HERE/'milestone_028.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. Logging-only bridge reached H86400 and exported complete-looking74.38MB raw; worker2317.309s but original shared2400 timed out during independent saved replay, so fullH/39 remain pending complete audit. Fixed full18 evidence mockABBA72 passed independent saved verification: old36 median1389.36765ms versus new36 median689.24825ms; this is evidence construction only, not native100ms. Next actual18 integrates source-bound observation gate and complete one-build evidence. Historical own-ACK service proof supports14 residual saved final inputs conditionally, but actual96 stays80/16 and two unloading cases unknown. All3overallgoals remain unmet.'
active['original_bridge_serialize_once_status']='Terminal shared-budget failure preserved: external2400.2095334s. HeartbeatH86400/39 delivered; producer assessment39actual token unloads/71physical/49postparking/10bridge, pending independent audit. Raw74383534bytes; worker2317.3093981s. Manifest37270complete rows/files. Small terminal review verifies82live/archive+67compiled026, no payload decode; finalraw file creation-to-lastwrite293.2170503s is filesystem wall,not isolatedCPU. Saved verifier had about51.303916s before outer end and produced no complete result. Separate fixed600 saved-only fullaudit being prepared, originalfailure never promoted.'
active['single_root_evidence_actual_mock']='prepare002 frozen128sources/51pure and independent narrow review. Exact18xABBA=72 full constructions, wholePython152.7235709s within240. Old36 min5.1488/median1389.36765/max3235.3559ms; candidate36 min4.8624/median689.24825/max1772.8069ms. All fields/order/types/floatbits/alias/strictdecode/return retained. Independent all72 savedreadback20.047s passed, native0/predict0. Historical request clocks are fixture data, not native latency; actual18 still16closed2unknown0under100. prepare001 preservedunexecuted after saved-topology/formula hardening.'
active['historical_service_support']='New pure48 + all238 saved attempts:176oldknown preserved,28 additional conditional support=14first+14recollection,34attempts unknown. Final saved inputs94supported/2unknown only; actual96 remains80assessed16unknown. B uses its actual own delivered selfACK and immutable publication requests, exactjob/gen/trav/finaledge and publicservice to derive separate servicebound; rawclamped-ready unchanged. Currentpair/owner/action/ACKunion/occupancy/Lwire guards retained. Two unloading-transition cases remainunknown. Earlier first-decision support changes future execution timing, so newnative96 is mandatory; source-bound adapter preparation active.'
active['root_observation_gate_status']='Real18 recorded shape audit and source diagnosis complete. New actual advance-chain adapter pure00273passed, not native/prepared campaign yet. Original .05 background,owneractivation and client.activate ID sequence retained; only root duplicate observation/drain skip under complete actual notification chain/noAchange/no newcall/no dueAretry. Runtime continuity computed internally, not externalJSON; future fullpolicy/outbox proof required. Firsthop prefix>=2 gate blocks real entryprefix[0]; minimum actualedge_exit_at proof and ID effects documented separately, not implemented or mixed into gate.'
actions=[
 'Execute separately prepared fixed600 saved-only bridge audit with all37270 new and27218 old hashes/ordered rows, exact policy/physical/FIFO/Storage/ACK/cap proof and all28506 states. Redirect only new audit export; never alter original2400 timeout.',
 'Prepare/review new actual18 one-build evidence plus source-bound root observation gate, retaining exact background .05/admission IDs, original firsthop logic, full raw/RPC/endpoint/physical audits and whole600 budget. Schedule native timing in an exclusive window.',
 'Finish historical-service real LocalTransport adapter/source/pure and prepare fresh96 under same information/candidates/budget. Do not upgrade old80/16 or unsupported unloading pair from saved counterfactuals.',
 'Separately resolve actual EDGE_ENTER firsthop proof and resulting background-ID changes; no claimed physical-time subtraction from measured compute.',
 'Full32 complete-request100ms, full-day alloffered business performance, and same-budget strong-reference joint-method effectiveness remain unmet. Keep all failures and interim proof scopes. No commit/push/externalmessage/GPTProsend.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone028\n\n全面恢复持续有效。原流已到H86400并导出结果，但2400秒内独立审计未完成，失败不改；完整证据构造72次比较中位约减半，真实请求100ms仍未达标。历史服务事实仅通过纯验证，旧实际96仍80/16。三个整体目标继续开放。\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone028：原流完整结果已保留，证据构造约减半，仍不降低验收标准

原流serialize-once固定2400试验在H86400完成运行，producer报告39次token卸载、71物理请求（22初始停车+49后续，其中10bridge），raw_final.json.gz最终74,383,534字节。worker函数连同最终导出2317.3093981秒；外Python2400.2095334秒超时，独立保存核验未完成。终态小审002核实82live/archive、67compiled026、输入与小件hash、37270清单行及文件数一致，但没有读取1.1GB API载荷或解压74MB最终文件，故不升级fullH/39证书。raw文件创建到末写293.2170503秒仅是文件墙钟；核验log创建到最终结束约51.303916秒。小审001路径分隔符KeyError失败保留，新002修正审计脚本后通过。后续单独600秒saved-only全审可复用完整数据，不能改写原2400失败或冒充原预算通过。

single_root_evidence_pair_prepare_002在所有agent暂停重任务的窗口完成固定18xABBA共72完整构造，128源码/51pure/根审/独立窄审，外Python152.7235709秒。旧36中位1389.36765ms，新36中位689.24825ms，约50.39%降低。完整事件、A/B端点、字段键序、标量类型/浮点位、alias独立、严格artifact解码和发布返回均保留；独立全72保存重读20.047秒通过。这个结果只证明mock完整证据/返回构造成本，不能称真实request100ms、模型加速或新native结果。原真实18仍16closed/2unknown、0/18<=100ms。prepare001保留未执行，因为保存verifier外层拓扑和历史时钟公式需要强化，002完整补测后才执行。

历史服务新纯接口只用决定者B当前真实own endpoint中的已送达selfACK与immutable publication ledger，将已观测最后入边的派生到达+公开服务时长列为独立字段，不覆写原service_ready_at。48纯测试和238保存尝试重放完成：176原known保持，28新增条件支持（14初次+14补采），34attempts未知；最终保存输入94/2只是可表达性。原实际80/16和六不完整参照族均不改；新guard可能让初次即可决策，从而改变后续真实时序，必须fresh96。两条卸载跨窗口缺实际terminal receipt仍unknown。新实际LocalTransport/session/admission绑定adapter正在独立准备。

通知观察优化已补真实18响应/outbox形状、实际advance调用记录和完整scheduler AST还原证明；纯00273通过，未执行native。全局.05节拍、后台owner激活和原client.activate保持，缺连续性/新call/到期retry/任何A通知均fullfallback。初始collect advance发生在链建立前，首步不造连续性。另一个firsthop问题是前置prefix>=2挡住真实entryprefix[0]；accepted027的真实view edge_exit_at只能由匹配EDGE_ENTER填写，reservation不能给该证据。提前关闭root还会减少client.activate并改变后续ID，须独立版本验证，未混入当前gate或计作物理等待的CPU收益。三个总目标仍未达标。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 58. 完整原流产物与证据成本改进不等于总体达标\n\n原流H86400/39 producer结果存在，但共享2400保存审计超时。完整18证据72构造约减半只是工程成本结果，实际request100ms仍失败。历史selfACK支持14个保存末态是条件输入扩展，旧actual80/16及六参照族不升级。继续same信息/候选/预算与严格逐件非恶化，不从不完整参照中宣称联合新颖性。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},
 'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),
 'overall_goal_achieved':False,'new_native_dispatched_here':0}
with receipt.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
