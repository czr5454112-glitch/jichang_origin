"""Preserve event-model correction and reviewed, unexecuted collection/request work."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE.parent;DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
pins={
 'live_obligation_event_revision_001/report.json':'47f57fdcd35bc1bed4b95800ec349e8d9944bba1a31a6e72f3110b445c73882b',
 'live_obligation_event_revision_independent_review_001.json':'7f4b759a8658da6c9cb26040f7641e1ea083fba9e4253d924896cb772dc9ef2c',
 'live_obligation_event_revision_001/method_selection_replay.json':'c1af14360340628ba1b80187497eee9681555d96371e545517e88768177cf45d',
 'live_obligation_event_revision_001/method_selection_replay_002.json':'69397db1ec16046cc33e3b5dd4223010cf9857a8b36d1909379f78a9770c31eb',
 'live_event_method_independent_review_002/review.json':'b998fba534e80434328273446d9b03125244300f55ae75a53e1ad6b564e06274',
 'live_obligation_lifecycle_v2_prepare_001/source_preparation.json':'385653f49050f896b25efa68dd1ef7883e742a732a43281e5124054ca79df673',
 'live_obligation_lifecycle_v2_prepare_001/root_source_review_001.json':'9134f44fb56a1986f6a3eee3f418a5117ee865203fe206218169c6f5d8bb5707',
 'initial_owner_route_source_prepare_002/plan.json':'73ecdfcc89124b89f23d76dec2a6bb1ddb4e8024c3b43671f0a2806862f90056',
 'initial_owner_route_source_prepare_002/root_source_review_001.json':'c944d169b3fca936b6d07ac26efd7f364f4a35165237055a1e950221f8ff291a',
}
for p,s in pins.items():assert sha(OUT/p)==s,p
event=read(OUT/'live_obligation_event_revision_001/report.json')
assert event['exact_assessed']==34 and event['exact_all96']==64 and event['both_native_error_windows_reproduced']
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
heartbeat=read(OUT/'original_cooperative_bridge_prepare_001/bridge/heartbeat.json')
backup=HERE/'before_milestone_024';receipt=HERE/'milestone_024.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');a=state['active_experiment']
state['current_stage']='Fully resumed. Native96 remains34assessed62unknown; new source-derived event model now matches all34 assessed exactly, without time offsets or protection epsilon. Corrected strict comparison removes old no_overlap protected gain; allfour methods58.712. Stable lifecycle v2 source51pure reviewed; one-fresh-pair collection implementation in progress. InitialownerA finite2 request source48pure/rootreview ready, actual harness being prepared. Originalbridge001 running under fixed2400s sharedbudget; delivered completions increased but no fullH/finalaudit yet. All3overall gates remain unmet.'
a['native_domain_event_model_status']='New public_live_obligation_event_projection_v2.py implements accepted027 create_leg outgoingbeacons, purgedservicecalendar rankingnotification, and recovery same_timestamp(abs<=1e-9) dispatchquantum. Exact physicaleventordering and strict perjob<= unchanged; no fittedoffset or nativeoutcome input.13pure plusfixed96pure predictions:34/34 formerlyassessed exactall5,64/96 overall exact(previous58); both8.649999999999995 wake/wait,8.65wake,8.651commit reproduced.6changed pure rows no_overlap00/04/08/12/28/29. Independent8sourcepins/192rawchecks confirms; not deploymentfullclosure, genericJIT/generationequivalence orheldoutmodelerrorbound. Old62nativeunknown remainunknown.'
a['revised_strong_method_model_status']='Saved revisedpure96 replay only,0newmodel/native:mechanismcoordinate60.061 vs pairrepair/MPC57.761 remains. no_overlapprevious57.71best nowreceiver+.001 vsincumbent, failsstrictprotection; all4methods58.712, both16familyrefsdefaultvector00. insufficientall58.461. Independent all12queryorders/all6families/480strictdeltas recomputed. Actualnative6families remainunknown. Firstreplay retainedinvalid becausecanonicalJSONkeyorder caused14exactfloatingaggregatemismatches; secondrestores uniquechronologicalcompletionorder(all5timesdistinct), exactstoredsumvalidated, no numericvalue/epsilonchange. Reviewerattempt1 schema-tag typo preserved.'
a['native_lifecycle_v2_status']='Newdomain_guard_v2/lifecycle_state_v2 source51pure/rootreview,0native/0predict/0recollection. Privateoldendpointbytecode/source/current/digest/ACKunion checks retained.192savedcollections tested:old126knownkept,30genuinecurrentchangesstillunknown;22/36oldtypedfailures nowconditionaldata,14stillstrictlyrejectelapsedknownservice. Potential52/96double-stage supplied-data support(16/22/14), notactualreclassification. Remaining14:4Eloadednode4 boundnow-.01,10Ploadednode10 boundnow-.03. CompletedE/Pneedactualdestinationreceipt/contract/sourceidentity;futurephasebound and conservativecapturestart preserved.'
a['native_fresh_collection_design_status']='Newsource/pure implementation authorized aftersavedwindow analysis:atmostoneNEWpair perphase aftertruecapturechange or knownphaseboundcrossing, never retimestamp/stitcholdcapture orpausephysics.40Bcandidatewindows Lservice_end-now~.06 permit fouractual.01messageadditions plus.01routewire with~.01slack;4Aemptycasesuseactualavailability/expiry39/notbefore7.84. Oldpeerreplywasphase-only once;newpolicy mustacceptmax2monotoneinvitationidentities. This isfeasibilityofdeclaredtimingonly, notactualsuccess. Areturnrecollectioncanchangephysicaltrajectory soeventv2normal-exchangepredictionsmaynotconform; no modelprotection claim.'
a['complete_native_request_status']='Initialownerroute sourceprepare002 plan73ec...,126sourcepins/81imagefiles,48pure/rootreview,0native/0actualworkerbenchmark. OriginalJSON00285sources unchanged. Actual027 commandresponse lacksowner_id; syntheticfixturewrongfield retainedin001,002bindsrealqueryowner+requestID,003adds pureentryclosure;prepare001wrongplanfilenamefailurepreserved. Fullnativeharness beingwritten toforceB@.11 beforeadvance,bothfixedcontinuationowners,actualrootbeforepub/freshview throughACK/actualfirsthop/drain/codec/outside-returntail,allcoldunamortized. NativeACKfaultschema mustbevalidated;2candidateslimitedprobe,notfull32solverorjointvalidity.'
state['next_actions']=[
 'Finish originalbridge001 atfixed2400budget; preserve fullorpartial tape,actualpending/terminalphysical facts and all28506denominator. Do not extrapolate heartbeat completions tofullH/ontime/100ms. No restart orsourceedit whilelive.',
 'Complete bounded one-fresh-pair source/pure policy and newaccepted027adapter; rootreview invitationidentity, replycaps, Lcurrentwindow, ACKunion andfuturemodelscope beforefixednativecomparison.',
 'Finish initialownerA actualharness withrealfixedB andcompletecold/rootaccounting; reviewsourceandfaultschema beforedispatch. Runperformance onlyafteroriginalbridge hasended.',
 'Keep corrected eventmodel and zeroepsilon strongcomparisons:oldno_overlapgainwithdrawn,mechanismknownpairrepair explains2.3gain; actualstrongnativefamiliesstillunknown.',
 'Record newfailures andsolutions,allsourceidentitiesandexactresumeentry. No commit,push,externalmessageorGPTProsendauthorized;threeoveralltargetsremainopen.'
];a['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone024\n\n全面恢复继续有效。原流bridge001正在共享2400秒预算内运行。新事件模型与已可评估34条实际轨迹逐件全等，但完整native仍34可评估/62未知；无重叠对照旧收益因真实+1ms已撤回。状态扩展51纯测试、有限双候选48纯测试已复核，补采策略和实际完整请求harness仍在实现，尚未新native执行。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n',encoding='utf8')
note='''

## milestone024：从源码修正1ms事件误差，撤回无重叠对照旧保护收益

accepted027源码链条明确：circulation_create_leg会向每个下游发初始beacon；beacon先按end<=now+1e-9清理服务日历，比较queue/incoming及仍在未来的calendar变化；resource recovery用same_timestamp(abs<=1e-9)决定是否增加max(minservice,dispatchheadway)，而主事件队列和同节点arbitration仍精确比较。旧Python模型漏前两条、recovery又只用==。独立新v2子类只补这三条，不改原生/旧模型/作业保护容差，不查native输出表。13边界测试通过，固定96纯回放全部留存：原34可评估轨迹五件时刻全等，96总64条全等（原58），旧62unknown不升级。两条8.649999999999995唤醒并等待→8.65再次唤醒→8.651实际进入链精确重现。独立审核8声明源码和192新旧原件哈希；仍非完整新部署闭包/通用JIT及calendar generation证明/留出误差界。

纯96强方法重算揭示真实结论变化：mechanism坐标60.061、pair/MPC57.761不变；no_overlap旧57.71方案receiver现在比incumbent晚约0.001，严格逐件保护失败，四方法最佳都58.712；insufficient四者58.461。实际native六参考家族仍unknown。第一次保存结果方法回放受JSON排序键改变求和顺序影响，14完整行被原精确aggregate检查拒绝，错误回放完整保留且不得引用；第二次按五个互异完成时刻恢复实际模型终态插入顺序，精确重现原completion_sum，不改变任何数值或逐件比较。独立检查12搜索顺序/6个16成员家族/全部逐件差值通过。独审自己第一次状态schema拼写错误也保留，不隐去失败。

新生命周期源门51纯测试（包括192实际保存collection）与root源码审完成：126旧known保持、30真实capture变化继续拒绝。36旧typed失败中22条件可表示、14仍拒绝，因为4个E/node4和10个P/node10已知service_end在now前.01/.03。数据层最多52/96两阶段同时支持（16/22/14），不是52条新的native实验。额外完成件只由准确destination-owned终态回执认定；服务、卸载、hold、空盘全部保留身份、已知界、起点<=unionfloor、下一界严格>now。补采计划最多每阶段一对新消息：40个B窗口有约.06余量，四个.01消息步骤+.01路由wire理论可容纳；4个A空盘用实际可用性与expiry/notbefore。旧peer只按phase答一次的限制必须在新有限协议中显式改为最多两个单调invitation。不能暂停物理或拼接旧快照；新增A补采可能改变实际返回时序，旧正常消息预测不能冒充新策略保护证据。

初始A双候选源包002封存126源码/81image、48纯测试、root复核；尚无native/实际worker性能。源码核查发现真实027 protocol_command没有owner_id，之前合成fixture要求该字段将导致永不闭合；旧纯001保留，修正为绑定真实查询owner=A与request_id，随后003纳入纯门自身源码闭包。prepare001错误计划文件名失败保留。实际harness正在实现，须明确B在.11且任何advance前提交、两端固定continuation、root从首次发布/采集前到外部return/ledger结束；全部冷启动与native接受成本单列不摊销。有限2候选是请求整合探针，不能替代完整32求解器、联合效果或两机100ms目标。

原图bridge001仍在固定2400秒共享预算执行，完成回执已超过旧8并开始桥接，但全H和独立审计尚未闭合。不得根据中途下界推断按时率、全量成功或预算达标。短边多段实体占用历史文档重新核对，确认其15例参考早已完成，DD3/DD4几何/驱动/服务机械资料仍缺；不重复旧见证，不擅自把零容量开放。三个总目标仍未达标。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 54. 事件语义更正收紧结论，有限模型改善仍非新颖性\n\n补下游beacon/日历通知/恢复时间规则后34已assessed全部逐件精确；no_overlap旧保护收益撤回，四方法58.712。主机制pairrepair已解释57.761vs60.061，未出现相同信息/候选/预算下实质方法优势。新生命周期与一次补采提高可验证覆盖的工作尚无新native，有限双候选不能替代完整求解目标。\n')
with receipt.open('x',encoding='utf8') as f:json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'bridge_heartbeat_observed':{k:heartbeat[k] for k in ('physical_time','wall_seconds','delivered_actual_completed_count','bridge_requests_submitted')},'overall_goal_achieved':False,'new_native_dispatched_here':0},f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
