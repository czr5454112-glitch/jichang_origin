$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'original_bridge_serialize_once_prepare_001'
$taskCampaign=Join-Path $taskFolder 'campaign.json'
$taskCampaignSha='d976e7f2d473e64ddb4e11895c06bfb9f21a11b43133babb71cd02491bb94464'
if ((Get-FileHash -LiteralPath $taskCampaign -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskCampaignSha) {throw 'Prepared campaign changed'}
$taskModule=Join-Path $taskRoot 'scripts/experiments/g31_ics_circulation/launch_original_bridge_serialize_once.py'
$taskManifest=Get-Content -LiteralPath $taskCampaign -Raw | ConvertFrom-Json
$taskModuleSha=$taskManifest.source_before.$taskModule
if (-not $taskModuleSha -or (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskModuleSha) {throw 'Prepared launcher changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if (Test-Path -LiteralPath $taskDestination) {throw 'Preserve prior external measurement'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json
if ($taskReady.status -ne 'ready_for_one_bounded_actual_attempt' -or $taskReady.campaign_sha256 -ne $taskCampaignSha -or $taskReady.wrapper_sha256 -ne $taskWrapperSha) {throw 'Reviewed wrapper or campaign changed'}
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha=(Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') {throw 'Prepared interpreter changed'}
$taskStarted=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.launch_original_bridge_serialize_once --output $taskFolder --campaign-sha256 $taskCampaignSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskUnchanged=((Get-FileHash -LiteralPath $taskCampaign -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskCampaignSha -and (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskModuleSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskWall=($taskEnd-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskRecord=[ordered]@{
    schema='g31.original_bridge.serialize_once.external_application_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStarted;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_2400_seconds=($taskWall -le 2400)
    campaign_sha256=$taskCampaignSha;launcher_sha256=$taskModuleSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_job_seconds=2400;native_branch_budget=1;max_concurrent_native_workers=1
    complete_100ms_certified=$false;alloffered_business_success=$false
    scope='Full Python parent startup/import/claims, owned bounded2400s subtree with one accepted026 fresh28506/22/H86400 physical trial, every policy/codec/API/tape/clock/heartbeat/diagnostic operation, full saved policy and physical replay plus every ordered row/hash of the old27218 complete API prefix, all28506 job-state export, source/receipt hashes, cleanup and parent exit. Immutable026 archives/build/binary are authority; live027 equality is not assumed. Whole observed cost includes parent tails beyond the ownedJob budget.'
    concurrent_experiment_policy='Launch only after initial-request timing window closes. This full-day functional trial may overlap source/pure development; no isolated latency benchmark or application speedup ratio is claimed.'
    logging_amendment='Only serialize-once Tape. Same BridgeOwner,10s cadence,all raw fields,39/78/100 caps,original026 physical semantics; old timeout remains failure. Fixed8 Tape ratio is not an application forecast.'
    exclusions='PowerShell/tool startup, prelaunch digest and post-exit digest/this outer receipt export are declared harness work. No complete business-request100ms certificate; cap39 is not alloffered success.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}
