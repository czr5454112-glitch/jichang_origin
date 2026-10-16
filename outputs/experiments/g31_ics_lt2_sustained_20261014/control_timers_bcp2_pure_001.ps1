$ErrorActionPreference = 'Stop'
$taskWorkspace = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$taskOutput = Join-Path $taskWorkspace 'outputs\experiments\g31_ics_lt2_sustained_20261014\bcp2'
$taskPython = 'C:\PROGRAMING\python3.11.9\python.exe'
$taskPythonHash = '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
$taskSourcePins = [ordered]@{
    'scripts/experiments/g31_ics_circulation/bridge_saved_c_digest.py' = 'd5b0eea69627e341c9008136b08d29a926357bd7f48429580bebff706078a0ec'
    'scripts/experiments/g31_ics_circulation/run_bridge_saved_c_digest_pure.py' = '169a7ea117dd04cedda6ad4c796b6cafb4f030dec971bf18f234c5231a0c6c98'
    'tests/test_g31_circulation_bridge_saved_c_digest.py' = 'fd14f20da0e4cf938d9cd6c803127199631eee572d4847b0a510f7ddecdb25b7'
    'scripts/experiments/g31_ics_circulation/run_bridge_saved_c_digest_pure_v2.py' = '8d86a94f5008734cb78098280430669f87254dc34e5cf82b47785ac8f35b9966'
    'tests/test_g31_circulation_bridge_saved_c_digest_v2.py' = 'c4f31ce0e81c41e38b51a51fba2a5fb7c4690147dad308665ed382a6108c66f5'
}
$taskEnvironment = [ordered]@{
    PYTHONPATH = 'src;.;tests'
    PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    PYTHONIOENCODING = 'utf-8'
}
$taskCommand = @($taskPython, '-m', 'scripts.experiments.g31_ics_circulation.run_bridge_saved_c_digest_pure_v2', '--output', $taskOutput)
$taskWrapperPath = $PSCommandPath
$taskHarnessClock = [Diagnostics.Stopwatch]::StartNew()
[long]$taskFrequency = [Diagnostics.Stopwatch]::Frequency
[long]$taskBudgetTicks = [long]120 * $taskFrequency
$taskStartTicks = $null
$taskEndTicks = $null
$taskStartedUTC = $null
$taskEndedUTC = $null
$taskExitCode = $null
$taskException = $null
$taskCleanupErrors = @()
$taskOuterTimeout = $false
$taskStarted = $false
$taskProcess = $null
$taskPID = $null
$taskWrapperHash = $null
$taskFreshOutput = $false

function Get-TaskHash([string] $LiteralFile) {
    return (Get-FileHash -LiteralPath $LiteralFile -Algorithm SHA256).Hash.ToLowerInvariant()
}

