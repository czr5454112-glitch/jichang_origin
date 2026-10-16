"""Register completed independent audits and preserve two optimization negatives."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC = ROOT / 'docs/g31_ics_circulation'
HERE = Path(__file__).resolve().parent

def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

report = HERE / 'milestone_009.json'
backup = HERE / 'before_milestone_009'
assert not report.exists() and not backup.exists()
pins = {
    'original_low_wip_reuse_independent_actual_review_002.json': '0b28cb513ec662c72e0970cb1f39259ea59f0d06bf7568889c843120f943aef1',
    'native_preexisting_v3_bound_business_001_comparison_audit.json': '5328168f1d43f18e8a3786ac99ddee2bf4f93dfab2ec6a72b3bcac7b42445bd2',
    'regional_path_bytes_actual_pure_001/receipt.json': '16582fb439df5bfc90ac33a79aaae904f35bcf585af40887c558679743428057',
    'protocol_query_copy_actual_pure_001/receipt.json': 'a47c123de0200e61bea80e15d09ef3fbad0fa3393b6f0fa12f3a9949e5b1434f',
}
for name, expected in pins.items(): assert sha(OUT / name) == expected
reuse, bound, cache, shallow = [read(OUT / name) for name in pins]
assert reuse['status'] == 'passed_saved_actual_two_supply_review' and reuse['native_executions_by_reviewer'] == 0
assert bound['status'] == 'saved_native60_and120_inputs_revalidated' and bound['actual_later_input_count'] == 120
assert bound['declared_comparison_status_counts'] == {'unknown': 60}
assert not any(bound['declared_fixed_family_complete'].values())
assert cache['source_changed'] == shallow['source_changed'] == []
assert cache['native_executions'] == shallow['native_executions'] == 0
assert cache['median_wall_ms']['bytes_pool'] > cache['median_wall_ms']['original']
assert shallow['query_count'] == 5013
heartbeat_bytes = (OUT / 'full024_chained_2x_20261015_001/heartbeat.json').read_bytes()
heartbeat = json.loads(heartbeat_bytes)
files = ['RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md']
backup.mkdir()
for name in files: (backup / name).write_bytes((DOC / name).read_bytes())
(HERE / 'milestone_009_full2x_heartbeat_snapshot.json').write_bytes(heartbeat_bytes)
state = read(DOC / 'RESEARCH_STATE.json')
active = state['active_experiment']
active['startup_low_wip_candidate'] = 'Reuse002 independent actual review002 passed:14321 API replay, actual received ACK/owner empty-return publication/peer FIFO chain and two same-token completions;8921-call first-phase comparison matches005 except only validated advance_to.result.wall_seconds. Review001 timing mismatch preserved. Source26 next FIFO head unreachable after jobs2/6, so further supply to26 cannot be assumed useful. All28506/22trays preserved; no strictprotection/full-day/100ms claim.'
active['planning_v3_status'] = 'Bound60 independent comparison audit complete:all120 actual later inputs revalidated;60 A verified,50 B verified,10 B unsupported/unknown. New4 assessed branches merely changed ACK from oldfallback to realprefer8, but actualedge8 and all5 completiontimes identical. Only2 fixed-window vectors improve receiver by .831/1.031s; both still initial-rejected unknown.45initial+1later rejection leave46unknown;all6 finite-reference families incomplete and60/60 registered protection comparisons unknown. New192 fixed-action runner in preparation, not executed.'
active['regional_path_cache_candidate'] = 'Native tuple-cache pair negative10.633849→11.539014s retained. Pure byte-key candidate median592.1271ms still slower than original351.7912ms across actual1000activation/7158pathcall distribution; no native dispatch/promotion. Pure query shallow-copy5013responses and24571API exact, median106.5168→46.9487ms, but fifth sample266.171ms vs baseline122.866ms retained without unsupported GC attribution; too small/inconsistent to justify separate native trial.'
state['current_stage'] = 'All3 overall requirements remain unmet. Original2x024 continues within7200s cap, latest saved seal recorded in milestone009 heartbeat snapshot. Same-token two-job cycle independently audited but loader26 prefix now exhausted. Corrected v3 improves interface assessment14/60, not utility; all registered strict comparisons unknown. Preparing finite original business request timing probe and full192 fixed-action counterfactual matrix; neither executed yet.'
state['next_actions'][1] = 'Design legal cross-loader expansion after independently audited two-job reuse, using only delivered peer FIFO facts and actual source return/empty state; preserve unreachable head and original22trays/all28506.'
state['next_actions'][2] = 'Finish independently reviewed192 fixed-action matrix preparation; all6 cases×32vectors preregistered, six180s packages/1080s total, one native worker. Unknown/failure rows retained; no online outcome oracle or favorable-case screening.'
state['next_actions'][4] = 'Prepare original authorized-R1 finite job4 caller-request probe from physical9600 to9900 censor, fresh root before observation, whole setup/warm/validation/retry/ACK/actual-edge accounting. Three fault cases share600s; not general original-stream or100ms certification.'
active['pending'] = state['next_actions']
write(DOC / 'RESEARCH_STATE.json', state)
text = (DOC / 'NEXT_ACTION.md').read_text(encoding='utf-8')
start, end = text.index('## 最新执行次序'), text.index('## 恢复初期队列')
current = '''## 最新执行次序（milestone009）

1. 原始2×同024继续运行，7200秒上限和最多2个native worker不变；本次截止14:30:05。已存seal与当前尾片严格区分，milestone009保存当时heartbeat快照。不得把未封存尾片当检查点。
2. reuse002独立实际审查002通过：14321API、实际ACK/返空/已交付邀请/peer FIFO链成立；8921调用与005首段比较仅排除合法原生耗时字段，旧review001失败原件保留。同盘job2/job6两次完成后source26下一FIFO头不可达，下一步设计跨loader扩展，不能机械重复供盘。
3. 1×全天保存证据仍为H86400、28506件、0完成、18在途、28488等盘；原worker hard_timeout未改，最终seal未独立native重放。完整业务请求耗时认证仍待完成。
4. bound60全部120后续输入已独立复核；新增4 assessed只是改为真实prefer8，而旧回退同样实际走8，五件完成时间无改进。仅两个fixed-window分支receiver改善.831/1.031秒，但初始拒绝仍unknown。45初始+1后续拒绝，46unknown；全部6固定族不完整、60个登记保护比较全unknown。下一192固定动作矩阵仍在准备，先做执行性与模型校准，不当在线oracle或创新证明。
5. 原图有限改路请求probe准备中：独立授权R1输入、job4在9600启动、9900删失界，首次观测前计根，真实ACK与实际下一跳均到齐才能成功闭合。三fault case共享600秒；保留全setup与重试成本及前缀差异，有限案例不能替代全天100ms认证。
6. 路径缓存原生慢8.51%；新字节键纯测592.1271ms仍慢于原351.7912ms，不启动native。浅树双复制5013查询与24571 API一致，中位总成本106.5168→46.9487ms，但保留266.171ms负尾，不作为100ms达标或生产推广依据。完整缺口见`LT2_QUERY_COPY_AND_REMAINING_100MS_20261015.md`。

最新证据索引`user_resume_20261015_001/milestone_009.json`。三项总目标仍未达标；继续本地优化、执行与问题记录，未提交或推送。

'''
(DOC / 'NEXT_ACTION.md').write_text(text[:start] + current + text[end:], encoding='utf-8')
note = '''

## milestone009：独立复核完成，区分接口改进与业务收益

reuse002的同盘两次实际服务已完成独立API/ACK/own-return/peer FIFO复核；source26下一个原始FIFO头不可达，不能反复给它送盘。bound60的120后续输入和全部逐件结果已复核：四个新增assessed分支实际路径及完成时间与旧回退相同，不构成收益；仅两固定窗改善receiver但初始拒绝仍unknown。全部六参考族不完整，60个严格保护比较都unknown。路径字节缓存仍比原求路慢；浅树复制仅纯测微小收益且有负尾，均不推广。准备新192动作执行矩阵与原图明确业务请求完整计时，尚无实际结果；三项整体要求维持未达标。
'''
with (DOC / 'RESUMPTION_20261015.md').open('a', encoding='utf-8') as stream: stream.write(note)
with (DOC / 'NOVELTY_LEDGER.md').open('a', encoding='utf-8') as stream:
    stream.write('\n\n## 39. 实际效果与接口通过数分开\n\n新增四个v3 assessed只让已发生的edge8拥有正确ACK证据，逐件完成时间与旧版本完全相同；不能把14/60相对10/60写成联合收益。两固定窗的局部改善仍有初始拒绝，严格比较保留unknown。原图同盘第二次完成独立复核是执行性进展，未建立R1→R2→R1保护收益。复制微优化的中位改善与负尾一起保留，不从局部核耗时推出完整100ms。\n')
write(report, {'schema': 'g31.resume_milestone.v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'immutable_evidence': pins, 'before_sha256': {name: sha(backup / name) for name in files},
    'after_sha256': {name: sha(DOC / name) for name in files},
    'full2x_snapshot': {'path': 'milestone_009_full2x_heartbeat_snapshot.json', 'sha256': sha(HERE / 'milestone_009_full2x_heartbeat_snapshot.json'), 'latest_native_seal': heartbeat['latest_native_seal']},
    'scope': 'Independent saved-evidence audits and pure optimization negatives; no three-goal certification, native checkpoint reconstruction or publication.'})
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(report)}))
