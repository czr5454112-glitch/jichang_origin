"""Checkpoint validated improvements and negative results; no goal promotion."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
pins={
 'initial_owner_route_entry_campaign_prepare_001/campaign.json':'d37d3e0ea9378974a8a331b97c21be48d6dfe3bab9c18d08b686c68041bd0097',
 'initial_owner_route_entry_campaign_prepare_001/external_application_wall.json':'665be69f6ffdf7c673c887568feb9b1f9d7420fce9f5298a2fed6d4bd8179239',
 'initial_owner_route_entry_independent_actual_review_001/report.json':'4f552bfddaaaa8e9f981438e63e9a9a84f1971c45e6e7389d60ab27084325792',
 'initial_owner_route_entry_independent_actual_review_001/recovered_verification.json':'6643d1531c5679443b23b47a99f2459602825830ea23d62a81acb7f12de4bcea',
 'initial_owner_route_entry_independent_actual_review_001/external_application_wall.json':'ef156e642a888a4a48f4cda28239d73307f4aa1c0529b7dee2db1a9d8ca53803',
 'complete_root_evidence_codec_pair_prepare_001/report.json':'072226f85bf988d78aa42c2a622ffb52272541513cba6a15e5afa43f2fcd0605',
 'complete_root_evidence_codec_pair_prepare_001/external_application_wall.json':'554ce696b983bff406c2588da85eb4fb0c8f2158ee04e706d09d9eaf1dc87b01',
 'complete_root_evidence_codec_independent_actual_review_001/report.json':'1ba8d09cffa0ca7c81407e4c6eadc8d18d9783942eadc4a097215f3b98415304',
 'complete_root_evidence_codec_independent_actual_review_001/external_application_wall.json':'59a66ea08a9b1f2084c40e2d9d5a4a3f9fc75daa6ab05f7bc5fbbd5e013537ee',
 'bridge_saved_linear_v3_terminal_review_001/report.json':'14ec8b97fdb7382f9b9f367529342c7fa023b69ad83a11a41121650e1fe5e922',
 'initial_entry_codec_integration_pure_001/receipt.json':'f4683662727ac391f6354452749b8779da38299cfe84b2dde7a373a1f3f8841c',
 'initial_entry_codec_integration_independent_source_review_001.json':'2022446916c907de180013db8a7d6e30e021db38acd47599b314712436991447',
 'completion_baton_source_design_001/design.json':'07d9652c71e4a0e5f460848f8d54ecf771f3b54d050f57b6490b27617bd1141f',
 'completion_baton_source_design_001/source_receipt_v2.json':'2d26b33e6d85ad5fcbf326b78c82c97636cc11dad8197701211a198b29c9e1fd',
 'bridge_saved_kernel_cost_prepare_001/plan.json':'0f69d7b25e750a73134506dca70c54a40d3d894c719a4a6ba9075d647a371fbc',
 'live_communication_conformance_prepare_002/plan.json':'029d5c97114651e348a2b66a4c3509e5d4bd10f5bbdd576cf738620100c2d08f',
 'live_communication_source_boundary_review_002.json':'f9ba8f42bf29f193ce3daf05112f362ca5ef9e90c39290ad13b3dd5c7df6dafc',
}
for path,digest in pins.items():assert sha(OUT/path)==digest,path
entry=read(OUT/'initial_owner_route_entry_independent_actual_review_001/report.json')
codec=read(OUT/'complete_root_evidence_codec_independent_actual_review_001/report.json')
assert (entry['closed_roots'],entry['open_or_unknown_roots'],entry['roots_at_most_100ms'])==(16,2,0)
assert entry['normal_pairs']=={'count':6,'strict_nonregression_count':6,'unknown_count':0}
normal=[v for k,v in entry['pairs'].items() if k.startswith('normal/')]
assert sum(any(delta<0 for delta in p['per_job_delta'].values()) for p in normal)==1
assert codec['saved_calls']==72 and codec['negative_or_equal_root_medians']==[]
assert codec['mock_samples_at_most_100ms']=={'A':0,'B':0}
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_031';receipt=HERE/'milestone_031.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. All3 overall goals remain unmet. Fresh unloading96 is independently96assessed/0unknown/all6 reference families, fixed mechanism gain only. Complete evidence codec ABBA72 independently exact and median32.60014percent faster, still0under100 and mock only. Entry actual18 producer failed in final saved-verifier globals; separate repaired full audit passed16closed2unknown/normal6protected but only1improve5equal,0under100. Bridge saved v3 timed out600 during policy replay. Communication conformance002 fixed96 is dispatched; substantive baton design and bounded bridge kernel diagnostic are prepared, not native-validated.'
state['working_tree_identity']='codex/g31-ics-v3-circulation at c3fba566; uncommitted local research. Production89c2935 and parent user PIBT preserved. No commit/push/externalmessage/GPTProsend. Root owns all dispatched jobs.'
active['bridge_saved_audit_status']='linearv3 exited1 hardtimeout whole600.2173738s;271progressrecords, last completed policy replay checkpoint18688 of37270, not exact final inflight call. Old prefix required27218 remains incomplete. All92live/archive sources unchanged. Decode/raw21.364s, oldsource/reference checks18.242s plus duplicated23.776s, full newrow hash18.962s; replay is dominant unclosed phase. Original fullH39 producer remains partial evidence. No blind600rerun or budget increase. New fixed old/newtail8 kernel ABBA diagnostic prepared79sources/39pure/120whole budget,0native/policy, not yet dispatched.'
active['first_hop_entry_candidate']='Separate actual18 executed allraw then final saved verification failed NameError Path from omitted inherited globals. Original exit1/no receipt/no verification/no recorded producer import-exit proof stay. Source regression186 passed but had not executed verify_saved or recursively checked LOAD_GLOBAL; lesson applies to all private clones. Versioned verifier v2 keeps original9function code/closures and restores defining globals;12pure passed. Separate full saved audit53.422411s passed allendpoint/physical/RPC/gate/outbox, original151/67 preserved.16closed2unknown; closed462.6283to1200.4956ms,0under100.1007of1196rootsteps skipped,18,966,296completebytes. Six normal5jobstrictprotected:1improved5equal, not earlier gate3improved. Earlier physical observed_entry at4.171 vsoldexit5.171 verified; logical clock difference is not CPU gain.'
active['entry_lost_gains_diagnosis']='normal/block0_load1 andblock1_load0 budget_two both RPCselected prefer_2 eligible but original decision_return_overrun_default_incumbent triggered. Worker21.2393/25.8999ms andcaller33.8689/40.2674ms. block0_load1 admissionthroughcollection28.4505ms plus collectionthroughfinalcheck64.5614ms exceed original60ms decision cutoff. Preserve negative/default samples; optimize predecision copies/guards instead of loosening deadlines. Separate rounds cannot establish causal timing gain.'
active['complete_evidence_codec_status']='Codec68pure+harness18,135frozen sources; ABBA72 across all18gate002 roots including2unknown,36perarm,whole58.5363275s. Independent unchanged full72 readback13.8726802s passed ordered/type/floatbits/fullquery proof/clocks/all135entryexit sources. Amedian330.84935ms/B222.992ms(-32.60013961percent), sum-29.64275816percent;all18rootmedianslower, eachsample retained,0of36eitherarm<=100. Retains original normalize/strictdecode, eliminates redundant encoder tree walk and replaces Python exact-tree with strictUTF8 Cjson reencode equality on proven domain; full proof/hash/ledger/publication stillcharged. No native request100ms proof.'
active['entry_codec_composition']='New private composition source7pure plus independent narrowreview passed, original151/codec135current/archive unchanged. Actualentry marker/fulloutbox proof before normalize; strict decode/reencode before evidence returns inside complete root; original collection/observe/drain/finalvalidate/nativechain retained. New actual18 package being prepared only, no native dispatch yet; correct verifier namespace, recursiveLOAD_GLOBAL and execution-smoke required.'
active['original_stream_baton_status']='Completion baton uses actual UNLOAD plus current empty/HOLD facts, consumes once, max1 loaded work and nearest legal local empty for same actual peer FIFO head; bridge permit limited to completed original tray. Source/abstract25pure design only. All11 first unreachable loader heads needStorage53; crossing one each exposes23additional reachable jobs,allalsoStorage53,0direct. No accepted026 job cancel/defer/goal-edit permission;cancel_transferonlyuncommittedempty,R1false. CommonStorage outbound head blocks normal successful processing whileheadretained. Existing max_decisions_exceeded fail_bag+queue.erase and horizon failure are real exceptions, leaving loaded resources; never claim unconditionalpermanentqueue or universal39 upperbound. Original39 is conditional safe-prefix bound. Design firstfinalizer Windowsnestedpath failure preserved, v2flat archive repair only.'
active['communication_model_status']='New delivered-data context/projected capture/communication model candidates; old93frozen unchanged.38pure plus10driver tests (recursiveLOAD_GLOBAL, deliberatemissingglobal, fullgeneratedrunone-tickfakeengine smoke andfuturefactrejection). No native authority from supplied/projecteddata. Original prepare001child-only180 retained unexecuted. Versioned00296source, full180-parentelapsed-1 sharedbudget, all96rawentryexit pins, dispatched session90691 for3x32 conformance. Actualfuture endpoints/completions are onlyverifier targets; ownerA initial delivereddata anddeclaredaction onlyenterpredict. Retrospective regression, notheldout or online superiority. Full outcomes pending at this checkpoint.'
actions=[
 'Read the terminal status and all96 first differences of communication conformance002; preserve unknowns, fix source-grounded causal event behavior in new versions, never fit future outcome clocks or weaken exact comparisons. Then same-information strong online methods.',
 'Prepare/review separate entry+completecodec actual18 package from corrected verifier, including original full checks and frozen evidence. Dispatch only after source/pure/independent review and an exclusive performance window. All100ms/full32 requirements unchanged.',
 'Diagnose the two observed decision-cutoff defaults and optimize predecision duplicate copies/validation as well as final publication; retain original60ms cutoff and complete100ms deadline, failed attempts and cold costs.',
 'Review and dispatch one fixed120 tail8 bridge kernel diagnostic; compare original C JSON vs recursive equality and safe copy cost without native/policy rerun. Only evidence-backed versioned audit optimization can justify another full37270/28506 audit.',
 'Advance source-valid completion baton and original Storage53 bottleneck feasibility. Same28506 denominator/22trays/FIFO/normal protections; distinguish natural existing failure semantics from successful business recovery. No arbitrary graph permissions or success by dropping jobs.',
 'Keep all3goals open and maintain exact failure/solution evidence for a later explicit GPTPro review request. No commit/push/external send.'
]
state['next_actions']=actions;active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone031\n\n全面恢复持续有效。完整证据优化72次对照及独审通过，中位耗时下降32.60%，仍不是100ms达标。actual entry18另行恢复独审通过，但原生产失败保留，只有1正常改善/5持平。全天完整审计仍超时，联合在线方法待通信预测一致性；三个总目标均未完成。\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(actions))+'\n',encoding='utf8')
note='''

## milestone031：完整证据优化成立；失败恢复、截止时间回退及全天障碍保留

完整证据codec以gate002的全18根（含2未知）做固定ABBA72，每臂36，全应用58.5363275秒。独立保存核验13.8726802秒通过全部字段、顺序/类型/浮点位、queryproof、时钟及135源入口出口绑定。中位330.84935→222.992ms，降32.60014%；总和降29.64276%，18组中位均改善，但双方均0/36低于100ms。这是完整证据处理mock，不能当实际完整请求证书。保留原normalize与strictdecode，只去冗余树遍历并以严格UTF8 Cjson重编码等价检查代替Python递归比较，所有哈希/ledger/return成本留在根内。

首入边actual18的151源/186纯门已运行，全应用107.4921913秒后exit1：所有18raw保存，但原最终verify_saved因私有namespace缺Path失败。原无receipt/verification及无生产import-exit记录保持，不补造。根审和独审原先只验指针，没执行verify_saved/递归LOAD_GLOBAL，教训明确保留。新v2修复只补定义模块globals，原9函数code/closure不动，12纯门通过；独立180界完整保存核验用53.422411秒通过18端点/物理/RPC/gate/outbox。16closed、2未知、0达100ms；closed462.6283–1200.4956ms；1007/1196省根观察，完整18,966,296bytes。六正常对照五件均非退化，但仅一改善、五持平。两组旧收益消失不是预测未选：RPC仍选prefer_2且eligible，却触发decision_return_overrun_default_incumbent。block0_load1 collection前28.4505ms加后续至finalcheck64.5614ms超过原60ms cutoff；另组caller40.2674ms也回退。保留原deadline与这些负结果，继续优化决策前开销。物理入边4.171替代旧等退出5.171已证实，逻辑提前不扣CPU墙钟。新entry+codec私有组合7纯门/独审窄检通过，尚无新actual集成结果。

桥保存linearv3的单600界仍超时（全应用600.2173738秒），271条日志足够，最后完成检查点18688，只是下界，不冒称精确最后在途调用。所有92源未改，完整37270/旧27218前缀核验未闭合；原producer39/H仍不可升级全天证书。实际大头在policy replay，不再盲目延时。另准备固定旧/新tail8共16gzip的120秒kernel ABBA：比较Python递归与原Cjson、deepcopy与限定decoded-tree JSON复制，79源/39纯门，未执行，无native/policy。所有旧失败继续保留。

全天业务completion baton只在真实卸载+当前empty/HOLD、原FIFO头及一次使用条件下换用合规本地空盘，保持max1loaded；25抽象纯门通过，不是实际改善证据。静态原图：11个第一不可达loader头全需Storage53；各跨过一个坏头后新增23可达任务也全需Storage53。原026没有job cancel/defer/goal-edit命令，cancel_transfer仅未提交empty且R1false，不能凭新权限清头。共同Storage53出库头阻塞结论仅限未失败/未终止且保持该头的正常执行段；max_decisions_exceeded原生fail_bag+erase及horizon失败是真实例外，会留下载荷资源，不能写成无条件永久阻塞或用失败当业务成功。39仍是狭义safe-prefix条件界，非全系统上限。

通信预测新候选保留原实际93源；38纯门加10个driver门（完整动态run假engine单tick、递归global缺失反例、未来事实拒绝）通过。原child-only180的prepare001保持未执行，002改成BOOT起算共享180并哈希全部96原raw入口出口；根审后正在跑首次固定3×32。模型只收一owner初始实际已送达端点和declared action，未来实际终态仅在预测后用于比较；条件投影消息不获native authority。即使exit0也不表示96一致性通过，未知必须完整保存。三个总目标均继续开放。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as stream:stream.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as stream:stream.write('\n\n## 61. 全证据C编码收益与决策截止回退需分开验收\n\n完整18根ABBA72与独立全检查支持codec工程优化（median -32.60%），尚0达到100ms。首入边actual18独立恢复核验仅1正常改善，2组旧收益因60ms决策回退丢失；不能隐藏默认/未知或以物理钟提前当CPU收益。原NameError生产失败与审计超时均保留。通信一致性和原流Storage53机制仍是后续研究条件，source/pure不等于算法有效性或全天业务验收。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},
 'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),
 'overall_goal_achieved':False,'native_dispatched_here':0,'conformance_session_at_checkpoint':90691}
with receipt.open('x',encoding='utf8') as stream:json.dump(record,stream,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
