"""Record actual repeat dispatch and retrospective exact projection evidence."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
DOC = ROOT/'docs/g31_ics_circulation'
HERE = Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
report=HERE/'milestone_013.json'; backup=HERE/'before_milestone_013'
assert not report.exists() and not backup.exists()
pins={
 'original_low_wip_repeat_prepare_001/ready.json':'822cc0e73d71a2c44efcc36618fcc11941c350b54c9621fda3081a6d8a8f4ca4',
 'original_low_wip_repeat_prepare_001/campaign.json':'7197497fc08ffa9b7ce0bc853ded3565545b56746d1d434019a1aea19d3d1551',
 'original_low_wip_repeat_prepare_001/root_source_review_001.json':'66bdf32fd44280f39bd112b139b26e54bda400cf92de8c84ef804173db8bcdf7',
 'original_low_wip_repeat_prepare_001/independent_source_review_001.json':'cf43bdc8d0f6e076e5d824c8cc8c8d9de0b5e4637bc1df8daec784a673f7a518',
 'user_resume_20261015_001/active_process_identity_007.json':'730fdc5daab9bb93fbc3e86b05937c3cfe46d62cffb906b7fd3f1fbfdadf9309',
 'public_native_preference_projection_validation_008.json':'f24bb52bbaad00c75c73e2db3f2c9d757945c3bdbdabf74411c535c2b9623ebd',
 'public_native_preference_projection_validation_008_source/receipt.json':'b1d60b40616fc9261cc9b71657c5b975899993f1bb7e97d6ec39f10b200ceb61',
 'public_projection_008_profile_001/report.json':'f6e1ab9acf4dc4068be6238b72bf127de8bd90359fb7a9e65aad248a1d05005a',
}
for n,h in pins.items(): assert sha(OUT/n)==h,n
for n in ('public_native_preference_projection_arithmetic_diagnosis_001.json',
          'public_native_preference_projection_wording_correction_001.json',
          'public_native_preference_projection_pure_005.xml'):
    pins[n]=sha(OUT/n)
validation=read(OUT/'public_native_preference_projection_validation_008.json')
rows=list(validation['rows'].values()); admitted=[r for r in rows if r['authority_valid_counterfactual_comparison']]
assert len(rows)==192 and len(admitted)==174
assert all(r['all_ordered_edge_entries_and_times_match'] and r['all_five_completion_doubles_exactly_match']
           and r['command_set_and_status_match'] and not r['model_protection_certified'] for r in admitted)
assert all(not r['unknown_promoted'] for r in rows)
xml=ET.parse(OUT/'public_native_preference_projection_pure_005.xml').getroot()
assert all(s.attrib['failures']==s.attrib['errors']==s.attrib['skipped']=='0' for s in xml.iter('testsuite'))
files=['RESEARCH_STATE.json','NEXT_ACTION.md','RESUMPTION_20261015.md','NOVELTY_LEDGER.md']
backup.mkdir()
for n in files:(backup/n).write_bytes((DOC/n).read_bytes())
state=read(DOC/'RESEARCH_STATE.json'); active=state['active_experiment']
active['repeating_low_wip_status']='Actual repeat001 dispatched15:12:23.63537, exec77481, outer36008/campaign37104/initialcap3worker35372. Caps3/8 are cumulative SUPPLY, bothonecirculatingtoken, original28506/22/R1false/H86400. Shared2400s ownWindowsJob includes two sequential cases and verification;72sources frozen. 44pure and independent source/rootpreflight passed. No actual pair result yet. Non-token owner postcap full-view loop is a source-diagnosed possible cost; separate candidate only, no current change/extension.'
active['public_preference_projection_status']='Retrospective008: all174 admitted192 native branches match ALL ordered EDGE_ENTER identities/times, commandstatuses and870completion doubles exactly.18unknown retained. Source-derived individual wire additions and JIT max(now,earliest_start(now+travel,service)-travel) arithmetic; no rounding/nextafter/protectionepsilon.24pure. Usedforsemanticdebugging, not unseen holdout. No actual online or later-state proof yet.'
state['next_actions'][1]='Keep actualrepeat001 withinshared2400s,72sourcesfrozen, caps3/8serial; independentactualreview onlyafterwholeJobterminal. Preserve incompletearms. Diagnose postcapidlefullviews in separate source-onlycandidate.'
state['next_actions'][2]='Use exact008 initialprojection as finite retrospectiveconformance; seed laterprojection from actualowned v3captures and validate separately before online60comparison. Samecandidatebudgets and strongbaselines; record~300ms32predictioncost beforecompleteprotocol.'
state['next_actions'][3]='Internaldeadline normal82.8126msfinitebound independentlypassed, fault1499.9973/openprefix33384.5651 retained. Prepare027 plain/timed sixcells withshared600Job, fullAPI/controller/commonseal parity and allunclassifiedphasecosts. Waitnative slot.'
active['pending']=state['next_actions'];write(DOC/'RESEARCH_STATE.json',state)
p=DOC/'NEXT_ACTION.md'; text=p.read_text(encoding='utf8').replace('## 最新执行次序（milestone012）','## 最新执行次序（milestone013）')
old=next(s for s in text.splitlines() if s.startswith('2. 第三次供给已独立'))
text=text.replace(old,old+' 通用cap3/cap8已于15:12:23实际启动，两臂串行共享2400秒Windows Job，包含核验；72来源冻结。当前没有实际配对结论，不延长原限。')
old=next(s for s in text.splitlines() if s.startswith('3. 192实际分支'))
text=text.replace(old,old+' 新008预测已精确匹配174已准入分支全部有序入边/时间、命令状态和870完成时刻；这是用于语义调试的回归集，不是未见验证。后续在线、later状态和全请求性能仍需实测。')
text=text.replace('user_resume_20261015_001/milestone_012.json','user_resume_20261015_001/milestone_013.json');p.write_text(text,encoding='utf8')
note='''

## milestone013：通用重复供盘实际启动；预测精确匹配仍限历史回归

通用cap3/cap8包经44项纯测、独立源码审查和根代理预检后，于15:12:23.63537实际启动。两臂保留原28506件、22盘、R1false、H86400，串行共享2400秒Windows Job（含核验），72源码冻结。准确身份见identity007；其中只读查询自身pwsh28016不是实验worker。cap3运行中发现一个开销问题：无循环盘的owner即使已有达到cap的真实ACK覆盖，也因判定顺序不能进入停止新供给的稳定状态，仍重复读取全视图。只准备单独候选，当前实验不改、不延限。

预测008按源代码恢复消息逐次加法和JIT合流时间表达式，精确匹配174已准入分支的全部有序EDGE_ENTER及时间、命令状态和870逐件完成double；18未知不提升。24项纯测通过。192记录曾用于诊断和修正语义，因此明确为回归验证，旧held-out措辞另存更正而不覆盖原件。

单候选记录约6.5–14.8毫秒不代表完整请求100ms。一次32候选纯剖析含剖析器开销0.569秒，发现重复构造场景、合同和路径势函数及事件推进都占时间；只用于定位，不能当稳定性能值。后续可复用单次请求公共上下文，但全部构造/复验费用仍须计入、候选预算不缩减。
'''
with (DOC/'RESUMPTION_20261015.md').open('a',encoding='utf8') as f:f.write(note)
with (DOC/'NOVELTY_LEDGER.md').open('a',encoding='utf8') as f:
    f.write('\n\n## 43. 精确回归不能替代未见在线效用\n\n008对174已准入历史分支的870完成时刻及全部入边轨迹精确匹配，无epsilon；这些记录用于过语义调试，不能称未见/统计holdout。旧强在线方法更优和普通坐标方法可解释收益的结论不变。下一门是合法later状态投影和同预算在线比较，不因模型贴合历史就宣称联合创新或保护证明。\n')
write(report,{'schema':'g31.resume_milestone.v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'immutable_evidence':pins,'before_sha256':{n:sha(backup/n) for n in files},'after_sha256':{n:sha(DOC/n) for n in files},
 'active_native_sessions':[40149,77481],'scope':'Actual bounded repeat dispatch; retrospective exact model conformance and profiling diagnosis. Three overall requirements unmet. No publication.'})
print(json.dumps({'state_updated':True,'milestone_sha256':sha(report)}))
