$ErrorActionPreference = 'Stop'
$taskWrapperWatch = [System.Diagnostics.Stopwatch]::StartNew()
$taskRoot = [System.IO.Path]::GetFullPath('C:\PROGRAMING\czr005\.g31_ics_circulation_worktree')
$taskOutput = Join-Path $taskRoot 'outputs\sinv1'
$taskPython = [System.IO.Path]::GetFullPath('C:\PROGRAMING\python3.11.9\python.exe')
$taskModule = 'scripts.experiments.g31_ics_circulation.run_static_root_inventory_pure'
$taskArgs = @('-m', $taskModule, '--output', $taskOutput)
$taskRunner = Join-Path $taskRoot 'scripts\experiments\g31_ics_circulation\run_static_root_inventory_pure.py'
if (Test-Path -LiteralPath $taskOutput) { throw 'static inventory pure output already exists' }
$taskWrapperPath = [System.IO.Path]::GetFullPath($PSCommandPath)
$taskWrapperSha = (Get-FileHash -LiteralPath $taskWrapperPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskRunnerSha = (Get-FileHash -LiteralPath $taskRunner -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPythonSha = (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') { throw 'unexpected Python binary' }
$taskExpectedPins = [ordered]@{
    'scripts/experiments/g31_ics_circulation/initial_owner_route_static_inventory.py' = 'fc115018e916af68972672aaa999412336f9dda01ba8e7c742bc299146ecee0a'
    'scripts/experiments/g31_ics_circulation/run_static_root_inventory_pure.py' = 'b1e46f7463d4eb005ab69ea9f4c2281b0600f4ea8170f7dfe956fceda15d1131'
    'tests/test_g31_circulation_static_root_inventory.py' = '6d01ba971fd0bbacb2838bb71347e2f5d9b8e5e4e4dd689fd9da7cf3d0bf54ae'
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
if ($taskFixedEntryPassed) {
    $taskLaunchAttempted = $true
    & $taskPython @taskArgs
    $taskExit = $LASTEXITCODE
}
$taskWatch.Stop()
$taskTicks = $taskWatch.ElapsedTicks
$taskFrequency = [System.Diagnostics.Stopwatch]::Frequency
$taskSeconds = [double]$taskTicks / [double]$taskFrequency
$taskOutputs = [ordered]@{}
foreach ($taskName in @('plan.json', 'collection.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'worker.stdout.log', 'worker.stderr.log')) {
    $taskPath = Join-Path $taskOutput $taskName
    $taskOutputs[$taskName] = $(if (Test-Path -LiteralPath $taskPath) {
        [ordered]@{ path = $taskPath; sha256 = (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() }
    } else { $null })
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
$taskStatusPass = ($taskLaunchAttempted -and $taskFixedEntryPassed -and $taskFixedExitPassed -and
    $taskExit -eq 0 -and $taskTicks -le (120 * $taskFrequency) -and
    $taskWrapperWatch.Elapsed.TotalSeconds -le 120 -and $taskWrapperAfter -eq $taskWrapperSha -and
    $taskRunnerAfter -eq $taskRunnerSha -and $taskPythonAfter -eq $taskPythonSha)
$taskWrapperExit = $(if ($taskStatusPass) { 0 } else { 1 })
$taskReceipt = [ordered]@{
    schema = 'g31.static_inventory_pure.external.v1'
    status = $(if ($taskStatusPass) { 'exited_zero' } else { 'failed_or_whole_budget_exceeded' })
    command = @($taskPython) + $taskArgs
    cwd = $taskRoot
    output_directory = $taskOutput
    python_sha256 = $taskPythonSha
    python_after_sha256 = $taskPythonAfter
    exitcode = $taskExit
    wrapper_exitcode = $taskWrapperExit
    stopwatch_frequency = $taskFrequency
    elapsed_ticks = $taskTicks
    external_application_seconds = $taskSeconds
    clock_scope = 'immediately_before_python_launch_through_process_return_including_python_startup_and_exit'
    wrapper_before_final_receipt_seconds = $taskWrapperWatch.Elapsed.TotalSeconds
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
