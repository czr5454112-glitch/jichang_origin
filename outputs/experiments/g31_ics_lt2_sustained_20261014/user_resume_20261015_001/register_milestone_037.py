from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'live_communication_scoped_inputs_prepare_001/plan.json':'68024f30b1cc262a7162b67b8a9828885ed5d5c738316cfd44585fb40b1ad7f8',
 'live_communication_scoped_inputs_prepare_001/final_receipt.json':'b89298d38daeece9b9f82c05d53ea7dfcd213cfee877c1c492b4206c990673d1',
 'live_communication_scoped_inputs_prepare_001/equivalence96.json':'560f17e0328ac05f87611fa5bdbeb1c6eaa9e6919a6bca659af7145d53db56a0',
 'live_communication_scoped_inputs_prepare_001/external_application_wall.json':'7b8137d693b006d05952582388116ce244f10f6f4fa5b54bcb76bbb210fb49fa',
 'scoped_public_inputs_profile_prepare_001/report.json':'3c3afa0274b9925d8373b53cf1f4925512cdbfea18fc66a55205d7e81000099f',
 'scoped_public_inputs_profile_prepare_001/external_application_wall.json':'5ba38bbfbc008878d14edf803eef1f390350838f7d8a0bd22202c0aa7560ab8d',
 'scoped_public_inputs_profile_prepare_001/independent_saved_hotspot_analysis_legal_001.json':'357f6cf0a9abc7a08bb2d2b5f73687c3444aad7a4efd03d262b584e6fdf4e2d2',
 'future_later_paired_six_prepare_001/plan.json':'5628a1262101d3a8bdcb21733d2185a538f752e81df12c26f207ebbb62ad9fbd',
 'future_later_paired_six_prepare_001/receipt.json':'a7046d9e1b4d14ba6328632704d12f86359b10f551139bf69424ac102435181e',
 'future_later_paired_six_prepare_001/rows.json':'3b6b8d066c60c51fcbcef28b4420d66131175009daa42546eed0d7a0f9f69be1',
 'future_later_paired_six_prepare_001/external_application_wall.json':'545eb679e73c72b2c00a01b8e6dcdc608543ec15cb20a31364bfd62d2b2b0b11',
 'planning_v2_batched_digest_cost_prepare_001/plan.json':'4288d316218b81f9ef743301ba0e9da9add3e909328c496eb40428ed0032d49d',
 'planning_v2_batched_digest_cost_prepare_001/result.json':'8461dcae96b3c0bf1d9f9974e4c8fc0b48265769679ef1c12b6702dff42319da',
 'planning_v2_batched_digest_cost_prepare_001/saved_verification.json':'cf1947d896d8f9843916abefdd8a366414be1e7d54775ae1224580578855280b',
 'planning_v2_batched_digest_cost_prepare_001/external_application_wall.json':'d6a698f64a7ab0f0bbc7d54f920dc1107bed8de6aabc5435ad69b6cc884d9f97',
 'planning_v2_batched_digest_cost_independent_source_review_r1_001.json':'dbe8d9f34c4132652144f21cee7581412a3a6795ac1386c5b62174f5ee569ef8'}
