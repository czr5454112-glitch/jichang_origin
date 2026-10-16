$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'json_prediction_RPC_prepare_002'
$taskPlan=Join-Path $taskFolder 'preregistered_protocol.json'
$taskModule=Join-Path $taskRoot 'scripts/experiments/g31_ics_circulation/measure_json_prediction_service.py'
$taskPlanSha='c30af2fa76ec3cb57d5fa627f7daf6b419bbdbb863c3ff8e384626880dd35d06'
$taskModuleSha='aea0efc18b51e7c2f1d1a58ee8143c58ccb01b951207e388aa6b1e487a305d43'
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) {throw 'Prepared plan changed'}
if ((Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskModuleSha) {throw 'Prepared module changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if (Test-Path -LiteralPath $taskDestination) {throw 'Preserve prior external measurement'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha=(Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') {throw 'Prepared interpreter changed'}
$taskStarted=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.measure_json_prediction_service --launch --output $taskFolder --plan-sha256 $taskPlanSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskModuleSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskRecord=[ordered]@{
    schema='g31.json_prediction_RPC.external_application_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStarted;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=($taskEnd-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
    plan_sha256=$taskPlanSha;module_sha256=$taskModuleSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    child_job_budget_seconds=120;native_executions=0;complete_100ms_certified=$false
    scope='Full Python parent startup/import/source verification, four owned isolated workers, 24 synchronous RPC calls with full baseline/all32 and caller encode/decode/ledger tail, source rehash/close/reclamation, complete saved-output verification/export and parent exit. Nested compute is never added twice; startup and close remain charged separately.'
    exclusions='PowerShell/tool startup, prelaunch digest and post-exit digest/this receipt export. These are declared harness work; no platform cold-start or complete business-request certificate.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskRecord.whole_python_application_seconds;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}
