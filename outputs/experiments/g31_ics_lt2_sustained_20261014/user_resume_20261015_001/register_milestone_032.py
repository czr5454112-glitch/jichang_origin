"""Record verified new results, timing correction and still-open goals."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
pins={
 'initial_owner_route_entry_codec_campaign_prepare_001/campaign.json':'8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a',
 'initial_owner_route_entry_codec_campaign_prepare_001/external_application_wall.json':'6c9ec7215158cd4429344c18e9c89c0688ed140b98385f197f451001334097c1',
 'initial_owner_route_entry_codec_campaign_prepare_001/receipt.json':'49b0d7e2f4d019c1546fb34f941813198d21189d39735eb6e0ac3101f8c184bf',
 'initial_entry_codec_saved_review_001/report.json':'283cadcc3ec8ba36b4b33da213c4b6f45ef9d33dd1ee29da690d2b8c703a3cee',
 'initial_entry_codec_saved_review_001/external_application_wall.json':'8ceb5b1957db76eaf6437fda22b33ceff0cf4edf959d9b6f7569a06b0a716d2e',
 'initial_owner_decision_cost_source_001/clarification.json':'af1f5100ba929637f03cfcbaecab3b6968102ac14757636072ca5e2a3a661fbc',
 'live_communication_conformance_prepare_002/external_application_wall.json':'76787446c51c08b327adc8fa9f5441cc9bc68eaac27beddffac58d111eb20502',
 'live_communication_partial_review_001/report.json':'671f67f1831b9c1e43a0d3c1f879f0cdda06ead50253102f1b66cb1fcd430656',
 'live_communication_lazy_prepare_001/plan.json':'afdcf5741fd835d7d9d4cb9f922bde7d7475b7bd4787ae6f6207a525652b9497',
 'live_communication_lazy_prepare_001/final_receipt.json':'07b26e476cd5ab328498e919a88503aa2ee64ef73ed21d6c02eb9af0f01c36b0',
 'live_communication_lazy_prepare_001/external_application_wall.json':'44c8a3ebe28f4649e5fa273419d90f675fa2ea6f71dc6b7fcd2581db9511268b',
 'live_comm_lazy_saved_review_001/report.json':'293da7bb9008125a7d6ed274b74dc48669437d752b407cc6bb7339a89bc00bc6',
 'live_comm_lazy_saved_review_001/external_application_wall.json':'fbf5e5d3b05ecbd259a1e4ad9d4973d3910cf89ea806ba383a7f01f73845878c',
 'bridge_saved_kernel_cost_prepare_001/plan.json':'0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc',
 'bridge_saved_kernel_cost_prepare_001/external_application_wall.json':'6b64d7e7311c76fde7e70215df13520170dc8c270fc1651715c92abe9fddad04',
 'bridge_saved_kernel_cost_readback_001/report.json':'0df9dba718be1f555142711d168fc45a42cdb3717e4cee3100a8f76ce47b8c66',
 'bridge_saved_c_compare_source_prepare_001/plan.json':'059d424630c578d035c65f329d27ace423b736bb44acf545252af861c2d14fe3',
 'c_tree_normalizer_feasibility_001/design.txt':'362d487789352ac12350c03607b0816517226c689d3ea147fe19e12ff0d73741',
}
for path,digest in pins.items():assert sha(OUT/path)==digest,path
entry=read(OUT/'initial_entry_codec_saved_review_001/report.json')
assert (entry['closed_roots'],entry['open_or_unknown_roots'],entry['roots_at_most_100ms'])==(16,2,0)
assert entry['normal_pairs']['strict_nonregression_count']==6 and len(entry['normal_pairs']['improved'])==2 and len(entry['normal_pairs']['equal'])==4
communication=read(OUT/'live_comm_lazy_saved_review_001/report.json')
assert (communication['exact_count'],communication['unknown_count'],communication['saved73_full_byte_equivalence'])==(96,0,73)
assert (communication['initial_owner_checks'],communication['actual_later_checks'],communication['actual_known_later'])==(192,226,192)
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_032';receipt=HERE/'milestone_032.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed; all3 overall goals remain unmet. New actual entry+codec18 successful and independently full-audited16closed2unknown/normal6protected2improve4equal/0under100. New lazy-view initial communication projection full96exact and saved73 complete outputs byte-identical, independently rechecked; rolling online support/strong method efficacy still open. Bridge fixed tail8 diagnostic supports original C comparison, but full37270 audit and all28506 business still unclosed. New source-only copy/normalization and legal rolling-state work continue.'
active['entry_codec_composition']='New169source/67compiled/41pure actual18 completed successfully in156.528396s. Receipt includes103 identical producer import entry/exit maps. Independent144source saved audit54.2396241s passed original full endpoint/physical/RPC/actual-entry/gate/fulloutbox/codec verifier.16closed2unknown,0under100;closed386.4671to1142.9403ms,median617.83185. Normal6 five-job strictprotected:2improved(block1_load0 andblock1_load1),4equal.1068of1254gate steps skipped;19,208,020complete bytes;startup763.3904ms,cleanup224.6764ms,8RPC. Separate rounds/deadline selections: no causal claim from altered choices or walls. Older failed entry producer and separate recovery stay distinct.'
active['entry_lost_gains_diagnosis']='Correction to milestone031: collection-through-finalcheck crosses the decision-return boundary and includes later fresh source/receiver guard;93.0119/98.6452ms finalcheck totals are not all predecision. Valid strict predecision lower bounds are Acollection record28.4505/31.4153 + RPCcaller33.8689/40.2674 =62.3194/71.6827ms, both exceed original60ms. Record timestamps precede deepcopy; omitted return/binding costs are nonnegative. RPCcaller minus worker12.6296/14.3675ms is composite codec/IPC/wait/ledger, not isolatedcopy. No limits changed.'
active['communication_model_status']='Original002 shared180 hardtimeout whole179.2177879s preserved:73exact23unclosed, firstmissing insufficient_advance/vector09 may have been inflight, missingreceipt/exitpins. Saved-only partial audit32.5775669s rechecked all73/146initial/162later146known. New lazy source100,8focused+4driverpure and inherited48. Only moves readonly unused fullview creation to two existing L trigger reads; exact inverseAST, all original events/capture/guards unchanged; valid closed-state scope, not generic malformedstate exception equivalence. Fresh all96 new predictions in97.8015263s within new evidence-based360 offline budget:96exact0unknown/226later192known/73old completeoutputbytes identical; original failure not rewritten. Independent saved96 audit59.3791636s rechecked192initial/226later/192known/five floathex endpoints/orderedchronology/all73bytes/source100+actual93 currentarchive entryexit. model cost min.3114761/median.36344435/max.6098303s,total37.1014412s; far from100ms full32. Initial state projection does not yet support later rolling replanning or establish online method superiority.'
active['bridge_saved_audit_status']='Original producer2400 and linear_v3 full600 failure remain; independent full37270 replay not closed. Fixedtail8 old/new16gzip kernel ABBA whole42.0673136s/120,79sources39pure: recursivecomparison median342.99155ms vsoriginalCjson203.5708ms(-40.64845%); deepcopy425.2627 vsstrictJSONencode+decode417.1393ms(-1.91021%). Producer-author savedreadback16.1228261s rechecked all96records/inputdigests/clocks, with prior independent source review; alias objects not saved so no new offline alias proof. New Ccomparison-only privatebinder80sources/32pure, actor deepcopy unchanged, nofull600dispatch. Tail gain is not wholeaudit guarantee. New original-text seconddecode-copy diagnostic source work is distinct from prior encode+decode result, not yet executed.'
active['normalization_c_helper']='Source feasibility only, separate CPython C API builtin-tree helper, no native027/026 rebuild or rootCMake changes. Preserve fresh containers/order/scalars/tuple conversion/depth64/node2M/keycounts/activechain aliases/resourcekey semantics. Nonbuiltin key/status/type-metaclass behavior must return unsupported before any userhook and fallback originalnormalize once; surrogate rejection remains laterUTF8. New standalone prototype/tests being written, not built or benchmarked. Full18 exactfield/byte parity precedes any runtime integration; no100ms claim.'
actions=[
 'Use full96 initial conformance as a prerequisite, then establish strictly supported later rolling states and original guards before same-information strong online methods. Do not feed actual future targets, unknown peer payloads or observer truth into predictions.',
 'Reduce genuine predecision repeat endpoint reads/copies using private owned snapshots while preserving session-bound authority, failed prefixes and fresh final guards. Keep60ms decision cutoff and complete100ms/full32 goals.',
 'Develop separate C normalizer prototype and differential domain/ownership/error tests; no frozen source/native rebuild. Require fixed18 complete byte parity before complete evidence A/B or actual campaign integration.',
 'Restore original C comparator in new private saved-audit binder; evaluate same-original-text decode for independent actor copy on fixed16 inputs with full equality/isolation and wholecost accounting. No blind600rerun or unsupported whole speed extrapolation.',
 'Close full37270/old27218 saved bridge replay before adopting39-completion baseline. Then legal completion-baton candidate requires actuallocal completion receipts and samehead strict all28506 protection; Storage53 and conditional39 limitations remain.',
 'Retain all failures/unknowns/startup/cleanup and all3 overall goals open. No commit/push/GPTProsend without user request.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone032\n\n全面恢复持续有效。通信初始投影已全96精确一致且独立核验，73旧完整输出逐字不变；尚不等于后来滚动预测或联合在线有效性。新entry+codec实际18独审通过，16闭合/2未知，正常6保护、2改善/4持平，完整100ms仍0达标。全天完整保存审计与原流业务仍未闭合，三个总目标均保持开放。\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone032：通信初始投影全96一致；实际18完整核验与成本边界纠正

新entry+codec实际运行169源/67编译归档/41纯门，156.528396秒成功结束，有receipt及103条相同import入口出口记录。独立保存核验54.2396241秒通过完整endpoint、physical、RPC、实际入边、gate、outbox及codec；16closed/2unknown/0低于100ms。closed386.4671–1142.9403ms，中位617.83185。六正常场景五件均严格不退化：block1_load0与block1_load1改善，其余四个持平。1068/1254 gate跳过，19,208,020完整证据bytes；startup763.3904ms、cleanup224.6764ms均保留。不同轮次的deadline选择变化不能归因为codec。上次entry生产失败及独立恢复原件继续保留。

更正milestone031的时钟归因：collection到final_local_check包含决策后的fresh guard，93.0119/98.6452ms不能全部称作决策前成本。确实成立的决策返回下界为collection记录时刻28.4505/31.4153ms加RPC caller33.8689/40.2674ms，即62.3194/71.6827ms，足以证明超过60ms截止；记录后的deepcopy和返回校验未扣除。RPC caller减worker的12.6296/14.3675ms是组合开销，不是孤立复制成本。新singlecapture方案仍须保留实际session、失败前缀和最终fresh校验。

通信002原180秒失败保存：全179.2177879秒，73已精确/23未闭合，首缺insufficient_advance/vector09可能在途，原缺receipt/exitpins不补造。部分独审32.5775669秒确认73预测、146初始、162后来采集（146known）。新的lazy-view只把无用的整view构造推迟到两处已有L触发读取，inverseAST可还原；事件、数字、采集和所有guard不改。该等价限定于已守卫有效模型状态，不能宣称任意坏内部状态异常完全一致。

新100源/12新增纯门/继承48门，用有实测依据的共享360秒离线预算重新计算全部96，实际97.8015263秒完成：96exact、226后来采集192known、已有73完整输出JSON解压后逐字相同。没有拼接旧结果。独立保存核验59.3791636秒重验全部192初始owner、226后来guard、五件floathex终态、顺序chronology、73完整bytes、100生产及原93current/archive入口出口，96通过/0未知。model单候选min0.3114761、中位0.36344435、max0.6098303秒，总37.1014412秒；明显仍未满足完整请求100ms或full32。离线预算调整不是产品门限变更；初始预测一致也不是后来滚动重规划支持或在线强方法胜出。

桥保存审计的固定tail8×old/new kernel对照42.0673136秒完成：原C JSON比较中位203.5708ms，相对递归342.99155ms下降40.64845%；JSON encode+decode复制417.1393对deepcopy425.2627ms仅降1.91021%，不据此换actor复制。生产作者另做16.1228261秒saved-only读回，验证16输入/96记录/摘要/时钟；独立性限于此前legal源审，运行时alias对象未保存，不能声称另行离线证明了对象身份。新C比较binder80源/32纯门，只私有替换比较，保留actor deepcopy；无新全600运行。正在准备直接二次解码同原文本的不同成本假设，但尚无结果。旧全天生产与全审计超时都保留，全天28506目标未达成。

C树normalizer独立原型仍在源码阶段，保留原完整值域、资源key、深度/节点计数、共享alias复制及循环错误；custom key/status/metaclass在任何hook前unsupported并完整回退原方法一次，不能把“不执行hook”的docstring当实现事实。新helper不改native027/026、父用户PIBT、根CMake或任何冻结包；固定全18完整字段/byte parity须在性能/运行集成之前成立。全部三项目标继续开放，记录仅供后续用户命令推送GPTPro审核，未发送。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as stream:stream.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as stream:stream.write('\n\n## 62. 全96通信一致性打通前置条件，尚未证明在线联合方法\n\n有效有限域lazy-view保留所有事件/guard，fresh96及old73完整bytes经独审一致；它缩短的是模型工程成本，后来滚动状态和同信息强方法仍未验证。新entry+codec18正常2改善/4持平但0达100ms；C比较kernel局部约40.65%不能推全日审计必过。原180/600/2400失败与2未知保留，全部总体目标未完成。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'native_dispatched_here':0,'external_messages_sent':0}
with receipt.open('x',encoding='utf8') as stream:json.dump(record,stream,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
