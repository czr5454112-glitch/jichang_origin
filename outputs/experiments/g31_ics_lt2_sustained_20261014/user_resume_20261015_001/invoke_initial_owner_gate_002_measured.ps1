$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'initial_owner_route_gate_campaign_prepare_002'
$taskCampaign=Join-Path $taskFolder 'campaign.json'
$taskCampaignSha='659685e577db515a56d2229aa546b15b6a0ba7e6c903d014d9f353df4c9614c4'
if ((Get-FileHash -LiteralPath $taskCampaign -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskCampaignSha) {throw 'Prepared campaign changed'}
$taskModule=Join-Path $taskRoot 'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_gate_campaign_v2.py'
$taskModuleSha='eaaafb556436f2203f6527ca457672c174e2965ab1997a723701151abccd4151'
if ((Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskModuleSha) {throw 'Prepared launcher changed'}
$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json
if ($taskReady.status -ne 'ready_for_one_bounded_actual_attempt' -or $taskReady.campaign_sha256 -ne $taskCampaignSha) {throw 'Prelaunch review missing'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if (Test-Path -LiteralPath $taskDestination) {throw 'Preserve prior external measurement'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskWrapperSha -ne $taskReady.wrapper_sha256) {throw 'Reviewed wrapper changed'}
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha=(Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') {throw 'Prepared interpreter changed'}
$taskStarted=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.launch_initial_owner_route_gate_campaign_v2 --output $taskFolder --campaign-sha256 $taskCampaignSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskUnchanged=((Get-FileHash -LiteralPath $taskCampaign -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskCampaignSha -and (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskModuleSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskWall=($taskEnd-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskRecord=[ordered]@{
    schema='g31.initial_owner_route_gate.external_application_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStarted;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_600_seconds=($taskWall -le 600)
    campaign_sha256=$taskCampaignSha;launcher_sha256=$taskModuleSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_job_seconds=600;native_branch_budget=18;max_concurrent_native_workers=1;pure_predictor_workers=1
    complete_100ms_certified=$false;full32_solver_certified=$false;alloffered_business_success=$false
    concurrent_experiment_policy='Fresh historical96 native and saved review completed. Before dispatch all agents confirmed no active children and paused new pure, native, compile, benchmark and heavy I/O until this performance window closes. Unrelated user/system load is not controlled.'
    scope='Full Python parent launch through exit: imports/prechecks, owned600s tree, native027 entry/exit acceptance,18 fresh H40 branches, actual fixed or finite2 initial-A roots, one pure JSON predictor startup/RPC/close, all policy/codec/complete required outbox proof/endpoint and physical export, saved full refresh/outbox/endpoint/RPC/physical verification, parent final receipts. Root walls and cold costs remain separate; nothing divided by18 and no physical/shared cost subtraction.'
    exclusions='PowerShell/tool startup, prelaunch digest and post-exit digest/this outer receipt export are declared harness work. Finite initial firsthop scope does not certify full32 solver, original all-day workload, general request100ms or two machines.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}
