"""Record audited actual integration results, costs and unresolved residuals."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]; OUT=HERE.parent; DOC=ROOT/'docs/g31_ics_circulation'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
pins={
 'initial_owner_route_campaign_v3_prepare_001/campaign.json':'e5459ab579d76e65c76ee41b0a4bc5f06224f3be0796ace6636ec4d0a2f7b46d',
 'initial_owner_route_campaign_v3_prepare_001/verification.json':'a7b0872499909c31a7c89028c03c523500aa03ddc050276962f11c0a168236d3',
 'initial_owner_route_campaign_v3_prepare_001/external_application_wall.json':'2452e435633edf431209dc161fb5677d74a4ccecf5a2dfcfb16a69672756a18b',
 'initial_owner_route_v3_independent_actual_review_001/report.json':'6619c11ca5aca23cb7bb083a7198d5fd6b56e9b7697a5c700b12a93628e641a5',
 'live_obligation_recollection_failure_diagnosis_001/report.json':'96ebd34b19c249fd376e45f90251f8ec596829432f8fdcdb357c745776fdec0d',
 'live_obligation_recollection_native_v2_prepare_001/preregistered_protocol.json':'f0db13dfee5ba0329664137cbcb1ef1452dc18be785950423cc8a7b6e020f6f8',
 'live_obligation_recollection_native_v2_prepare_001/receipt.json':'9c74752264109f665e6e155f5ff38c2d844c28119c714f9fd4efbc4d9073d9c9',
 'live_obligation_recollection_native_v2_prepare_001/external_application_wall.json':'4013c717c98fe6fee9e5ffb086d27c23c80b0751b8dbdfca16d410d0cb5426ca',
 'live_obligation_recollection_native_v2_saved_review_001.json':'c21c9e90c92fb12ccf846fe2072f81c7b43531e969aa3ff031a8ea0d733e88af',
 'original_bridge_serialize_once_prepare_001/root_prelaunch_review_001.json':'031a075400954693def5ede92346dbd4a3678897bd4ec4c39609670ae34af78e',
 'bridge_serialize_tuple_boundary_review_001/review.json':'57cdb0f32c9c8082c157d807221f385a5df778e5a37b59ec5525b721f005d8c0',
 'initial_owner_v3_cost_figure_002/receipt.json':'889ad259721f2c7db967308bd7d5ed4403af5655bd0e3b76a9b19fe29534025b',
}
for path,digest in pins.items(): assert sha(OUT/path)==digest,path
initial=read(OUT/'initial_owner_route_v3_independent_actual_review_001/report.json')
assert initial['branches']==18 and initial['closed_roots']==16 and initial['roots_at_most_100ms']==0
native=read(OUT/'live_obligation_recollection_native_v2_prepare_001/receipt.json')
assert sum(v['assessed'] for v in native['comparisons']['cases'].values())==80
assert sum(v['unknown'] for v in native['comparisons']['cases'].values())==16
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_027';receipt=HERE/'milestone_027.json'
assert not backup.exists() and not receipt.exists();backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for n in names:(backup/n).write_bytes((DOC/n).read_bytes())
progress_path=HERE/'bridge_serialize_progress_at_m027.json'
progress=read(OUT/'original_bridge_serialize_once_prepare_001/bridge/heartbeat.json')
with progress_path.open('x',encoding='utf8') as f:json.dump({'recorded_utc':datetime.now(timezone.utc).isoformat(),
 'status':'running_heartbeat_lower_bound_only','heartbeat':progress,'fullH_or_final_audit_certified':False},f,ensure_ascii=False,indent=2)
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
state['current_stage']='Fully resumed. Initialowner v3 actual18 independently audited:16closed2initialACKdrop unknown,0/18<=100ms;8RPC fullbaseline+candidate,8strict nonregressing finite pairs and3normal improvements. Main recorded cost is full evidence construction/codec,not finite2 predictor. Fresh96-v2 actual independently audited80assessed16unknown,46freshpairs,32second inputs verified/14unknown;all96 fullH40/all5 physically complete but6reference families incomplete. Logging-only original026 full-day bridge running underunchanged2400 sharedbudget. New exact single-build evidence and fail-closed root observation gate under source/pure development. Overall3goals remain unmet.'
active['initial_owner_actual_v3']='Fresh18 external92.9546363s;130live/archive+67compiled,134pure and independent saved9.825s.16closed/2initial_ack_drop3unknown,0/18<=100ms.Closed root857.7709–3696.6162ms;8actualRPC/8fullbaseline/8additionalcandidate,normal3pairs improve and all8knownpairs exact5delta<=0;drop pair unknown. Baseline/candidate normal-delivery finite model is not a fault-domain certificate. Startup744.466ms/close+cleanup205.942ms retained,wholecampaign never divided. Originalactual002failure andv2preparation remain untouched.'
active['initial_owner_cost_diagnosis']='Six disjoint measured-boundary intervals add exactly to each warm root. Workercompute14.5391–23.0852ms andRPC22.6095–35.2192ms are nested,not additive or isolated nativeCPU. Closed evidence body456.25–2139.79ms plus returnledger/codec tail196.94–965.05ms;151–610events/1.5–6.1MB. Repeated deepcopy/normalize/encode/decode dominates. Exact fullfield/order/alias-safe onebuild evidence variant and full18/72mockABBA shared240 preparation authorized,not yet executed. TypedC++kernel kept design-only pending larger caller cost repair. Newfigure002 usesimmutable18data;001fontwarning artifact retained.'
active['native_fresh96_v2_actual001']='Same96/600 actualexternal310.8429368s,worker309.5991439s;85runtime sources andold82unchanged. Independent all96 endpoint/physical replay passed;all96H40/all5physicalcomplete.80assessed16unknown (30/2,22/10,28/4),all6complete16refsunknown andallfull32null. Old52 remain52;old44 yield28newassessed16unknown.46actualfreshpairs (B42/A4),32secondinputs verified14unknown. No old row upgraded or old message-model protection reused. Residualsource diagnosis in progress:14clamped-now ready metadata,2unloading bound crossed;do not add retries/epsilon/wire relaxation.'
active['root_observation_gate_status']='Independent pure42 prototype only; original global .05 tick/A-Bcursor/owner activations/client.root admission IDs retained. Root duplicate observations may be skipped only if actual complete all-owner notification chain, noAchange/no new protocol call/no dueAretry; all unknown paths fallback. Real saved18 response/outbox shape replay and source-bound integration still required. Separatefirsthop observed_entry vs precondition requiringprefixlen2 under source review;no physical wait credited as compute improvement.'
active['original_bridge_serialize_once_status']='Root-reviewed82sources93pure,67compiled026,independenttupleboundaryreview;actualsession74892 running under2400 sharedbudget,onefresh28506/22/H86400 trial plus fullsaved/prefixaudit. Heartbeat snapshot recorded separately,notfullH evidence. No policy/tick/field/physical/budget changes;max39completion bound notalloffered success.'
state['next_actions']=[
 'Keep original bridge running to its fixed2400 bound; retain anypartial/failure and require full saved policy/physical plus old27218prefix audit before fullH finite conclusion.',
 'Freeze/review exact one-build root evidence module and full18 mockABBA72/240 package. All events/fields/order/floatbits/alias/strictcodec and body/outside costs retained. Do not benchmark during bridge if claiming an isolated comparison.',
 'Complete root observation gate real-data/source-chain validation; keep background .05 scheduling and IDs. Audit firsthop entry proof separately without weakening actual execution evidence.',
 'Finish source-bound16unknown diagnosis and only then propose truthful state-domain or metadata support under exact service/current/ACK guards. Keep6families incomplete and no nativeoracle policy input.',
 'Full32 complete-request100ms,originalall-day operationaltarget and same-information/budget joint-method effectiveness remain open. No commit,push,externalmessage orGPTProsend authorized.'
]
active['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone027\n\n全面恢复继续有效。完整请求真实18分支可审计：16闭合/2未知，0达到100ms；三个正常案例逐件不恶化且有改善，但只是有限两候选。重复证据构造与编码为主要已测成本。新补采96达到80可审计/16未知，完整参照族仍不足。原流日志优化完整试验正在原2400秒预算内运行。三个总目标均未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n',encoding='utf8')
note='''

## milestone027：实际18请求闭环、主要成本定位与补采80/16

initial_owner_route_campaign_v3_prepare_001真实运行经130来源/67compiled/134pure/root审后在独占实验窗口完成，外Python92.9546363秒。独立保存审计重读全部18、8RPC、真实端点/完整物理与READY/CLOSED：16closed、2初始drop3 unknown_collection，0/18在100ms内；closed857.7709–3696.6162ms。8完整baseline+8额外candidate均真实调用，8可比pair严格五件delta<=0，其中正常block0_load2、block1_load0、block1_load2出现改善，其余已知pair相等；初始drop pair未知。有限两候选与正常模型不能冒充full32、联合新颖性或未来故障保护证书。启动744.466ms、关闭清理205.942ms、整轮及保存审计成本独立保留，不摊薄。

独立成本分解用六个互不重叠记录边界精确加回每个root，未扣除共享/物理工作。实际workercompute14.5391–23.0852ms，RPC caller22.6095–35.2192ms，均是嵌套墙钟不是独占CPU。主要成本在151–610个事件、1.5–6.1MB证据的重复处理：evidence body456.25–2139.79ms，outside ledger/codec tail196.94–965.05ms。优先实现新独立完整证据一次fresh normalize/encode和去冗余deepcopy，保留严格roundtrip/字段顺序/标量/alias独立；用全部18实际内容做72次mock ABBA，240秒研究包预算不改变native600或request100ms标准。typed C++内核只保留设计，避免优化小头。另研究原后台.05保持的root观察门：完整cursor/通知、无A变化/无到期retry/无新call才跳无效双读，所有不明确fullfallback。原生真实形状和来源链还需集成验证。firsthop已有entry分支被prefix>=2前置条件挡住之疑点单独查证，不把少等物理时间当CPU收益。

live_obligation_recollection_native_v2_prepare_001修复受限node/edge tuple表示，经64pure/85源/root审后完整96实际完成，外310.8429368秒（与bridge功能试验并行，不作独占速度比）。独立96端点/每次补采/有界reply/物理审计全部通过，96均H40五件物理完成。80assessed/16unknown，分case30/2、22/10、28/4；旧52保留52，旧44失败中新运行28可审计、16仍未知。46实际freshpairs=B42/A4，32个二次输入verified、14未知。6完整16参照族仍全部unknown、full32均null，不能据此声称强参照收益。原v1实际zero补采/52-44和旧native96的34-62不改。剩余14疑似task_service_end无剩余interval时clamp到capture now但标已知服务界；另2 unloading界跨采集。继续定位具体tray/phase/真实receipt，不新增retry、不改wire/窗口、不加epsilon。

原流serialize-once bridge已在原2400共享预算内启动；82来源、93pure、根审及独立tuple边界源审完成。仅日志实现变化，策略/10秒节拍/28506/22/H86400/39-78-100和026物理不变，完整保存回放与旧27218前缀比较仍计预算。运行心跳只是下界，暂不宣称全天或达标。成本图initial_owner_v3_cost_figure_002从独立18报告生成并视觉检查；001字体缺失警告版本保留，002修正字体，没有新native/model测量。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 57. 实际有限请求收益与完整成本仍严格区分\n\n真实18中三正常有限pair改善、八已知pair逐件不恶化，但0/18达100ms。完整证据重复处理是工程瓶颈，不是方法新颖性。补采新96为80/16，六参照族全未知；实际46fresh不能替代全族或同信息强方法验证。原流新日志方案仍在运行。所有整体目标继续开放。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'running_bridge_snapshot_sha256':sha(progress_path),
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'new_native_dispatched_here':0}
with receipt.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt),'bridge_snapshot':{k:progress[k] for k in ('physical_time','wall_seconds','delivered_actual_completed_count')}}))
