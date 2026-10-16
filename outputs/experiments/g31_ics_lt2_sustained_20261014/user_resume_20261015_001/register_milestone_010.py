"""Register actual finite progress and the unsuccessful early-wakeup trial."""
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
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

report, backup = HERE/'milestone_010.json', HERE/'before_milestone_010'
assert not report.exists() and not backup.exists()
pins = {
 'original_low_wip_third_independent_actual_review_001.json': 'a86f11070293e70f0a42d5dba4b6cd1d21005847be05e3b839e7778a02d92a3c',
 'native_preference_matrix_native_001_independent_audit.json': '6347a357c5a4537b1f81f8bfde061340a0e5f454ce536f45c0dc62010636fc5c',
 'native_preference_matrix_native_001_mechanism_diagnosis.json': '8f17d28ce0f23e16c485f87eed354d3abe8409e7462784f922db4d0669f3076c',
 'original_route_update_independent_actual_review_001.json': 'e1a2f284799dfed976a44f0786a19a8faf655d329b52b08f0f52237498c40af7',
 'original_route_eligibility_prepare_001/external_launch_receipt.json': 'bd148e4e6a0d52c73daaa272d2744a4c18cdfa5d8f7d4483778b6ebd5f579854',
 'original_route_eligibility_prepare_001/root_source_review_001.json': '3a2b07fb2bbf593f2003b0841548a57338e88af5d8875103cc4e2b7e48e326f8',
 'original_route_eligibility_independent_source_review_001.json': '5e9c95d7a2cecfe44e8fd4d6ec5aaa660bd5f7de96702f92352f4f182d7e46c1',
}
for name, digest in pins.items(): assert sha(OUT/name)==digest
third, matrix, mechanism, route = [read(OUT/name) for name in list(pins)[:4]]
assert third['status']=='passed_saved_actual_third_cycle_review' and third['offered']==28506
assert matrix['status']=='saved192_revalidated_no_new_native' and matrix['new_native_executions']==0
assert route['closed_roots']==2 and route['open_roots']==1 and not route['complete_100ms_certified']
candidate = read(OUT/'original_route_eligibility_prepare_001/receipt.json')
verified = read(OUT/'original_route_eligibility_prepare_001/independent_verification.json')
assert candidate['status']=='completed_finite_probe' and candidate['source_changed']==[]
assert verified['closed_roots']==2 and verified['open_roots']==1
assert verified['cases']['baseline']['warm_elapsed_upper_ms']==1049.5904
for name in ['receipt.json','independent_verification.json']:
 relative='original_route_eligibility_prepare_001/'+name; pins[relative]=sha(OUT/relative)
