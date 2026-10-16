"""Record independently closed96 and actual18; retain all failed attempts."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
pins={
 'live_obligation_unloading_saved_audit_001/terminal_summary_clarified_001.json':'77c2bec5681d3a90f8884d8cb2257508d0eb18a52be96d96c62f0592587645fe',
 'live_obligation_unloading_native_saved_review_001.json':'504288c4604c9931143c359dc4037957d82504490335e3844736b85a3c720fef',
 'live_obligation_unloading_saved_audit_001/receipt.json':'94c799e973a30da27b9f9776e6d6ee30e4b9daac73941f901f92992aeea05b0a',
 'live_obligation_unloading_native_prepare_001/preregistered_protocol.json':'6c82cc7ad10aae82f2f9d9059899dca20753e4bf0f5a78885d2e53e505199ecd',
 'live_obligation_unloading_native_prepare_001/receipt.json':'34a6d6d6d0b9008a9fbea2b0f8050d6afc2f69c3594dd22505f1c730ec859f3c',
 'live_obligation_unloading_native_prepare_001/external_application_wall.json':'206f51733a1396b5dbd0021052e74cefd95de8ced518ee9b03ea7203d7517127',
 'initial_owner_route_gate_independent_actual_review_001/report.json':'95361ce13acfd4711a3bc3c68fe37fb51aae1a9a841dd56ed3ddaae693bc9849',
 'initial_owner_route_gate_campaign_prepare_002/campaign.json':'659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4',
 'initial_owner_route_gate_campaign_prepare_002/external_application_wall.json':'f62581487c60d949c627cbeb9fded699bb8e0606d6fa9e8990acb8aacced1b6d',
 'initial_owner_route_gate_campaign_prepare_001/root_dispatch_withheld_001.json':'9b0a188713e33412b13990e3393377e147825e6fd3528a60bc333c55d699f759',
 'bridge_saved_linear_terminal_review_001/report.json':'7cd216af1c1f88097c8781ea2c4383f256b489c5d058dab6894fa491cf55c231',
 'bridge_saved_linear_v3_prepare_001/plan.json':'4bbf6f364ac097db7fbf2bd1ff35f9ea74500566f367933e552bf6da6f0bd87e',
 'bridge_saved_linear_v3_prepare_001/root_source_review_001.json':'72ef11bf807bf1460977669761d47b1a35786de9c4c08e40fdeedc2688e904b3',
 'firsthop_entry_integration_pure_001/tests.xml':'8a25c2f786d23663dee85f8ab226eeed40334a9596b4a2ccab0ebaa15cc69891',
 'firsthop_entry_integration_pure_001/independent_source_review_control_timers_001.json':'65b0fde1d1a59ccad759d6e87618dd82d5ce1cfdcc481df54a81be101fe4ead8',
}
for p,h in pins.items():assert sha(OUT/p)==h,p
summary=read(OUT/'live_obligation_unloading_saved_audit_001/terminal_summary_clarified_001.json')
assert summary['status_counts']=={'assessed':96} and summary['remaining_unknown_branch_count']==0
assert summary['physical_counts']=={'full_H40':96,'all_five_complete':96}
assert summary['independent_replay_error_count']==0
assert all(v['status']=='complete_native_finite_reference' and v['assessed_members']==16
    for row in summary['cases'].values() for v in row['references'].values())
for ref in summary['run_references'].values():assert sha(ref['path'])==ref['sha256']
actual18=read(OUT/'initial_owner_route_gate_independent_actual_review_001/report.json')
assert (actual18['closed_roots'],actual18['open_or_unknown_roots'],actual18['roots_at_most_100ms'])==(16,2,0)
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_030';receipt=HERE/'milestone_030.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. New unloading-policy actual96 independently verified96assessed/0unknown,all96H40/all5complete,all6complete16referencefamilies. Mechanism25 protects all5 against both familybest12 with2.3000000000000114 total-time gain; fixed-action evidence only. Actual18 gatev2 independently verified16closed2unknown,0under100ms,normal6pairs allstrictprotected(3improve/3equal). Complete-evidence optimization, actual-entry closure candidate, online information/model conformance and substantive all-day throughput policy are active. Separate saved bridge linearv3 fixed600 is running; previous failures remain. All3overallgoals unmet.'
state['working_tree_identity']='codex/g31-ics-v3-circulation at c3fba566; uncommitted local research. Production89c2935 and parent user PIBT hash preserved. Actual96 and18 campaigns closed; saved-only bridge linearv3 is running. No commit, push or external review send.'
active['unloading_native96_status']='93frozen sources/79pure; one actual96 whole265.7289843s within600. Independent0native/0predict saved audit44.8919301s within180,200entryexitpins equal,0replayerrors.96assessed/0unknown,all96H40/fivecomplete;old94remain andold2newassessed.34actualfresh pairs(B30/A4)allverified. Lasttwo actualcaptures9.24/9.26 delivered9.27 include realreceiverUNLOAD_COMPLETE9.22, no completion inferred from schedule. Historical14first-collection derivations retained(E4/P10).'
active['historical_native_comparison']='Latest fresh unloading96 hasall6complete16families. Mechanism full32best25 strictly protects all5 vs bothfamilybest12,gain2.3000000000000114. No_overlap full32/default00best58.711999999999996. Insufficient full32best24sum58.46099999999999 matched exactly bycomplete later-defaultbest24; no invented joint gain there. Old94/2 frozen. Newvector17route7to8 actuallyupdated9.28/entered9.29/ACK9.30 butreuse1/reuse2each+.4399999999999942vsoldfallback; retainnegativecandidate.95actualendpoints exacttoold,1different. Fixed finite comparisons notonlineoptimizer proof.'
active['unloading_summary_field_clarification']='Originalterminal_summary remaining_unknown_reasons counted alltransient failed reads,notremainingbranches. Separateclarified001 bindsoriginal:34failedattempts allfollowedbyverifiedfreshpair;remainingunknownbranches0. Originalunchanged. No retrospectiveclassification ofold94/2.'
active['initial_owner_gate_v2_actual']='141frozen sources/67compiled/130pure. Actual18 whole158.4650877s; independentcompleteendpoint/physical/RPC/gate/outbox53.934451s.16closed2initial_ack_drop3unknown,0/18<=100ms;closed595.2962to1161.8369ms.6normalpairsall5strict<=0,3improve/3equal.1240/1485rootobservationstepsskipped;22,610,412completeencodedrootbytes.8RPC worker15.4644to26.3145ms,caller23.7313to77.1066ms nested. Coldstartup736.368ms,fullsetup9318.8941ms,cleanup229.4658ms unamortized. Oldv3 comparison descriptive,notABBAcausal. Unknownroots942.6524/885.9688ms includeadditionalfullqueryproof;no costhidden.'
active['gate_v1_withheld']='Preparedv1 was withheld before native because PythonACKsemantic equality lost intermediate keyorder/intfloat/signedzero representation evenwhenfinalrestored. Newv2 body_is_new strictrepresentation flag separatefrom originalack_changedhandling;emptyreset/oldunconditionalassignment retained. Allv1sources139/readyremainhistorical,neverdispatch001.130pureincludesmiddlechange-restorationnegative.'
active['bridge_saved_audit_status']='Earlierlinear001closed1after92.0623104s;1024progressfilledbyperbootstraprowdecode stages,lastold005api000428decode_start,terminalserialize_bridge_prefix_order. Firsttracebacknotpersisted;logcapacitycausalmechanism source-supported,notactualfirstexceptionproof. Versionedprogressv2 ordinaryreadsaggregateevery256;full10305bootstrap+37270hash/replay+128reserve465/1024. Newdriverv3 stickyfirstfatal andexactfailureidentitysidecar,69pure,92source rootreview. Onefixed600saved-onlyattemptsession68905running,all37270+27218hash/orderedargs/policy/physical/28506/22guardsretained. Preserveproducer2400,prioraudit600,linear00192s,pure00160timeoutandunexecutedv2prepare.'
active['first_hop_entry_candidate']='SeparateactualEDGE_ENTERpredicate32pure andprivategateintegration177pure(old130+32+15),independentsourcecheckpassed. Exactaccepted027edge_exit_atrequiresrealmatchingcurrenttraversalentryreceipt;reserveedgealoneinsufficient. Sourceprefix[0]canbeobservedbeforeexit;originalpostexitoutputs/actualACK/completepostreadsame-time drain retained. Bothobserve/postdrainprivatecontractrebound,noimportedmutation;proofmarkerinsidechargedcompleteevidence. Noactualcampaignyet. Earlierclosurechangeslateradmissions/IDs;no unchangedtapeclaim andlogical1snotCPUgain.'
actions=[
 'Await one running fixed600 bridge linearv3 saved audit; review complete success or precise first-failure stage, preserveallpreviousfailures. Do not promote producer39/H before fullcheck.',
 'Develop practical existing22-tray original28506 business throughput policy from source/history with FIFO/storage/physical guards and normal protection. One-token21parked incumbent is narrow; no extra trays/arbitrary topology changes/assumed100percent completion.',
 'Optimize complete root evidence repeated Python walks while retaining every field, exactorderedtype/signedzero, strictdecode and allcosts. Source/pure first; newactual18 only after frozenreview.100ms/full32 goalsunchanged.',
 'Prepare separate actualentry closure integration campaign after177pure/source review; keep same18inputs/faults/fullHphysical audit. Earlierclosure maychangeIDs; no oldtape equality assumption. Do not mix evidencecodec candidate without separate evidence.',
 'Build actualdelivered-data context and predictor conformance for historical+unloading messagepolicy; offline96outcomes areverifier targets only,neverpolicyinputs. Then strongonline coordinate/plateau/pairrepair-LNS/finiteMPC same32domain/budget32 andlater<=4 withstrictdeploymentprotection.',
 'Keep threeoverallgoals open. No commit/push/externalmessage/GPTProsend; maintain evidence and failure ledger for later explicitreview request.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone030\n\n全面恢复持续有效。新实际96已独审全部可评估、六个完整16参照族；机制案例全五件非恶化、约2.3秒总时间改善。实际18独审16闭环/2未知，0个完整请求达到100ms。全天原流业务与强在线联合方法仍未达标，继续按下列入口推进。\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone030：实际96全部闭合，18请求仍未达100ms，全天审计修复继续

卸载跨采集窗口仅扩展原有一次fresh pair资格：不把scheduled unload end当完成事实。新实际96在265.7289843秒完成，93冻结源/79纯门；完整独审44.8919301秒、200入口出口pins相同、0重放错误。96assessed/0unknown，全96到H40且五件完成。最后两个B分支实际在9.24/9.26采集、9.27送达，A消息携带实际receiver UNLOAD_COMPLETE9.22；34补采(B30/A4)全部核验。六个16成员参照族齐全。mechanism25对两族best12仍全五件严格不恶化、总时间改善2.3000000000000114；no_overlap默认最优；insufficient最优24由later-default族完全匹配，不强造联合必要性。95行终态与旧94/2相同；vector17真实route更新9.28、9.29进入7→8、ACK9.30，但两reuse任务各比旧fallback慢约.44，负候选保留。旧94/2原件不升级。小summary旧字段误把全程未知读回叫remaining reasons，另存澄清版，剩余未知分支实际0。

Gate v1在准备完成后发现Python ACK equality丢失中间键序/类型/符号零变化，尚未执行即撤下派发；新v2将body_is_new严格表示变化与原ack_changed处理分开，保留原赋值/空reset与所有成本。新130纯/141源/67编译来源actual18全程158.4650877秒；独立完整端点、物理、RPC、gate与outbox核验53.934451秒。16closed/2drop3unknown，0/18完整100ms；closed595.2962–1161.8369ms。六正常对照五任务均不退化，三改善三持平；1240/1485步省重复根观察，22,610,412根证据bytes完整保留。8RPC worker15.4644–26.3145ms/caller23.7313–77.1066ms为嵌套区间；冷启动736.368ms、全setup9318.8941ms、cleanup229.4658ms不摊薄。旧轮对比仅描述，不当作ABBA因果。两个unknown的新完整queryproof有成本，942.6524/885.9688ms如实记录。

全天linear001在92.0623104秒失败：bootstrap每条API读写两进度行耗尽1024，最后old005/api000428开始；最终只留serialize_bridge_prefix_order，首个异常未记住，不能伪称已有其traceback。新进度核保留全部读取，只每256条聚合，完整规模计数465/1024；首个进度异常sticky，真实checker异常优先于随后清理故障，另存精确对象身份sidecar。纯001的60秒归档/合成Windows resolve超时与未执行v2包保留，新v3 69通过/92冻结源/根审后单次600 saved audit正在运行。原2400、600、92秒失败均不改；未先升级39/H证书。

首段真实入边候选另行完成32谓词负例及177集成纯门、独立窄审；依赖accepted027已发生EDGE_ENTER匹配当前traversal后才暴露的edge_exit_at。原ACK、实际同刻排空、后续物理证据全保留；两个root观察路径私有重绑，不改旧全局。它可以提前结束root并改变后续ID，不能继承gate的ID不变结论；尚未实际执行，也不能把逻辑时间提前一秒当CPU收益。接下来并行推进完整证据遍历优化、同信息在线预测一致性、实质多盘全天业务策略；三个总目标保持未完成。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 60. 全96有限反事实成立与完整证据计时仍失败\n\n卸载跨窗口通过原有一次补采得到真实终态回执，全96/六完整参照族独审成立；机制25约2.3改善维持严格五件保护，其他案例如实保留无联合增益和负候选。它不是在线算法优越性；强方法需新通信政策预测一致性。实际18gate保留全证据仍0/18达到100ms；源级少重复遍历与首段实际入边都是工程候选，非新solver贡献。原日志/ACK表示错误及修复证据保留，不删失败。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},
 'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),
 'overall_goal_achieved':False,'new_native_dispatched_here':0,'running_saved_audit_session':68905}
with receipt.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
