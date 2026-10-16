$ErrorActionPreference = 'Stop'
$taskWrapperWatch = [System.Diagnostics.Stopwatch]::StartNew()
$taskRoot = [System.IO.Path]::GetFullPath('C:\PROGRAMING\czr005\.g31_ics_circulation_worktree')
$taskOutput = Join-Path $taskRoot 'outputs\sicp1'
$taskPython = [System.IO.Path]::GetFullPath('C:\PROGRAMING\python3.11.9\python.exe')
$taskModule = 'scripts.experiments.g31_ics_circulation.run_static_inventory_campaign_pure'
$taskArgs = @('-m', $taskModule, '--output', $taskOutput)
$taskRunner = Join-Path $taskRoot 'scripts\experiments\g31_ics_circulation\run_static_inventory_campaign_pure.py'
if (Test-Path -LiteralPath $taskOutput) { throw 'static inventory campaign pure output already exists' }
$taskWrapperPath = [System.IO.Path]::GetFullPath($PSCommandPath)
$taskWrapperSha = (Get-FileHash -LiteralPath $taskWrapperPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskRunnerSha = (Get-FileHash -LiteralPath $taskRunner -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPythonSha = (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') { throw 'unexpected Python binary' }
$taskExpectedPins = [ordered]@{
    'scripts/experiments/g31_ics_circulation/single_capture_static_inventory_runtime.py' = '9ec4089e19232c4671ee76175ea9b6b068dc57f1e042bf2a398f1a03655b8c60'
    'scripts/experiments/g31_ics_circulation/initial_owner_route_static_inventory_campaign.py' = '0c53e2396fabdbf500d1493dfbb4699ae569867e3f6d0808772022e16ab6202a'
    'scripts/experiments/g31_ics_circulation/verify_initial_owner_route_static_inventory_campaign.py' = 'de81c27b3904354f9bb16eb21cbb47cbc6b3d41fa133e3f723a4cc8ac66464ce'
    'scripts/experiments/g31_ics_circulation/launch_initial_owner_route_static_inventory_campaign.py' = '1711d17609507ea5a068b8121b97276d7adf9a892ced87a051dd7016673ca662'
    'scripts/experiments/g31_ics_circulation/prepare_initial_owner_route_static_inventory_campaign.py' = '037100391abc1a3fd5355ecfc452256bd80e056d00fafb5d2f0397702e9ae3ce'
    'scripts/experiments/g31_ics_circulation/run_static_inventory_campaign_pure.py' = '243012d2874f812b8caa33040f8946480a0656162455011218d15857b67af139'
    'tests/test_g31_circulation_static_inventory_campaign.py' = '51925c46127ac8ed355eaaa43944c8a4761f26e0b5d223ff1840a4f14d07cdcf'
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
$taskStatusPass = ($taskLaunchAttempted -and $null -eq $taskException -and $taskFixedEntryPassed -and $taskFixedExitPassed -and
    $taskExit -eq 0 -and $taskTicks -le (120 * $taskFrequency) -and
    $taskWrapperWatch.Elapsed.TotalSeconds -le 120 -and $taskWrapperAfter -eq $taskWrapperSha -and
    $taskRunnerAfter -eq $taskRunnerSha -and $taskPythonAfter -eq $taskPythonSha)
$taskWrapperExit = $(if ($taskStatusPass) { 0 } else { 1 })
$taskReceipt = [ordered]@{
    schema = 'g31.static_inventory_campaign_pure.external.v1'
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
