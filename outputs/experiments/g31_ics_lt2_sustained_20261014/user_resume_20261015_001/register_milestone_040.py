from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'live_communication_initial_scoped_inputs_prepare_001/plan.json':'8036d19b2f397551df1fe593f45b17097ef6cf314a6521319ad33b772cfb491c',
 'live_communication_initial_scoped_inputs_prepare_001/final_receipt.json':'34bba02fd695b81383ac94d0e81baf279cff1c5702e04d5c4c09f6f1ff5aea2a',
 'live_communication_initial_scoped_inputs_prepare_001/external_application_wall.json':'047c2f7d297e088413b54e721be7394018c5bf0aafc3ddd20f273987f521f462',
 'live_initial_six_seam_prepare_001/plan.json':'29452ac24d205fbd516700a7af051a19805d239dd75f96e091b7f57304e83085',
 'live_initial_six_seam_prepare_001/receipt.json':'524b29515d0f6e3bc963c5e38b1161528646eb090c27d9793551199332ecef46',
 'live_initial_six_seam_prepare_001/external_application_wall.json':'d2e648dc0034dcedc5fc8896f785da900ab82ac1db0ccf084fa70d3c39ce8a37',
 'planning_v2_C_encoder_source_prepare_001/source_plan.json':'f644e09943a967e9daf43ff377c6e8ba8a57416186e8ad1c966fa2ac7b6f2592',
 'planning_v2_C_encoder_source_prepare_001/independent_narrow_review_legal_001.json':'cf6ed935705dff5395d18b191ae60d6df5bd5a7228da6f0cbdee65d92100fea9',
 'initial_full32_runtime_boundary_design_001.json':'38a007831a8f23d5e1036eb2cd7d45095c037666674af830b738312e28db1f4a'}
for p,d in pins.items():assert sha(OUT/p)==d,p
for folder in ('live_communication_initial_scoped_inputs_prepare_001','live_initial_six_seam_prepare_001'):
 r=json.loads((OUT/folder/('final_receipt.json' if 'communication' in folder else 'receipt.json')).read_bytes())
 assert r['source_changed']==[]
 if 'communication' in folder:
  assert r['full_output_exact']==96 and r['unknown_or_difference']==0 and r['early_invocations']==96
  assert r['actual_collection_data_checks']==226 and r['actual_known_collection_data']==192
  assert r['early_unbound_invocations']==0 and r['early_ordinal_mapping_certified'] is True
 else:
  assert r['initial_domains']==6 and r['known_initial_domains']==3 and r['unknown_initial_domains']==3
  assert r['run_acceptance_status']=='closed_run_acceptance_passed'
  assert r['model_predictions']==r['physical_requests_submitted']==0
 correction=HERE/'live_initial_six_root_review_decode_correction_001.json'
