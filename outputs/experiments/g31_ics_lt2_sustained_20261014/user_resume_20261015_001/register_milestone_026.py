"""Preserve actual failures, bounded logging gain and fresh96 denominator."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]; OUT=HERE.parent
DOC=ROOT/'docs/g31_ics_circulation'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
pins={
 'initial_owner_route_campaign_prepare_002/root_failure_readback_001.json':'ef4703fd3a36b3587115b249369d5f16b66a1ece1c143ab56983521eca5de7de',
 'initial_owner_route_campaign_prepare_002/external_application_wall.json':'12d29ffd03f3d6f9bff3944c594c230887d796c76e32008ce14d5ad5b813acf7',
 'serialize_once_tape_prepare_001/result.json':'7efe2da12e641372f2995777be3f7a3f5529501512597e8cfe879f84d898b021',
 'serialize_once_tape_prepare_001/external_application_wall.json':'9868f8526061a276e0bf4728f578dab38ea8c3d20d2cca62e013de7f684f1daa',
 'serialize_once_tape_independent_readback_001/review.json':'d0da53e99de8b4e81d55ac3b1287821caef3345772ce3eacc2cbbcd360c79349',
 'live_obligation_recollection_native_prepare_001/preregistered_protocol.json':'9b5d2cc047a0c75cdde4d916542728b491dccc71c09cf026720aad9c135dea98',
 'live_obligation_recollection_native_prepare_001/receipt.json':'c39e537d40b5a1dbcc09359aad490ffc266e286d41af7d658c769faf9643b8a5',
 'live_obligation_recollection_native_prepare_001/branch_ledger.json':'29c55edf3b1d1c16c3644c2af31f109eb8e7538aeef4517eb8e837419899c01a',
 'live_obligation_recollection_native_prepare_001/run_acceptance.json':'31dd7d4a8f1cbc13bac902ff0088ec724dffcf2a48e893588f381a5858675f16',
 'live_obligation_recollection_native_prepare_001/external_application_wall.json':'3c9c5d2cc6db448a91ceacd33ee218ac7a0e54af4bf84e2fef43fc0db30201be',
 'original_bridge_serialize_once_prepare_001/campaign.json':'d976e7f2d473e64ddb4e11895c06bfb9f21a11b43133babb71cd02491bb94464',
}
for path,digest in pins.items(): assert sha(OUT/path)==digest,path
native=read(OUT/'live_obligation_recollection_native_prepare_001/receipt.json')
assert native['branch_count']==96 and native['status']=='completed_with_unknowns'
assert sum(v['assessed'] for v in native['comparisons']['cases'].values())==52
assert sum(v['unknown'] for v in native['comparisons']['cases'].values())==44
parent=ROOT.parent/'cpp/ics_core/runtime/bounded_local_pibt.hpp'
assert sha(parent)=='b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951'
backup=HERE/'before_milestone_026'; receipt=HERE/'milestone_026.json'
assert not backup.exists() and not receipt.exists(); backup.mkdir()
names=('RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md')
for name in names: (backup/name).write_bytes((DOC/name).read_bytes())
state=read(DOC/'RESEARCH_STATE.json'); active=state['active_experiment']
state['current_stage']='Fully resumed. Initialowner actual002 failed strict JSON boundary (26.2657979s,18raw/0serializedroots); all evidence retained. Serialize-once fixed8 ABBA32 mock tapes exactly match ordered saved content and clocks, local bundle68.1143% lower cost,39.1831113s whole; not native/fullH/100ms. Fresh recollection actual96 closed246.9393125s with52assessed44unknown; all6reference families incomplete. Native tuple vs JSON list current-view equality causes false online retry rejection and saved replay mismatch; independent versioned fix being prepared, old sources/results immutable. New same-policy original026 logging-only bridge prepared, not dispatched. All3overall goals remain unmet.'
active['initial_owner_actual002_failure']='Owned18 campaign external26.2657979s,accepted run closed invalid[]. Firstdefault final bundle encode and firstbudget2 packet encode reject json_non_builtin; savedJSON replay also reveals integer resources keys. Firstbudget2 fails before RPC pipewrite and aborts predictor; remaining16 lack live predictor authority.18raw but0serialized root returns; finalclose RPC_already_closed; no verification or100ms result. Old124/image untouched. Versioned boundary repair retains real collector/ledger/session, root failure clocks and aborted cleanup. Its firstpreparedv2 source review found bool lifecycle clocks and missing-raw branch clocks insufficiently checked; new source revision required before actual rerun.'
active['serialize_once_tape_actual']='Fixed8 complete old bridge rows27210..27217,ABBA32 mock replay calls,71source pins/48pure. Legacy median1348.05595ms vsnew429.83695ms including equalmockdeepcopy,Tape,gzip/hash/manifest,clock;68.1143% lower,3.1362ratio. All32 exactordereddecoded rows and clocks independentlyverified, no native/predictor calls. WholePython39.1831113s. Local result is not native speedup or fullH forecast. New82source93pure bridge prepared at original2400 budget, all28506/22/H86400 and39/78/100 unchanged; full saved policy/physical audit and old27218 prefix comparison charged inside budget.'
active['native_fresh96_actual001']='96 actual branches completed, external246.9393125s/worker245.8118423s,run acceptance closed invalid[],82source unchanged.52assessed/44unknown_failed; bycase16/16,22/10,14/18. All6complete16 reference families remain unknown. Firstknown mismatch: online actual view has native node/edge tuple while sealed raw endpoint JSON view has lists; wholeview== falsely rejects retry, saved JSON comparison differs. No old34/62 promotion and no newmodel protection or optimizer certificate. Independent all96 saved diagnosis and versioned actual-source fix underway; no samepackage restart.'
state['next_actions']=[
 'Close independent fresh96 saved diagnosis; implement separate versioned tuple/list representation comparison under unchanged real native seal and all current/action/ACK/window guards. Test actual binding shapes across live-to-JSON boundaries, prepare same96/600 fresh campaign.',
 'Complete initial-owner versioned strict builtin normalization and failure-clock audit fixes, source review and pure gates. Run fixed18 actual root benchmark only in exclusive native/pure/IO window, retaining all failed/open roots and unamortized cold costs.',
 'Root-review and dispatch prepared same-policy serialize-once original bridge after request latency window. Keep original2400 shared budget, all fields/28506denominator/physical constraints and full saved+oldprefix audit; no fullH promise.',
 'Continue toward full32 complete-request100ms and strict same-information/budget joint-method effectiveness. Finite2 integration and local logging improvements are intermediate evidence only.',
 'Preserve every failure, unknown, old source closure and history. No commit,push,external message or GPTPro send authorized.'
]
active['pending']=state['next_actions']
(DOC/'RESEARCH_STATE.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
(DOC/'NEXT_ACTION.md').write_text('# 当前执行入口 — milestone026\n\n全面恢复继续有效。日志固定8条ABBA实测保存成本下降68.1143%，内容和时钟独立核验一致，尚非全天或100ms结论。新96实际耗时246.9393125秒，52可审计、44未知，完整参照族仍缺失。真实原生tuple与落盘list的表示差异在两条集成链暴露；先做独立版本修复和原生形状测试，不把JSON测试当真实运行。原流新日志包已准备，待完整请求独占实测后派发。三个总目标均未达标。\n\n'+'\n'.join(f'{i+1}. {v}' for i,v in enumerate(state['next_actions']))+'\n',encoding='utf8')
note='''

## milestone026：保存成本实测改善，真实接口问题与新96未知完整保留

initial_owner_route_campaign_prepare_002实际18分支在26.2657979秒结束。run acceptance通过且18raw都保留，但首default在final bundle编码、首budget2在RPC发送前packet编码遭json_non_builtin；其后predictor已abort，剩余16构造没有fresh process authority。保存JSON重建能复现整数resources键，却不能证明原来的tuple类型；tuple必须从accepted027 binding节点/边记录源码形状构造。root evidence相同strict codec导致没有保存完整root返回，final close又遭RPC_already_closed。此轮没有完整请求100ms结果，不能以18raw或closed acceptance冒充18请求成功。根保存审计ef4703fd…确认原124源码及raw；失败记录不覆盖。

无损serialize-once Tape的独立固定8条实测采用ABBA共32次mock调用，0native/0model。旧两批1365.777/1330.3349ms，新439.2606/420.4133ms，中位数1348.05595→429.83695ms，保存bundle降低68.1143%，比率3.1362。32输出逐字段顺序、gziphash、clock读回核验全通过；外Python39.1831113秒包括准备/保存核验/导出。该数字只属于固定8条mock+Tape完整保存路径，不能外推native整体、全天或100ms。新原流日志包保持原76源码和全部策略/节拍/物理字段，新增82来源/93纯测试；39/78/100、28506jobs/22trays/H86400与2400预算不变。完整saved策略/物理审计及旧27218完整API前缀比较也纳入同预算，旧超时无效行保留且不修复。

live_obligation_recollection_native_prepare_001已完成实际96分支，外Python246.9393125秒，worker245.8118423秒，accepted run正常关闭、invalid空、82源码无变化。52assessed/44unknown_failed：mechanism16/16、no_overlap22/10、insufficient14/18，六个完整16成员参照族全unknown。初步源绑定定位是NativeCollectionAttempt保存raw view时JSON化node/edge tuple为list，而实际policy当前view仍含tuple；直接整dict==拒绝not_the_collected_current_view，保存后两边变list又使retry_screen_replay不同。这是实际接口表示缺陷，不是允许放宽当前状态、ACK union或服务窗口。旧96的34/62仍不变；新52/44也原样保留。正在独立全96保存诊断，再以新版本和同96/600预算验证，不能靠修保存数据把在线从未发生的补采算成功。

初始请求v2源审还抓到失败生命周期时钟bool可充int、缺raw失败branch时钟未核验两处；未派发，要求新版本补exact非负int/顺序/elapsed和混合资源键拒绝。后续测试必须同时覆盖真实binding形状与JSON保存形状，避免同类问题循环。三个总目标继续未达标；不降低标准、不发送GPTPro。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f: f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f: f.write('\n\n## 56. 日志成本改善不等于方法实效，实际接口修复尚待验证\n\n固定8条ABBA日志bundle降低68.1143%是无损执行成本改进；不构成全天吞吐或联合方法新颖性。新96实际52/44且六参照族未知，补采因tuple/list当前view比较被错误拒绝。初始18实际编码失败，没有100ms结果。新版本必须先补真实binding形状与失败时钟校验；完整分母、严格保护、三目标不变。\n')
record={'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in names},
 'after_sha256':{n:sha(DOC/n) for n in names},'parent_user_file_sha256':sha(parent),
 'overall_goal_achieved':False,'new_native_dispatched_here':0}
with receipt.open('x',encoding='utf8') as f: json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'state_updated':True,'milestone_sha256':sha(receipt)}))
