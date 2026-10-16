from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT, OUT = HERE.parents[3], HERE.parent
DOC = ROOT / 'docs/g31_ics_circulation'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins = {
    'outputs/sinv1/root_saved_review_001.json': '7f3a5b27b48e3e2877902167c2ed1a070252410b53a6c7032c07d580d6368fed',
    'outputs/bsp1/root_saved_review_001.json': 'b668953d24cad5e8e96a3bf0243f8048cbab94389debe2f4efbcf053a8f80949',
    'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp1/plan.json': 'bb4a9eac921337b52ce108c06f634ff7cc5799c19bc4b6f2dbd80a53ae85b7cc',
    'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp1/receipt.json': '3730d1e722dac45849e57f2a854d15f95a82824895995ae73b9c7e6d891db9e0',
    'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp1/tests.xml': 'efdd6d535a51e84b93ff91ce4a2c35b50de811aa39b9531e0fb04203a08bbf38',
    'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp1/external_application_wall.json': '371abe87919ba367ae89ae6cec5f1fba840c3693aecb90a0b9913f31ac9a5356',
    'outputs/experiments/g31_ics_lt2_sustained_20261014/user_resume_20261015_001/online21_callsite_review_001.json': '5bf6da368cb94fd46cf62a10613fc92189a0fe6d58982d68daea3530ef09c355',
}
for name, digest in pins.items():
    assert sha(ROOT / name) == digest, name
bc = OUT / 'bcp1'
receipt = json.loads((bc / 'receipt.json').read_bytes())
external = json.loads((bc / 'external_application_wall.json').read_bytes())
plan = json.loads((bc / 'plan.json').read_bytes())
tests = ET.parse(bc / 'tests.xml').getroot().findall('.//testcase')
bad = [t for t in tests if any(n.tag in ('failure', 'error', 'skipped') for n in t)]
assert len(tests) == 37 and len(bad) == 1
assert bad[0].get('name') == 'test_both_assess_layers_resolve_same_fresh_factory_namespace'
assert receipt['status'] == 'failed_or_unknown' and external['exit_code'] == 1
assert external['source_changed'] == [] and external['missing_outputs'] == []
assert type(external['elapsed_ticks']) is int and external['elapsed_ticks'] <= 120 * external['tick_frequency']
for name, digest in plan['source_sha256'].items():
    assert sha(ROOT / name) == digest == sha(bc / 'source' / name), name
parent = ROOT.parent / 'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names = ('RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md')
backup = HERE / 'before_milestone_047'
backup.mkdir(exist_ok=False)
for name in names:
    (backup / name).write_bytes((DOC / name).read_bytes())
state = json.loads((DOC / 'RESEARCH_STATE.json').read_bytes())
state['current_stage'] = '三个总目标仍未达标。请求静态inventory纯门49/49、模型静态proof纯门37/37通过，root保存复核通过；尚未实际性能/完整96/18接入。全天C digest纯门bcp1为36pass/1fail，实际对照入口schema不一致正在按原factory修测试，不删除完整schema比较；全部原件保留。'
active = state['active_experiment']
active['new_static_and_bridge_work'] = {
    'status': 'two_synthetic_gates_passed_bridge_one_fixture_baseline_failure_retained',
    'actual_request': {'directory': 'outputs/sinv1', 'tests': 49, 'passed': 49, 'sources': 222,
        'whole_seconds': 29.5611517, 'root_review': pins['outputs/sinv1/root_saved_review_001.json'],
        'next': 'New actual18 integration source; all same600/60/100ms and C/RPC lifetime checks, explicit constructor sidecar clock. Not yet executed.'},
    'model_source': {'directory': 'outputs/bsp1', 'tests': 37, 'passed': 37, 'sources': 200,
        'whole_seconds': 22.8001285, 'root_review': pins['outputs/bsp1/root_saved_review_001.json'],
        'next': 'One separately reviewed real bind-only domain gate: one original proof, one cached proof and close; zero model engine/fork/resume. Then full96 equivalence.'},
    'all_day': {'directory': str(bc), 'tests': 37, 'passed': 36, 'failed': 1,
        'sources': len(plan['source_sha256']), 'whole_seconds': external['whole_python_seconds'],
        'failure': bad[0].get('name'), 'status': 'not_accepted',
        'source_basis': 'Original r.runner_namespace changes SCHEMA to serialize_once; test used r.original.assess directly. Fix the comparison entry, retaining complete bytes and both real assessment paths; do not change policy binder to satisfy the bad baseline.'},
    'actual_native_C_model_calls_in_these_pure_gates': 0,
    'speed_or_complete100ms_claimed': False,
}
active['online21_callsite_review'] = {'artifact': str(HERE / 'online21_callsite_review_001.json'),
    'sha256': '5bf6da368cb94fd46cf62a10613fc92189a0fe6d58982d68daea3530ef09c355',
    'findings': 4, 'sources': 8, 'implemented_or_dispatched': False,
    'critical': 'Fixed96 cross-owner equality stop is not an online consensus protocol. Future online controller needs own-only proposals and truthful retained-suffix/no-replan metadata; aggregate actual execution only for retrospective assessment.'}
