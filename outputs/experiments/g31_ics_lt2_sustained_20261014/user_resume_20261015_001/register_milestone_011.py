"""Preserve actual timeout and separately register verified same-binary restart."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC=ROOT/'docs/g31_ics_circulation';HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
report=HERE/'milestone_011.json';backup=HERE/'before_milestone_011'
assert not report.exists() and not backup.exists()
pins={
 'original_route_eligibility_independent_actual_review_001.json':'fc397721618ddc80cfeeaabecb698352612dc0684c8cfc32e56312edc8e4200d',
 'full024_chained_cut_2x_20261015_002/cut_manifest.json':'9755eb2238163ef42696bed28fa33c2c53ef384bb22c8fecde16be5a7fd5c43d',
 'full024_chained_cut_2x_20261015_002/source_stop_receipt.json':'2f3f3f08b50ec447a8127c13ebf26ea24548d53630ac13fee93ff06ea438d1f4',
 'full024_chained_cut_2x_20261015_002/dispatch_ready.json':'3d5cc6101642537e5e279f555700323dee0d2b0fd50addeb997fca7bb196c4ca',
 'full024_chained_cut_2x_20261015_002_independent_metadata_review.json':'9699434bdb7a39dd554427d52685ccbbf5369e4c911a265f4f9c064751b85195',
 'user_resume_20261015_001/full024_chained_2x_terminated_observation_001.json':'646b5aa756e5eac744acda593c5c4a8b1928cbe50b6dd1f07c0089461c3f4ab5',
 'user_resume_20261015_001/active_process_identity_006.json':'1aa19f27da9f76a847419cccf7e88c10b47772b81c19f340c4e2e56276c70fad',
}
for n,d in pins.items():assert sha(OUT/n)==d
old=OUT/'full024_chained_2x_20261015_001';receipt=read(old/'receipt.json');heartbeat=read(old/'heartbeat.json')
assert receipt['status']=='hard_timeout' and receipt['source_changed']==[] and receipt['wall_seconds']==7200.507854700001
assert heartbeat['physical_time']==82624.81314999794 and heartbeat['offered_by_current_time']==57012
for n in ['receipt.json','heartbeat.json']:pins['full024_chained_2x_20261015_001/'+n]=sha(old/n)
current=OUT/'full024_chained_2x_20261015_002';current_bytes=(current/'receipt.json').read_bytes();active_receipt=json.loads(current_bytes)
assert active_receipt['status']=='running' and active_receipt['hard_timeout_seconds']==7200
files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md'];backup.mkdir()
for n in files:(backup/n).write_bytes((DOC/n).read_bytes())
snap=HERE/'milestone_011_full2x002_running_receipt_snapshot.json';snap.write_bytes(current_bytes)
s=read(DOC/'RESEARCH_STATE.json');a=s['active_experiment']
a['chained_resume_status']='Chained001 actual hard_timeout7200.5078547s/source_changed[]. Last published510/H82624.81314999794/all57012arrived; latest actualseal496/H79200=7000702d5a400775920e6c350c55e62d2de2d564b2bb6b0f241d55f3eb93b29b. Exact oldparent30620/worker25980 absent. Newcut002497sealed/14excluded,2198.5079853s prior reconstruction+all latest priorcosts retained. Same024002 worker21344/parent19316 actualstart14:35:55,hardcap16:35:55,exec40149. Full native known-seal reconstruction currently pending;49sources remain frozen. Initial paused-running ancestor has no final source-drift report, explicitlyunknown.'
a['original_caller_route_probe']+=' Eligibility independent actual review001 now passed all3 prefixes/request tapes/cold envelopes. No native/physics cost deducted; measured wall intervals alone do not classify isolated complete computation. New internal-deadline design retains all accounting.'
s['current_stage']='Same024 full2x chained002 reconstructing497shards after genuine001timeout; no full2x final outcome yet. Three-cycle original execution and finite joint causal effects independently reviewed; reusable cap3/cap8 owner-local policy and genuine internal deadline candidate in development. Three overall requirements remain unmet.'
s['next_actions'][0]='Keep same024 full2x002 within7200s from14:35:55 to16:35:55;49frozen runtime sources,knownH79200seal gate,allpriorcosts. At most2 actualnativeworkers. IfH86400producerfiles exist afterterminal, use independently reviewed chainedaudit; otherwise preserve failure and selectactualseal.'
a['pending']=s['next_actions'];write(DOC/'RESEARCH_STATE.json',s)
p=DOC/'NEXT_ACTION.md';t=p.read_text(encoding='utf8').replace('## 最新执行次序（milestone010）','## 最新执行次序（milestone011）')
t=t.replace('1. 原始2×同024仍遵守14:30:05的7200秒上限；终止后核对准确父子进程缺席，再从最新实际seal续跑，保留祖先重建和未封存尾段成本。不可直接换026或把运行中尾片当checkpoint。','1. 原始2×chained001实际7200.5078547秒超时，49来源未变；全部57012已到达，最后发布H82624.81315，已知seal仍H79200。确认旧父子退出后，新同024 chained002从497片重建，14尾片和2198.5079853秒祖先重建及其他费用保留。实际worker21344在14:35:55启动，16:35:55硬截止；封印校验仍在进行，不把运行中前缀当全天完成。')
t=t.replace('独立实际审查和开销归因继续，不减掉慢阶段声称100ms。','独立实际审查现已通过；开销归因和新内部deadline方案继续。温态/全campaign是保守墙钟界，不替代含真实复验的完整计算计时，也不减掉慢阶段声称100ms。')
t=t.replace('user_resume_20261015_001/milestone_010.json','user_resume_20261015_001/milestone_011.json');p.write_text(t,encoding='utf8')
note='''

## milestone011：第二次同024封存续跑，未改写超时

chained001在7200.5078547秒实际超时，最后发布H82624.81315且57012件已全部到达；最近封印仍H79200。旧父子进程准确缺席核对后，新cut002绑定497封存片、14排除尾片和全部费用，独立小元数据核验通过。新002实际14:35:55开始，16:35:55硬截止；当前先做真实全前缀重建，未认证全天结果。最初暂停的running祖先没有终态source_changed字段，明示未知，不能伪造为空。eligibility负结果独立实际复核通过；完整计算、逻辑等待与保守全墙钟界继续分列。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 41. 完整计算与保守墙钟界的范围\n\nLT2 §9.1要求完整请求计算及最大连续服务段，并另列排队、消息等待、物理推进和端到端。当前原图probe的全部campaign按根全额计入是保守敏感性上界，超过100ms本身不是已隔离的计算超限证明；同样不能删除源端/接收端真实复验或未归因间隔来认证100ms。内部唤醒优化须保留这些口径。\n')
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'active_receipt_snapshot':{'path':str(snap.relative_to(OUT)),'sha256':sha(snap)},'before_sha256':{n:sha(backup/n) for n in files},'after_sha256':{n:sha(DOC/n) for n in files},'native_session_id':40149,'scope':'Actual timeout,exactabsence,samebinaryrestart; pending fullreconstruction and full2x outcome. No certification or publication.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
