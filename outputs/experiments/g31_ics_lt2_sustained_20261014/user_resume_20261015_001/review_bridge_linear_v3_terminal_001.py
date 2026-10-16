"""Small terminal/progress read only; no full raw/API decode or replay."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
HERE=Path(__file__).resolve().parent;OUT=HERE.parent;ROOT=HERE.parents[3]
source=OUT/'bridge_saved_linear_v3_prepare_001';dest=OUT/'bridge_saved_linear_v3_terminal_review_001'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
assert sha(source/'plan.json')=='4bbf6f364ac097db7fbf2bd1ff35f9ea74500566f367933e552bf6da6f0bd87e'
assert sha(source/'external_application_wall.json')=='277e2c8371e1016600629c0f68536c9f650e5332a48e32f1d0493cae70545a7a'
plan=read(source/'plan.json');bounded=read(source/'bounded_execution.json');outer=read(source/'external_application_wall.json')
assert bounded['process']['status']=='hard_timeout' and outer['exit_code']==1
assert not (source/'report.json').exists()
for name,digest in plan['source_before'].items():
    assert sha(name)==sha(source/'source'/Path(name).relative_to(ROOT))==digest
rows=[json.loads(line) for line in (source/'progress.jsonl').read_text(encoding='utf8').splitlines()]
assert len(rows)==271 and [r['record'] for r in rows]==list(range(271))
first=rows[0]['at_ns'];last=rows[-1]
assert last['event']=='api_replay_progress' and last['completed']==last['old_prefix_completed']==18688
stages=[{'name':r['stage'],'milliseconds':r['elapsed_ns']/1e6,'record':r['record']} for r in rows if r['event']=='stage_end']
api=[r for r in rows if r['event']=='api_replay_progress']
blocks=[{'completed_before':a['completed'],'completed_after':b['completed'],
         'seconds':(b['at_ns']-a['at_ns'])/1e9} for a,b in zip(api,api[1:])]
record={'schema':'g31.bridge.linear_v3_terminal_small_review.v1',
    'status':'unknown_full_saved_audit_timeout_preserved','recorded_utc':datetime.now(timezone.utc).isoformat(),
    'references':{name:{'path':str(source/name),'sha256':sha(source/name)} for name in
        ('plan.json','external_application_wall.json','bounded_execution.json','progress.jsonl','stdout.log','stderr.log')},
    'live_archive_sources_unchanged':len(plan['source_before']),
    'whole_python_application_seconds':outer['whole_python_application_seconds'],
    'owned_process_status':bounded['process']['status'],'whole_fixed_seconds':600,
    'log_records':len(rows),'log_limit':1024,'journal_limit_not_exhausted':True,
    'completed_stages':stages,'last_progress':last,'log_span_seconds':(last['at_ns']-first)/1e9,
    'last_complete_logged_replay_prefix':18688,'required_new_rows':37270,'required_old_prefix_rows':27218,
    'slowest_logged_256_call_blocks':sorted(blocks,key=lambda r:r['seconds'],reverse=True)[:5],
    'missing_terminal_files':[n for n in ('report.json','failure.json','instrumentation_failure.json','all_job_states.json.gz')
                              if not (source/n).exists()],
    'interpretation':'Logging bug is bypassed, but complete_policy_replay was still running at the shared600 censor. Last logged18688 is a completed-prefix lower bound, not the exact final in-flight call. No complete physical/FIFO/storage/alloffered certificate is available.',
    'cost_hypothesis':'Late replay blocks combine decompression, old-prefix comparison, actor deepcopy and policy work. Current recursive ordered comparator is Python code; original double JSON encoding may exploit C. Block intervals do not isolate a function. Measure bounded representative row operations before changing another full audit.',
    'next_diagnostic_only':'Consider fixed saved old/new row pairs for exact recursive-vs-original-C comparison and actor-copy cost; keep original comparators and all scalar/order semantics. No general speed claim or budget extension.',
    'big_raw_or_API_reads':0,'native_calls':0,'predictor_calls':0,
    'original_2400_and_prior_600_and_linear001_failures_unchanged':True,
    'producer39_fullH_claim_upgraded':False,'overall_goals_completed':False,
    'producer_script':{'path':str(Path(__file__).resolve()),'sha256':sha(__file__)}}
dest.mkdir(exist_ok=False)
with (dest/'report.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2,allow_nan=False)
print(json.dumps({'report_sha256':sha(dest/'report.json'),'stages':stages,'last_logged_replay':18688}))
