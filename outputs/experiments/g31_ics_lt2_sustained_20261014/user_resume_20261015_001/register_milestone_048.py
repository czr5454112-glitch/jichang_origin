from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DOC = ROOT/'docs/g31_ics_circulation'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
pins = {
    'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp2/root_saved_review_001.json': '4db25792478f03dac007cc6466148c4ddc55fce98407ee2f551bb2c974b7df7c',
    'outputs/bdbp1/root_saved_review_001.json': '43eca928f7d4c72f52e88326f10e714b8c1a9e48f9009c9ec4223c859e6d3516',
    'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp1/receipt.json': '3730d1e722dac45849e57f2a854d15f95a82824895995ae73b9c7e6d891db9e0',
}
for name, digest in pins.items(): assert sha(ROOT/name) == digest, name
parent = ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent) == 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names = ('RESEARCH_STATE.json', 'NEXT_ACTION.md', 'RESUMPTION_20261015.md', 'NOVELTY_LEDGER.md')
backup = HERE/'before_milestone_048'; backup.mkdir(exist_ok=False)
for name in names: (backup/name).write_bytes((DOC/name).read_bytes())
state = json.loads((DOC/'RESEARCH_STATE.json').read_bytes())
state['current_stage'] = '三个总目标仍未达标。全天C digest新bcp2纯门37/37和模型bind driver新15门通过且root独立保存核验；全天完整600和真实模型bind尚未执行。静态inventory actual18接线/constructor计时正在源审。'
active = state['active_experiment']
active['new_static_and_bridge_work']['all_day'] = {
    'directory':'outputs/experiments/g31_ics_lt2_sustained_20261014/bcp2',
    'status':'synthetic37_passed_saved_readback_verified_full600_unexecuted',
    'tests':37, 'passed':37, 'sources':115, 'whole_seconds':59.4570877,
    'root_review':pins['outputs/experiments/g31_ics_lt2_sustained_20261014/bcp2/root_saved_review_001.json'],
    'prior_failure_retained':'bcp1 remains36pass1fail; v2 changes only baseline factory expression; original production binder and full byte comparisons unchanged.'}
active['new_static_and_bridge_work']['model_bind_driver'] = {
    'directory':'outputs/bdbp1', 'status':'synthetic15_passed_real_dependency_gate_unexecuted',
    'tests':15, 'passed':15, 'sources':203, 'whole_seconds':23.3753764,
    'root_review':pins['outputs/bdbp1/root_saved_review_001.json'],
    'next':'Metadata preparation then one cold bind/one warm proof/close under120; zero engine/fork/resume/native/C; unsupported dependency fails without omission.'}
actions = [
    '审阅并准备新全天C digest完整保存审计：同37270/27218/28506/22/600，原语义/actor/prefix检查与7779+3082 C入口出口检查保留；bcp2只是接线合成门。',
    '模型bind新15门已过，先准备短路径bdb1元数据并根审，再一次有界真实依赖域检查：冷原proof一次、warm一次、close，0engine/fork/resume。失败保留并显式修复依赖处理。',
    '完成静态inventory actual18接线源审与聚焦纯门、metadata、实际复验；保留C6124/RPC检查、18分母、600/60ms/100ms，并新增完整constructor wall sidecar，不把它当inventory CPU。',
    '真实模型绑定通过后完整96等价；随后在线7臂×3场景同信息/同32预算，独立owner提案、真实动作事后assessment，初始后缀保留不得标为重规划。',
    '全天原流1x/2x、严格正常保护、full32完整100ms与联合有效性仍开放；不改拓扑/FIFO/盘数，不删失败/未知，不弱化强基线。',
    '继续记录失败与修复，保持原证据及父目录用户代码；无新指令不发GPTPro、不push/commit。',
]
state['next_actions'] = active['pending'] = actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone048\n\n全天C绑定37门及模型bind driver15门通过；尚无新全天/完整请求性能或真实模型域结果，三项目标不变。\n\n'+'\n'.join(f'{i+1}. {a}' for i,a in enumerate(actions))+'\n', encoding='utf8')
note = '''\n\n## milestone048：C绑定复验37通过、模型绑定流程15通过

bcp2保留冻结生产binder，仅将错误测试对照换为旧runner实际工厂入口；逐完整字节和两层assessor执行检查仍在，37/37通过，115来源当前/归档一致，完整Python59.4570877/120秒。根saved-only核验4db25792…b7df7c，不重复执行测试。bcp1的36pass/1fail及其源码、日志全部保留。下一步是新全600源码/metadata，未声称全天过关。

模型绑定流程新增15门全部通过，203来源，完整Python23.3753764/120秒；根保存复核43eca928…6d3516。原37门不重跑。下一真实域检查只允许一次冷bind、一次warm证明和close，不运行模型engine/fork/resume；65/66预算的合成功能测试不能替代真实依赖域与完整96等价。准备步骤必须绑定本15门、原37门和旧65完整证明字节。

请求static inventory新actual18源码源审中，补入构造调用完整墙钟，保持原60ms选择/100ms请求和600共享预算。根在执行前发现测试对嵌套source_proof键使用了错误顶层路径，以及prepare对纯门外时钟绑定尚不完整，已要求修正断言路径和加强绑定，不删除断言、不放宽预算。尚未运行该新campaign。
'''
with (DOC/'RESUMPTION_20261015.md').open('a', encoding='utf8') as f: f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a', encoding='utf8') as f:
    f.write('\n\n## 78. 两项新接线合成门闭合，真实性能和方法有效性仍待验\n\n37项C绑定与15项模型绑定流程检查通过仅证明受测接线行为，不是全天600、完整请求100ms或联合方法必要性的证据。真实依赖域、完整96、actual18和公平online21仍须逐步验证。\n')
record = {'schema':'g31.resume_milestone.v1', 'recorded_utc':datetime.now(timezone.utc).isoformat(),
    'immutable_evidence':pins, 'before_sha256':{n:sha(backup/n) for n in names},
    'after_sha256':{n:sha(DOC/n) for n in names}, 'parent_user_file_sha256':sha(parent),
    'overall_goal_achieved':False, 'new_actual_native_or_model_runs_since047':0,
    'closed_sessions':['7064','23655'], 'active_experiment_processes':[], 'external_messages_sent':0}
target = HERE/'milestone_048.json'
with target.open('x', encoding='utf8') as f: json.dump(record, f, ensure_ascii=False, indent=2)
print(json.dumps({'state_updated':True, 'milestone_sha256':sha(target)}))
