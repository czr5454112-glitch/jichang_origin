from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]; OUT=HERE.parent; DOC=ROOT/'docs/g31_ics_circulation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={
 'outputs/sicp1/root_saved_review_001.json':'f2921a9d07a5a7c6ed7b40d33d0bfc27771d514c59bad48de0cf4b0ca36d93e7',
 'outputs/bdb1/root_failure_readback_001.json':'640b2cd63d7051ec4041707a92a0e4e28c18678eaaa4767c32096ee75440390f',
 'outputs/experiments/g31_ics_lt2_sustained_20261014/control_timers_bcdp1_terminal_source_review_001.json':'92f21059c8cb0127356e9cefaeacf30851d58ff1e3317537fd5c7b916ed37e4a',
 'outputs/experiments/g31_ics_lt2_sustained_20261014/bcdp1/plan.json':'df4bb1995188626493f7f9e93b709240c90472ad8c24a730b10219e543d44af4',
 'outputs/experiments/g31_ics_lt2_sustained_20261014/bcdp1/external_application_wall.json':'b81b5d0a409d4a49ad0c632eb3d084c645264973fdd75c05e77942706020a75f'}
for name,digest in pins.items():assert sha(ROOT/name)==digest,name
failed=OUT/'bcdp1'
p=json.loads((failed/'plan.json').read_bytes());e=json.loads((failed/'external_application_wall.json').read_bytes())
assert len(p['source_sha256'])==134 and p['tests']==12
assert e['outer_timeout'] is True and e['exit_code']==-1 and e['source_changed']==[]
assert e['whole_python_seconds']==120.0867485 and e['elapsed_ticks']>120*e['tick_frequency']
assert not any((failed/name).exists() for name in ('tests.xml','worker.json','receipt.json','bounded_execution.json','parent_stdout.log','parent_stderr.log'))
for name,digest in p['source_sha256'].items():assert sha(ROOT/name)==sha(failed/'source'/name)==digest,name
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
backup=HERE/'before_milestone_049';backup.mkdir(exist_ok=False)
for name in names:(backup/name).write_bytes((DOC/name).read_bytes())
state=json.loads((DOC/'RESEARCH_STATE.json').read_bytes()); active=state['active_experiment']
state['current_stage']='三项目标仍未达标。static inventory actual18接线54/54纯门及root保存核验通过，正在准备实际复验。真实模型bind首次在非有限静态float前置依赖拒绝，0原proof；新v2精确位绑定源审中。全天新driver12门测试前超时，134归档完整，计划合并19轮重叠源码遍历而保持完整集合/120。'
work=active['new_static_and_bridge_work']
work['actual_request_integration']={'directory':'outputs/sicp1','status':'synthetic54_passed_saved_review_verified_actual18_unexecuted',
 'tests':54,'sources':230,'whole_seconds':21.2928519,'root_review':pins['outputs/sicp1/root_saved_review_001.json'],
 'next':'Owned120 metadata at new short sicm1; same18/600/60ms/100ms, C6124/RPC/full saved checks, complete constructor wall sidecar.'}
work['model_actual_bind']={'directory':'outputs/bdb1','status':'failed_actual_dependency_domain_retained',
 'whole_seconds':4.9957546,'cold_bind_reported_ms':160.3151,'original_proof_calls':0,'warm_uses':0,
 'reason':'nonfinite_static_value during dependency traversal; first exact slot absent from v1 traceback, not inferred.',
 'root_review':pins['outputs/bdb1/root_failure_readback_001.json'],
 'next':'New v2 exactIEEE static float bits with full dependency walk, unchanged finiteJSON/model guards, diagnostic labels and focused functional gate; no actual retry yet.'}
work['all_day_driver']={'directory':str(failed),'status':'outer120_timeout_before_test_results',
 'declared_tests':12,'actual_test_results':'unknown_no_XML_or_worker_receipt','sources':134,'whole_seconds':120.0867485,
 'source_structure':'19 separately seeded base.source_paths graph walks per source collection, plus distinct image/C/cooperative resolvers. No CPU attribution from mtime/log absence.',
 'next':'New shared-visited per-resolver version, inverseAST/synthetic and fixed134 real-domain equivalence; all current/archive hashes and loaded checks remain per entry/exit, limit120.'}
