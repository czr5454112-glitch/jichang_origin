param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedRootReviewSha256)
$ErrorActionPreference = 'Stop'
$taskWorkspace = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$taskBase = Join-Path $taskWorkspace 'outputs\experiments\g31_ics_lt2_sustained_20261014'
$taskOutput = Join-Path $taskBase 'bcdm2'
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
    PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    PYTHONIOENCODING = 'utf-8'
}
$taskPlanHash = 'ce7168ac603be884b45c8822aefadef70a65a0f546971a4b675e52539af87b57'
$taskMetadataPins = [ordered]@{
    'plan.json' = $taskPlanHash
    'preparation.json' = '723753e39c001b283371d9064218ed6ec2cc6f61a8379c01183068612bba033e'
    'external_application_wall.json' = '1e3c81253299df70d82c2c064d2892f7aa8c484ea06b8930a389aac6ec367e96'
    'startup_environment_plan.json' = 'daf88e9cd85a70c6e8b7030acd2fbd1d6419d8f7e007da37461bab19805adfd3'
    'root_execution_review_001.json' = $ExpectedRootReviewSha256
}
$taskCgatePath = Join-Path $taskBase 'planning_v2_C_encoder_gate_prepare_003\plan.json'
$taskCgateHash = 'd6912d695e36707dbba6bd7a0359e5ec6c6ed1a964323e99c4aae4fecf28579b'
$taskStartupExpected = [ordered]@{PYTHONPATH=$null;PYTHONHOME=$null;PYTHONNOUSERSITE=$null;SETUPTOOLS_USE_DISTUTILS=$null}
$taskStartupConfigured = [ordered]@{}
$taskStartupActions = [ordered]@{}
$taskStartupCrosscheck = $false
$taskModule = 'scripts.experiments.g31_ics_circulation.audit_bridge_saved_c_digest_v2'
$taskCommand = @($taskPython, '-m', $taskModule, '--execute', '--output', $taskOutput,
    '--plan-sha256', $taskPlanHash)
