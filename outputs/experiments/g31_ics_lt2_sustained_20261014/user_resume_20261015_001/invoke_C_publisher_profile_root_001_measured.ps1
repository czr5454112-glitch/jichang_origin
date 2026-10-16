$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'complete_C_publisher_profile_prepare_001'
$taskPlan=Join-Path $taskFolder 'plan.json'
$taskPlanSha='5b9ff4bd5f643bf64c47fb9e5f55afc6914af5eee1bbfe8ca11f6bd51f3c0c85'
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) {throw 'Prepared plan changed'}
if ((Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPythonSha) {throw 'Prepared interpreter changed'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json
if ($taskReady.status -ne 'ready_for_one_complete_C_publisher_profile18' -or $taskReady.plan_sha256 -ne $taskPlanSha -or $taskReady.wrapper_sha256 -ne $taskWrapperSha) {throw 'Review identity changed'}
if ((Get-FileHash -LiteralPath $taskReady.root_review.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReady.root_review.sha256) {throw 'Root review changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if ((Test-Path -LiteralPath $taskDestination) -or (Test-Path -LiteralPath (Join-Path $taskFolder 'execution_claim.json'))) {throw 'Preserve previous attempt'}
$taskStart=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.profile_complete_c_publisher_saved18 --execute --output $taskFolder --expected-plan $taskPlanSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskWall=([Diagnostics.Stopwatch]::GetTimestamp()-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskRecord=[ordered]@{
    schema='g31.complete_C_publisher_profile18.external_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStart;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_120_seconds=($taskWall -le 120)
    plan_sha256=$taskPlanSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_seconds=120;fixed_historical_roots=18;profiled_publishers=18;direct_support_preflight_publishers=18;C_extension_loads=1;model_calls=0;native_simulation_calls=0
    model_conformance_not_inferred_from_exit_code=$true;complete_native_request_100ms_certified=$false
    scope='Fixed18 historical complete entry-codec records,including16closed2unknown. Accepted C-normalizer complete publisher unchanged;18directsupport preflights and18cProfiles enclosing fresh root construction through append/return. Full output saves precede comparison, exact all fields/order/types/floathex and regenerated clocks checked, saved full records reread. All old source/toolchain6124/runtime/binary/raw guards plus new sources preserved. Setup,C load,all36publisher calls,profiles/exports/readback/cleanup/exit within120. Instrumented diagnostic only; overlapping cumulative times, no uninstrumented speedup/native100ms/full32 or online utility claim.'
    exclusions='PowerShell/tool startup and explicit prelaunch/postexit digest checks plus this outer receipt export are harness work outside the Python interval.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}

if ($taskWall -gt 120) {throw 'Whole Python complete C publisher profile18 budget exceeded'}
