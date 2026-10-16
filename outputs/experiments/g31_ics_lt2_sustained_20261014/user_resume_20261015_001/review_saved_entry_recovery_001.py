"""Root review and measured wrapper for separate failed-producer saved audit."""
from pathlib import Path
from datetime import datetime, timezone
import json
from scripts.experiments.g31_ics_circulation import review_initial_owner_route_entry_saved_v2 as reader

c=reader.c
out=c.OUT/'initial_owner_route_entry_independent_actual_review_001'
here=Path(__file__).resolve().parent
expected='5363525a3a3203f2d1783ad4b93c856384852b4366faf29c4b1fca698b845a3e'
plan=reader.verify_prepared(out,expected)
producer,evidence,outer,ledger=reader.producer_state(Path(plan['source_directory']))
loaded=reader.actual_loaded(producer,plan)
assert len(plan['source_sha256'])==141 and len(producer['source_sha256'])==151
assert len(producer['compiled_source_archive_sha256'])==67 and len(ledger)==18
assert reader.verifier.source_proof()['new_missing_globals']=={k:[] for k in reader.verifier.source_proof()['new_missing_globals']}
assert c.sha(reader.__file__)=='0ad1805a91fb61bd73425ee1a8a06f10b7a3b4b90ebe488115f5866003673e31'
assert not (out/'execution_claim.json').exists()
wrapper=here/'invoke_saved_entry_recovery_001_measured.ps1'
body=r'''$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'initial_owner_route_entry_independent_actual_review_001'
$taskPlan=Join-Path $taskFolder 'plan.json'
$taskPlanSha='5363525a3a3203f2d1783ad4b93c856384852b4366faf29c4b1fca698b845a3e'
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) {throw 'Prepared plan changed'}
if ((Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPythonSha) {throw 'Prepared interpreter changed'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json
if ($taskReady.status -ne 'ready_for_one_separate_saved_audit' -or $taskReady.plan_sha256 -ne $taskPlanSha -or $taskReady.wrapper_sha256 -ne $taskWrapperSha) {throw 'Review identity changed'}
if ((Get-FileHash -LiteralPath $taskReady.root_review.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReady.root_review.sha256) {throw 'Root review changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if ((Test-Path -LiteralPath $taskDestination) -or (Test-Path -LiteralPath (Join-Path $taskFolder 'execution_claim.json'))) {throw 'Preserve previous attempt'}
$taskStart=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.review_initial_owner_route_entry_saved_v2 --execute --output $taskFolder --plan-sha256 $taskPlanSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskWall=([Diagnostics.Stopwatch]::GetTimestamp()-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskRecord=[ordered]@{
    schema='g31.initial_entry.separate_saved_recovery.external_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStart;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_180_seconds=($taskWall -le 180)
    plan_sha256=$taskPlanSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_seconds=180;fixed_saved_branches=18;native_calls=0;predictor_calls=0
    original_producer_failed=$true;producer_exit_import_proof='unknown_not_recreated'
    scope='Independent full saved endpoint/physical/RPC/gate/outbox audit after repaired verifier globals. Full launch/import/pin/read/decode/check/export/cleanup/exit cost is included. No native rerun. Original producer exit1 and missing receipt remain.'
    exclusions='PowerShell/tool startup and explicit prelaunch/postexit digest checks plus this outer receipt export are harness work outside the Python interval.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}
'''
with wrapper.open('x',encoding='utf8',newline='\n') as stream:stream.write(body)
report={'schema':'g31.initial_entry.separate_saved_audit.root_review.v1',
 'recorded_utc':datetime.now(timezone.utc).isoformat(),'status':'ready_for_one_separate_saved_audit',
 'plan':c.reference(out/'plan.json'),'source_review':c.reference(out/'source_review.json'),
 'audit_sources':141,'producer_sources':151,'compiled_archive_sources':67,'loaded_checked':len(loaded),
 'pure_regressions':12,'full_saved_branches':18,'owned_seconds':180,'new_native_or_predictor_calls':0,
 'reviewed_rules':[
  'Read full reader, repaired verifier and preserved failure. Original nine function code and closures are unchanged; inherited defining globals now resolve, including comprehension globals.',
  'Same original full saved verification executes once. Passive summary callback uses the same decoded branch and cannot replace the original checker result.',
  'All18 raw hashes, failed exit1/stderr/launch evidence, all151 producer source plus67 compiled archive,141 audit source and entry/exit loaded imports are independently bound.',
  'Original missing producer receipt/verification and missing recorded producer import-exit check remain explicit unknown. New recovered verification is separate.',
  'Earlier physical clock is not compute saving. Different admissions/IDs/continuation are allowed only through full endpoint/physical checks; gate002 comparison is descriptive.',
  'Fixed180 owns import/pin/check/export/cleanup; prior saved18 cost53.934451 provides cost evidence but not guaranteed runtime.'
 ],'producer':c.reference(__file__),'wrapper':c.reference(wrapper)}
review=out/'root_source_review_001.json'
with review.open('x',encoding='utf8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
ready=out/'root_ready_001.json'
with ready.open('x',encoding='utf8') as stream:json.dump({'status':'ready_for_one_separate_saved_audit',
 'plan_sha256':expected,'root_review':c.reference(review),'wrapper_sha256':c.sha(wrapper),
 'owned_seconds':180,'full_audit_dispatched':False},stream,indent=2)
print(json.dumps({'review_sha256':c.sha(review),'ready_sha256':c.sha(ready),'wrapper_sha256':c.sha(wrapper)}))
