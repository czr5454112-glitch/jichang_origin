"""Close the literature/status handoff from small saved evidence only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DOC = ROOT / 'docs/g31_ics_circulation'
OUT = 'outputs/experiments/g31_ics_lt2_sustained_20261014/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


pins = {
    'outputs/bsv3p1/root_saved_review_001.json': 'ee9e546aff146fdd1550893222648f46fb2a0a184864fe1b7a2fcacca1169187',
    'outputs/bsv3p1/root_stdlib_review_001.json': '400dbeb3a67aad1a5c178607a877145a3a7608c7746fb72cd177cb21e2dc0238',
    'outputs/cprep1/root_saved_review_001.json': 'ce423b8b57ffcb7cdbff8ef882cef262990b676d1bbbd219913f6ea72b1bfa0f',
    'outputs/bdbv3p1_failure_summary_001.json': 'a2142aa7621bd439924de942e26cdd66c6a74cb5e400f5c6017e70e80fd66a08',
    OUT + 'control_timers_bcdm2_terminal_readback_002.json': 'bed37a7c8f089d318c5a094903f5d3909ac465f5501f6872f3dbfa1b441d6f03',
    OUT + 'bcdm2/actual_external_application_wall.json': '06bc6252a03b94219cd72a778557d88d7cc3a1a09e8f94681cd70f33ec19a0ae',
    'outputs/ocmp1/root_saved_review_001.json': '783f1bfa5b41b1c54d5fb20162be23372da947ce1be164632213898ad23385e9',
    OUT + 'user_resume_20261015_001/four_papers_review_manifest_20261016_001.json': '3f0418d13cf50af26d6e0f994ac879499d9eff6f792581669cf7630a46c1f5bf',
    'docs/g31_ics_circulation/LT2_METHOD_COMPARISON_20261014.md': 'fb2f43db5bdcc83a5aec822e2c77adba963fe98d80618a8e4a8f456e7cb8abae',
}
for name, expected in pins.items():
    assert sha(ROOT / name) == expected, name
parent = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'

# Check failed test evidence and actual timeout clocks without running project code.
failed = json.loads((ROOT / 'outputs/bdbv3p1_failure_summary_001.json').read_bytes())
for ref in failed['references'].values():
    assert sha(ref['path']) == ref['sha256']
cases = ET.parse(ROOT / 'outputs/bdbv3p1/tests.xml').getroot().findall('.//testcase')
assert len(cases) == 30 and sum(case.find('failure') is not None for case in cases) == 1
assert not any(case.find('error') is not None or case.find('skipped') is not None for case in cases)
terminal = json.loads((ROOT / (OUT + 'control_timers_bcdm2_terminal_readback_002.json')).read_bytes())
audit = ROOT / (OUT + 'bcdm2')
for name, ref in terminal['small_outputs'].items():
    assert (audit / name).stat().st_size == ref['bytes']
    assert sha(audit / name) == ref['sha256']
for name in terminal['missing_outputs']:
    assert not (audit / name).exists()
progress = [json.loads(line) for line in (audit / 'progress.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(progress) == 279 and progress[-1] == terminal['progress']['last']
assert progress[-1]['completed'] == 20224
clock = terminal['clock']
assert clock['end_ticks'] - clock['start_ticks'] == clock['elapsed_ticks']
assert clock['elapsed_ticks'] > clock['budget_ticks'] == 600 * clock['frequency']
assert terminal['whole_python_seconds'] == clock['elapsed_ticks'] / clock['frequency']
assert terminal['outer_timeout'] is True and terminal['C_exit_verified'] is False
assert terminal['python_exit_code'] == -1
for directory, count in [('bsv3p1', 42), ('cprep1', 36), ('ocmp1', 56)]:
    review = json.loads((ROOT / 'outputs' / directory / 'root_saved_review_001.json').read_bytes())
    assert review['tests'] == count

names = ('RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md')
backup = HERE / 'before_milestone_052'
backup.mkdir(exist_ok=False)
for name in names:
    (backup / name).write_bytes((DOC / name).read_bytes())
state = json.loads((DOC / 'RESEARCH_STATE.json').read_bytes())
active = state['active_experiment']
work = active['new_static_and_bridge_work']
state['current_stage'] = ('三项目标仍未达标。完整18仍0/18低于100ms；prelude36纯门通过，实际新18未跑。'
    'v3静态依赖42通过，接线30门29通过1条Windows路径断言失败；修订30源码已备未运行，真实v3/full96未跑。'
    'bcdm2环境修正后仍600.0507775秒超时，最后行检查点20224/37270，无完整policy/C出口证书。'
    'online比较56纯门通过并根审，但实际online21与滚动重估未执行。四篇用户论文已逐篇评估并记录可迁移机制和边界。')
work['model_v3'] = {'status': '42_passed_driver30_failed_versioned_fix_source_only',
    'binding_pure': {'directory': 'outputs/bsv3p1', 'tests': 42, 'sources': 213},
    'driver_pure': {'directory': 'outputs/bdbv3p1', 'tests': 30, 'passed': 29, 'failed': 1,
                    'whole_seconds': 52.7662869, 'failure': 'Windows path suffix test assertion after parser returned'},
    'next': 'Review independent test_v2 and runner/wrapper bdbv3p2; same30, exact canonical artifact path and digest; old8+42 mandatory. Do not modify failed source/evidence.',
    'actual_v3_executed': False, 'full96_v3_executed': False}
work['all_day_driver']['previous_actual_bcdm1'] = work['all_day_driver'].pop('actual')
work['all_day_driver']['status'] = 'bcdm2_saved600_timeout_no_full_policy_or_C_exit'
work['all_day_driver']['actual'] = {'directory': OUT + 'bcdm2', 'whole_seconds': 600.0507775,
    'outer_exitcode': -1, 'outer_timeout': True, 'last_row_checkpoint': 20224, 'total_rows': 37270,
    'row_checkpoint_is_policy_completion': False, 'inner_terminal_receipt_present': False,
    'C_entry_saved': True, 'C_exit_verified': False, 'full_saved_audit_closed': False,
    'small_metadata_root_readback': True, 'full_raw_replayed_by_root': False,
    'next': 'Source-only fixed512-prefix profile design exists; review before any new execution. No automatic600 retry or budget increase.'}
work['constructor_prelude'] = {'status': '36_pure_passed_runtime_integration_source_only',
    'directory': 'outputs/cprep1', 'tests': 36, 'sources': 234,
    'new_actual18_executed': False, 'scope': 'Separate boundary check, metadata and append cost while preserving old constructor clocks and errors.'}
work['online_comparison'] = {'status': '56_synthetic_passed_root_saved_review',
    'directory': 'outputs/ocmp1', 'tests': 56, 'sources': 238, 'whole_seconds': 11.9599121,
    'scope': 'Data-only prospective comparison logic:21 branches, full per-job protection and complete forecast-reference eligibility. Successful selected execution cannot replace missing reference forecasts.',
    'actual_online21_executed': False, 'joint_effectiveness_established': False}
work['supplied_four_papers'] = {'status': 'review_registered_no_method_validation',
    'manifest': OUT + 'user_resume_20261015_001/four_papers_review_manifest_20261016_001.json',
    'method_mapping': 'docs/g31_ics_circulation/LT2_METHOD_COMPARISON_20261014.md',
    'priorities': ['Local shared-event behavioral contracts and nonblocking checks',
                  'Region/route hierarchy with lower feasibility/value feedback',
                  'Event-triggered lawful conditional-suffix updates',
                  'Later grouped-heldout lawful-observation demonstration ranking'],
    'new_training_or_native_runs': 0}
actions = [
    '审 bdbv3p2 独立修订源码并运行同30纯门；旧8+42和失败30完整保留。通过后才能新真实1cold1warm绑定门，再完整96；full96 draft2尚未执行。',
    'online比较56合成已根审，继续实际online21注册及完整保存验证，补建每owner完整forecast-reference证据；不可把比较逻辑通过当方法通过。所有方法同信息/full32预算/逐件保护。',
    'prelude36已通过；先审runtime接入草案和边界完整性，之后再新门及实际18。完整100ms仍0/18，finalization仍独立定位，冷成本保留。',
    'bcdm2已600超时，不重跑。固定512前缀诊断仅设计；先审保留C入口出口/原policy/每次digest的计时方案，不能把早段归因外推后段或扩大600预算。',
    '按四篇文献映射推进方法：局部共享契约、区域/路线反馈、事件触发后缀修复，先同信息强基线和受控消融，再决定轻量示范排序。不得导入全局在线真值、瞬时通信、删除队首或增加托盘。',
    '全天all28506、完整请求100ms、联合有效性三目标不变。保留失败/unknown；无用户后续命令不GPTPro外发、不push/commit。']
state['next_actions'] = active['pending'] = actions
(DOC / 'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(DOC / 'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone052\n\n三项目标未达标，继续按保存证据推进；不重跑已封存失败。\n\n' +
    '\n'.join(f'{i+1}. {value}' for i, value in enumerate(actions)) + '\n', encoding='utf-8')
note = '''

## milestone052：四篇文献完成映射，比较56通过；全天超时与接线失败保留

v3 canonical __future__ 静态依赖42纯门通过并根审；driver30门实际29通过1失败，52.7662869秒。
失败是测试对Windows路径使用正斜杠suffix断言，原parser已返回；旧门仍失败。独立test_v2及
runner/wrapper bdbv3p2仅源码待审，尚未执行，真实v3 cold/warm和新full96也未运行。

cprep1 prelude36纯门通过并根审，234来源，28.8034655秒；runtime接入仅源码。
ocmp1 data-only比较56/56通过，238来源，11.9599121秒；根核完整collection/XML、owned/outer
回执和全部current/archive来源，根回执783f1bfa…3385e9。它检验unknown、逐件零容差和完整
参照预测资格，尚无actual online21、滚动重估或联合有效性结果。

bcdm2修正四个C启动环境键后仍在600.0507775秒外层超时。279条journal最后行检查点20224，
总37270；该检查点早于外层observer/policy消费，不是20224个完整策略步骤认证。缺少inner
bounded终态、C出口、最终report和all_job_states。根本轮只核小回执、时钟、journal及文件
绑定，没有再次读取巨型raw或完整重放；direct/fallback比例和CPU热点未知。固定512前缀
profile目前只有设计，不准自动重跑600或放宽预算。bcdm2 metadata终态001写false为null的
错误保留，002仅修小记录，不修改实际结果。

用户四篇PDF已评估方法、实验和限制，逐页JSON及原PDF哈希已存，汇总清单
four_papers_review_manifest_20261016_001.json SHA3f0418d1…c1f5bf。现有方法比较文档追加
具体接入与消融建议：共享事件契约和组合非阻塞、保留多种合法动作的模板、区域与局部路线
价值反馈、后续同合法观测专家排序。已明确两区域/全观测/即时通信等假设差异，学习不是
供给预测，T2BR批时延不能摊成100ms，原图物理不可行不能由学习解除。没有训练或新方法
实测。预测/版本/ACK/tombstone等已有能力不能重新计创新。原三项目标继续保持NOT MET。
'''
with (DOC / 'RESUMPTION_20261015.md').open('a', encoding='utf-8') as stream:
    stream.write(note)
with (DOC / 'NOVELTY_LEDGER.md').open('a', encoding='utf-8') as stream:
    stream.write('\n\n## 82. 契约、分层与示范学习的借鉴边界\n\n四篇用户论文已读并逐页记录。'
        '共享契约/非阻塞、允许多种动作的模板、区域/路线反馈、离线示范排序均已有先例；'
        '待验证增量仍是有限盘/FIFO/Storage下必须联合修复哪些下游复用义务。'
        '瞬时通信和全局状态不能进入公平在线输入；既有版本与ACK不算新机制。'
        'comparison56、prelude36和绑定42仅工程合成门；actual online21未执行，'
        '全天saved600仍失败、完整请求100ms仍0/18。\n')
record = {'schema': 'g31.resume_milestone.v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'immutable_evidence': pins, 'before_sha256': {n: sha(backup / n) for n in names},
    'after_sha256': {n: sha(DOC / n) for n in names}, 'parent_user_file_sha256': sha(parent),
    'overall_goal_achieved': False, 'external_messages_sent': 0,
    'verification_scope': 'Saved small evidence and previously completed root reviews; no new full raw audit, native execution or performance certification.'}
target = HERE / 'milestone_052.json'
with target.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
assert json.loads((DOC / 'RESEARCH_STATE.json').read_bytes())['next_actions'] == actions
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(target),
                  'overall_goal_achieved': False}, ensure_ascii=False))
