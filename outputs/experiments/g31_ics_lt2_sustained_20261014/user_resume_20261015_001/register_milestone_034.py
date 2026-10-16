from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
pins={
 'bridge_saved_text_actor_prepare_001/external_application_wall.json':'8215f25b11efe738bece294b5c9fc98d05a66d28095f5ba2eed44770979940b1',
 'bridge_text_actor_terminal_review_001/report.json':'cdbfc909c0e81dd9686f2aed619953dfd6dcc112c180f2eb7be1488d0f7b0f93',
 'live_phase_b_pause_prepare_001/external_application_wall.json':'8bfc10df9f64768570ff1ae8fbb9e5df528aba5bc7b953d097bfc8fcb9192013',
 'live_phase_b_pause_saved_review_prepare_001/report.json':'cc947571f61ef8c3e6b3f56fa4f4693048175a0f29c53156945b37cc2a9a9de5',
 'live_phase_b_pause_saved_review_prepare_001/external_application_wall.json':'5706c2aafb07fe1047fe61b2f1eb356e4785eb0b1ffb8d1e36cbf796d7c46fb3',
 'c_tree_normalizer_saved18_prepare_002/report.json':'7961d01ebada0b428fa552baca465e8cdc0b07a056b45675283ed66045f52e01',
 'c_tree_normalizer_saved18_prepare_002/external_application_wall.json':'3cd556a54a1b5989c8b9fa5b7137b5e86a9e5e198915426b11d326131283cba8',
 'conditional_continuation_source_summary_001.json':'e75a148aa4188c391189923b68af6dc434e04df3df3b50076157ff15d96768a7',
 'complete_C_publisher_binding_pure_001/receipt.json':'a8d686a1e872534fb8e4d434ff1ca04d2d6301849d321fce723ea32926dd331c',
 'bridge_replay_copy_scopes_source_001/plan.json':'421ff5c5db0ae9358412cef86ec6450286720e9a15ed05e574364a754512f142',
}
for p,d in pins.items():assert sha(OUT/p)==d,p
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_034';backup.mkdir(exist_ok=False)
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed; all3 overall goals unmet. Bridge full audit600timeout remains. Passive6/14 and independent saved readback passed. C18 direct-supported full parity passed; complete publisher8pure passed, cost ABBA72 preparation pending. Fourframe same-action continuation19fakepure passed, real6 preparation pending. Bridge private copy scopes37pure passed, synthetic cost preparation pending.'
active['bridge_saved_audit_status']='New full audit hard_timeout600.2124356s, actor19712/oldprefix19712 ordinal19711,275 journal rows, required37270new/27218old incomplete. Progress correction applies to all previous linear markers: emitted after tape checks/old-prefix comparison/actor construction BEFORE outer observer/policy consumption, so not current policy completion nor last in-flight call identification. Root terminal readback checked96live/archive and small journal/clock pins. No final full physical/policy acceptance. Late256interval around24.6s cannot isolate cost. No blind600rerun. New two discard-refresh callers and temporary direct own capture borrow37pure passed, preserving retained client_view and PossessionGate original durable copies/allguards. Synthetic64job/16revision cost harness preparing, never invented runtime client state from final raw.'
active['normalization_c_helper']='Isolated build/61functional unchanged. Fullsaved18v2 direct builtin supported18,16closed2unknown retained; exact types/order/floathex/freshness/fulloriginalcodec+strictdecode passed whole38.5607279s/180.10new+169/135frozen+6124toolchain+18raw/runtime entryexit unchanged,7projectimports,GCtrue. Complete root bytes19222296 differs from evidence-only19208020. Verification cost only. Private completepublisher binding8pure passed4.3459392s internalharness/120 with Python provider only,0Cloads. Module88cb1b9d623395297c3814184a981593b8bb0a53cbca98165cd71bc50a9cafa5. Original code/fullglobals/clock/encoder/strictdecoder/hashledger/return retained; onlynormalize provider changes. Full18ABBA72 C publisher cost source preparation pending, no native100ms.'
active['rolling_passive_snapshot']='Six actualpassive model calls whole12.4314135s/120,6exact0unknown14points,fullpredictionbytesexactfrozenlazy,source/loadedentryexit unchanged. Independent author savedreader passed8.0741031s/120,6bytes14metadata12initialguards14actualinventories,106sources including105producer. Graphs notsaved: no independent alias/isolation reproof; producer attestation only. Passive remains resumableFalse,noopaqueIDrelation/filter/hiddenstatecoverage/nativeauthority. Separate explicit4frame same-action continuation19fakepure passed,root readmodule/tests;count20001 bypassfinish,horizon poppedtime andA/B remainders retained. Real6/14cut/39resume comparison preparing,notexecuted.'
active['complete_C_publisher_binding_pure']={'plan_sha256':'49d5d42d82f4d0034016bea126802871bac106f1f7edb34f4702aee8eba0817c','tests':8,'whole_internal_seconds':4.3459392,'C_loads':0,'actual_cost_or_native_claim':False}
actions=[
 'Review and dispatch one full18ABBA72/240 C-normalizer complete-publisher mock cost. Direct C support on actual normalization arguments; fullcodec/hashledger/return plus setup/exports/teardown charged. No inference to native100ms.',
 'Review fourframe same-action driver and one120 real6/14cut/39resume fullprediction comparison. No prefix restart or next event before current remainder; no hiddenstatecoverage or strongmethod claim.',
 'Review two private copy scopes synthetic64job/16revision ABBA cost under120. Fullbridge600 remains failed; no blindrerun/budgetextension and gains not additive.',
 'Implement versioned singlecapture livebinding/failure-aware branch verifier from reviewed design; preserve reported root separately from certified root and all18 denominator. Afinal fresh; Bincomplete can coexist with reportedclosure and must certifyunknown.',
 'Continue all28506/H86400 normalprotection, full32 complete100ms and fair sameinformation strong joint efficacy. Full39 saved acceptance before lawful completionbaton; topology/FIFO/trays/failuredenominators unchanged.',
 'Preserve all problems/solutions/failures for later user-commanded GPTPro review; no external send/push/commit.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone034\n\n全面恢复持续有效，三项目标均未达标。全天复核仍600秒超时；六输入被动快照及独立读回通过；C完整18份直接路径等价通过，性能未测。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone034：完整 C 路径与六输入被动快照通过，全天复核失败保留

新版完整桥接审计仍于600.2124356秒超时，最后actor19712/ordinal19711，未完成37270新记录与27218旧前缀。修正此前所有progress解释：记录在tape检查/旧前缀比较/actor构造后、外层observer/policy消费前，所以不是该策略步骤完成证明，也不能定位最终在途调用。终态小读回核96源及journal时钟。局部复制67.69%改善未解决整体瓶颈；两处私有副本候选37pure通过，synthetic成本尚在准备，保留全部guards/client_view/PossessionGate持久副本。

六真实被动模型whole12.4314135秒通过，6完整预测逐字等同frozenlazy、14快照点。独立作者savedreader8.0741031秒通过6完整字节、14metadata、12初始guards和14actualinventory。graphs未保存，不能重新证明运行时alias/隔离；被动点仍不可恢复，不能筛真实隐藏状态。新独立四帧same-action源码19fakepure通过，真实6/14cut/39resume对照准备中，无native/coverage授权。

C helper完整18条v2通过whole38.5607279秒：直接builtin非NotImplemented18，16closed2unknown保留，类型/顺序/floathex/新容器/原codec/strictdecode全核；10新源、169/135旧源、6124toolchain和18raw/runtime入口出口不变。verification成本不是性能。完整publisher私有绑定8pure通过internal4.3459392秒、无C加载；保持原code/完整globals/clock/hashledger/strictcodec。完整18ABBA72成本门准备中，不等于native100ms。

单次采集设计继续有效：raw.failure=None仍可能B incomplete且A reported closed，必须保留实际物理事实但certified_root unknown，checker拒绝不能提升为合法unknown，18分母不能减。冻结失败不覆盖，父目录用户文件未改；尚未发送GPTPro或推送。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 64. 完整树等价及被动点验证，整体仍待证\n\nC18直接路径及六被动模型/独立saved读回通过；尚无完整100ms或隐藏状态覆盖。四帧续演和两处副本仅待真实验证候选。全天600再次失败及progress边界修正保留，局部收益不能代替全量保护或公平强方法证据。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'native_dispatched_here':0,'external_messages_sent':0}
with (HERE/'milestone_034.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_034.json')}))
