$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskRoot = [System.IO.Path]::GetFullPath('C:\PROGRAMING\czr005\.g31_ics_circulation_worktree')
$taskOutput = Join-Path $taskRoot 'outputs\odp1'
$taskPython = [System.IO.Path]::GetFullPath('C:\PROGRAMING\python3.11.9\python.exe')
$taskArgs = @('-m', 'scripts.experiments.g31_ics_circulation.run_online_initial_dispatch_pure', '--output', $taskOutput)
$taskCommand = @($taskPython) + $taskArgs
$taskExternal = Join-Path $taskOutput 'external_application_wall.json'
if (Test-Path -LiteralPath $taskOutput) { throw 'odp1 already exists; no retry or overwrite' }
$taskWrapper = [System.IO.Path]::GetFullPath($PSCommandPath)
$taskSources = [ordered]@{
    'scripts/experiments/g31_ics_circulation/live_obligation_online_initial_dispatch.py' = '23e50a67a508024e74cbca4d242b0885774c436c1f8a882d112ac61c16e558a0'
    'tests/test_g31_circulation_online_initial_dispatch.py' = '97bd4a2e1511ba8a6ec3f631457b7855064ad38923593fe42433845d7a81f02f'
    'scripts/experiments/g31_ics_circulation/run_online_initial_dispatch_pure.py' = 'd8dcc8f36eb2ff58284779f63f327bc17ec9aa7be0e92cf6f1f6ea46b7f871d6'
    'scripts/experiments/g31_ics_circulation/run_bound_source_proof_pure.py' = '6d350eec74903476f29d66b0993a85a39cad866bee0c1fae87902201066039bf'
}
function Task-Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA246).Hash.ToLowerInvariant() }
function Task-SameCommand($Observed) {
    if ($Observed -isnot [array] -or $Observed.Count -ne $taskCommand.Count) { throw 'command cardinality/type mismatch' }
    for ($taskIndex = 0; $taskIndex -lt $taskCommand.Count; $taskIndex++) {
        if ($Observed[$taskIndex] -isnot [string] -or $Observed[$taskIndex] -cne $taskCommand[$taskIndex]) { throw 'command exact value mismatch' }
    }
}
$taskExpected = [ordered]@{ $taskPython = '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec' }
foreach ($taskName in $taskSources.Keys) { $taskExpected[(Join-Path $taskRoot $taskName)] = $taskSources[$taskName] }
$taskExpected[$taskWrapper] = Task-Sha $taskWrapper
$taskBefore = [ordered]@{}; $taskAfter = [ordered]@{}; $taskOutputs = [ordered]@{}
$taskOutputNames = @('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'stdout.log', 'stderr.log')
$taskFrequency = [long][System.Diagnostics.Stopwatch]::Frequency
$taskTicks = $null; $taskSeconds = $null; $taskExit = $null; $taskLaunched = $false
$taskWrapperExit = 1; $taskStatus = 'unknown_prelaunch_failure'; $taskError = $null
try {
    foreach ($taskPath in $taskExpected.Keys) {
        $taskBefore[$taskPath] = Task-Sha $taskPath
        if ($taskBefore[$taskPath] -cne $taskExpected[$taskPath]) { throw ('prelaunch pin mismatch: ' + $taskPath) }
    }
    Set-Location -LiteralPath $taskRoot
    $env:PYTHONPATH = 'src;.;tests'
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $taskLaunched = $true; $taskStatus = 'unknown_pure_execution'
    $taskWatch = [System.Diagnostics.Stopwatch]::StartNew()
    try { & $taskPython @taskArgs; $taskExit = $LASTEXITCODE }
    finally { $taskWatch.Stop(); $taskTicks = [long]$taskWatch.ElapsedTicks; $taskSeconds = [double]$taskTicks / [double]$taskFrequency }
    if ($taskExit -ne 0) { throw 'Python process did not exit zero' }
    if ($taskFrequency -le 0 -or $taskTicks -lt 0 -or $taskTicks -gt ([long]120 * $taskFrequency)) { throw 'invalid or exceeded whole Python120 clock' }
    $taskPlan = Get-Content -LiteralPath (Join-Path $taskOutput 'plan.json') -Raw | ConvertFrom-Json
    $taskReceipt = Get-Content -LiteralPath (Join-Path $taskOutput 'receipt.json') -Raw | ConvertFrom-Json
    $taskBounded = Get-Content -LiteralPath (Join-Path $taskOutput 'bounded_parent_receipt.json') -Raw | ConvertFrom-Json
    if ($taskPlan.schema -cne 'g31.bound_source_proof.synthetic_pure.v1' -or $taskPlan.expected_tests -ne 24 -or $taskPlan.shared_seconds -ne 120 -or $taskPlan.output_directory -cne $taskOutput) { throw 'plan contract' }
    if ($taskPlan.environment.python -cne $taskPython -or $taskPlan.environment.sha246 -cne $taskExpected[$taskPython]) { throw 'plan interpreter binding' }
    if (@($taskPlan.tests).Count -ne 1 -or $taskPlan.tests[0] -cne 'tests/test_g31_circulation_online_initial_dispatch.py') { throw 'test domain' }
    if ($taskPlan.runner_source_proof.test_count -ne 24 -or $taskPlan.runner_source_proof.original_worker_and_main_code -cne $true -or $taskPlan.runner_source_proof.complete_private_namespace -cne $true -or $taskPlan.runner_source_proof.sticky_original_execution_monitor_unchanged -cne $true -or $taskPlan.runner_source_proof.initial_dispatch_only -cne $true) { throw 'online synthetic runner proof' }
    foreach ($taskName in $taskSources.Keys) {
        if ($taskPlan.source_sha246.PSObject.Properties[$taskName].Value -cne $taskSources[$taskName]) { throw ('plan source binding: ' + $taskName) }
        $taskRelative = $taskPlan.source_archive.PSObject.Properties[$taskName].Value
        if ($taskRelative -cne ('source/' + $taskName)) { throw ('archive canonical path: ' + $taskName) }
        if ((Task-Sha (Join-Path $taskOutput $taskRelative)) -cne $taskSources[$taskName]) { throw ('archive source binding: ' + $taskName) }
    }
    if ($taskReceipt.status -cne 'passed' -or $taskReceipt.pytest_exitcode -ne 0 -or $taskReceipt.tests -ne 24 -or $taskReceipt.expected_tests -ne 24) { throw 'receipt incomplete' }
    if ($taskReceipt.plan_sha246 -cne (Task-Sha (Join-Path $taskOutput 'plan.json')) -or $taskReceipt.XML_sha246 -cne (Task-Sha (Join-Path $taskOutput 'tests.xml'))) { throw 'receipt plan/XML bindings' }
    if ($null -eq $taskReceipt.source_changed -or @($taskReceipt.source_changed).Count -ne 0 -or $null -eq $taskReceipt.blocked_real_calls -or @($taskReceipt.blocked_real_calls).Count -ne 0 -or $taskReceipt.monitor_active_after_tests -cne $true) { throw 'source or execution monitor failure' }
    foreach ($taskField in @('real_original_proof_calls', 'model_entry_calls', 'native_calls', 'custom_data_C_loads')) {
        if ($taskReceipt.PSObject.Properties[$taskField].Value -ne 0) { throw ('forbidden execution: ' + $taskField) }
    }
    if ($taskBounded.status -cne 'passed' -or $taskBounded.shared_seconds -ne 120 -or $taskBounded.output_directory -cne $taskOutput -or $taskBounded.process.status -cne 'exited' -or $taskBounded.process.exitcode -ne 0) { throw 'owned process/budget contract' }
    Task-SameCommand $taskBounded.command
    if ($taskBounded.receipt_sha246 -cne (Task-Sha (Join-Path $taskOutput 'receipt.json'))) { throw 'bounded receipt binding' }
    [xml]$taskXml = Get-Content -LiteralPath (Join-Path $taskOutput 'tests.xml') -Raw
    if (@($taskXml.SelectNodes('//testcase')).Count -ne 24 -or @($taskXml.SelectNodes('//failure|//error|//skipped')).Count -ne 0) { throw 'XML exact24 or failure' }
    $taskStatus = 'passed24_synthetic_with_external_bound'; $taskWrapperExit = 0
}
catch { $taskError = $_.Exception.Message; $taskWrapperExit = 1; $taskStatus = $(if ($taskLaunched) { 'unknown_failed_or_whole_budget_exceeded' } else { 'unknown_prelaunch_failure' }) }
finally {
    foreach ($taskPath in $taskExpected.Keys) {
        try {
            $taskAfter[$taskPath] = Task-Sha $taskPath
            if ($taskAfter[$taskPath] -cne $taskExpected[$taskPath]) { throw 'pin changed' }
        } catch { $taskAfter[$taskPath] = [ordered]@{ error = $_.Exception.Message }; $taskWrapperExit = 1; $taskStatus = 'unknown_final_pin_failure' }
    }
    foreach ($taskName in $taskOutputNames) {
        $taskPath = Join-Path $taskOutput $taskName
        try { $taskOutputs[$taskName] = $(if (Test-Path -LiteralPath $taskPath -PathType Leaf) { [ordered]@{ path = $taskPath; sha246 = Task-Sha $taskPath } } else { $null }) }
        catch { $taskOutputs[$taskName] = [ordered]@{ error = $_.Exception.Message }; $taskWrapperExit = 1; $taskStatus = 'unknown_output_binding_failure' }
        if ($taskWrapperExit -eq 0 -and $null -eq $taskOutputs[$taskName]) { $taskWrapperExit = 1; $taskStatus = 'unknown_missing_output' }
    }
    $taskResult = [ordered]@{
        schema = 'g31.online_initial_dispatch.pure_external.v1'
        status = $taskStatus; error = $taskError; launched = $taskLaunched
        command = $taskCommand; cwd = $taskRoot; output_directory = $taskOutput
        exitcode = $taskExit; wrapper_exitcode = $taskWrapperExit
        stopwatch_frequency = $taskFrequency; elapsed_ticks = $taskTicks; external_application_seconds = $taskSeconds
        shared_limit_seconds = 120; clock_scope = 'immediately_before_python_launch_through_process_return'
        external_pin_checks_and_receipt_export_outside_python_clock = $true
        expected_pins = $taskExpected; pins_before = $taskBefore; pins_after = $taskAfter; outputs = $taskOutputs
        scope = 'Only24 synthetic initial dispatch and failure-boundary tests; actual Transport code uses fake sessions. No real proof/model/native/custom C execution or complete request latency claim. External checks bind saved results, not a second test run.'
    }
    if (-not (Test-Path -LiteralPath $taskOutput)) { [void][System.IO.Directory]::CreateDirectory($taskOutput) }
    $taskBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(($taskResult | ConvertTo-Json -Depth 15) + "`n")
    $taskStream = [System.IO.File]::Open($taskExternal, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $taskStream.Write($taskBytes, 0, $taskBytes.Length) } finally { $taskStream.Dispose() }
    [ordered]@{ status = $taskStatus; wrapper_exitcode = $taskWrapperExit; external_application_seconds = $taskSeconds; receipt = $taskExternal; sha246 = Task-Sha $taskExternal } | ConvertTo-Json
}
exit $taskWrapperExit
