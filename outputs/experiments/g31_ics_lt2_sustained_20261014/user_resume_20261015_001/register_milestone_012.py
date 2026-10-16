"""Register reviewed finite internal-deadline result, preserving open roots."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC = ROOT / 'docs/g31_ics_circulation'
HERE = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')

report = HERE / 'milestone_012.json'
backup = HERE / 'before_milestone_012'
assert not report.exists() and not backup.exists()
pins = {
    'original_route_internal_deadline_independent_actual_review_001.json': 'b58e67d262de9e81d8dcd2d42dc5ca9d985d5cc109a01c994df6d646d9fdebad',
    'original_route_internal_deadline_independent_source_review_001.json': '26d07f096bd5c47997b3b57413a2ed54d63e683b95576a6d03e4064cf3d02e15',
    'original_route_internal_deadline_elapsed_diagnosis_001.json': '59da85a63bf86a0ce1de4ae0456c76a12213f33baa4352d70a9ed1d0abc4c3d3',
    'original_route_internal_deadline_prepare_001/external_launch_receipt.json': '0b3057e34471688aa3efe499d565f79ae6a3793fc1807fb0f160e20698d86e83',
    'original_route_internal_deadline_prepare_001/independent_verification.json': 'df34efe08cc6419a2c58689a3e49b3493f4fa875aa54441a98205f311e3a2ae0',
    'chained_saved_horizon_prepare_002/receipt.json': 'a28b5bb145a4bc5a953630e67db55294186345aaae775574eb4e755fdb1100d3',
    'chained_saved_horizon_independent_source_review_002.json': 'f1c501b754d85faeaee456ae88e4cd7e0fb286ddb8618fe2e02136060c4d18be',
    'public_native_preference_projection_validation_001.json': '622b0dc0517ffaafd6f89d767e7a39bedb0513536f80d954a07357ba498c66f5',
}
for name, expected in pins.items():
    assert sha(OUT/name) == expected, name
review = json.loads((OUT/'original_route_internal_deadline_independent_actual_review_001.json').read_bytes())
assert review['status'] == 'passed_saved_actual_and_external_launch_review'
assert (review['declared_roots'], review['closed_roots'], review['open_roots']) == (3, 2, 1)
assert review['cases']['baseline']['warm_elapsed_upper_ms'] == 82.8126
files = ['RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md']
backup.mkdir()
for name in files:
    (backup/name).write_bytes((DOC/name).read_bytes())
state = json.loads((DOC/'RESEARCH_STATE.json').read_bytes())
state['active_experiment']['original_caller_route_probe'] = (
    'Internal-deadline001 actual and independent saved review passed: normal warm upper82.8126ms/1attempt; '
    'firstACKdrop1499.9973ms/2attempts; withheldACKopen33384.5651ms prefix/5attempts, no completion upper. '
    'Same request tapes and actual commonH9900 producer seals as outer-split001; no independent native reconstruction. '
    'External launch155.6237658s fully charged to each root as campaign sensitivity; not isolated complete compute. '
    'Native envelopes+allgaps remain charged, no physics subtraction. Finite initialized normal-root bound only; overall100ms unmet.'
)
state['current_stage'] = (
    'Same024 full2x chained002 knownH79200 reconstruction pending, hardcap16:35:55;49sources frozen. '
    'Normal original-map finite request internal wake82.8126ms independently reviewed; fault/open cases unresolved. '
    'Generic owner-local one-token cap3/cap8 full-day policy in pure verification. Public preference projection174 admitted '
    'edge/status matches but timing residuals remain and strict protection is not certified. All three overall requirements unmet.'
)
state['active_experiment']['internal_deadline_review'] = str(OUT/'original_route_internal_deadline_independent_actual_review_001.json')
write(DOC/'RESEARCH_STATE.json', state)
p = DOC/'NEXT_ACTION.md'
text = p.read_text(encoding='utf8').replace('## 最新执行次序（milestone011）', '## 最新执行次序（milestone012）')
old = next(line for line in text.splitlines() if line.startswith('4. 完整原图请求原probe'))
new = ('4. 内部deadline实际正常根温态上界82.8126毫秒，首次ACK丢失1499.9973毫秒，持续缺ACK仍open、前缀33384.5651毫秒。'
       '实际请求轨迹、pre9600语义前缀和共同H9900原生producer封印均经独立保存证据复核；不等于独立原生重建。'
       '完整campaign155623.7658毫秒按每根全额保留，属于保守敏感性界。旧外层分片1049.5904/2768.9834毫秒负结果保留。'
       '正常有限初始化请求已有改善，故障覆盖和完整计算独占归因仍未解决；下一步准备027阶段测量，所有未归因间隔保留。')
text = text.replace(old, new).replace('user_resume_20261015_001/milestone_011.json', 'user_resume_20261015_001/milestone_012.json')
p.write_text(text, encoding='utf8')
note = '''

## milestone012：正常请求内部唤醒改善，故障仍未解决

内部deadline001实际及独立保存证据复核通过：正常有限初始化请求82.8126毫秒温态上界；首次ACK丢失1499.9973毫秒；持续缺ACK仍open，33384.5651毫秒仅已观察前缀。共同H9900 producer封印和全部请求轨迹与外层deadline参考相同，但没有独立原生重建。外部launch-to-exit155.6237658秒保守按每根全额计入，不把它当作已隔离的请求计算。

正常根的14.1982毫秒原生调用包络和68.6144毫秒全部间隔仍完整保留。旧外层分片负结果和全部重试成本不删除。下一步027阶段测量须保留真实源/接收复验与未归因余量。通用重复供盘的cap3/cap8是累计SUPPLY数量，两个方案均只有一个循环盘，不能写成WIP3与WIP8；文献解释已另存。公共偏好模型虽已匹配174个已准入分支的实际边与命令状态，时间残差仍不满足零epsilon逐件保护。
'''
with (DOC/'RESUMPTION_20261015.md').open('a', encoding='utf8') as f:
    f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a', encoding='utf8') as f:
    f.write('\n\n## 42. 内部唤醒有限改善与循环供给范围\n\n正常原图请求82.8126毫秒有限温态界已独立核验；ACK故障约1500毫秒及未闭合根仍在，整体100ms不放行。cap3/cap8是同一单盘策略的累计供给上限，不是WIP水平比较。文献只支持有限在制品限制拥塞的动机，不能推出当前FIFO系统无死锁或创新性。\n')
literature = DOC/'LT2_BOUNDED_RELEASE_LITERATURE_CHECK_20261015.md'
write(report, {
    'schema': 'g31.resume_milestone.v1',
    'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'immutable_evidence': pins,
    'literature_note': {'path': str(literature.relative_to(ROOT)), 'sha256': sha(literature)},
    'before_sha256': {n: sha(backup/n) for n in files},
    'after_sha256': {n: sha(DOC/n) for n in files},
    'scope': 'Finite normal warm bound; fault/open unresolved; whole campaign retained. No overall certification or publication.'
})
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(report)}))
