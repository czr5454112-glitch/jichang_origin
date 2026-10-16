"""Register independently bound finite results without promoting open goals."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DOC = ROOT/'docs/g31_ics_circulation'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
pins = {
 'original_low_wip_cap_relay_actual_review_001.json': '9b30bdc7abb24e65e4ad4816653f2835e4259d1b882145f517db357cc450e69e',
 'full2x_endpoint_diagnostic_002/report.json': 'f5461811fed8fc464d933d1484d01b17a6e404651a8d4bf580ccd6fbabb3839d',
 'preference_quiet_profile_001/diagnosis.json': '948814b6cf0e7a08bd64ef58678f7ecdfeda5658fe2be38ab480cb25040388bb',
 'preference_protection_cut_summary_001.json': '73db0f164f243ee0b384611316641fadb8ee1349a0562b7bf06732179ab759d6',
 'preference_protection_cut_independent_source_review_001.json': 'c28c13c1f85b5ff4fbc63862a27b377d7ced0c4403bca1e7d48c61c965d311c8',
 'deferred_tape_cost_001/findings.json': '350548563611422292e3d8918d0831f23ee314417bb752112628abf96696b08c',
 'joint_protection_mechanism_design_001.json': '4da7ab2ec3e337dd56063f6587abb34411d5ac05e94a6084af90665e3eb651a4',
}
for name,digest in pins.items(): assert sha(OUT/name) == digest, name
census_path = OUT/'pending_ack_notification_census_001/report.json'
census = read(census_path)
assert census['status'] == 'completed_read_only_census' and census['source_changed'] == []
assert census['new_native_executions'] == 0 and census['physics_or_shared_cost_subtracted_ns'] == 0
pins[str(census_path.relative_to(OUT)).replace('\\','/')] = sha(census_path)
cap = read(OUT/'original_low_wip_cap_relay_actual_review_001.json')
assert (cap['offered'],cap['completed'],cap['completed_on_time'],cap['unfinished']) == (28506,8,3,28498)
assert cap['strict_horizon_deadline_violations'] == 28503
assert cap['whole_application_campaign_wall_seconds'] < 2400
assert cap['strict_protection'] == 'unknown_unfinished_offered_jobs'
endpoint = read(OUT/'full2x_endpoint_diagnostic_002/report.json')
assert endpoint['completed_business_jobs'] == 0 and not endpoint['deadlock_certified']
assert not endpoint['current_receiving_dependency_cycle_found']
cut = read(OUT/'preference_protection_cut_summary_001.json')
assert cut['conditional_prefix_rejections'] == 93 and cut['nonpruned_full_outputs_exact'] == 99
parent = ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup, receipt = HERE/'before_milestone_018', HERE/'milestone_018.json'
assert not backup.exists() and not receipt.exists()
backup.mkdir()
names = ('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names: (backup/name).write_bytes((DOC/name).read_bytes())
state = read(DOC/'RESEARCH_STATE.json')
state['current_stage'] = 'User fully resumed. Original caprelay actual+saved verification closed: H86400/all28506,8 completed/3 on time,28498 unfinished, protection unknown. Full1x/2x business remains0. Whole-request100ms and independently useful R1-R2-laterR1 remain unmet. Protection-cut logic proved only in restricted initial model; faster-context benchmark and diagnostic spool actual candidate pending.'
state['execution_status'] = 'Active local research; strict standards unchanged. No overall success, commit, push, external message or GPTPro send.'
a = state['active_experiment']
a['repeating_low_wip_status'] = 'Caprelay001 actual+24070-row saved policy replay passed in849.7147176s<2400. H86400/all28506/22trays,8 completions(2,3,6,8,9,10,11,12),3 ontime,28498 waiting,28503 strict horizon violations; restricted arrival-to-unload cost1211336616.566057. One token8 actual supplies/unloads,21 parked. Both owner fresh cap proofs and delivered own relay/ACK observed; historical proof authorizes no new physical action. No new same-policy cap3 pair; all-job protection unknown.026 archive bound to accepted026 receipts/binary; live027 eight-file differences not execution drift. Initial review path/version precheck errors preserved.'
a['full2x_endpoint_status'] = 'Corrected narrow002 reads final0525+input+small offline snapshot,0native/no whole replay. Resource53 FIFO [28,29,30,31]: head business projected:2x:0 to99 statically unreachable, second business projected:2x:2 to116 reachable but blocked. Exactly3 current loaded legs statically unreachable. Seven full-receiver dependencies form an acyclic chain to53, no capacity-cycle/deadlock proof. native completed_count10 means transport legs, business0. Wrong001 four-unreachable result explicitly superseded.'
a['quiet_tail_status'] = 'Closed negative:192 full outputs exact,24ABBA medians212.0494->246.54375ms; fixed profile halves tick calls28312->13994 but scan/heap costs raise run.315476->.337080s and extraAST raises constructor.136922->.224431s. Total.530245->.640500s. Stop microtuning, no promotion.'
a['notification_query_census_status'] = 'Closed negative: three retained actual tapes read once in6.2948018s,0native. Only0/16/55 safe-boundary post-hop queries were eligible; corresponding saved native envelope0/.2338/.9311ms, negligible beside64.3337/970.5869/27365.3727ms warm roots. No query omission implemented. Continuous notification coverage and original immutable-request guard remain required.'
a['protection_cut_status'] = 'Restricted initial-model logic only:40 pure tests pass;192 candidates yield93 completed-job strict counterexamples and99 exact full predictions; four-method orders/counts/selected actions/selected full outputs preserved. Full same-input baseline required and cuts consume evaluations. Prefix rejection carries unknown suffix, not fake prediction or native protection. Independent new fastRequestContext integration pure-tested, fixed6case ABBA being prepared; no performance result yet.'
a['diagnostic_spool_status'] = 'Fixed three actual tapes x three sinks pure comparison passed9 byte-identical readbacks/42tests in65.4334627s<120;76pins unchanged. Durable spool immediate JSON/UTF8/write/flush hot cost23.67-24.71% lower; total replay changes-1.30%,+1.18%,-3.57%, so net gains small with a regression. Fixed256MiB/160000rows, overflow unknown; RAM excluded from native. Separate robust-finalclose version and one spool-only3fault600s actual+fullsaved package authorized for preparation, not yet dispatched. All final compression costs retained.'
a['joint_protection_design_status'] = 'New source/analytic hypothesis only, no native/grid: keep a protected job live at later reuse, preserve mandatory storage and all-job protection; isolate R1 release->actual R2 supply->later R1 resource bypass. All methods receive same graph/actions/time/budgets with strong continuous timing baseline. Existing legal advance only1-1.5s; receiver E overlap and native_default routing remain embedding unknowns. One fixed mechanism plus two preregistered negatives being screened. Existing discovery/validation evidence unchanged; no novelty certification.'
state['next_actions'] = [
 'Review and run one fixed6case ABBA fastRequestContext versus combinedProtectionRequestContext under120s external hard bound; charge both full context,baseline,32queries and encoding. Keep negative result if no net gain.',
 'Review robust-finalclose spool source/pure results then one fixed original3fault actual+fullsaved600s campaign; immutable026 binary/archived sources, original policy/seals and request identities unchanged. Measure whole requests, do not deduct hypothetical savings.',
 'Finish one exact analytic joint-mechanism screen and two fixed negatives; receiver occupancy/native_default/full legal reservation embedding must be satisfied before any new native experiment.',
 'Keep original1x/2x full denominators, originalR1 permissions and cap0 edge97->98. Legal low-WIP admission may avoid FIFO blockage but cannot claim complete original workload or all-job protection.',
 'Native narrow exclusive timing attribution and actual final revalidation remain needed; warm normal64.3337ms is a finite case, not overall100ms.',
 'Preserve immutable failures, unknown lineage and full process costs; record problems and solutions for later user-directed GPTPro review. No commit,push or sending without instruction.',
]
a['pending'] = state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
note = '''

## milestone018：8次业务循环核验闭合，仍严格保留全天与100ms缺口

终态双向发布修复完成实际执行和24070行完整保存重放，整进程849.715秒，低于2400秒上限。原全天28506件全部保留，22盘中同一盘完成8次供盘—装载—卸载循环，其他21盘按声明停放。完成件2、3、6、8、9、10、11、12中仅3件按时；28498件未完成，严格H86400逾期28503，截断总流转成本1211336616.566057。两owner均有新鲜终态证明、真实单次发布和送达ACK；历史证明不授权新动作。逐件保护仍未知，没有新的同策略cap3对照。复核过程曾用错归档目录并误把live027当作026源权威，均在出报告前停止；改为真实cap8归档和已接受026构建绑定，原运行证据未修改。

全天2倍终态窄诊断修正：53队列[28,29,30,31]首件到99不可达，但第二件到116可达、受FIFO首件阻塞；只有3个当前载货段静态不可达。7条满接收资源依赖构成无环链，不能宣称已证明容量环死锁。native completed_count10是运输段完成，业务仍0。旧001把4件均列为99的错误明确撤回，002保留证据映射。

两条优化假设关闭为负结果：静默tick虽然减少14318次handler，扫描、heap处理和额外AST编译抵消收益，不再调参叠加。通知查询筛选即使满足连续通知与不可变请求检查，三个案例最多只节省0、0.2338、0.9311ms已测API包络，不值得实施。

新保护剪枝只在受限初始模型证明已完成件的严格恶化不可被后缀修复：192候选中93个早停反证均被完整预测确认，99个其余输出完全一致；四方法查询顺序、预算和最终选择保持。每个早停仍计一次候选，未执行后缀标unknown，绝不伪造完整预测。与较快RequestContext的独立组合版本待公平计入初始化、完整baseline和32查询后测净收益。

诊断流水线新候选保留API返回前JSON和逐调用UTF8落盘flush，只把gzip压缩放到close；三真实tape九次回读字节一致。调用内费用下降约24%，但完整费用变化为-1.30%、+1.18%、-3.57%，有负例且只有单样本。固定256MiB/160000行超限保持unknown，RAM版本不用于实际；close压缩始终计入总进程。下一步仅一次独立spool三故障实际验证，不能把纯结果当作请求100ms通过。

联合机制仍是新解析设计：保留后续冲突发生时仍存活的受保护件，使R1释放、真实R2供盘和后来R1绕行具有可检验联系。当前合法提前量只有1—1.5秒；接收端E占用与native_default路由尚未完整嵌入。固定一正两负解析筛选先于任何扩大试验；已有联合必要性负结果和未运行验证集保持原状。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f: f.write(note)
with (DOC/'NEXT_ACTION.md').open('a',encoding='utf8') as f:
 f.write('\n\n## 最新执行次序（milestone018）\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n')
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:
 f.write('\n\n## 48. 条件保护反证、诊断压缩与联合必要性的边界\n\n已完成件的严格恶化可作为受限预测模型中的剪枝反证；它不证明全原生保护或联合必要性。诊断压缩移动、终态发布修复属于工程改进，不能当作联合算法创新。新资源冲突设计仍缺完整合法嵌入；R1、R2、后续R1分别作用和强基线比较都不能省略。\n')
with receipt.open('x',encoding='utf8') as f:
 json.dump({'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},
 'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),
 'overall_goal_achieved':False,'new_native_dispatched_here':0},f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