pins[str(correction.relative_to(OUT))]=sha(correction)
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_040';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());a=state['active_experiment']
state['current_stage']='All3 goals open. Initialcontext+prediction scope original96 exact0unknown passed53.5483112/360,226checks192known. First actual initial6seam closed24.1860584/120 with3knownB/3unknownA: A reads service_ready fields absent from observe_protocol, not demonstrated illegal route. New version must derive lawful wire bound from actual public/delivered evidence, preserve strict guards. Ctyped-v2 source reviewed, build/pure preparation only. No active root sessions.'
a['initial_scope_full96']='174sources,29pure002 after preserved importfailure001. Actualwhole53.5483112/360,96fulloutputs exact0unknown,226actual192known,96early0unbound/mappingtrue/source[]/GCtrue. One originalSaver and original futureguards retained. Component only; instrumentedwhole not paired speed and no native100ms.'
a['actual_initial_six']='173sources/36syntheticpure passed21.4451988. Actual3accepted027 sessions/6owner scopes whole24.1860584/120; full44+21entryexit acceptance closed/sourceunchanged; all3B validated,all3A unknown_fresh_current_guard,6denominator retained. A KeyError service_ready_known: actual observe_protocol lacks service_ready_known/at used by adapter; these are capture fields. Initial collections succeeded; route legality not disproved by absentkey. No model/provider/physicalsubmit/nativeprotection/100ms. Need versioned public-bound correction and actual-schema regression before another attempt.'
a['typed_C_encoder']='Independent 7source draft f644e099...2592, root and legal cf6ed935...fea9 read handwritten fullfield order; no concrete blocker in declared stableexactbuiltin CPython3.11.9 domain. Originalhashlib, uint64mask, Pack8/-0/NaN/Inf,UTF8 and ACKisnotNone retained; onlyhookfreeNotImplemented→originalonce. Sevenfiles is not executableclosure.0build/load/test/actualfixture/perf sofar. New separatebuild120 thenfunctional120 need fulltoolchain/sourceclosure anddirectCvsfallback counts; oldnormalizer/writer frozen.'
a['runtime32_boundary']='Source-only design38a00783...1f4a counts272+cuts fullgraphencodes,48mutablewalks,32beforegraphdecodes,32destructiveprobes,atleast65sourceinventories pernormalfull32. Not measuredcostdominance. New exactfactory-owned execution path may remove only diagnostic graphtraversals with inverseAST and ownership proof; originalfutureAPI/dynamicguards/32wholegraphclones/16contexts/all32outcomes stay. Newcontract cannot reuse uncomputed diagnosticflags. Full96 output/graph verifier beforefairtiming/nativeuse.'
a['scoped_v2_ABBA24']=a['scoped_v2_ABBA24'].replace('Full96 adapter25pure passed and164sources frozen; actual active session86384.','Full96 adapter25pure/164sources subsequently passed; see scoped_v2_full96. No active session86384.')
a['owned_decoder_v2']=a['owned_decoder_v2'].replace('Pythonnormalizer only; fair C/C+owned binding source pending,0performance gain claim.','This historical87pure was followed by sameC owneddecoder72; see owned_decoder_C_ABBA72 for measured scope and limits.')
actions=[
 'Fix actual initial A adapter in newversion using real public/delivered fields and previously validated loading transition; retain strict now+.01<ready,identity/generation/traversal/owner/capacity. Preserve actual0013known3unknown. Regress actual schema and failure boundaries before fresh6run.',
 'Finish C typed-v2 build/pure orchestration: independentowned120build with source/compiler/SDK/header pins, no load; then functional120 directC fullbytes and boundaryparity with separatefallback accounting. Rootreview beforeeach actualstage. No performance or all-day extrapolation until correctness.',
 'Source-only private owned projection bundle copy elision: preserve all6 original validation calls, prove revalidate result fresh/unescaped and exacthelper code, no cache. Newversion/tests only,174frozen unchanged.',
 'Implement new runtime32 evaluator only after fixed initialseam correction: explicit ownedconstruction contract, originalfutureAPIs/dynamicguards remain, offline diagnostic verifier full96 comparison. Every strongmethod pays same32 and actual strict5job outcomes stillrequired.',
 'All-day originalall28506 and normalprotection remainopen. Do notrerun600withoutvalidateddigestcost gain; preserve600/2400 failures. Complete actual18 remains434–976ms/0under100/2unknown; componentgains notcertificate.',
 'No active root sessions atcheckpoint. Continue; no externalGPTProsend/push/commit.'
]
state['next_actions']=actions;a['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone040\n\n三个总目标继续开放。初始作用域全96通过；真实接口首轮保留3通过/3未知，正在修正公开字段接线。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone040：初始共享全96通过，真实接口暴露字段接线错误

174sources、29pure002后，初始上下文与预测共享作用域完成原全96，whole53.5483112/360；96exact0unknown、226实际数据检查/192known、96early-save/0unbound、累计序号映射/source/GC均通过。所有初始A/B guard与facts比较保留，future实际上下文仍原函数globals，单Saver不重置。仅一致性证据，不把本次whole与先前配对计时混作速度比较。pure001错误类属性导致import失败继续保留。

真实初始6门首轮：173sources/36合成门，3个accepted027会话，whole24.1860584/120，原44+21验收entry/exit闭合、来源未变。三个B均通过，三个A均保留unknown_fresh_current_guard，不能因exit0称全通过。定位A为KeyError service_ready_known：observe_protocol实际没有该字段，service_ready_known/service_ready_at属于planning capture。实际初始采集成功；该错误不证明route不可行。下一版本须由真实公开字段和既有validated loading transition得到严格时间界，不得读隐藏native状态或删除wire guard。0模型/32provider/物理提交，尚无在线联合有效性。根prelaunch元数据误写actual_fixture_decodes0，独立更正文件记录verify_plan实际读取6个scene输入JSON（新旧各3），原件保留；0rawoutput/model/native不变。

独立C typed-v2七份源码获根与legal窄审，在声明CPython3.11.9/stable builtin域无具体阻断；仍0build/load/test/perf。需新完整toolchain/source闭包、独立build120与functional120、全字段完整字节与异常顺序门；direct-C支持和fallback分别计数。旧Python writer/C normalizer/native不变。

完整32运行路径source分析数出每完整batch272+cut次全图编码、48mutable图遍历、32全图decode及32破坏性探针，至少65future源码inventory；仅静态调用数不等于热点实测。拟新factory-owned执行版本只分离离线诊断，保留原future API/current/ACK/wire guards及32全图clone/16上下文/32结果。独立离线全96/图隔离仍需通过，新contract不可冒用未执行graphproof。全天原流、完整100ms和强公平联合有效性仍未达标，无外发/提交推送，父目录用户文件未改。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 70. 实际接口失败揭示公开视图与捕获字段必须区分\n\n初始scope全96一致；实际六owner检查仅B三项通过，A因不存在的观察字段拒绝。修复须用已送达公开证据证明相同严格时间窗，不能以模型值代替当前原生权限。新C编码与执行/离线诊断分离均未获得性能或在线优势证书。三目标维持。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'new_native_branches_since039':3,'native_owner_domains_known':3,'native_owner_domains_unknown':3,'external_messages_sent':0}
with (HERE/'milestone_040.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_040.json')}))
