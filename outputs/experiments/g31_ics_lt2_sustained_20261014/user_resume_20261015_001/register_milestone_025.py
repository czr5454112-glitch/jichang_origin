"""Record the bounded bridge timeout and reviewed source-only recollection."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]; OUT=HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
pins={
 'bridge001_terminal_partial_review_001/review.json':'0bd6bf3faf488b1fb0e488c6bf2c7f31d1c1e3419d707461bfe6df0bc4c3cbc2',
 'bridge_live_cost_source_diagnosis_001/report.json':'b0398d4351bcda56ab5b42a993e7f891267dde2b86bc8bd9bb634b49dcffc242',
 'original_cooperative_bridge_prepare_001/external_application_wall.json':'341218e11f25ae4bce6d6a1714bb4df028b4d25e3b8fab5678ee22fa6ea073d3',
 'live_obligation_recollection_source_prepare_001/source_preparation.json':'31b9884de31f4c55eddc18525adc0761f98fa70cedf40bb0a98add80cb7b47f7',
 'live_obligation_recollection_source_prepare_001/root_source_review_001.json':'df8b24aa4193b5bcb785df476c9a7219af0ef128753c56f17fa2f1801252f132',
}
for path,digest in pins.items():assert sha(OUT/path)==digest,path
terminal=read(OUT/'bridge001_terminal_partial_review_001/review.json')
assert terminal['status']=='verified_hard_timeout_partial_evidence_only'
assert terminal['manifest_complete_rows']==27218
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_025';receipt=HERE/'milestone_025.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. Originalbridge001 hit fixed2400s owned budget, external2400.2173s, last complete advanceH41700;26delivered completions lowerbound only, nofullH orphysicalaudit. Preserve27218manifestedAPI andoneunmanifestedtruncatedrow. Source-derived event revision retains34exact assessed/62actualunknown. One-fresh-pair source51pure and81source independentrootreview passed; new96package beingprepared, no native dispatch yet. Complete-request actual harness and lossless tape optimization under source/pure development. All3overall gates remain unmet.'
active['original_bridge_001_terminal_status']='unknown_shared_budget_overrun. Fixed2400s ownedJob hard timeout, wholePython2400.2173068. LastheartbeatH41690/wall2390.2179982/26deliveredactualcompletionfacts/54physical/32postparking/5bridge submitted;lastcompleteadvanceH41700.27218complete manifest rows, sameAPIclockprefix, allreferencedfilesexist,last8hasheddecoded. Next027218.json.gz62845bytes truncatedEOF, unmanifested retained. No raw_final,assessment,fulljobstatesorverifier. Fullmanifestcontentsnotallrehashed/replayed.26isheartbeatlowerbound, neitherthroughputatH86400norontime/protection/capclosure. No budgetincrease orsamepackage restart.'
active['original_bridge_cost_diagnosis']='Saved last500 API clock rows span90.15s:planning_snapshots_v2 complete native+canonicalize+gzip/write/hash63.41s/130calls (~70.3%). Endpointreturnsone latestpeerbody containingreleasedwaitingcontracts; bothowners re-render every10s. CurrentTape result JSONdumps-loads thenjsondump andhash duplicatework. Newseparate losslessserialize-once source/pure beingprepared; exactdecodedrawfields/argsbeforecall/resultbeforecaller/exception/finally/manifest required. No policycadence/cache/fullfieldremoval and no currentbinary changes authorized.'
active['native_fresh_collection_design_status']='StageB sourceprepare00131b988...;81live/archive pins preserveold75+StageA3+newB3,51purepassed androotreviewdf8b24.... Failedreadsealbindsnative027session/time/content. Maxonefreshpairperphase andtwoactualmonotonepeerinvitations. SameoriginaluncommittedL, exactcurrentphysicalactions, terminalACKunion and strictknownservice/wirewindow.44savedwindows conditionalonly. Newseparate96runner/launcher source/preparation authorized withcommonpolicy/fullH40/fivejobs/600ownedbudget, success+exceptioncollectionattempts. No newnative executed; old34/62notpromoted,normal-exchangepredictornotcertifiedforthisnewmessageschedule.'
state['next_actions']=[
 'Finish and review losslessserialize-onceTape pure evidence; freeze a bounded functional/cost comparison beforeanotherfullbridge. Preserveallrawfields and2400fullapplicationbudget; originalshortlinkcapacity/FIFO untouched.',
 'Prepare/review separatefresh96 nativecampaign using onefreshpair policy, fullsourceclosure andallattempts; immutableold96 stays34assessed62unknown. Dispatchonlyafterrootprelaunchreview.',
 'Finish/review initialownerA actualcomplete-request harness; retainfinalfreshendpoints, realB@.11 andbothcontinuations, actualACK+firsthop+drain+outside-returncost. Onlyrealconfiguredfaults. Benchmarkwithoutconcurrentnativebridge/domain workloads.',
 'Continue towardfull32complete100ms andstrictsameinformation/budgetjointmethodeffectiveness; finite2requestprobeandretrospectivemodelmatchesdonotmeetthosegoals.',
 'Retainallnegativeandpartialresults andregistrationfailures. No commit,push,externalmessageorGPTProsendauthorized.'
]
active['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone025\n\n全面恢复继续有效。原流bridge001在固定2400秒预算超时；末次完整advance到H41700，26件已送达完成仅为下界，没有全天或完整审计。不得重启同包或延长预算掩盖失败。新补采源包81份源码、51纯测试和root审完成，新96执行包正在准备。完整请求实际harness和无损序列化优化仍在源/纯验证。三个总目标均未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n',encoding='utf8')
note='''

## milestone025：原流2400秒预算失败完整保留，一次补采源审通过

original_cooperative_bridge_prepare_001按冻结预算结束：外层whole Python2400.2173068秒，owned Job hard timeout。末心跳H41690收到26件实际完成事实，54物理请求/32停车后空盘请求/5桥接请求已提交；独立尾部核验找到最后完整advance到H41700。均不是H86400全天结论，提交数也不能当作实际到达数。27218条manifest完整且换行，API clocks同前缀，全部引用文件存在，最后8条逐个hash/解压；下一027218.json.gz为62845字节未入manifest的截断gzip，原样保留。未对所有27k文件重新hash或全策略回放。无raw_final/assessment/全量作业终态/完整verifier，原28506总分母不变，按unknown_shared_budget_overrun记录。不延长2400秒、不在同包重启、不凭26下界外推按时率或吞吐成功。

最后500个API成本记录约90.15秒，其中planning_snapshots_v2全调用（原生、canonicalize、gzip、写盘、hash）约63.41秒/130次，约70.3%。它每次返回一条最新peer消息，但payload含全部已释放待处理合同；当前Tape对结果先dumps-loads，再dump保存，存在重复编解码。新独立serialize-once模块正在准备，要求完整解码行、参数调用前快照、结果返回前保存、异常/finally/ordinal/manifest不变。此诊断不是native单独耗时或100ms证明。不会凭最近notification mask跳过可能需要的reply/cap处理，不改10秒策略节拍或删除大字段。

一次补采StageB源包冻结81 live/archive，旧75与StageA3保持，新adapter/policy/tests共3；51纯测试和root源码复核通过。实际失败读取seal绑定session/time/content，旧JSON无法授予动作权限；每阶段最多一对新消息，peer最多两个不同且单调实际invitation，保持原L身份/动作全集/ACK union/已知服务窗口严格界。44个保存窗口只证明理论允许尝试，尚无新native成功。授权准备独立96固定分支执行包：私有namespace、success和exception全attempt导出、fullH40/fivejobs、600秒共同owned预算及entry/exit接受和审计。新消息时序可能改变物理轨迹，不能借旧正常消息模型冒充保护。原96的34assessed/62unknown保持。root审第一次误读schema键archive在写报告前失败，原脚本和失败说明保留，随后按真实source_archive/source_sha256复核通过，不涉及native或模型。

完整请求实际harness正在准备18个固定分支：六原case各default/budget2，再首case三种实际fault各两臂。现有native owner outage只挡wire/execution，不能宣称route-only ACKdrop；drop_ack_packets全局配置也影响初始采集。由于实际native adapter要求精确session类型，使用明确的原始初始/最终端点、immutable传输记录、native边界及fullphysical记录，不伪称完整每API拦截tape。root时钟仍包含全部读取。有限2候选只是完整请求集成探针，不降低完整32候选100ms、原流全天、联合方法实效要求。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 55. Bridge增加中途完成但全天预算失败，协议补采仍待实际验证\n\nBridge001在2400秒结束于H41700，26完成事实下界不构成全天收益或联合保护。无损日志编解码优化属于执行成本修复，不是方法新颖性。一次补采81源/51纯/root审允许新固定96验证，原34/62不重分类。三个总目标继续开放。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'new_native_dispatched_here':0}
with receipt.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
