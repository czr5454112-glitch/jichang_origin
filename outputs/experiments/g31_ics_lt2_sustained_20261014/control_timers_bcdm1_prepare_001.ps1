$ErrorActionPreference = 'Stop'
$taskWorkspace = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$taskBase = Join-Path $taskWorkspace 'outputs\experiments\g31_ics_lt2_sustained_20261014'
$taskOutput = Join-Path $taskBase 'bcdm1'
$taskPure = Join-Path $taskBase 'bcdp2'
$taskPython = 'C:\PROGRAMING\python3.11.9\python.exe'
$taskPythonHash = '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
$taskReferencePins = [ordered]@{
    'plan.json' = '3cec8d06031be2dc7b41af3f5fca6c9e7e3ec43399ef0bda071e7d8ac0ee4c22'
    'receipt.json' = 'f4f880adc9d659a2f0cc9f96ab40fac6b85b554ac837fe86fd6c4cd1918ef285'
    'worker.json' = 'e5a1bf5cb9f1d6768f9ddc710d25ee26fda0148f7073119e52fafb6933a527a9'
    'bounded_execution.json' = '5c4978d4a3f6e7da216b2ad8f6b5eeb80ce892110f3fe9b9c562d165976526d8'
    'tests.xml' = '8af4bb8722c07cc4b8946965eff3f66395310125423d7cab9b677d4d618fe180'
    'parent_stages.jsonl' = '0874531d2ca74f9a33f1c8dbb8b9fb9d59f4f2fd047bb8c8b4ab99916e04d537'
    'worker_stages.jsonl' = 'dd07b05b164e191118267415713fa175591271396e630b18c82823fb940b2bf3'
    'external_application_wall.json' = '143ace300e68d8f9e6a8f4fe2a0b5f6dd438229a6d1ea4668508af5cdf9f66bd'
}
$taskEnvironment = [ordered]@{
    PYTHONPATH = 'src;.;tests'
    PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    PYTHONIOENCODING = 'utf-8'
}
$taskModule = 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_c_digest_v2'
$taskCommand = @($taskPython, '-m', $taskModule, '--prepare', '--output', $taskOutput,
    '--pure-receipt', (Join-Path $taskPure 'receipt.json'))
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
$taskSourcePins = [ordered]@{}

