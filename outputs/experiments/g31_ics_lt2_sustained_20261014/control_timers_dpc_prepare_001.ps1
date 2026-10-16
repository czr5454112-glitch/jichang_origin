$ErrorActionPreference = 'Stop'
$taskWorkspace = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$taskBase = Join-Path $taskWorkspace 'outputs\experiments\g31_ics_lt2_sustained_20261014'
$taskOutput = Join-Path $taskBase 'dpc_prepare_001'
$taskPure = Join-Path $taskBase 'dpc_pure_001'
$taskRunner = Join-Path $taskWorkspace 'scripts\experiments\g31_ics_circulation\measure_delivered_peer_c_encoder.py'
$taskExpectedRunner = '8d33910416329638f1174f9544b25b58857557e6f5afd95b16f0affa4c247d66'
$taskPureReceipt = Join-Path $taskPure 'receipt.json'
$taskExpectedPureReceipt = 'ddb078e7b08dcae837921b6f579b7fe9656a3cdd5c0639a7daebbf60f242be6e'
$taskPureExternal = Join-Path $taskPure 'external_application_wall.json'
$taskExpectedPureExternal = '8a4856cdfd0b53e88caee7e1d6eea737f69b9567bb5532a8a081489627822820'
function Get-TaskHash([string] $LiteralFile) { return (Get-FileHash -LiteralPath $LiteralFile -Algorithm SHA256).Hash.ToLowerInvariant() }
$taskHarnessClock = [Diagnostics.Stopwatch]::StartNew()
if (Test-Path -LiteralPath $taskOutput) { throw 'fresh_prepare_output_required' }
if ((Get-TaskHash $taskRunner) -ne $taskExpectedRunner -or (Get-TaskHash $taskPureReceipt) -ne $taskExpectedPureReceipt -or (Get-TaskHash $taskPureExternal) -ne $taskExpectedPureExternal) { throw 'preparation_identity' }
$taskPins = (Get-Content -LiteralPath $taskPureReceipt -Raw | ConvertFrom-Json).source_sha256
foreach ($taskProperty in $taskPins.PSObject.Properties) {
    if ((Get-TaskHash (Join-Path $taskWorkspace $taskProperty.Name)) -ne $taskProperty.Value) { throw ('source_identity:' + $taskProperty.Name) }
}
$taskWrapperPath = $PSCommandPath
$taskWrapperHash = Get-TaskHash $taskWrapperPath
$taskCommand = @('C:\PROGRAMING\python3.11.9\python.exe','-m','scripts.experiments.g31_ics_circulation.measure_delivered_peer_c_encoder','--prepare','--output',$taskOutput,'--pure-dir',$taskPure)
$taskStartInfo = [Diagnostics.ProcessStartInfo]::new()
$taskStartInfo.FileName = $taskCommand[0]
$taskStartInfo.WorkingDirectory = $taskWorkspace
$taskStartInfo.UseShellExecute = $false
$taskStartInfo.CreateNoWindow = $true
$taskStartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
foreach ($taskArgument in $taskCommand[1..($taskCommand.Count-1)]) { [void]$taskStartInfo.ArgumentList.Add([string]$taskArgument) }
$taskProcess = [Diagnostics.Process]::new()
$taskProcess.StartInfo = $taskStartInfo
$taskStartedUTC = [DateTime]::UtcNow.ToString('o')
$taskStartTicks = [Diagnostics.Stopwatch]::GetTimestamp()
$taskExitCode = $null
$taskException = $null
$taskOuterTimeout = $false
$taskStarted = $false
try {
    if (-not $taskProcess.Start()) { throw 'python_start_failed' }
    $taskStarted = $true
    if (-not $taskProcess.WaitForExit(120000)) { $taskOuterTimeout=$true; $taskProcess.Kill($true); $taskProcess.WaitForExit() }
    $taskExitCode = $taskProcess.ExitCode
} catch {
    $taskException = $_.Exception.Message
    if ($taskStarted -and -not $taskProcess.HasExited) { $taskProcess.Kill($true); $taskProcess.WaitForExit() }
} finally {
    $taskEndTicks = [Diagnostics.Stopwatch]::GetTimestamp()
    $taskEndedUTC = [DateTime]::UtcNow.ToString('o')
    $taskProcess.Dispose()
}
$taskElapsedTicks = $taskEndTicks - $taskStartTicks
$taskFrequency = [Diagnostics.Stopwatch]::Frequency
$taskChanged = @()
foreach ($taskProperty in $taskPins.PSObject.Properties) {
    try { if ((Get-TaskHash (Join-Path $taskWorkspace $taskProperty.Name)) -ne $taskProperty.Value) { $taskChanged += $taskProperty.Name } }
    catch { $taskChanged += $taskProperty.Name }
}
foreach ($taskIdentity in @(@($taskWrapperPath,$taskWrapperHash),@($taskPureReceipt,$taskExpectedPureReceipt),@($taskPureExternal,$taskExpectedPureExternal))) {
    if ((Get-TaskHash $taskIdentity[0]) -ne $taskIdentity[1]) { $taskChanged += $taskIdentity[0] }
}
$taskOutputHashes = [ordered]@{}
foreach ($taskName in @('plan.json','ready.json','prepare_bounded.json')) {
    $taskFile=Join-Path $taskOutput $taskName
    if (Test-Path -LiteralPath $taskFile) { $taskOutputHashes[$taskName]=Get-TaskHash $taskFile }
}
$taskRecord = [ordered]@{
    schema='g31.delivered_peer.C_encoder.prepare_external.v1';command=$taskCommand
    runner=[ordered]@{path=$taskRunner;sha256=$taskExpectedRunner};wrapper=[ordered]@{path=$taskWrapperPath;sha256=$taskWrapperHash}
    pure_receipt=[ordered]@{path=$taskPureReceipt;sha256=$taskExpectedPureReceipt};pure_external=[ordered]@{path=$taskPureExternal;sha256=$taskExpectedPureExternal}
    source_count=@($taskPins.PSObject.Properties).Count;source_changed=@($taskChanged)
    exit_code=$taskExitCode;elapsed_ticks=$taskElapsedTicks;tick_frequency=$taskFrequency;whole_python_seconds=([double]$taskElapsedTicks/[double]$taskFrequency)
    output_sha256=$taskOutputHashes;started_UTC=$taskStartedUTC;ended_UTC=$taskEndedUTC;outer_timeout=$taskOuterTimeout;exception=$taskException
    accepted_clock_only=($taskExitCode -eq 0 -and -not $taskOuterTimeout -and $null -eq $taskException -and $taskElapsedTicks -le (120*$taskFrequency) -and $taskChanged.Count -eq 0)
    scope='Metadata/source authority preparation, compressed fixture copy/hash only; zero actual fixture decode/C load/native/model/performance. Python launch/imports/child/parent export and exit included; wrapper startup/prelaunch and external receipt export are separate harness costs.'
    harness_pre_external_export_seconds=$taskHarnessClock.Elapsed.TotalSeconds
}
if (-not (Test-Path -LiteralPath $taskOutput)) { [void][IO.Directory]::CreateDirectory($taskOutput) }
$taskExternal = Join-Path $taskOutput 'external_application_wall.json'
if (Test-Path -LiteralPath $taskExternal) { throw 'external_receipt_already_exists' }
[IO.File]::WriteAllText($taskExternal,($taskRecord|ConvertTo-Json -Depth 14),[Text.UTF8Encoding]::new($false))
[ordered]@{exit_code=$taskExitCode;whole_python_seconds=$taskRecord.whole_python_seconds;source_changed=$taskChanged;external_sha256=(Get-TaskHash $taskExternal);output_sha256=$taskOutputHashes}|ConvertTo-Json -Depth 5
if (-not $taskRecord.accepted_clock_only) { exit 1 }
exit 0