work['online_initial_dispatch_draft']={'source':'scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py',
 'sha256':sha(ROOT/'scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py'),
 'status':'unexecuted_unreviewed_draft','claim':'Own collection and full32 selector then current revalidation/immutable local submit only; no peer-proposal equality and no later re-estimation or complete100ms certificate.'}
actions=[
 '请求接线54纯门已通过；审新sicm1 owned120 metadata入口并执行/根审，再同18/600实际复验。保留60ms选择、100ms完整请求及C/RPC检查，constructor wall只能作为嵌套阶段成本。',
 '模型v1真实bind失败保留；新v2按精确IEEE位封存静态float，保持finiteJSON/model约束与完整依赖。补v2工厂全链/永久失效聚焦门，之后另版本prepare/真实域门，再完整96等价。',
 '全天driver12门bcdp1保留120超时和完整134归档；合并重复静态依赖遍历，按各resolver原语义及固定134域严格等价，测试前阶段加日志。原12尚未知，新门必须执行，不重跑旧37。',
 '根新online initial dispatch仅未执行草案，需独立源审/功能门/完整runner和审计。公平7臂×3场景同信息同32预算、各owner只持己提案；初始后缀不得标为后续重规划。',
 '三项目标保持：全天原流1x/2x与严格正常保护、full32完整100ms、联合方法有效性；不改物理/FIFO/盘数，不删失败/未知，不弱化强基线。',
 '持续记录失败和解决方案。无新指令不发GPTPro、不push/commit。']
state['next_actions']=active['pending']=actions
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone049\n\nactual18新接线54门通过；真实模型bind和全天driver纯门各保留一次失败，修复进行中。三项目标未达标。\n\n'+'\n'.join(f'{i+1}. {a}' for i,a in enumerate(actions))+'\n',encoding='utf8')
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write('''\n\n## milestone049：请求新接线54通过；两项首次接入失败保留

sicp1实际collection/XML54全通过，230当前/归档源码一致，完整Python21.2928519/120秒，root保存复核f2921a9d…6d93e7。原49不重跑。新入口保留18/600及60ms/100ms、原C6124/RPC/物理/未知检查，增加完整constructor墙钟与失败sidecar，实际性能仍待验证。

bdb1 metadata16.8108493秒通过后，一次真实依赖域门4.9957546秒退出失败；cold bind报告160.3151ms，在依赖静态float非有限检查拒绝，原proof/inventory/private皆0，warm0，未运行模型。v1未报告具体slot，不能断定首个math.inf位置。根回读640b2cd6…40390f；v2仅将静态浮点按64位精确值绑定，保留JSON有限数限制、完整依赖域和全部动态检查，新增最深label。旧源码/失败回执不可改。

bcdp1全天driver纯门120.0867485秒被外层终止，只写出plan和134个完整source归档；无tests.xml、worker、owned子进程/parent日志，因此12测试结果未知。根再次核134 current/archive；结构审查发现每次source收集19轮独立可达图遍历，尚无CPU归因，不能把mtime或缺日志当测量。新版本拟按原resolver语义共享visited集合，要求原134实际返回域精确一致、新文件单列，每次内容哈希和loaded检查保留，120不扩展。

根另写online initial dispatcher未执行草案：每owner自己collect/full32/select/立即current重验/immutable submit，保留实际提交身份和异常进度，不读对方提案，不以全局一致当共识。该草案尚无功能或实际结果，不是rolling联合有效性证明。\n''')
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 79. 接线54合成通过，真实依赖域与测试启动成本暴露新问题\n\nstatic库存复用尚待实际18成本；非有限静态float拒绝须用精确位封存解决，不能放宽JSON/model域。全天纯门在测试结果前超时，优化重复源码遍历仍须保留完整集合和逐次哈希。以上工程门无联合算法新颖性或100ms达标含义。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,
 'before_sha256':{n:sha(backup/n) for n in names},'after_sha256':{n:sha(DOC/n) for n in names},
 'parent_user_file_sha256':sha(parent),'overall_goal_achieved':False,'active_experiment_processes':[],
 'new_actual_native_or_model_runs_since048':0,'one_actual_binding_attempt_before_original_proof':True,'external_messages_sent':0}
target=HERE/'milestone_049.json'
with target.open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(target)}))