heartbeat_bytes=(OUT/'full024_chained_2x_20261015_001/heartbeat.json').read_bytes()
heartbeat=json.loads(heartbeat_bytes)
files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md']
backup.mkdir()
for name in files: (backup/name).write_bytes((DOC/name).read_bytes())
(HERE/'milestone_010_full2x_heartbeat_snapshot.json').write_bytes(heartbeat_bytes)
state=read(DOC/'RESEARCH_STATE.json'); active=state['active_experiment']
active['startup_low_wip_candidate']='Third001 independently reviewed:14600 saved API,25 received physical ACK, same token jobs2/6/8 LOAD-UNLOAD-HOLD, all28506 and22trays retained. Third peer-selected loader49/job8; source26 next FIFO job14 unreachable retained. Third completes21759.803 at international owner46. Prior two cycles exact; H28800/8740 arrived/3 completed. Strict protection not assessed. Next reusable owner-local cycle design, not automatic fourth authority or39-achievability claim.'
active['planning_v3_status']='All192 fixed-action native vectors executed:174 assessed18unknown;192 physical audits and five-job completion pass;5/12 full16-member reference families complete. Complete block1_load2 family improvement4.1s protects all5 but later actions default. Registered block1_load1 quartet/subcube has initial release/R2 occupancy/later7-to8 receiver improvement. Ordinary coordinate search also follows strictly improving paths, and full reference families incomplete. Prior bound60 strong online choices were already faster than new cube; fix actual default/preference/dispatch semantics, not claim missed utility or novelty.'
active['original_caller_route_probe']='Original three-fault actual independently reviewed:closed320.6656/1535.1397ms warm,open28381.2882ms prefix; whole campaign94720.0027ms charged fully per root. Early-eligibility trial actual passed verifier with same fresh-view guard and true9603.5 boundary, but slower1049.5904/2768.9834ms warm; open38942.2021ms/5attempts. Full candidate campaign156842.8145ms retained, extra independent actual audit pending. Diagnose measured added-boundary/export costs; no100ms claim.'
state['current_stage']='Three overall requirements remain unmet. Independently verified original three-cycle same-token execution and finite strict five-job joint effects; strongest reference/online novelty remain unproved. Earlier legal wakeup worsened full elapsed timing; retain negative and diagnose. Full2x024 unchanged7200s cap; current state only heartbeat snapshot, not full result.'
state['next_actions']=[
 'Full2x024 current cap14:30:05 unchanged. At actual terminal preserve receipt and verify exact parent/worker absence, then continue same024 from latest known seal if incomplete. No direct binary migration; all ancestor/tail costs retained.',
 'Develop bounded reusable owner-local same-token return/peer-FIFO policy after independently audited third cycle; actual current owner46, no remote action payload inference, no unreachable head skipping, full28506/22trays retained.',
 'Calibrate default/preference/actual dispatch model against saved192; old strong online method already beats new diagnostic cube. Compare future public-only fix with equally informed coordinate search; retain unknown references.',
 'Independently audit eligibility negative, measure added boundary/export gaps. If evidence supports, new isolated internal public-deadline controller extension with actual native deadline logging, no response rewrite, old49 sources frozen.',
 'Run chained saved-horizon audit only once actualH86400 complete manifest and terminal receipt exist; no running-prefix full-day claims.',
 'Keep failures, source pins and full costs; run relevant current zero-skip regression at coherent freeze. No commit,push or GPTPro send without instruction.'
]
active['pending']=state['next_actions'];write(DOC/'RESEARCH_STATE.json',state)
text=(DOC/'NEXT_ACTION.md').read_text(encoding='utf8'); start=text.index('## 最新执行次序');end=text.index('## 恢复初期队列')
current='''## 最新执行次序（milestone010）

1. 原始2×同024仍遵守14:30:05的7200秒上限；终止后核对准确父子进程缺席，再从最新实际seal续跑，保留祖先重建和未封存尾段成本。不可直接换026或把运行中尾片当checkpoint。
2. 第三次供给已独立通过14600API、25真实收到ACK和所有物理记录复核：同盘完成job2/6/8，第三次由真实peer FIFO选择49，21759.803在international节点46返空。全部28506业务与22盘保留；26下一不可达FIFO头未跳过。推进可重复owner-local周期，不把三次成功推广成39次可达或全天保护。
3. 192实际分支全执行，174assessed/18unknown；全部物理审计与5件完成通过，只有5/12完整参考族。完整族4.1秒收益的后续动作都是default。另一有限子立方体有R1释放→R2占位→后续实际改路收益，但普通坐标搜索同样解释、完整参考族不齐。旧强在线方法实际更快，下一步修正default/preference/真实dispatch语义，不能制造遗漏收益。
4. 完整原图请求原probe为320.6656/1535.1397毫秒温态闭合，持续缺ACK保留open；完整campaign94720.0027毫秒全额计入每根。提前合法观测新probe真实执行通过，但温态恶化到1049.5904/2768.9834毫秒，open38942.2021毫秒、5尝试。全campaign156842.8145毫秒保留；独立实际审查和开销归因继续，不减掉慢阶段声称100ms。
5. 链式全天审计新模块已纯测；须终态和完整H86400 manifest后才扫描。原1×全天仍0完成，原超时回执和最终seal未独立重放的限制不变。
6. 路径缓存/字节缓存负结果和浅复制负尾继续保留。源码冻结后做相关零skip回归，尚无提交、推送或GPT Pro发送。

最新证据索引`user_resume_20261015_001/milestone_010.json`。三项总目标仍未达标；有限机制进展与负结果同时保留。

'''
(DOC/'NEXT_ACTION.md').write_text(text[:start]+current+text[end:],encoding='utf8')
note='''

## milestone010：第三次真实完成、有限联合效果与计时负结果

第三门14600API/25实际ACK独立复核通过，同盘job2/6/8均实际完成并返空，当前owner46；仍无全天保护。192分支全部执行，174assessed/18unknown，只有5/12完整参考族。完整族4.1秒保护收益与后续default相伴；另一个子立方体存在真实后续改路收益，但普通坐标搜索也可解释，旧强在线选择还更快，不宣称创新。首次合法唤醒从9660前移9603.5，却将正常温态请求从320.6656ms增加至1049.5904ms；全部campaign与未完成根保留，继续做实际开销归因和独立内部deadline设计。三项整体目标未降低。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:f.write('\n\n## 40. 有限因果效果不等于超过强参考\n\n192矩阵存在可审计R1释放、R2返空占位、后续实际改路的逐件保护子例；普通坐标搜索存在严格改善路径，且旧强在线方法在该case已选到更快结果。完整参考族4.1秒改善则不含后续主动改路。两者不能拼成联合创新证明。更早逻辑唤醒却更慢的墙钟结果完整保留，不能用模拟时间提前替代完整请求100ms。\n')
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in files},'after_sha256':{n:sha(DOC/n) for n in files},'full2x_snapshot':{'path':'milestone_010_full2x_heartbeat_snapshot.json','sha256':sha(HERE/'milestone_010_full2x_heartbeat_snapshot.json'),'latest_native_seal':heartbeat['latest_native_seal']},'scope':'Actual finite results and independent audits; eligibility further independent actual review pending. No goal certification or publication.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
