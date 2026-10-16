"""Preserve actual full2x H86400 seal and failed repeat-verifier evidence."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC=ROOT/'docs/g31_ics_circulation'
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def write(p,value):
    with p.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

report=HERE/'milestone_014.json';backup=HERE/'before_milestone_014'
assert not report.exists() and not backup.exists()
pins={
 'original_low_wip_repeat_prepare_001/powershell_launch_receipt.json':'27eae7f2070cd82d48b83dca384ca5cc238829afafda7fefc73ef753ecea33c9',
 'original_route_native027_phase_prepare_002/ready.json':'5ba514664ab77971d664d1ba969e12b3b5f6be8160c8ddeef2ef3eb609a6447a',
 'original_route_native027_phase_prepare_002/root_source_review_001.json':'8740a623107490d5e105536f1717f7953723867d05ccbdf308d62317ed6cbc91',
 'user_resume_20261015_001/active_process_identity_008.json':'388b04b16e2257b2547bfc0cfe58b9451bb62f7d730c50f304b5284e69e249fa',
 'native_public_preference_ready_001.json':'4a3dd52905058f1b270c11bfd2299ba146cae8bf8b4fecc78bada4f96ea16ec4',
 'native_public_preference_independent_source_review_001.json':'16f9e88ed1c799193dfbbc788cbfd2498801299e9f6dfd8b6391d090c6969087',
 'public_native_projection_guard_review_001.json':'404c5b22ed1b2ce95ccc399c9c5622c3cfcecd1cddd70eb96eb6ce554538a7e6',
 'public_native_preference_projection_validation_010.json':'3e8fd198d71c2452faad9e4a4a657e0e8727823ac25211e9cc72296edd7c5f41',
 'public_native_later_preference_projection_validation_003.json':'7a50e356053b71da44acc5c6e0cb2331d2ed38b130fbb858db6252eab3ce0852',
 'public_native_initial_two_owner_agreement_001.json':'4a0ff8f46b9c29555cb23f309d0ef5e24967665950b7ae8148c5e0e974771ac1',
 'route_pending_ack_source_001/source_plan.json':'d2b723550f44ef7c500b4711d58dd85c346fb6b2db458fbc2b5ef6f6f11c25f6',
 'original_low_wip_quiescent_prepare_001/ready.json':'58eb4e886740db17dbe421d4f2ea254a5aa97eb005a11ee345a56095bccc148d',
}
for name,digest in pins.items():assert sha(OUT/name)==digest,name
full=OUT/'full024_chained_2x_20261015_002'
heartbeat=read(full/'heartbeat.json')
assert heartbeat['physical_time']==86400 and heartbeat['offered_by_current_time']==57012
assert heartbeat['latest_native_seal']['native_state_sha256']=='a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826'
repeat=read(OUT/'original_low_wip_repeat_prepare_001/external_launch_receipt.json')
assert repeat['process']['status']=='hard_timeout' and repeat['process']['windows_job_kill_on_close'] is True
ledger=read(OUT/'original_low_wip_repeat_prepare_001/branch_ledger.json')
assert ledger['cap3']['execution']['exit_code']==0 and ledger['cap3']['verification']['exit_code']==1
backup.mkdir()
for name in ('heartbeat.json','receipt.json','reconstruction.json'):
    data=(full/name).read_bytes();target=backup/('full2x_'+name);target.write_bytes(data)
    pins[str(target.relative_to(OUT))]=sha(target)
files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md']
for name in files:(backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json');active=state['active_experiment']
active['full2x_latest_status']='Actual chained002 reconstructed497/H79200 and matched seal; new H86400 reached with57012 offered/arrived,526shards,256756owneractivations. Actual final native seal a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826. Producer exec40149 still finalizing within original7200s deadline16:35:55; complete saved audit not yet run. Initial ancestor source-finalization absence remains unknown.'
active['repeating_low_wip_status']='repeat001 CLOSED1 at2400.1560703s. cap3 actual worker0 reachedH86400 (1338.5s), original saved verifier1 after385.297s: wrong calls top-level request_id, actual schema nested request.request_id. cap8 incomplete at wholeJobtimeout. Do not claim pair pass. New independent corrected saved verifier preserves failure; no native rerun solely for verifier error. Separate quiescent candidate prepared after57pure, pending actual.'
active['public_preference_projection_status']='Guard review found initial008 failed to reject changed supplied availability/occupancy. Fixed initial010 retains174 exact admitted comparisons/870completion doubles and18unknown; later003348 current-stage exact predictions requires actual current owner action endpoint facts, terminal ACK strictly before capture union.192 A/B initial predictions equal, still not atomic agreement.73source online9gate/60business prepared,89pure+independent source review; not yet executed.'
active['route_phase_status']='Actual native027 plain/timed six-cell phase002 running exec49602 since15:53:57, ownshared600s Job. All costs including unclassified remainder retained; no complete100ms certificate. Separate pendingACK-only candidate39pure and saved request replay passed; actual native parity/speed pending.'
state['next_actions'][0]='After actual full2x terminal receipt and complete manifest, run bounded3600s saved chain audit with actual H86400 seal and all57012. Preserve initial ancestor drift-finalization unknown and all reconstruction/export/seal costs.'
state['next_actions'][1]='Finish originalcap3 independent corrected saved review; cap8timeout staysunknown. Review and execute separate quiescent cap3/cap8 with samefullH/allinput/onecirculatingtoken/shared2400, exact physical comparison where completed.'
state['next_actions'][2]='After native slot frees, execute exact same-source9 delivery gate then60 online comparison from native_public_preference_ready001. Same32/4caps and four complete fixed-window arms; independent saved audit must retain unknown and per-job strict protection.'
state['next_actions'][3]='Finish actual phase002 comparison; then separate pendingACK-only actual threefault candidate with exact preproof semantics, real retries/ACK/drain and commonH seals. No arbitrary100ms cost subtraction.'
active['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
note='''

## milestone014：2×原流取得全天封印；失败与修复分别保留

chained002实际重建497段到H79200并匹配原生封印，随后推进到H86400。全部57012件已到达，526段、256756次owner激活，最终原生状态SHA为a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826。记录时producer仍收尾，原7200秒上限不延长。保存记录的完整审计尚未执行；初始暂停祖先缺少源码漂移最终化字段的限制仍保留。

repeat001按2400秒共享上限结束。cap3实际模拟exit0到全天，但附加校验错误地读取calls顶层request_id，真实字段在request.request_id，校验exit1；cap8在整组限时内未完成。原错误、385.297秒校验成本、cap8未知分母全部保留。仅用独立新版校验现有cap3，不为校验器错误重跑模拟。另备quiescent候选：达到真实cap ACK覆盖后停止新的供给决策，继续原协议刷新、重试和物理推进，须经实际物理一致性比较。

模型守卫审查发现旧008对某些改变后的可用性/占用未拒绝；新010修复后174已准入分支仍逐边/时间、命令和870完成double精确匹配。later003要求真实当前owner动作事实，348当前阶段预测精确，18原未知不升级。A/B两owner192组同动作预测相同不构成原子协议证明。新同源9交付门及60在线比较已通过89纯测和独立源码审查，尚未运行。

原图三故障×插桩开关计时对照已实际启动，共享600秒。待ACK时减少完整观察的独立候选通过39纯测和保存请求回放，仍需真实native前后轨迹、封印及计时检验。整体三项目标仍未宣布达标。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NEXT_ACTION.md').open('a',encoding='utf8') as f:
    f.write('\n\n## 最新执行次序（milestone014）\n\n'+'\n'.join(f'{i+1}. {x}' for i,x in enumerate(state['next_actions'][:4]))+'\n')
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:
    f.write('\n\n## 44. 全天封印与完整保护、历史拟合与在线作用分别取证\n\n2×原流取得H86400封印只解决运行覆盖，业务效果和逐件保护仍待完整保存审计。初始010/later003守卫修复与历史精确拟合支持在线测试，不证明联合优势；普通坐标与四固定窗口强基线保持。cap3校验字段错误单独登记，旧失败不覆盖，cap8未知不删除。\n')
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in files},'after_sha256':{n:sha(DOC/n) for n in files},
 'active_native_sessions':[40149,49602],'scope':'Actual full2x H86400 native seal, failed repeat verification, prepared guarded online and pendingACK candidates. Three overall requirements remain unachieved.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
