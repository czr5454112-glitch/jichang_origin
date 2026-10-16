"""Close full2x audit, pending ACK and negative performance experiments."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE.parent
DOC = ROOT / 'docs/g31_ics_circulation'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())

pins = {
 'full024_chained_2x_20261015_002_saved_audit_001.json': 'c9168ca8209df07723a1deef386d1b29c9e0ff992c63b242360018740d0c35d3',
 'full024_chained_2x_20261015_002_saved_audit_independent_review_001.json': 'ecee737c38991859d85e02258fc8c1ea63fd4c7cb25f352d3a8fd87adbed6feb',
 'original_route_pending_ack_report_review_001.json': 'e169f6f68d79efa7d3def029b11de78158ed4069b2146abc35591e53e73d2293',
 'original_route_pending_ack_independent_report_review_001.json': '5927caa1f40304829b63929a46e3df30f1a08be109f3e35b1317f6cced54ecf8',
 'original_route_pending_ack_prepare_001/independent_verification.json': '660547e068fe019793090200ff269b2697fe1bdb7465dff03e6465edb1f8c0cc',
 'original_route_pending_ack_prepare_001/powershell_launch_receipt.json': 'f2255ed74dc120fa1f88f6054328407474e3b5b05f2dc94a77aa5dbe016689be',
 'quiescent_cap8_prefix_diagnostic_001/report.json': 'cfe95d62094ef20048173d31a9a9b9fe56b6ac5c247985ab92699fd55bcef3dd',
 'preference_prefix_pair_002_independent_audit.json': '6c1ae12222fb4312c3cb745b1f47aff161942eb38f910d5dcfeb98a5486856d5',
 'preference_static_context_summary_001.json': 'fe6fe76328af56827b46ca0f9ec1f540c44aabaacf09b3e3bda855a1c60d206a',
 'preference_quiet_pair_001_independent_review.json': 'cce1ba3fc2e76112dbad1791d90e4fd3b5bc687976541fed794b1a1d5acce3f5',
 'preference_quiet_pair_001/external_application_wall.json': '1027a57bfac2b887eef82b3f49bc612020e9dd90775f0f4c1386a6aac945deca',
 'original_low_wip_cap_relay_prepare_001/independent_source_review_001.json': '6cb672f4f01704f580fbb88c8f516ce250ded20a0155eca40cd2aa69d3d7d0e4',
}
for name, expected in pins.items(): assert sha(OUT / name) == expected, name
audit = read(OUT / 'full024_chained_2x_20261015_002_saved_audit_001.json')
assert audit['status'] == 'passed_saved_physical_horizon'
assert (audit['offered'], audit['completed'], audit['unfinished']) == (57012, 0, 57012)
assert audit['resume_proof']['any_ancestor_source_drift_finalization_unknown'] is True
quiescent = read(OUT / 'original_low_wip_quiescent_prepare_001/external_launch_receipt.json')
assert quiescent['process']['status'] == 'hard_timeout'
quiet = read(OUT / 'preference_quiet_pair_001/receipt.json')
assert quiet['status'] == 'completed_exact_pure_quiet_pair' and quiet['source_changed'] == []
assert quiet['initial_conformance_count'] == 192 and len(quiet['timing_samples']) == 24
assert all(not x['candidate_faster'] for x in quiet['case_pairs'])
for name in ('original_low_wip_quiescent_prepare_001/external_launch_receipt.json',
             'original_low_wip_quiescent_prepare_001/powershell_launch_receipt.json',
             'original_low_wip_quiescent_prepare_001/branch_ledger.json',
             'preference_quiet_pair_001/receipt.json',
             'full024_chained_2x_20261015_002/receipt.json'):
    pins[name] = sha(OUT / name)
parent = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup, report = HERE / 'before_milestone_017', HERE / 'milestone_017.json'
assert not backup.exists() and not report.exists()
backup.mkdir()
files = ['RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md']
for name in files: (backup / name).write_bytes((DOC / name).read_bytes())
state = read(DOC / 'RESEARCH_STATE.json')
state['current_stage'] = 'Full1x and2x complete physical horizons independently audited, business completion remains0. PendingACK finite normal warm bound64.3337ms, fault/open/cold whole-request100ms unresolved. Original low-WIP quiescent cap8 timed out after asymmetric terminal proof; fresh one-relay-per-owner cap8-only candidate prepared. Prefix/static/quiet pure optimizations negative; no joint independent benefit yet.'
state['execution_status'] = 'User fully resumed; local research continuing with immutable failures/unknowns. No overall success, new commit, push or GPTPro send.'
a = state['active_experiment']
a['full2x_latest_status'] = 'Saved audit passed526shards/H86400/all57012,0complete/17in_transit/56995waiting;287traversals/22trays/0open traversals,63915immutable requests+8901retries=72816calls/10open protocol roots. Strict late57012. Ownermax1074.1492ms/4872activations>100, not isolated complete-request timing. Audit external2112.1846536s<3600; producer hard_timeout7200.6285888 unchanged. Final producerseal a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826; no new native seal replay. Initial ancestor final source-drift unknown retained; cumulative reconstruction5360.4557476s, excluded-tail costs retained.'
a['chained_resume_status'] = 'Closed: chained002 reached actualH86400 and all57012; separate saved horizon audit passed with declared lineage limits. Producer itself hard_timeout. No full business success or arbitrary cross-process checkpoint persistence.'
a['pending_ack_status'] = 'Actual3fault same026 campaign and complete saved verifier closed in199.1382522s<600; all88runtime pins unchanged. Exact permitted post-first-hop observation omission, same ordered background/commonH9900seals. Normal warm64.3337ms/7requestAPI;drop970.5869ms/43API;missingACKopen27365.3727ms/495API.2closed1open; cold conservative root bounds18046.2555/19965.7236/57688.0545ms retained. No isolated physics deductions or overall100ms certification.'
a['repeating_low_wip_status'] = 'Quiescent001 closed at shared2400.1599116s timeout. Cap3 actual+saved verified H86400/all28506/3complete. Cap8 saved manifest19506API/H29130 only;8actual token unloads visible but full audit/horizon unknown, orphan019506 excluded and no cut native seal. At26030 domestic accepts fresh peer5+own3 cap8 proof, stops publishing; international sees stale domestic proof and keeps polling. New caprelay publishes exactly one own native snapshot after first cap proof;55pure/source review passed, new cap8-only2400 worker+fullsaved verifier prepared. Oldcap3 not a new same-policy pair.'
a['prefix_performance_status'] = 'Pureprefix002 all192initial+48later full outputs exact,49pins unchanged; initial median244.3871->395.73875ms, totals2827.5023->4625.1513ms. Later first-return46.29245->137.8612ms/first-reuse38.76875->126.2934ms. Negative; no promotion. Profile identifies AST compilation and48dynamic clones; cumulative categories overlap.'
a['static_factory_status'] = 'Purestatic00124warm32 full-output batches exact; total5659.289->5870.063ms(+3.72%),median236.769->247.771ms; cold3550.536-4113.320ms retained.6fair100ms/20msreserve probes evaluate2-4of32,83.98-98.07ms, allunknown_no_native_final_revalidation. No native or legal incumbent certificate.'
a['quiet_tail_status'] = 'Independent quiet00113core+8harness pure checks,192fulloutputs/24ABBA exact,44pins unchanged; originalcontext median212.0494ms vsquiet246.54375ms,6of6case medians slower. WholePython12.5374086s. Each exact heap pop/time/horizon/event budget retained; skips only proven no-op tick handler. Negative, no promotion; one fixed profile planned, no blind parameter search.'
state['lt2_sustained_progress']['full0242x_saved_horizon_audit'] = {
    'status': audit['status'], 'producer_receipt_status': 'hard_timeout',
    'physical_horizon_completed': 86400, 'offered': 57012, 'completed': 0, 'unfinished': 57012,
    'strict_deadline_violations': 57012, 'complete_request_100ms_certified': False,
    'ancestor_source_drift_finalization_unknown': True,
    'report': 'full024_chained_2x_20261015_002_saved_audit_001.json'}
state['next_actions'] = [
 'Run prepared independently reviewed caprelay fresh cap8-only with one2400s hard bound including full saved verifier; no cap3 pair or throughput/protection success until real evidence.',
 'Close negative prefix/static/quiet cost hypotheses; one fixed quiet profile only, then structural accounting. Do not layer optimizations onto a slower base.',
 'Prove narrow irreversible completed-job protection rejection before any partial-search implementation; complete same-input baseline required, unknown is not rejection, all methods same query and baseline costs.',
 'Use full2x terminal saved snapshot for narrow static reachability/resource-block diagnosis; no replaying whole failed day without a new concrete mechanism.',
 'Keep original input permissions, capacities,FIFO,28506/57012 denominators and strict per-job protection. Native exclusive attribution and final revalidation remain unfinished100ms work.',
 'Joint necessity remains negative in completed discovery domains; preserve strong baselines and unexecuted validation unknowns. No blind candidate-grid expansion.',
 'Maintain all failures, real full launch costs and coherent regression scope; no commit,push,GPTPro send without user instruction.',
]
a['pending'] = state['next_actions']
(DOC / 'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')
note = '''

## milestone017：全天审计闭合，业务停滞与性能负结果保留

2倍原流的526分片独立保存审计完成，H86400、57012件全部在分母，完成0、在途17、待盘56995，严格逾期57012；22盘共287次穿越且无开放穿越。63915个不可变请求加8901次重试等于72816次调用，10个协议请求未闭合。单owner activation最大1074.1492ms、4872次超过100ms，这不能替代完整请求独占计算归因。独立审计外层2112.185秒，原producer的7200.629秒硬超时不改写；最终封印仍是producer记录，初代祖先缺最终漂移报告仍未知，累计5360.456秒重建及排除尾段成本全部保留。1倍/2倍全天覆盖现均有审计，全天业务要求仍未满足。

pendingACK三故障新实际试验和完整保存核验在199.138秒内结束。已有实际首跳证据后，只省去后续无必要的完整视图读取，重试、原请求身份、ACK查询及背景轨迹保持。正常暖请求保守上界64.3337ms；丢首次ACK仍970.5869ms，缺ACK开放前缀27365.3727ms，冷启动整根上界也保留。有限正常暖案例有进展，不据此宣称完整100ms总体通过。

quiescent原2400秒试验已超时：cap3全天3件完成并通过保存核验，cap8只保留H29130/19506条manifest记录，8次卸载可见但全天结果未知。新定位是26030时一方得到新鲜终态证明后停止发布，另一方仍只能看到过期证明。最小修复仅在首次达到cap时补发一次自身真实planning snapshot；双方新鲜cap证明及真实delivered ACK都必须验到。新单cap8版本55项纯测试和独立源审通过，仍需新实际验证；旧cap3不能充当新版本对照。

性能负结果分别保存：前缀共享初始32候选中位244.387降速到395.739ms；静态工厂总耗时增加3.72%；独立静默tick尾段方案在192个完整输出一致的条件下，中位212.049增至246.544ms，6个案例都慢。复制、静态检查与编译费用可能抵消事件处理节省，必须计入完整成本；不继续在变慢方案上盲目叠加。预算壳的2—4/32评估虽然在纯计算预算内，但缺真实native最终复验，全部保持unknown。下一条保护剪枝仅研究已完成件不可修复的严格反证，不能伪造完整预测或消除尚未执行候选。
'''
with (DOC / 'RESUMPTION_20261015.md').open('a', encoding='utf8') as f: f.write(note)
with (DOC / 'NEXT_ACTION.md').open('a', encoding='utf8') as f:
    f.write('\n\n## 最新执行次序（milestone017）\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n')
with (DOC / 'NOVELTY_LEDGER.md').open('a', encoding='utf8') as f:
    f.write('\n\n## 47. 性能负结果与终态协议修复不构成联合创新\n\n前缀共享、静态工厂和静默tick三个方案在已声明成对纯试验中未获净加速，保留源检查、编译、复制和输出成本。pendingACK正常暖根64.3337ms只属于有限工程改善。跨owner终态单次发布是已定位协议活性修复候选，尚未实际验收；它不能证明R1→R2→R1联合方法必要性。全部目标继续保留。\n')
with report.open('x', encoding='utf8') as f:
    json.dump({'schema': 'g31.resume_milestone.v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
      'immutable_evidence': pins, 'before_sha256': {n: sha(backup/n) for n in files},
      'after_sha256': {n: sha(DOC/n) for n in files}, 'parent_user_file_sha256': sha(parent),
      'overall_goal_achieved': False, 'new_native_dispatched_here': 0}, f, ensure_ascii=False, indent=2)
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(report)}))
