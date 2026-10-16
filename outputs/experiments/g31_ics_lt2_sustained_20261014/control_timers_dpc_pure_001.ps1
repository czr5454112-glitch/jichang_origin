$ErrorActionPreference = 'Stop'
$taskWorkspace = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$taskOutput = Join-Path $taskWorkspace 'outputs\experiments\g31_ics_lt2_sustained_20261014\dpc_pure_001'
$taskRunner = Join-Path $taskWorkspace 'scripts\experiments\g31_ics_circulation\measure_delivered_peer_c_encoder.py'
$taskExpectedRunner = '8d33910416329638f1174f9544b25b58857557e6f5afd95b16f0affa4c247d66'
$taskSourcePins = [ordered]@{
    'scripts/experiments/g31_ics_circulation/planning_v2_c_encoder_authority.py' = '3e50a8f155b96c49fd9824dd2e236b49dd8167f4e6374635de2783ab8a6a194d'
    'scripts/experiments/g31_ics_circulation/delivered_peer_c_encoder_probe.py' = 'ba12a0b4b1a0de55e59e7ac9efaa0d573de47abe032ee2aa5ace081b4d6318b8'
    'scripts/experiments/g31_ics_circulation/measure_delivered_peer_c_encoder.py' = $taskExpectedRunner
    'tests/test_g31_circulation_delivered_peer_c_encoder.py' = '3e8f3485f1d77dbbfd0b1b74f49cfa4f42f2ef66e13628cc14ac40e17751e47b'
}
function Get-TaskHash([string] $LiteralFile) {
    return (Get-FileHash -LiteralPath $LiteralFile -Algorithm SHA256).Hash.ToLowerInvariant()
}
$taskHarnessClock = [Diagnostics.Stopwatch]::StartNew()
if (Test-Path -LiteralPath $taskOutput) { throw 'fresh_pure_output_required' }
foreach ($taskName in $taskSourcePins.Keys) {
    if ((Get-TaskHash (Join-Path $taskWorkspace $taskName)) -ne $taskSourcePins[$taskName]) { throw ('source_identity:' + $taskName) }
}
$taskWrapperPath = $PSCommandPath
$taskWrapperHash = Get-TaskHash $taskWrapperPath
$taskCommand = @('C:\PROGRAMING\python3.11.9\python.exe','-m','scripts.experiments.g31_ics_circulation.measure_delivered_peer_c_encoder','--pure','--output',$taskOutput)
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
    if (-not $taskProcess.WaitForExit(120000)) {
        $taskOuterTimeout = $true
        $taskProcess.Kill($true)
        $taskProcess.WaitForExit()
    }
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
$taskWall = [double]$taskElapsedTicks / [double]$taskFrequency
$taskChanged = @()
foreach ($taskName in $taskSourcePins.Keys) {
    try {
        if ((Get-TaskHash (Join-Path $taskWorkspace $taskName)) -ne $taskSourcePins[$taskName]) { $taskChanged += $taskName }
    } catch { $taskChanged += $taskName }
}
if ((Get-TaskHash $taskWrapperPath) -ne $taskWrapperHash) { $taskChanged += $taskWrapperPath }
$taskOutputHashes = [ordered]@{}
foreach ($taskName in @('receipt.json','bounded_execution.json','tests.xml')) {
    $taskFile = Join-Path $taskOutput $taskName
    if (Test-Path -LiteralPath $taskFile) { $taskOutputHashes[$taskName] = Get-TaskHash $taskFile }
}
$taskRecord = [ordered]@{
    schema = 'g31.delivered_peer.C_encoder.pure_external.v1'
    command = $taskCommand
    runner = [ordered]@{path=$taskRunner;sha256=$taskExpectedRunner}
    wrapper = [ordered]@{path=$taskWrapperPath;sha256=$taskWrapperHash}
    four_new_source_pins = $taskSourcePins
    source_changed = @($taskChanged)
    exit_code = $taskExitCode
    elapsed_ticks = $taskElapsedTicks
    tick_frequency = $taskFrequency
    whole_python_seconds = $taskWall
    output_sha256 = $taskOutputHashes
    started_UTC = $taskStartedUTC
    ended_UTC = $taskEndedUTC
    outer_timeout = $taskOuterTimeout
    exception = $taskException
    accepted_clock_only = ($taskExitCode -eq 0 -and -not $taskOuterTimeout -and $null -eq $taskException -and $taskElapsedTicks -le (120*$taskFrequency) -and $taskChanged.Count -eq 0)
    scope = 'Full Python launch/imports, complete source closure current/archive checks,83 synthetic tests, child/parent output and exit. No C extension load, actual fixture decode, native simulation, model or performance comparison. Wrapper startup/prelaunch checks and final external export are harness outside the Python envelope.'
    harness_pre_external_export_seconds = $taskHarnessClock.Elapsed.TotalSeconds
}
if (-not (Test-Path -LiteralPath $taskOutput)) { [void][IO.Directory]::CreateDirectory($taskOutput) }
$taskExternal = Join-Path $taskOutput 'external_application_wall.json'
if (Test-Path -LiteralPath $taskExternal) { throw 'external_receipt_already_exists' }
[IO.File]::WriteAllText($taskExternal, ($taskRecord | ConvertTo-Json -Depth 14), [Text.UTF8Encoding]::new($false))
[ordered]@{exit_code=$taskExitCode;whole_python_seconds=$taskWall;source_changed=$taskChanged;external_sha256=(Get-TaskHash $taskExternal);output_sha256=$taskOutputHashes} | ConvertTo-Json -Depth 5
if (-not $taskRecord.accepted_clock_only) { exit 1 }
exit 0
