from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT,OUT=HERE.parents[3],HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'live_communication_scoped_inputs_v2_prepare_001/plan.json':'d64ab44189e5c7cb3d79b109072a6f29d22c9004cd8da872ceffc65dbc8a9fe9',
 'live_communication_scoped_inputs_v2_prepare_001/final_receipt.json':'372ed4e862feaf0a9c2644ee268ed951c5e1905942081cd9cd6cbf69ce4bd740',
 'live_communication_scoped_inputs_v2_prepare_001/external_application_wall.json':'849a0ad7112a1f5d9e1e5cf29e532ac360cc88a5faf2fad3f65fcbde01019754',
 'complete_root_owned_decode_C_pair_prepare_001/plan.json':'947f7c33f012f4b4b3248cbbfe1cc037537340c3da89971160ec732d91bae00d',
 'complete_root_owned_decode_C_pair_prepare_001/report.json':'af3602b4e72f640bf2535773c38c58943ff5ae8b8a81ca0b3551dea01c416e5f',
 'complete_root_owned_decode_C_pair_prepare_001/receipt.json':'3b37c0e54c7c905d394870ee297d8f15d1320b7a96f42ac24ac4044148e2b31c',
 'complete_root_owned_decode_C_pair_prepare_001/external_application_wall.json':'bb0d6820f0f6ab0b839614fb83c948d499d7f1ab917b8a36ee871b0d785df73e',
 'initial_scoped_inputs_six_cost_prepare_001/plan.json':'20522f420b69367c2cd09ebc1d9a6774b5b4853970cdde363ac637b3cfe3bf31',
 'initial_scoped_inputs_six_cost_prepare_001/report.json':'b1b043f9df91ae0dbc1fa16c7d9bd6490c82316bc51707850747dbb0fed92898',
 'initial_scoped_inputs_six_cost_prepare_001/receipt.json':'7daf1c47f1e425843dfc4044b437ec3328333ed3470cf5713e4a032574163a17',
 'initial_scoped_inputs_six_cost_prepare_001/external_application_wall.json':'6cbffb993f662bd77f6e12dca6f2a9c20093c655d4967b8a251b7f801b0d93a1',
 'delivered_peer_cost_prepare_004/plan.json':'904afc076ef0d94d5a55356715473cedf9469715358debb473b2721b64e4cd62',
 'delivered_peer_cost_prepare_004/result.json':'c4c82e9883d727fdfe335eae26437c4764bfca04c60b418e5d09be1bb62b28bc',
 'delivered_peer_cost_prepare_004/external_application_wall.json':'561bc2907c7070d3d78683ed2fe425ef14fcbd702514c30e2d95c4420b574a93',
 'delivered_peer_cost_pure_004/receipt.json':'0713b309feecf79e31260216731a0660d4b48b0ce8d9f962fde24bdf2ac0c2e2',
 'delivered_peer_cost_pure_004/tests.xml':'24a08fdd05f62e8aa85a18b08aa8263e4decdb953910106d187aa599497e36f2',
 'delivered_peer_cost_prepare_003/external_application_wall.json':'59d0d86c7a810f592977f807f299632b5e824c9c90661644b37b716647519d0f',
 'live_initial_decision_seam_prepare_001/plan.json':'b99c0e61d308dec0ca803eb06cd058b54f8a1b8abef86f9ff5b5c550e427a8ff',
 'live_initial_six_seam_design_001.json':'811e0ead91c505a83610484f98dc0275b20ab50535e38101eb1bfbb42d761e1b',
 'planning_v2_c_encoder_source_design_001.json':'82e32713b6edb19796ffc514797e29292eabe627ab4a5170c3d656e3fe9eb1d0'}
