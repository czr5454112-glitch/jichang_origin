$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'original_cooperative_bridge_prepare_001'
$taskCampaign=Join-Path $taskFolder 'campaign.json'
$taskCampaignSha='406c5e2ef785805888be33e0d6e79812cc4d0a64f3c18d1bcaea33eb7cbc3655'
if ((Get-FileHash -LiteralPath $taskCampaign -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskCampaignSha) {throw 'Prepared campaign changed'}
$taskModule=Join-Path $taskRoot 'scripts/experiments/g31_ics_circulation/launch_original_cooperative_bridge.py'
$taskManifest=Get-Content -LiteralPath $taskCampaign -Raw | ConvertFrom-Json
$taskModuleSha=$taskManifest.source_before.$taskModule
if (-not $taskModuleSha -or (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskModuleSha) {throw 'Prepared launcher changed'}
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
    & $taskPython -m scripts.experiments.g31_ics_circulation.launch_original_cooperative_bridge --output $taskFolder --campaign-sha256 $taskCampaignSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskUnchanged=((Get-FileHash -LiteralPath $taskCampaign -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskCampaignSha -and (Get-FileHash -LiteralPath $taskModule -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskModuleSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskWall=($taskEnd-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskRecord=[ordered]@{
    schema='g31.original_cooperative_bridge.external_application_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStarted;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_2400_seconds=($taskWall -le 2400)
    campaign_sha256=$taskCampaignSha;launcher_sha256=$taskModuleSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_job_seconds=2400;native_branch_budget=1;max_concurrent_native_workers=1
    complete_100ms_certified=$false;alloffered_business_success=$false
    scope='Full Python parent startup/import/claims, owned bounded2400s subtree with one accepted026 fresh28506/22/H86400 physical trial, every policy/codec/API/tape/clock/heartbeat/diagnostic operation, full saved policy and physical replay, all28506 job-state export, source/receipt hashes, cleanup and parent exit. Immutable026 archives/build/binary are authority; live027 equality is not assumed. Whole observed cost includes parent tails beyond the ownedJob budget.'
    exclusions='PowerShell/tool startup, prelaunch digest and post-exit digest/this outer receipt export are declared harness work. No complete business-request100ms certificate; cap39 is not alloffered success.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}
