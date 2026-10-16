$ErrorActionPreference = 'Stop'
$taskWrapperWatch = [System.Diagnostics.Stopwatch]::StartNew()
$taskRoot = [System.IO.Path]::GetFullPath('C:\PROGRAMING\czr005\.g31_ics_circulation_worktree')
$taskOutput = Join-Path $taskRoot 'outputs\sicm1'
$taskPure = Join-Path $taskRoot 'outputs\sicp1'
$taskPython = [System.IO.Path]::GetFullPath('C:\PROGRAMING\python3.11.9\python.exe')
$taskModule = 'scripts.experiments.g31_ics_circulation.run_static_inventory_campaign_prepare'
$taskArgs = @('-m', $taskModule, '--output', $taskOutput, '--pure-directory', $taskPure)
$taskRunner = Join-Path $taskRoot 'scripts\experiments\g31_ics_circulation\run_static_inventory_campaign_prepare.py'
$taskStdout = $taskOutput + '.outer.stdout.log'
$taskStderr = $taskOutput + '.outer.stderr.log'
$taskTargets = @($taskOutput, $taskStdout, $taskStderr,
    ($taskOutput + '.metadata_claim.json'), ($taskOutput + '.metadata_worker.stdout.log'),
    ($taskOutput + '.metadata_worker.stderr.log'), ($taskOutput + '.metadata_parent.json'))
foreach ($taskTarget in $taskTargets) {
    if ((Test-Path -LiteralPath $taskTarget) -or $taskTarget.Length -ge 260) {
        throw "metadata evidence exists or path too long: $taskTarget"
    }
}
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
    'scripts/experiments/g31_ics_circulation/run_static_inventory_campaign_prepare.py' = 'ce0f3324ecf9ce7b655806a98f83fcb70f1e3550a44d43d7ad60e4d4c632f20e'
    'scripts/experiments/g31_ics_circulation/bounded_windows_job.py' = '798ae87c19d5fa61569b1c9301cebe7ef6a5885302f32f42380cf53fd6363cde'
    'outputs/sicp1/plan.json' = 'b34a896cf0b9c503536198fc6131faa18b0acfd00629560d62bf14a333805d6a'
    'outputs/sicp1/receipt.json' = '63ac2801d83165115d4710b500c04df43064b1b705a5944aeb284c9ce50e64fb'
    'outputs/sicp1/external_application_wall.json' = '2fea6cfa084b295919d17c0020228082ef830d79238260f27832f554a178bb13'
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
$taskStarted = [DateTime]::UtcNow.ToString('o')
$taskLaunchAttempted = $false
$taskExit = $null
$taskException = $null
try {
    if ($taskFixedEntryPassed) {
        $taskLaunchAttempted = $true
        & $taskPython @taskArgs 1> $taskStdout 2> $taskStderr
        $taskExit = $LASTEXITCODE
    }
} catch {
    $taskException = $_.Exception.ToString()
} finally {
    $taskWatch.Stop()
}
$taskEnded = [DateTime]::UtcNow.ToString('o')
$taskTicks = $taskWatch.ElapsedTicks
$taskFrequency = [System.Diagnostics.Stopwatch]::Frequency
$taskSeconds = [double]$taskTicks / [double]$taskFrequency
$taskOutputPaths = [ordered]@{}
foreach ($taskName in @('campaign.json', 'branch_ledger.json', 'source_preparation.json', 'preparation_failure.json', 'metadata_source_binding.json')) {
    $taskOutputPaths[$taskName] = Join-Path $taskOutput $taskName
}
foreach ($taskSuffix in @('.metadata_claim.json', '.metadata_parent.json', '.metadata_worker.stdout.log', '.metadata_worker.stderr.log', '.outer.stdout.log', '.outer.stderr.log')) {
    $taskOutputPaths[$taskSuffix] = $taskOutput + $taskSuffix
}
$taskOutputs = [ordered]@{}
foreach ($taskName in $taskOutputPaths.Keys) {
    $taskPath = $taskOutputPaths[$taskName]
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
$taskArtifactsPresent = $true
foreach ($taskRequired in @('campaign.json', 'branch_ledger.json', 'source_preparation.json', 'metadata_source_binding.json',
    '.metadata_claim.json', '.metadata_parent.json', '.metadata_worker.stdout.log', '.metadata_worker.stderr.log', '.outer.stdout.log', '.outer.stderr.log')) {
    if ($null -eq $taskOutputs[$taskRequired]) { $taskArtifactsPresent = $false }
}
$taskStatusPass = ($taskLaunchAttempted -and $null -eq $taskException -and $taskFixedEntryPassed -and $taskFixedExitPassed -and
    $taskExit -eq 0 -and $taskTicks -le (120 * $taskFrequency) -and $taskArtifactsPresent -and
    $null -eq $taskOutputs['preparation_failure.json'] -and $taskWrapperWatch.Elapsed.TotalSeconds -le 120 -and
    $taskWrapperAfter -eq $taskWrapperSha -and $taskRunnerAfter -eq $taskRunnerSha -and $taskPythonAfter -eq $taskPythonSha)
$taskWrapperExit = $(if ($taskStatusPass) { 0 } else { 1 })
$taskReceipt = [ordered]@{
    schema = 'g31.static_inventory_campaign.metadata.external.v1'
    status = $(if ($taskStatusPass) { 'exited_zero' } else { 'failed_or_whole_budget_exceeded' })
    command = @($taskPython) + $taskArgs
    cwd = $taskRoot
    output_directory = $taskOutput
    pure_directory = $taskPure
    python_sha256 = $taskPythonSha
    python_after_sha256 = $taskPythonAfter
    exitcode = $taskExit
    wrapper_exitcode = $taskWrapperExit
    exception = $taskException
    started_utc = $taskStarted
    ended_utc = $taskEnded
    shared_seconds = 120
    stopwatch_frequency = $taskFrequency
    elapsed_ticks = $taskTicks
    external_application_seconds = $taskSeconds
    clock_scope = 'immediately_before_python_launch_through_process_return_including_python_startup_and_exit'
    wrapper_before_final_receipt_seconds = $taskWrapperWatch.Elapsed.TotalSeconds
    wrapper = [ordered]@{ path = $taskWrapperPath; sha256 = $taskWrapperSha }
    wrapper_after_sha256 = $taskWrapperAfter
    runner = [ordered]@{ path = $taskRunner; sha256 = $taskRunnerSha }
    runner_after_sha256 = $taskRunnerAfter
    fixed_source_and_evidence_pins = $taskFixedPins
    fixed_entry_passed = $taskFixedEntryPassed
    fixed_exit_passed = $taskFixedExitPassed
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
    performance_runs = 0
    metadata_only = $true
    actual_campaign_dispatched = $false
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