for p,d in pins.items():assert sha(OUT/p)==d,p
r=json.loads((OUT/'live_communication_scoped_inputs_v2_prepare_001/final_receipt.json').read_bytes())
assert r['full_output_exact']==96 and r['unknown_or_difference']==0
assert r['actual_collection_data_checks']==226 and r['actual_known_collection_data']==192
assert r['early_invocations']==96 and r['early_unbound_invocations']==0 and r['source_changed']==[]
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_039';backup.mkdir(exist_ok=False)
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes());active=state['active_experiment']
state['current_stage']='All3 goals open. Scopedv2 original96 exact0unknown/226checks192known passed74.7095131. SameC owneddecoder72 exact, median125.5448->102.5555ms. Initialcontext+predictionABBA24 exact, median422.25885->169.0113ms. Originaldelivered_peer32 attribution fixed2 allabsent, no optimization claim. Actual initial adapter47pure/168source passed; next6native seam and initialscopefull96 source/pure underway. No active root performance sessions.'
active['scoped_v2_full96']='25pure;164sources;whole74.7095131/360. 96fulloutputs exact0unknown,226actualchecks192known,96earlyinvocations0unbound, mappingcertified/sourceunchanged/GCenabled. Modelspan includes earlysave/hash/journal, not direct bareABBA timing. No native/fullrequest100ms.'
active['owned_decoder_C_ABBA72']='87owned+18binding+26harness=131pure,153sources. Same original verified C normalizer botharms, currentC vs sameC+ownedinternaldecode. Direct18preflight and complete72originalsavedchecker passed whole75.1202559/240;36each. Amedian125.5448 B102.5555ms, Amax277.5854 B205.9948;17/18pairedroots improve, postsubmit_source_outage/block0_load0/fixed_default does not. Historical16closed2unknown retained. No actualnative integration/100ms, no independent second72audit, no forcedGC or cleanup certificate.'
active['initial_scope_ABBA24']='22component+30harnesspure,171sources,whole10.4414751/120. Botharms include original initialcontext builder and prediction. Bfresh scope reused only within same call, exact original A/B guards and comparison preserved.24exact0unknown/sourceunchanged; Amedian422.25885 B169.0113ms, Amax461.0069 B196.8595. Do not compare combined169 to prior barepredict102. Full96 initialscope next; no complete100ms.'
active['delivered_peer_actual_attribution']='57pure v4/78sources;whole14.6178315/120;32 originalABBA calls fixed27212/27215, allabsent(None),0native/model/policy. Aoriginal medians37.1643/58.45875ms; Bsameinstrumented medians31.5551/46.70925ms, nested originaldigest31.5186/46.68265, outside0.0365/0.0265. Timer not optimizer; arm differences not gain. Only original absent paths, no successfulcoverage/all-dayfrequency. Keep exact validation/error order; no moving expiry beforedigest.'
active['delivered_peer_failures_retained']='v1 38pure then strict metric audit found bool/float/negative gaps, noactual. v2 52pure; sourceclosure missed bare-import test, rootexpected75 vs74 stoppedprelaunch, noactual. v3 52pure76sources; launchfailed0.4923005 beforeworker due shared exclusive stdout.log fromprepare,actualvalidator0 (outerdeclared32 is notexecution). v4 separatestage logs+5flowtests ->57pure78sources, passed. Never overwrite/restart olddirs; explicitly list baretestimports in sourceclosure and distinguish declared/actual counters.'
active['live_initial_online_seam']='Actual-origin initial adapter/shared32provider/sameinformation selectors47syntheticpure passed16.5026094,168sources frozen. Candidate requires both returned suffix and valid outerstatus; no escaped saved prediction after postaudit failure. Sameinfo strictcoordinate/plateau/pairrepair/MPC allpay32, explicit incumbent nooldbest. No actualonlinegain. New3sessions/6owner collector records original3endpoint prefix/errors, noextraqueries/proxy;36synthetic cases drafted,0actual. Guarded proposal never dispatch authority; laterrolling correspondence unresolved.'
actions=[
 'Complete initialcontext scope full96 source/pure/prepare; root actual360 retains original96outputs/226checks192known and one cumulative SaveBeforeReturn. Preserve newpure001 importfailure beforetests; repairednewsource uses constructor identity, pure002 newdirectory.',
 'Review and run new3sessions/6owner initial actual seam after36pure/sourcegates: same accepted027 runtime44+21 entryexit,originalinput/action16,4publicationcalls percase,12collectortriplets,total120. No32provider/model/physicaldispatch yet. Preserve originalgetterexceptions againstmonitorfault and keep all6 unknown denominator.',
 'C typed-v2 encoder source-only prototype: fused exactbuiltin validation in original consumption order, unsupportedNotImplemented fallbackonce, originalhashlib/floatbits/uint64/UTF8/ACK semantics. No build/load/perf until source review and gates. Preserve failed batchedwriter and allabsentfixture limits.',
 'Plan full32 online implementation separating expensive offline graph/alias diagnostics from necessary runtime information/current-state guards with source ownership proof; no guard deletion or cachedfuturetarget. Current216.9747081s diagnostic is not100ms provider.',
 'All-day all28506offered strict normalprotection stillopen; existing600/2400 failures retained. Improve actual digest bottleneck before another justified bounded replay; no frequency extrapolation from2fixtures.',
 'No active root sessions atcheckpoint. All3 goalsopen; prioractual18 complete requests434–976ms,0under100,2unknown remain. No externalGPTProsend/push/commit.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone039\n\n全面恢复继续有效，全天原流、完整请求100ms、联合方法有效性均未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(actions))+'\n',encoding='utf8')
note='''\n\n## milestone039：原全96一致，两个组件实测改善，保留失败与范围

v2公共输入全96完成，whole74.7095131/360；96完整输出exact、0unknown，226实际数据检查/192known，96early-save累计调用/0unbound，原全检查、序号绑定和来源均通过。此次初始上下文调用未优化，保存/hash/journal计入modelspan，不能当裸预测计时。

同一C normalizer配对的内部owned解码实验131pure/153sources后执行，whole75.1202559/240，18原C预检、72完整样本检查通过。两arm各36样本，中位125.5448→102.5555ms，最大277.5854→205.9948；17/18配对改善，postsubmit_source_outage/block0_load0/fixed_default未改善，保留。历史16closed/2unknown不升级。公开decoder、ledger_tree、严格JSON及canonical reencode仍在；尚未接入实际native完整18，不能宣称100ms。

初始上下文构造与预测共同计时的6输入ABBA24通过，whole10.4414751/120、24exact0unknown；A中位422.25885、B169.0113ms，最大461.0069→196.8595ms。原caller两owner guards与facts比较保留，只在本次调用共享public构造。该169ms含初始阶段，不与先前裸预测102ms混比。新全96初始scope纯门首轮在import阶段失败（把实例predict误当类属性，0tests/0模型），旧源和失败保留，新目录修复后继续。

全天固定两项原delivered_peer归因32次完成，whole14.6178315/120；两个原输入所有结果均absent(None)。A原validator中位37.1643/58.45875ms，B原validator加计时中位31.5551/46.70925ms，嵌套原digest31.5186/46.68265ms，外部0.0365/0.0265ms。不是优化实验，不能把A/B差值当收益，也没有成功coverage路径或全天频率证书。保持先digest后expiry的原异常语义。

归因工具中途问题原样保留：v1计数检查容许bool/float/负值，v2强化后源码闭包遗漏tests裸导入（expected75实74，未启动），v3启动因prepare/execute共用exclusive stdout.log失败（0.4923005秒，实际调用0；outer的32只是预定分母）。v4分阶段独占日志并增5测试，57pure/78sources后成功。不得覆盖失败目录，源码闭包显式列出裸导入测试，声明数量不能冒充实际数量。

真实初始adapter、shared32provider、同信息强方法47synthetic通过，168sources封存。预测成功与外层审计状态双重约束，失败后的残留prediction不可用于选择。下一步仅3原生会话/6owner初始送达与fresh-current接口验证，保存原三endpoint成功/异常前缀、不增加调用或替换session；之后才接32候选与公平强方法。当前full32诊断216.97秒含重图和隔离探针，须区分离线证明与必要在线guard，不可降低验证标准。全部三目标开放，根无运行会话，父目录用户C++哈希不变，无外发/提交推送。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 69. 共享构造与内部解码优化通过局部验证，联合优势仍待真实在线比较\n\nv2全96输出一致；同C内部解码72配对中位125.54→102.56ms、初始构造加预测24配对422.26→169.01ms，均非完整100ms。原delivered_peer两输入全absent，仅定位其原摘要成本。实际数据adapter47pure及168source为接入准备，尚未产生在线强基线比较或严格实际保护证据。全天all28506、完整100ms、联合有效性三目标不变。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'root_sessions_active_at_checkpoint':[],
 'new_native_branches_since038':0,'external_messages_sent':0}
with (HERE/'milestone_039.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(HERE/'milestone_039.json')}))