try {
    if (Test-Path -LiteralPath $taskOutput) { throw 'fresh_bcp2_output_required' }
    $taskFreshOutput = $true
    $taskWrapperHash = Get-TaskHash $taskWrapperPath
    if ((Get-TaskHash $taskPython) -ne $taskPythonHash) { throw 'python_identity' }
    foreach ($taskName in $taskSourcePins.Keys) {
        if ((Get-TaskHash (Join-Path $taskWorkspace $taskName)) -ne $taskSourcePins[$taskName]) {
            throw ('source_identity:' + $taskName)
        }
    }
    $taskStartInfo = [Diagnostics.ProcessStartInfo]::new()
    $taskStartInfo.FileName = $taskPython
    $taskStartInfo.WorkingDirectory = $taskWorkspace
    $taskStartInfo.UseShellExecute = $false
    $taskStartInfo.CreateNoWindow = $true
    $taskStartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    foreach ($taskArgument in $taskCommand[1..($taskCommand.Count - 1)]) {
        [void]$taskStartInfo.ArgumentList.Add([string]$taskArgument)
    }
    foreach ($taskName in $taskEnvironment.Keys) {
        $taskStartInfo.Environment[$taskName] = [string]$taskEnvironment[$taskName]
    }
    $taskProcess = [Diagnostics.Process]::new()
    $taskProcess.StartInfo = $taskStartInfo
    $taskStartedUTC = [DateTime]::UtcNow.ToString('o')
    $taskStartTicks = [Diagnostics.Stopwatch]::GetTimestamp()
    if (-not $taskProcess.Start()) { throw 'python_start_failed' }
    $taskStarted = $true
    $taskPID = $taskProcess.Id
    [long]$taskRemainingTicks = $taskBudgetTicks - ([Diagnostics.Stopwatch]::GetTimestamp() - $taskStartTicks)
    $taskExited = $false
    if ($taskRemainingTicks -gt 0) {
        $taskWaitMilliseconds = [int][Math]::Ceiling(1000.0 * $taskRemainingTicks / $taskFrequency)
        $taskExited = $taskProcess.WaitForExit($taskWaitMilliseconds)
    }
    if (-not $taskExited) {
        $taskOuterTimeout = $true
        $taskProcess.Kill($true)
        $taskProcess.WaitForExit()
    }
    $taskExitCode = $taskProcess.ExitCode
} catch {
    $taskException = [ordered]@{type=$_.Exception.GetType().FullName; message=$_.Exception.Message}
    if ($taskStarted) {
        try {
            if (-not $taskProcess.HasExited) { $taskProcess.Kill($true); $taskProcess.WaitForExit() }
            $taskExitCode = $taskProcess.ExitCode
        } catch { $taskCleanupErrors += $_.Exception.Message }
    }
} finally {
    if ($null -ne $taskStartTicks) {
        $taskEndTicks = [Diagnostics.Stopwatch]::GetTimestamp()
        $taskEndedUTC = [DateTime]::UtcNow.ToString('o')
    }
    if ($null -ne $taskProcess) { $taskProcess.Dispose() }
}
$taskElapsedTicks = $null
$taskWall = $null
if ($null -ne $taskStartTicks -and $null -ne $taskEndTicks) {
    $taskElapsedTicks = [long]($taskEndTicks - $taskStartTicks)
    $taskWall = [double]$taskElapsedTicks / [double]$taskFrequency
}
$taskChanged = @()
foreach ($taskName in $taskSourcePins.Keys) {
    try {
        if ((Get-TaskHash (Join-Path $taskWorkspace $taskName)) -ne $taskSourcePins[$taskName]) { $taskChanged += $taskName }
    } catch { $taskChanged += $taskName }
}
try { if ((Get-TaskHash $taskPython) -ne $taskPythonHash) { $taskChanged += $taskPython } }
catch { $taskChanged += $taskPython }
try {
    if ($null -eq $taskWrapperHash -or (Get-TaskHash $taskWrapperPath) -ne $taskWrapperHash) { $taskChanged += $taskWrapperPath }
} catch { $taskChanged += $taskWrapperPath }
$taskOutputHashes = [ordered]@{}
$taskMissing = @()
foreach ($taskName in @('plan.json','receipt.json','worker.json','bounded_execution.json','tests.xml','parent_stdout.log','parent_stderr.log')) {
    $taskFile = Join-Path $taskOutput $taskName
    try {
        if (Test-Path -LiteralPath $taskFile -PathType Leaf) { $taskOutputHashes[$taskName] = Get-TaskHash $taskFile }
        else { $taskMissing += $taskName }
    } catch { $taskMissing += $taskName }
}
$taskAccepted = ($taskStarted -and $taskExitCode -eq 0 -and -not $taskOuterTimeout -and
    $null -eq $taskException -and $taskCleanupErrors.Count -eq 0 -and $taskChanged.Count -eq 0 -and
    $taskMissing.Count -eq 0 -and $null -ne $taskElapsedTicks -and
    $taskElapsedTicks -ge 0 -and $taskElapsedTicks -le $taskBudgetTicks)
$taskRecord = [ordered]@{
    schema = 'g31.bridge.saved_C_digest.pure_external.v1'
    command = $taskCommand
    working_directory = $taskWorkspace
    environment_explicit = $taskEnvironment
    remaining_environment = 'Inherited unchanged; no new HASHSEED/NOUSERSITE setting.'
    python = [ordered]@{path=$taskPython;sha256=$taskPythonHash}
    wrapper = [ordered]@{path=$taskWrapperPath;sha256=$taskWrapperHash}
    source_sha256 = $taskSourcePins
    source_changed = @($taskChanged)
    pid = $taskPID
    started = $taskStarted
    exit_code = $taskExitCode
    started_UTC = $taskStartedUTC
    ended_UTC = $taskEndedUTC
    start_ticks = $taskStartTicks
    end_ticks = $taskEndTicks
    elapsed_ticks = $taskElapsedTicks
    tick_frequency = $taskFrequency
    budget_ticks = $taskBudgetTicks
    whole_python_seconds = $taskWall
    outer_timeout = $taskOuterTimeout
    exception = $taskException
    cleanup_errors = @($taskCleanupErrors)
    output_sha256 = $taskOutputHashes
    missing_outputs = @($taskMissing)
    accepted_launch_and_clock = $taskAccepted
    expected_tests = 37
    scope = 'Full Python launch/import, source union archive/checks, synthetic37, outputs and exit. No C load, actual fixture decode, native/model/performance/full bridge audit. Inner receipt/XML separately establish test outcome. PowerShell startup/prelaunch checks and final external export are disclosed harness overhead outside the Python envelope.'
    harness_pre_external_export_seconds = $taskHarnessClock.Elapsed.TotalSeconds
}
if ($taskFreshOutput) {
    if (-not (Test-Path -LiteralPath $taskOutput)) { [void][IO.Directory]::CreateDirectory($taskOutput) }
    $taskExternal = Join-Path $taskOutput 'external_application_wall.json'
} else {
    $taskExternal = Join-Path (Split-Path -Parent $taskWrapperPath) 'control_timers_bcp2_prelaunch_failure_001.json'
}
$taskRaw = [Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 16))
$taskStream = [IO.File]::Open($taskExternal, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $taskStream.Write($taskRaw, 0, $taskRaw.Length) } finally { $taskStream.Dispose() }
[ordered]@{exit_code=$taskExitCode;whole_python_seconds=$taskWall;source_changed=@($taskChanged);missing_outputs=@($taskMissing);external_sha256=(Get-TaskHash $taskExternal)} | ConvertTo-Json -Depth 4
if (-not $taskAccepted) { exit 1 }
exit 0
