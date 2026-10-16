$ErrorActionPreference = 'Stop'
$taskWrapperWatch = [System.Diagnostics.Stopwatch]::StartNew()
$taskRoot = [System.IO.Path]::GetFullPath('C:\PROGRAMING\czr005\.g31_ics_circulation_worktree')
$taskOutput = Join-Path $taskRoot 'outputs\cprep1'
$taskPython = [System.IO.Path]::GetFullPath('C:\PROGRAMING\python3.11.9\python.exe')
$taskModule = 'scripts.experiments.g31_ics_circulation.run_constructor_prelude_pure'
$taskArgs = @('-m', $taskModule, '--output', $taskOutput)
$taskRunner = Join-Path $taskRoot 'scripts\experiments\g31_ics_circulation\run_constructor_prelude_pure.py'
if (Test-Path -LiteralPath $taskOutput) { throw 'constructor prelude pure output already exists' }
$taskWrapperPath = [System.IO.Path]::GetFullPath($PSCommandPath)
$taskWrapperSha = (Get-FileHash -LiteralPath $taskWrapperPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskRunnerSha = (Get-FileHash -LiteralPath $taskRunner -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPythonSha = (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') { throw 'unexpected Python binary' }
$taskExpectedPins = [ordered]@{
    'scripts/experiments/g31_ics_circulation/constructor_prelude_instrumentation.py' = '711fa89e746950b6bcf16e489d29610f1d03118b9fffb1b9b863baa739cb2f91'
    'tests/test_g31_circulation_constructor_prelude.py' = '02e66eb5702142cd33a2244f8aa048dd65b86a8123451c6d2c1be088868595b9'
    'scripts/experiments/g31_ics_circulation/run_constructor_prelude_pure.py' = '2faac450b124e54a8a03edb928089368e1e553f3c385cae3b2a63a24c679aff3'
    'scripts/experiments/g31_ics_circulation/run_static_root_inventory_pure.py' = 'b1e46f7463d4eb005ab69ea9f4c2281b0600f4ea8170f7dfe956fceda15d1131'
    'outputs/sicp1/plan.json' = 'b34a896cf0b9c503536198fc6131faa18b0acfd00629560d62bf14a333805d6a'
    'outputs/sicp1/root_saved_review_001.json' = 'f2921a9d07a5a7c6ed7b40d33d0bfc27771d514c59bad48de0cf4b0ca36d93e7'
}
$taskFixedPins = [ordered]@{}
$taskFixedEntryPassed = $true
foreach ($taskRelative in $taskExpectedPins.Keys) {
    $taskPinPath = Join-Path $taskRoot $taskRelative
    $taskPinHash = (Get-FileHash -LiteralPath $taskPinPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskPinMatches = ($taskPinHash -eq $taskExpectedPins[$taskRelative])
    if (-not $taskPinMatches) { $taskFixedEntryPassed = $false }
    $taskFixedPins[$taskRelative] = [ordered]@{
        path = $taskPinPath; expected_sha256 = $taskExpectedPins[$taskRelative]
        entry_sha256 = $taskPinHash; entry_matches = $taskPinMatches
    }
}
$env:PYTHONPATH = 'src;.;tests'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location -LiteralPath $taskRoot
$taskWatch = [System.Diagnostics.Stopwatch]::StartNew()
$taskLaunchAttempted = $false
$taskExit = $null
$taskException = $null
try {
    if ($taskFixedEntryPassed) {
        $taskLaunchAttempted = $true
        & $taskPython @taskArgs
        $taskExit = $LASTEXITCODE
    }
} catch {
    $taskException = $_.Exception.ToString()
} finally {
    $taskWatch.Stop()
}
$taskTicks = $taskWatch.ElapsedTicks
$taskFrequency = [System.Diagnostics.Stopwatch]::Frequency
$taskSeconds = [double]$taskTicks / [double]$taskFrequency
$taskOutputs = [ordered]@{}
$taskMissingOutputs = [System.Collections.Generic.List[string]]::new()
foreach ($taskName in @('plan.json', 'collection.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'worker.stdout.log', 'worker.stderr.log')) {
    $taskPath = Join-Path $taskOutput $taskName
    if (Test-Path -LiteralPath $taskPath -PathType Leaf) {
        $taskOutputs[$taskName] = [ordered]@{
            path = $taskPath; sha256 = (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    } else {
        $taskOutputs[$taskName] = $null
        $taskMissingOutputs.Add($taskName)
    }
}
$taskWrapperAfter = (Get-FileHash -LiteralPath $taskWrapperPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskRunnerAfter = (Get-FileHash -LiteralPath $taskRunner -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPythonAfter = (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
$taskFixedExitPassed = $true
foreach ($taskRelative in $taskExpectedPins.Keys) {
    $taskPinHash = (Get-FileHash -LiteralPath $taskFixedPins[$taskRelative].path -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskPinMatches = ($taskPinHash -eq $taskExpectedPins[$taskRelative])
    if (-not $taskPinMatches) { $taskFixedExitPassed = $false }
    $taskFixedPins[$taskRelative]['exit_sha256'] = $taskPinHash
    $taskFixedPins[$taskRelative]['exit_matches'] = $taskPinMatches
}
$taskWrapperTicks = $taskWrapperWatch.ElapsedTicks
$taskStatusPass = ($taskLaunchAttempted -and $null -eq $taskException -and $taskFixedEntryPassed -and $taskFixedExitPassed -and
    $taskExit -eq 0 -and $taskMissingOutputs.Count -eq 0 -and $taskTicks -le (120 * $taskFrequency) -and
    $taskWrapperTicks -le (120 * $taskFrequency) -and $taskWrapperAfter -eq $taskWrapperSha -and
    $taskRunnerAfter -eq $taskRunnerSha -and $taskPythonAfter -eq $taskPythonSha)
$taskWrapperExit = $(if ($taskStatusPass) { 0 } else { 1 })
$taskReceipt = [ordered]@{
    schema = 'g31.constructor_prelude_pure.external.v1'
    status = $(if ($taskStatusPass) { 'exited_zero' } else { 'failed_or_whole_budget_exceeded' })
    command = @($taskPython) + $taskArgs
    cwd = $taskRoot
    output_directory = $taskOutput
    python_sha256 = $taskPythonSha
    python_after_sha256 = $taskPythonAfter
    exitcode = $taskExit
    wrapper_exitcode = $taskWrapperExit
    exception = $taskException
    stopwatch_frequency = $taskFrequency
    elapsed_ticks = $taskTicks
    external_application_seconds = $taskSeconds
    clock_scope = 'immediately_before_python_launch_through_process_return_including_python_startup_and_exit'
    wrapper_before_final_receipt_ticks = $taskWrapperTicks
    wrapper_before_final_receipt_seconds = [double]$taskWrapperTicks / [double]$taskFrequency
    wrapper_clock_scope = 'wrapper_entry_through_all_output_hashes_and_exit_pins_before_final_receipt_export'
    wrapper = [ordered]@{ path = $taskWrapperPath; sha256 = $taskWrapperSha }
    wrapper_after_sha256 = $taskWrapperAfter
    runner = [ordered]@{ path = $taskRunner; sha256 = $taskRunnerSha }
    runner_after_sha256 = $taskRunnerAfter
    fixed_source_pins = $taskFixedPins
    fixed_source_entry_passed = $taskFixedEntryPassed
    fixed_source_exit_passed = $taskFixedExitPassed
    python_launch_attempted = $taskLaunchAttempted
    environment = [ordered]@{
        PYTHONPATH = $env:PYTHONPATH
        PYTEST_DISABLE_PLUGIN_AUTOLOAD = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
        PYTHONIOENCODING = $env:PYTHONIOENCODING
    }
    outputs = $taskOutputs
    missing_outputs = @($taskMissingOutputs.ToArray())
    actual_test_count_source = 'collection.json recorded by the plugin before execution; cross-checked against tests.xml by the owned worker'
    native_calls = 0
    model_predictions = 0
    custom_C_loads = 0
    actual_raw_reads = 0
    synthetic_only = $true
}
if (-not (Test-Path -LiteralPath $taskOutput)) {
    New-Item -ItemType Directory -Path $taskOutput | Out-Null
}
$taskReceiptPath = Join-Path $taskOutput 'external_application_wall.json'
$taskText = $taskReceipt | ConvertTo-Json -Depth 15
$taskStream = [System.IO.File]::Open($taskReceiptPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
try {
    $taskBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($taskText + "`n")
    $taskStream.Write($taskBytes, 0, $taskBytes.Length)
} finally {
    $taskStream.Dispose()
}
Write-Output $taskText
exit $taskWrapperExit
