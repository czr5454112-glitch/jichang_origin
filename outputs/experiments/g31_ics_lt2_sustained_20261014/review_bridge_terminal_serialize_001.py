"""Bounded small terminal metadata audit: no native, raw gzip or API payload reads."""
import time
BOOT=time.monotonic()
import hashlib,json,os,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
SOURCE=OUT/'original_bridge_serialize_once_prepare_001'
DEST=OUT/'bridge_serialize_once_terminal_partial_review_001'
CAMPAIGN='d976e7f2d473e64ddb4e11895c06bfb9f21a11b43133babb71cd02491bb94464'
EXTERNAL='95a682b80bb76d1788ae6c7f3ab522cfc44ca8a8d248308527b53bcc64b317a4'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def require(v,m):
    if not v:raise ValueError(m)
def write(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,indent=2,ensure_ascii=False,allow_nan=False)
def stat(p):
    if not p.exists():return {'exists':False}
    s=p.stat()
    return {'exists':True,'bytes':s.st_size,'created_utc':datetime.fromtimestamp(s.st_ctime,timezone.utc).isoformat(),
        'modified_utc':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat(),'ctime_ns':s.st_ctime_ns,'mtime_ns':s.st_mtime_ns}
def worker():
    require(sys.stdin.readline()=='bridge_terminal_small_001\n','job_admission')
    case=SOURCE/'bridge';campaign=read(SOURCE/'campaign.json');plan=read(case/'preregistered_protocol.json')
    external=read(SOURCE/'external_application_wall.json');launch=read(SOURCE/'external_launch_receipt.json')
    require(sha(SOURCE/'campaign.json')==CAMPAIGN and sha(SOURCE/'external_application_wall.json')==EXTERNAL,'fixed_terminal_identity')
    require(external['exit_code']==1 and external['whole_python_application_seconds']==2400.2095334 and
        launch['process']['status']=='hard_timeout' and launch['process']['windows_job_kill_on_close'] is True,'not_expected_terminal')
    require(sha(case/'preregistered_protocol.json')==campaign['case_plans']['bridge'],'case_plan')
    files={str(p.relative_to(SOURCE)):stat(p) for p in [SOURCE/'receipt.json',case/'raw_final.json.gz',case/'assessment.json',
        case/'worker_elapsed.json',case/'verification.log',case/'independent_verification.json',case/'all_job_states.json.gz',
        case/'worker.log',case/'error_prefix.json.gz']}
    require(not files['receipt.json']['exists'] and not files['bridge/independent_verification.json']['exists'],'unexpected_complete_artifacts')
    for name,h in launch['artifact_sha256'].items():require(sha(SOURCE/name)==h,'terminal_artifact:'+name)
    source_checks=[]
    for name,h in plan['source_before'].items():
        p=Path(name);archive=case/'source_archive'/p.relative_to(ROOT)
        require(sha(p)==sha(archive)==h,'live_archive_source:'+name);source_checks.append(name)
    for name,h in plan['compiled_source_sha256'].items():require(sha(case/'compiled_source_archive'/name)==h,'compiled026_archive:'+name)
    for name,h in plan['authority_pins'].items():require(sha(Path(name))==h,'accepted026_authority:'+name)
    require(sha(Path(plan['binary']))==plan['binary_sha256'],'accepted026_binary')
    require(sha(case/'input.json.gz')==plan['input_sha256'],'input')
    require(len(source_checks)==82 and len(plan['compiled_source_sha256'])==67 and plan['offered']==28506 and plan['trays']==22 and plan['horizon']==86400,'fixed_scope')
    manifest=case/'api/manifest.jsonl';count=0;tail=[];endpoints={}
    with manifest.open('rb') as stream:
        for line in stream:
            require(line.endswith(b'\n'),'manifest_partial_line')
            row=json.loads(line);require(row['path']==f'{count:06d}.json.gz' and len(row['sha256'])==64 and
                all(x in '0123456789abcdef' for x in row['sha256']),'manifest_domain')
            tail.append(row);tail=tail[-3:];count+=1;endpoints[row['endpoint']]=endpoints.get(row['endpoint'],0)+1
    names=[e.name for e in os.scandir(case/'api') if e.is_file() and e.name.endswith('.json.gz')]
    require(len(names)==count and set(names)=={f'{i:06d}.json.gz' for i in range(count)},'row_file_domain')
    heartbeat=read(case/'heartbeat.json');assessment=read(case/'assessment.json');elapsed=read(case/'worker_elapsed.json')
    require(count==heartbeat['api_rows']==37270 and heartbeat['physical_time']==assessment['horizon']==86400 and
        heartbeat['delivered_actual_completed_count']==assessment['actual_token_unloads']==assessment['direct_supplies']==39,'saved_summary_disagreement')
    rawstat=files['bridge/raw_final.json.gz'];vstat=files['bridge/verification.log']
    require(rawstat['bytes']==74383534 and files['bridge/assessment.json']['exists'] and vstat['exists'],'final_output_missing')
    source_paths=[ROOT/'scripts/experiments/g31_ics_circulation'/n for n in ('research_original_low_wip.py',
        'research_original_cooperative_bridge.py','verify_original_cooperative_bridge.py','verify_original_bridge_serialize_once.py')]
    report={'schema':'g31.bridge_serialize_once.terminal_partial_review.v1','status':'confirmed_original_timeout_with_final_raw_unverified',
        'source':str(SOURCE),'campaign_sha256':CAMPAIGN,'external_sha256':EXTERNAL,'original_exit':external['exit_code'],
        'whole_python_seconds':external['whole_python_application_seconds'],'owned_process':launch['process'],
        'original_status_unchanged':launch['status'],'source82_live_archive_verified':len(source_checks),
        'compiled026_archive_verified':len(plan['compiled_source_sha256']),'binary_sha256':plan['binary_sha256'],
        'input_sha256':plan['input_sha256'],'offered':28506,'trays':22,'heartbeat':heartbeat,'producer_assessment':assessment,
        'manifest':{'sha256':sha(manifest),'complete_line_count':count,'matching_filename_count':len(names),'endpoint_counts':endpoints,'tail':tail,
            'row_payload_hashes_or_contents_reread':False},'files':files,'worker_elapsed':elapsed,
        'diagnosis':{'worker_function_seconds':elapsed['elapsed_ns']/1e9,
            'raw_file_open_to_last_write_seconds':(rawstat['mtime_ns']-rawstat['ctime_ns'])/1e9,
            'verification_file_created_utc':vstat['created_utc'],
            'verification_file_creation_to_external_exit_seconds':datetime.fromisoformat(external['ended_utc'].replace('Z','+00:00')).timestamp()-vstat['ctime_ns']/1e9,
            'source_sequence':['worker: run_policy -> result_at -> physical audit -> native seal -> raw gzip/json dump -> assessment -> worker_elapsed',
                'campaign: verify child dispatched only after worker subprocess returned0; verification.log is created at dispatch',
                'verifier: full37270 policy replay plus old27218 comparison, physical recomputation and all-job export required before independent_verification.json'],
            'conclusion':'Final raw and assessment completed; source control flow plus verification.log proves the saved-verifier stage was dispatched after a successful worker return. It did not emit its completion artifact before whole2400 timeout.',
            'time_limits':'Filesystem creation/mtime intervals are wall observations, not isolated function/CPU spans. Empty verification.log does not identify which verifier substage was cut.'},
        'preserved_unknowns':['H86400 and39 remain producer heartbeat/assessment evidence pending full saved audit.','No new native seal replay. No independent full policy, physical, FIFO, deadline, relay or old27218-prefix acceptance yet.',
            'Live027 C++ identity is not used as accepted026 authority.','CIM access was unavailable to reviewer; terminal process evidence is the pinned ownedJob/external receipt, plus root notification of closure.'],
        'source_evidence':{str(p):sha(p) for p in source_paths},'read_scope':{'native_calls':0,'predictions':0,'tests':0,
            'api_payload_files_read':0,'final_raw_gzip_decoded':False,'final_raw_gzip_hashed':False,'input_gzip_decoded':False},
        'metadata_read_wall_seconds':time.monotonic()-BOOT}
    write(DEST/'review.json',report)
if __name__=='__main__':
    if '--worker' in sys.argv:worker()
    else:
        DEST.mkdir(exist_ok=False)
        sys.path.insert(0,str(ROOT))
        from scripts.experiments.g31_ics_circulation import bounded_windows_job
        with (DEST/'stdout.log').open('x') as out,(DEST/'stderr.log').open('x') as err:
            process=bounded_windows_job.run([sys.executable,str(Path(__file__).resolve()),'--worker'],
                timeout=max(.001,60-(time.monotonic()-BOOT)),admission='bridge_terminal_small_001',stdout=out,stderr=err,cwd=ROOT)
        write(DEST/'bounded_execution.json',{'process':process,'script_sha256':sha(Path(__file__)),
            'post_import_before_receipt_seconds':time.monotonic()-BOOT,'native_calls':0,'raw_gzip_reads':0,
            'review_sha256':sha(DEST/'review.json') if (DEST/'review.json').exists() else None})
        raise SystemExit(0 if process['status']=='exited' and process['exitcode']==0 else 1)