for p,d in pins.items():assert sha(OUT/p)==d,p
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_037';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment']
state['current_stage']='Fully resumed, all3 goals unmet. Scoped v1 full96 exact/0unknown passed; profile6 locates remaining fulltable deepcopy and escaped historical binding. Future later-action paired6/12 suffix exact passed, not online/hiddenstate coverage. Batched digest fixed2 ABBA32+4bytes exact but much slower, rejected for promotion. V2 private public-read source under test, complete32 shared-prefix source design and all-day bounded attribution pending.'
active['scoped_full96']='155source fixed original96/226laterchecks192known passed shared360; whole79.9378395s,exact96unknown0unbound0. Complete early saves before model return/original checks, ordinal mapping only after original96pass, full96 old/early/late bytes/types/order/floathex/chronology exact. Model wall includes earlysave/hash/journal, not comparable to bare ABBA model span. DefaultGC and source/runtime entryexit retained. No new independent saved96 reader, full32 solver/hiddenstate coverage/native100ms claim.'
active['scoped_profile6']='Whole13.446116/120,6exact0unknown and6models,154source unchanged. Complete freshscope creation/private binding included in model cProfile, original initial contexts separate unchanged6profiles. scope.inputs44/55 fulltable deepcopies cum253.98–378.31ms,43–54%of instrumented model; cumulative times overlap. no_overlap/vector00 history helper base remained original initial guard,10 original construction.inputs calls versus1 other5; correctness passed but scope performance leak. Newv2 only private history.base binding,public_input fresh one-case copy,identify original readonly loop borrows private table; generic inputs still fullfresh deepcopy. No endpoint/validation/outcome cache or initialcontext optimization mixed. Source/tests pending, no performance claim.'
active['future_later_paired6']='62fork pure plus22driver pure gate. Actual6 initial engines/6advance/8prefixsame-resume/12futureforks/12suffixresumes exact6unknown0 under28.1187678/120;sourceunchanged. At first knownB postcollect/predecision both later actions clone same unconsumed parent before suffix. Strict current/wire/past action guards; graph only later action differs, parent/sibling mutable graphs isolated and mutation probes preserved. Full predictions saved before target reads and exact12 outputs/chronology. No prefix restart/extra collect/adaptive alternative cut. 32domain/opaqueIDs/hidden-state coverage/onlineeffectiveness unproved.'
active['planning_v2_batched_digest_cost']='Negative fixed2actual unprofiled ABBA32+4completebyteoracle,whole25.3903919/120,123pure002 afterteststub failure001 retained. Fulltypedbytes/nativesavedSHA exact both2pairs,all32measurements guards/source/runtime savedchecked. A/B digest median27212:28.7789/70.9182ms;27215:48.73495/115.8761ms. Bfullbuiltinpreflight/groupguards inside callable, defaultGC, samebody exact. B is slower and not promoted; do not remove necessary preflight to claim gain. Diagnostic bodyguard/check456–706ms is not actual policyguard. No new600 or100ms claim; prior attribution frequency unresolved.'
actions=[
 'Validate newscopedv2 source/focused pure and prepare fixed6ABBA24 v1-v2; keep oldv1 immutable and initialcontext caller unchanged. Fresh scope/setup allinsideB, full outputs saved before targets, defaultGC and full24denominator. Rootreview beforeactual.',
 'Build source-only complete32-action shared-prefix path from proven6/12futureforks. Exact independent Cartesian domain, strictfirstB unsupported remainsunknown, allinitialsetup/clones/observationfilter charged. Actiondomain coverage is not hiddenstatecoverage or onlineauthority.',
 'Batched typed digest actualABBA is negative; preserve and do not promote. Source-read all-day actor/query/policy digest callsites and plan bounded phase clocks to determine actual600 bottleneck/frequency before another fullaudit.',
 'Complete-request100ms still unmet: last16closed native roots434–976ms,0under100. Preserve60ms decisionreturn cutoff and100ms deadline, include publication/finalvalidation/cleanup; no component-only substitute.',
 'Original all28506-offered all-day audit remains600timeout. Accepted39 completion proof required beforelawful completion-baton rollout; normalprotection/unknowns/topology/FIFO/trays unchanged.',
 'All3 goals remainopen. Continue autonomous improvements and preserve failure/fix history forlater user-commanded GPTProreview; no external send/push/commit.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone037\n\n全面恢复继续有效，三项目标均未达标。公共输入v1全96完整一致、未来动作6前缀/12后缀一致；批量摘要编码实际变慢，保留负结果并停止推广。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone037：全96与未来动作分叉通过，批量摘要优化被真实成本反证

公共输入v1固定全96验收通过，whole79.9378395/360秒，96exact、0unknown、0未绑定早期序号，原226later检查/192known保持。完整预测在facade返回前保存，原96全部通过后才映射固定顺序；旧/早/晚完整bytes、JSON类型/顺序/floathex与时序一致。此driver模型span含提前保存/hash/journal，不能与此前裸ABBA模型计时直接比较；无新独立saved96或在线full32证书。

v1六输入cProfile完整一致，whole13.446116/120。完整freshscope及私有接线计入模型profile，原initialcontext仍单列6次未改。scope.inputs每预测44/55次整表deepcopy累计253.98–378.31ms；no_overlap/vector00历史服务helper.base漏接旧initialguard，原inputs构造10次，其余5个各1次。clone_module累计仅0.1023–0.172ms，非下一热点。累计时间重叠、插桩扰动，不当作未插桩速度。新v2仅私有单case deepcopy、identify只读借表和history.base接线，全部guard与generic整表freshcopy保留；测试/ABBA尚待完成。

未来动作源62pure（首轮scalar误传dict encoder失败保留并修复）及driver22pure通过；实际固定6前缀/12后缀whole28.1187678/120，6exact0unknown。6start、6advance、8同动作prefixresume、12fork、12future-resume严格计数；第一个knownB切点严格wire/current条件，两动作在同一未消费父图上克隆后再跑，past动作固定、只有later_action改动，父/兄弟隔离及破坏性复制探针通过。12完整预测提前保存后与独立原始结果逐项相等。没有prefixrestart/额外collect/适配性换切点；不等于full32、原生opaqueID关系、隐状态覆盖或在线联合有效性。

批量typed-v2摘要75原功能+48harness门通过。首次123门122pass/1fail是hash替身过宽导致负例提前拒绝，保留失败XML/源码，仅收窄替身后123全部通过。根与独立源审后固定2实际输入ABBA32+额外4完整字节编码，whole25.3903919/120；2完整字节pair/4binary和原nativeSHA、全部32计时/8batch及保存读回一致。性能负结果：27212原28.7789ms/新70.9182ms，27215原48.73495ms/新115.8761ms。新函数完整builtin预检计时内显著变慢，不能去掉预检后冒称优化，暂不推广。诊断全bodyguard456–706ms不代表实际policy调用成本；不据此盲跑600。

最新native18仍16closed2unknown、0个100ms；全天原流600失败继续有效。三目标均未降标、未完成，无GPTPro外发或提交推送，父目录用户C++文件哈希不变。当前root测量会话均已关闭，agents继续v2纯门/full32源设计/全天归因。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 67. 全预测与未来分叉有一致性证据，批量编码是负结果\n\n公共输入v1全96精确，未来动作6前缀/12后缀精确。这证明限定模型的执行重用保持结果，不证明隐状态覆盖或在线联合优势。批量typed writer完整字节正确但实际含预检成本大幅变慢，停止推广并保留反例。100ms和全天原流以及强公平基线联合有效性仍未达标。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'new_native_branches_since036':0,'external_messages_sent':0}
with (HERE/'milestone_037.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_037.json')}))