function Get-TaskHash([string] $LiteralFile) {
    return (Get-FileHash -LiteralPath $LiteralFile -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-TaskSourcePath([string] $RelativeFile) {
    $taskCanonical = [IO.Path]::GetFullPath((Join-Path $taskWorkspace $RelativeFile))
    $taskPrefix = $taskWorkspace.TrimEnd('\') + '\'
    if ([IO.Path]::IsPathRooted($RelativeFile) -or
        -not $taskCanonical.StartsWith($taskPrefix, [StringComparison]::OrdinalIgnoreCase) -or
        $taskCanonical.Length -ge 260) { throw ('source_path_domain:' + $RelativeFile) }
    return $taskCanonical
}

try {
    if (Test-Path -LiteralPath $taskOutput) { throw 'fresh_bcdm1_output_required' }
    $taskFreshOutput = $true
    $taskWrapperHash = Get-TaskHash $taskWrapperPath
    if ((Get-TaskHash $taskPython) -ne $taskPythonHash) { throw 'python_identity' }
    foreach ($taskName in $taskReferencePins.Keys) {
        if ((Get-TaskHash (Join-Path $taskPure $taskName)) -ne $taskReferencePins[$taskName]) {
            throw ('pure_reference_identity:' + $taskName)
        }
    }
    $taskPureReceipt = Get-Content -Raw -LiteralPath (Join-Path $taskPure 'receipt.json') | ConvertFrom-Json
    foreach ($taskProperty in $taskPureReceipt.source_sha256.PSObject.Properties) {
        $taskName = $taskProperty.Name
        $taskSource = Get-TaskSourcePath $taskName
        $taskArchive = Join-Path (Join-Path $taskPure 'source') $taskName
        if ((Get-TaskHash $taskSource) -ne $taskProperty.Value -or
            (Get-TaskHash $taskArchive) -ne $taskProperty.Value) { throw ('source_identity:' + $taskName) }
        $taskSourcePins[$taskName] = $taskProperty.Value
    }
    if ($taskSourcePins.Count -ne 138) { throw 'source_domain_138' }
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
        if ((Get-TaskHash (Get-TaskSourcePath $taskName)) -ne $taskSourcePins[$taskName] -or
            (Get-TaskHash (Join-Path (Join-Path $taskPure 'source') $taskName)) -ne $taskSourcePins[$taskName]) {
            $taskChanged += $taskName
        }
    } catch { $taskChanged += $taskName }
}
foreach ($taskName in $taskReferencePins.Keys) {
    try {
        if ((Get-TaskHash (Join-Path $taskPure $taskName)) -ne $taskReferencePins[$taskName]) {
            $taskChanged += ('pure/' + $taskName)
        }
    } catch { $taskChanged += ('pure/' + $taskName) }
}
try { if ((Get-TaskHash $taskPython) -ne $taskPythonHash) { $taskChanged += $taskPython } }
catch { $taskChanged += $taskPython }
try {
    if ($null -eq $taskWrapperHash -or (Get-TaskHash $taskWrapperPath) -ne $taskWrapperHash) { $taskChanged += $taskWrapperPath }
} catch { $taskChanged += $taskWrapperPath }
$taskOutputHashes = [ordered]@{}
$taskMissing = @()
foreach ($taskName in @('plan.json', 'preparation.json')) {
    try {
        $taskFile = Join-Path $taskOutput $taskName
        if (Test-Path -LiteralPath $taskFile -PathType Leaf) { $taskOutputHashes[$taskName] = Get-TaskHash $taskFile }
        else { $taskMissing += $taskName }
    } catch { $taskMissing += $taskName }
}
$taskMetadataCheck = $false
$taskMetadataError = $null
try {
    $taskPlan = Get-Content -Raw -LiteralPath (Join-Path $taskOutput 'plan.json') | ConvertFrom-Json
    $taskPrepared = Get-Content -Raw -LiteralPath (Join-Path $taskOutput 'preparation.json') | ConvertFrom-Json
    if ($taskPrepared.status -ne 'prepared_source_review_pending' -or
        $taskPrepared.plan_sha256 -ne $taskOutputHashes['plan.json'] -or
        $taskPrepared.source_count -ne 138 -or $taskPrepared.routing_pure_tests -ne 37 -or
        $taskPrepared.driver_pure_tests -ne 27 -or $taskPrepared.driver_pure_executed -ne $true -or
        $taskPrepared.saved_audit_executed -ne $false -or $taskPrepared.extension_loads -ne 0 -or
        $taskPrepared.native_calls -ne 0 -or $taskPrepared.predictions -ne 0 -or
        $taskPrepared.large_evidence_reads_this_preparation -ne 0 -or
        $taskPlan.schema -ne 'g31.bridge.saved_C_digest_audit.v2' -or
        @($taskPlan.source_before.PSObject.Properties).Count -ne 138) { throw 'prepared_metadata_contract' }
    $taskExpectedExecution = @($taskPython, '-m', $taskModule, '--execute', '--output', $taskOutput,
        '--plan-sha256', $taskOutputHashes['plan.json'])
    if (($taskPrepared.command | ConvertTo-Json -Compress) -cne ($taskExpectedExecution | ConvertTo-Json -Compress)) {
        throw 'prepared_execution_command'
    }
    foreach ($taskName in $taskSourcePins.Keys) {
        $taskSource = Get-TaskSourcePath $taskName
        $taskExpected = $taskSourcePins[$taskName]
        if ($taskPlan.source_before.PSObject.Properties[$taskSource].Value -ne $taskExpected -or
            (Get-TaskHash (Join-Path (Join-Path $taskOutput 'source') $taskName)) -ne $taskExpected) {
            throw ('prepared_source_archive:' + $taskName)
        }
    }
    $taskMetadataCheck = $true
} catch { $taskMetadataError = $_.Exception.Message }
$taskAccepted = ($taskStarted -and $taskExitCode -eq 0 -and -not $taskOuterTimeout -and
    $null -eq $taskException -and $taskCleanupErrors.Count -eq 0 -and $taskChanged.Count -eq 0 -and
    $taskMissing.Count -eq 0 -and $taskMetadataCheck -and $null -ne $taskElapsedTicks -and
    $taskElapsedTicks -ge 0 -and $taskElapsedTicks -le $taskBudgetTicks)
$taskRecord = [ordered]@{
    schema = 'g31.bridge.saved_C_digest.metadata_external.v1'
    command = $taskCommand
    working_directory = $taskWorkspace
    environment_explicit = $taskEnvironment
    remaining_environment = 'Inherited unchanged; no new HASHSEED/NOUSERSITE setting.'
    python = [ordered]@{path=$taskPython;sha256=$taskPythonHash}
    wrapper = [ordered]@{path=$taskWrapperPath;sha256=$taskWrapperHash}
    pure_directory = $taskPure
    pure_reference_sha256 = $taskReferencePins
    source_sha256 = $taskSourcePins
    source_count = $taskSourcePins.Count
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
    metadata_checked = $taskMetadataCheck
    metadata_error = $taskMetadataError
    accepted_metadata_launch_and_clock = $taskAccepted
    scope = 'Metadata preparation only. All138 current and independent source archives, accepted routing37 and separate driver27 evidence remain checked. Large saved evidence hashes are inherited with disclosed provenance; actual600 must freshly rehash them. No C load, actual fixture decode, native/model/predictor, benchmark or full saved audit. Single Python preparation process is externally bounded120, with full launch/import/output/exit charged. No inner WindowsJob is claimed for metadata-only prepare. PowerShell startup/prelaunch and post-exit hash/check/external export are harness overhead, outside the Python envelope.'
    harness_pre_external_export_seconds = $taskHarnessClock.Elapsed.TotalSeconds
}
if ($taskFreshOutput) {
    if (-not (Test-Path -LiteralPath $taskOutput)) { [void][IO.Directory]::CreateDirectory($taskOutput) }
    $taskExternal = Join-Path $taskOutput 'external_application_wall.json'
} else {
    $taskExternal = Join-Path (Split-Path -Parent $taskWrapperPath) 'control_timers_bcdm1_prelaunch_failure_001.json'
}
$taskRaw = [Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 16))
$taskStream = [IO.File]::Open($taskExternal, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $taskStream.Write($taskRaw, 0, $taskRaw.Length) } finally { $taskStream.Dispose() }
[ordered]@{exit_code=$taskExitCode;whole_python_seconds=$taskWall;source_changed=@($taskChanged);missing_outputs=@($taskMissing);metadata_checked=$taskMetadataCheck;external_sha256=(Get-TaskHash $taskExternal)} | ConvertTo-Json -Depth 4
if (-not $taskAccepted) { exit 1 }
exit 0