$taskWrapperPath = $PSCommandPath
$taskHarnessClock = [Diagnostics.Stopwatch]::StartNew()
[long]$taskFrequency = [Diagnostics.Stopwatch]::Frequency
[long]$taskBudgetTicks = [long]600 * $taskFrequency
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
    foreach ($taskName in @('actual_external_application_wall.json', 'execution_claim.json', 'bounded_execution.json',
        'report.json', 'progress.jsonl', 'stdout.log', 'stderr.log', 'C_encoder_entry.json', 'C_encoder_exit.json',
        'all_job_states.json.gz', 'failure.json')) {
        if (Test-Path -LiteralPath (Join-Path $taskOutput $taskName)) { throw ('preserve_saved600_attempt:' + $taskName) }
    }
    foreach ($taskName in $taskMetadataPins.Keys) {
        if ((Get-TaskHash (Join-Path $taskOutput $taskName)) -ne $taskMetadataPins[$taskName]) {
            throw ('reviewed_metadata_identity:' + $taskName)
        }
    }
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
        $taskOwnArchive = Join-Path (Join-Path $taskOutput 'source') $taskName
        if ((Get-TaskHash $taskSource) -ne $taskProperty.Value -or
            (Get-TaskHash $taskArchive) -ne $taskProperty.Value -or (Get-TaskHash $taskOwnArchive) -ne $taskProperty.Value) { throw ('source_identity:' + $taskName) }
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
    if ((Get-TaskHash $taskCgatePath) -ne $taskCgateHash) { throw 'C_gate_plan_identity' }
    $taskCgate = Get-Content -Raw -LiteralPath $taskCgatePath | ConvertFrom-Json
    $taskStartupSaved = Get-Content -Raw -LiteralPath (Join-Path $taskOutput 'startup_environment_plan.json') | ConvertFrom-Json
    if ((@($taskCgate.python_startup_environment.PSObject.Properties.Name) | ConvertTo-Json -Compress) -cne
        (@($taskStartupExpected.Keys) | ConvertTo-Json -Compress)) { throw 'C_startup_key_domain' }
    if ($taskStartupSaved.schema -ne 'g31.bridge.saved_C_digest.startup_environment_plan.v1' -or
        $taskStartupSaved.C_gate_plan.path -cne $taskCgatePath -or $taskStartupSaved.C_gate_plan.sha256 -cne $taskCgateHash -or
        $taskStartupSaved.exact_crosscheck -ne $true -or
        ($taskStartupSaved.expected | ConvertTo-Json -Compress) -cne ($taskStartupExpected | ConvertTo-Json -Compress) -or
        ($taskStartupSaved.other_explicit | ConvertTo-Json -Compress) -cne ($taskEnvironment | ConvertTo-Json -Compress)) { throw 'paired_startup_plan' }
    foreach ($taskName in $taskStartupExpected.Keys) {
        $taskValue = $taskCgate.python_startup_environment.PSObject.Properties[$taskName].Value
        if ($null -ne $taskValue -or $taskEnvironment.Contains($taskName)) { throw ('C_startup_expected_absence:' + $taskName) }
        [void]$taskStartInfo.Environment.Remove($taskName)
        $taskStartupActions[$taskName] = 'Remove'
        $taskPresent = $taskStartInfo.Environment.ContainsKey($taskName)
        if ($taskPresent) { throw ('C_startup_remove_failed:' + $taskName) }
        $taskStartupConfigured[$taskName] = [ordered]@{present=$taskPresent;value=$null}
    }
    if (($taskStartupSaved.actions | ConvertTo-Json -Compress) -cne ($taskStartupActions | ConvertTo-Json -Compress) -or
        ($taskStartupSaved.configured_process_startinfo | ConvertTo-Json -Depth 4 -Compress) -cne ($taskStartupConfigured | ConvertTo-Json -Depth 4 -Compress)) { throw 'paired_startup_remove_mapping' }
    $taskStartupCrosscheck = $true
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
            (Get-TaskHash (Join-Path (Join-Path $taskPure 'source') $taskName)) -ne $taskSourcePins[$taskName] -or
            (Get-TaskHash (Join-Path (Join-Path $taskOutput 'source') $taskName)) -ne $taskSourcePins[$taskName]) {
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
foreach ($taskName in $taskMetadataPins.Keys) {
    try {
        if ((Get-TaskHash (Join-Path $taskOutput $taskName)) -ne $taskMetadataPins[$taskName]) {
            $taskChanged += ('metadata/' + $taskName)
        }
    } catch { $taskChanged += ('metadata/' + $taskName) }
}
try { if ((Get-TaskHash $taskCgatePath) -ne $taskCgateHash) { $taskChanged += 'C_gate_plan' } }
catch { $taskChanged += 'C_gate_plan' }
$taskOutputHashes = [ordered]@{}
$taskMissing = @()
foreach ($taskName in @('plan.json', 'preparation.json', 'execution_claim.json', 'bounded_execution.json',
    'report.json', 'progress.jsonl', 'stdout.log', 'stderr.log', 'C_encoder_entry.json', 'C_encoder_exit.json',
    'all_job_states.json.gz')) {
    try {
        $taskFile = Join-Path $taskOutput $taskName
        if (Test-Path -LiteralPath $taskFile -PathType Leaf) { $taskOutputHashes[$taskName] = Get-TaskHash $taskFile }
        else { $taskMissing += $taskName }
    } catch { $taskMissing += $taskName }
}
$taskAuditCheck = $false
$taskAuditError = $null
try {
    $taskReport = Get-Content -Raw -LiteralPath (Join-Path $taskOutput 'report.json') | ConvertFrom-Json
    $taskBounded = Get-Content -Raw -LiteralPath (Join-Path $taskOutput 'bounded_execution.json') | ConvertFrom-Json
    if ($taskReport.schema -ne 'g31.bridge.saved_C_digest_audit.v2' -or
        $taskReport.status -ne 'passed_complete_saved_audit' -or $taskReport.plan_sha256 -ne $taskPlanHash -or
        $taskReport.result.replay.api_rows -ne 37270 -or
        $taskReport.result.same_policy_old001_complete_prefix.rows -ne 27218 -or
        $taskReport.native_calls -ne 0 -or $taskReport.predictions -ne 0 -or
        $taskReport.C_encoder.extension_loads -ne 1 -or
        $taskReport.C_encoder.actual_direct_and_fallback_counts -ne 'not_instrumented_unknown' -or
        $taskBounded.hard_seconds -ne 600 -or $taskBounded.process.status -ne 'exited' -or
        $taskBounded.process.exitcode -ne 0 -or
        $taskBounded.process.windows_job_kill_on_close -ne $true -or
        $taskBounded.process.child_released_only_after_job_assignment -ne $true -or
        $taskBounded.report_sha256 -ne $taskOutputHashes['report.json']) { throw 'complete_saved_audit_contract' }
    $taskAuditCheck = $true
} catch { $taskAuditError = $_.Exception.Message }
# Preserve known failure-sidecar hashes without treating any failed attempt as
# a successful partial certificate. Never decode the producer's large raw here.
foreach ($taskName in @('failure.json', 'failure_origin.json')) {
    $taskFile = Join-Path $taskOutput $taskName
    if (Test-Path -LiteralPath $taskFile -PathType Leaf) {
        try { $taskOutputHashes[$taskName] = Get-TaskHash $taskFile }
        catch { $taskMissing += $taskName }
    }
}
$taskAccepted = ($taskStarted -and $taskExitCode -eq 0 -and -not $taskOuterTimeout -and
    $null -eq $taskException -and $taskCleanupErrors.Count -eq 0 -and $taskChanged.Count -eq 0 -and
    $taskMissing.Count -eq 0 -and $taskAuditCheck -and $taskStartupCrosscheck -and $null -ne $taskElapsedTicks -and
    $taskElapsedTicks -ge 0 -and $taskElapsedTicks -le $taskBudgetTicks)
$taskRecord = [ordered]@{
    schema = 'g31.bridge.saved_C_digest.saved600_external.v2'
    command = $taskCommand
    working_directory = $taskWorkspace
    environment_explicit = $taskEnvironment
    C_gate_startup_environment = $taskStartupExpected
    C_gate_environment_actions = $taskStartupActions
    C_gate_configured_process_startinfo = $taskStartupConfigured
    C_gate_startup_crosscheck = $taskStartupCrosscheck
    C_gate_plan = [ordered]@{path=$taskCgatePath;sha256=$taskCgateHash}
    remaining_environment = 'Four exact C-bound keys removed; two explicit test/UTF8 keys set. All other variables inherited unchanged.'
    python = [ordered]@{path=$taskPython;sha256=$taskPythonHash}
    wrapper = [ordered]@{path=$taskWrapperPath;sha256=$taskWrapperHash}
    pure_directory = $taskPure
    pure_reference_sha256 = $taskReferencePins
    metadata_reference_sha256 = $taskMetadataPins
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
    complete_saved_audit_checked = $taskAuditCheck
    audit_error = $taskAuditError
    accepted_complete_saved_audit_and_clock = $taskAccepted
    scope = 'ONE separate saved-only600. Full Python launch/import, original input/raw/source/reference hash checks, all37270 new and27218 old ordered rows, policy replay and all28506-job/22-tray physical/FIFO/Storage/ACK/cap checks, accepted C encoder load and7779/3082 dependency checks on entry/exit, derived export/cleanup/exit are charged. Original policy and actor-copy scheme remain; only private typed-v2 digest binding changes. No new native simulator or predictor. Actual C direct/fallback mix uninstrumented unknown. Original producer2400 and every prior saved600 failure remain failed; no business completeness/speedup/100ms claim. Internal owned WindowsJob and external process-tree limit are each600. PowerShell startup/prelaunch/post-exit hashes and final external export are disclosed harness overhead outside Python wall. Progress completedN does not certify the Nth policy consumption or a full audit.'
    harness_pre_external_export_seconds = $taskHarnessClock.Elapsed.TotalSeconds
}
if ($taskFreshOutput) {
    if (-not (Test-Path -LiteralPath $taskOutput)) { [void][IO.Directory]::CreateDirectory($taskOutput) }
    $taskExternal = Join-Path $taskOutput 'actual_external_application_wall.json'
} else {
    $taskExternal = Join-Path (Split-Path -Parent $taskWrapperPath) 'control_timers_bcdm2_saved600_prelaunch_failure_001.json'
}
$taskRaw = [Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 16))
$taskStream = [IO.File]::Open($taskExternal, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $taskStream.Write($taskRaw, 0, $taskRaw.Length) } finally { $taskStream.Dispose() }
[ordered]@{exit_code=$taskExitCode;whole_python_seconds=$taskWall;source_changed=@($taskChanged);missing_outputs=@($taskMissing);complete_saved_audit_checked=$taskAuditCheck;external_sha256=(Get-TaskHash $taskExternal)} | ConvertTo-Json -Depth 4
if (-not $taskAccepted) { exit 1 }
exit 0
