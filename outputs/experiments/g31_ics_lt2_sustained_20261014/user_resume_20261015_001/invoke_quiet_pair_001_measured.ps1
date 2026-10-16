$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'preference_quiet_pair_001'
$taskPlan=Join-Path $taskFolder 'preregistered_protocol.json'
$taskModule=Join-Path $taskRoot 'scripts/experiments/g31_ics_circulation/measure_public_preference_quiet.py'
$taskPlanSha='41922041ffe189df3b0a9b4ac7e8612efea79ad6e8e04aaaed45f6324a1b92f9'
$taskModuleSha='f467eb5f46d3fcad1f7cca5300dd95dc03c6c3fdd9a79b85e8dd33093e599714'
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) {throw 'Prepared plan changed'}
if ((Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskModuleSha) {throw 'Prepared module changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if (Test-Path -LiteralPath $taskDestination) {throw 'Preserve prior external measurement'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskStarted=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & 'C:/PROGRAMING/python3.11.9/python.exe' -m scripts.experiments.g31_ics_circulation.measure_public_preference_quiet --launch --output $taskFolder
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskModuleSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha)
$taskRecord=[ordered]@{
    schema='g31.quiet_pair.external_application_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStarted;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=($taskEnd-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
    plan_sha256=$taskPlanSha;module_sha256=$taskModuleSha;wrapper_sha256=$taskWrapperSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    child_job_budget_seconds=120;native_executions=0;complete_100ms_certified=$false
    scope='Full Python parent startup/import, owned worker startup/conformance/paired measurements/verification/export, parent final receipt and exit. Batch timings retain all per-request preparation and candidate output copies.'
    exclusions='PowerShell/tool startup, prelaunch digest and post-exit digest/this receipt export. These are declared harness work; no platform cold-start or complete business-request certificate.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskRecord.whole_python_application_seconds;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}
