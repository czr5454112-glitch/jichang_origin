"""Independent saved72 readback; no prediction, native or new benchmark."""
from pathlib import Path
import json,sys,time,statistics
from scripts.experiments.g31_ics_circulation import measure_single_root_evidence as m
from scripts.experiments.g31_ics_circulation import bounded_windows_job
c=m.c; source=c.OUT/'single_root_evidence_pair_prepare_002'
out=c.OUT/'single_root_evidence_pair_independent_review_002'
plan_sha='086dd891c9b60a2700045c5c75da0cd9d67776f541e1c8c9eb215f82d8ba36cf'
if '--child' in sys.argv:
 assert sys.stdin.readline()==plan_sha+'\n'
 plan=m.verify_pins(source,plan_sha)
 loaded_entry=c.check_loaded_sources(plan)
 pins={n:c.sha(source/n) for n in ('report.json','receipt.json','bounded_execution.json','external_application_wall.json','ledger.json')}
 assert pins['report.json']=='813215d1a5cc1be6361bf10c0a5c84e76cfe08234a5796c3fa12f6ee8fd93380'
 assert pins['receipt.json']=='d0c2826ccf7e7685da27c48047f9f841aa3dcf60da665ea59f5a827d4f34cd42'
 assert pins['external_application_wall.json']=='020ad158ecea9dbf49df247c41d53ecc6d446730726de0e3e579131df2f8e73a'
 external=c.read(source/'external_application_wall.json')
 assert external['status']=='application_exited_zero' and external['evidence_unchanged'] and external['whole_python_within_240_seconds']
 report=m.verify_saved(source,plan_sha)
 assert m.m.candidate.exact_tree(report,c.read(source/'report.json'))
 assert c.read(source/'receipt.json')['source_changed']==[]
 pairs=[]
 for key in plan['input_raw']:
  values={arm:[r['elapsed_ms'] for r in report['samples'] if r['key']==key and r['arm']==arm] for arm in ('A','B')}
  assert all(len(v)==2 for v in values.values())
  a,b=(statistics.median(values[arm]) for arm in ('A','B'))
  pairs.append({'key':key,'A_median_ms':a,'B_median_ms':b,'B_over_A':b/a})
 loaded_exit=c.check_loaded_sources(plan)
 assert pins=={n:c.sha(source/n) for n in pins}
 summary=report['summary_ms']
 result={'status':'passed_independent_saved18_ABBA72_readback','plan_sha256':plan_sha,
  'source_count':len(plan['source_sha256']),'all_original_roots':18,'saved_calls':72,
  'summary_ms':summary,'paired_root_medians':pairs,
  'all_sample_median_reduction_fraction':1-summary['B']['median']/summary['A']['median'],
  'source_unchanged':True,'source_artifact_sha256':pins,
  'loaded_sources_entry':loaded_entry,'loaded_sources_exit':loaded_exit,
  'whole_original_python_seconds':external['whole_python_application_seconds'],
  'scope':'Independent repeat of full saved row/hash/topology/type/order/clock-formula verification for all72 and original18 data. New comparison is solely actual mock evidence construction/return; old historical root clocks are fixture data.',
  'native_calls':0,'new_predictions':0,'new_benchmark_calls':0,'complete_native_request_100ms_certified':False,
  'producer':c.reference(__file__)}
 c.write(out/'review.json',result)
 print(json.dumps({'status':result['status'],'review_sha256':c.sha(out/'review.json'),'reduction':result['all_sample_median_reduction_fraction']}))
else:
 out.mkdir(exist_ok=False)
 script=Path(__file__).resolve()
 expression="from pathlib import Path; p=Path("+repr(str(script))+"); exec(compile(p.read_text(encoding='utf8'),str(p),'exec'),{'__name__':'independent_saved_review','__file__':str(p)})"
 command=[sys.executable,'-c',expression,'--child']
 began=time.perf_counter()
 with (out/'stdout.log').open('x',encoding='utf8') as stdout,(out/'stderr.log').open('x',encoding='utf8') as stderr:
  process=bounded_windows_job.run(command,timeout=90.,admission=plan_sha,stdout=stdout,stderr=stderr,cwd=c.ROOT)
 result={'process':process,'audit_wall_seconds':time.perf_counter()-began,
  'producer':c.reference(script),'native_calls':0,'new_predictions':0,'new_benchmark_calls':0,
  'scope':'Separate saved audit only; not deducted from or added as success to any original request measurement.'}
 c.write(out/'bounded_execution.json',result)
 print(json.dumps({'process':process,'review_sha256':c.sha(out/'review.json') if (out/'review.json').exists() else None}))
 if process['status']!='exited' or process['exitcode']!=0:raise SystemExit(1)