actions = [
    '完成全天C digest测试对照入口修订的源审，在新bcp2目录一次有界纯门；原bcp1及冻结binder不改。通过后再准备同37270/27218/28506/22/600完整保存审计。',
    '先审模型real bind-only域门，再一次有界执行：冷原proof一次、warm一次和close，0engine/fork/resume。unsupported静态依赖保留失败并明确处理，不跳过依赖。',
    '审请求静态inventory的新actual18接线与constructor计时，保留原C/RPC全检查、18分母、600共享预算、60ms选择及100ms完整请求；不把49合成通过叫速度达标。',
    '模型缓存真实域门后做完整96输出/点/动作/未知分母等价，随后同信息同32预算在线7臂×3场景。独立owner选择，不把全局相等当线上共识；诚实标记初始提案保留而非后续重规划。',
    '全天原流1x/2x、严格正常保护、full32完整100ms、联合方法有效性及双机必要档继续开放；不改拓扑/FIFO/盘数、不删除失败/未知、不弱化强基线。',
    '继续记录问题与修复。无新指令不发GPTPro，不push/commit。',
]
state['next_actions'] = actions
active['pending'] = actions
(DOC / 'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
(DOC / 'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone047\n\n两项证明复用纯门通过；全天C绑定纯门保留1项对照入口失败，尚无新实际性能/全天结果。三个总目标仍未达标。\n\n' + '\n'.join(f'{i+1}. {a}' for i, a in enumerate(actions)) + '\n', encoding='utf8')
note = '''\n\n## milestone047：两项证明复用纯门通过，全天接线对照错误显式保留

请求静态inventory候选完成49/49合成测试，222来源，Python外whole29.5611517/120秒，root保存回读7f3a5b27…68fed。原constructor代码、动态session/transport/owner/ACK检查保留，新增静态descriptor底层代码/NaN位变异检测与长路径零写入反例。模型proof候选37/37合成通过，200来源，外whole22.8001285/120秒，root回读b668953d…80949；未调用真实原proof或模型入口。65/66预算、fresh证明、源文件内容变化、loaded检查异常永久失效均为功能门，不是实际加速结果。

全天C digest私有绑定bcp1为36通过/1失败，45.2230876/120秒；全部37项实际执行，源码归档无漂移。失败测试直接拿旧original.assess比较，而真实旧runner_factory已经换SCHEMA为serialize_once；源码证实该差异，候选必须与正确原工厂路径逐完整字节比较，不能剔除schema或改变生产逻辑来迁就错误对照。原失败日志/源码快照保留，修订尚未复跑。C32实际局部收益仍只支持尝试这一新全天接线，不代表全天已过。

在线21源审记录4个接线要求：旧fixed96全局A/B选择不等即停不能当线上共识；每owner仅持有自己的提案；保留初始后缀须标明没有后续模型重规划；实际合成动作规格只供事后assessment。8源码固定，未做新在线dispatch。三个目标标准不变。

root第一次sinv1保存复核命令多写外SHA的b1，正确被门拒绝且未生成报告；只修命令参数后回读成功，helper/producer证据不变、没有重跑测试，单独correction JSON已保存。
'''
with (DOC / 'RESUMPTION_20261015.md').open('a', encoding='utf8') as stream:
    stream.write(note)
with (DOC / 'NOVELTY_LEDGER.md').open('a', encoding='utf8') as stream:
    stream.write('\n\n## 77. 两项静态证明复用通过合成功能门，实际收益与方法有效性待验\n\n49+37合成通过不代表真实依赖域、完整32候选或100ms通过。全天绑定1项对照schema错误已保留，完整字节标准不降。在线控制不能借用固定向量实验的跨owner全局一致性门作为共识；执行与事后assessment的信息边界已记录。\n')
record = {'schema': 'g31.resume_milestone.v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'immutable_evidence': pins, 'before_sha256': {n: sha(backup / n) for n in names},
    'after_sha256': {n: sha(DOC / n) for n in names}, 'parent_user_file_sha256': sha(parent),
    'overall_goal_achieved': False, 'active_processes': [], 'new_native_branches_since046': 0,
    'external_messages_sent': 0}
with (HERE / 'milestone_047.json').open('x', encoding='utf8') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
print(json.dumps({'state_updated': True, 'milestone_sha256': sha(HERE / 'milestone_047.json'),
                  'bridge_failed_gate_sources': len(plan['source_sha256'])}))
