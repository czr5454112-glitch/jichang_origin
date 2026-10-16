$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/PROGRAMING/czr005/.g31_ics_circulation_worktree'
$taskOutput = "$taskRoot/outputs/experiments/g31_ics_lt2_sustained_20261014/live_initial_six_seam_pure_001"
$taskPython = 'C:/PROGRAMING/python3.11.9/python.exe'
$taskArgs = @('-m', 'scripts.experiments.g31_ics_circulation.run_live_initial_six_seam_pure', '--output', $taskOutput)
Set-Location -LiteralPath $taskRoot
$taskWatch = [System.Diagnostics.Stopwatch]::StartNew()
& $taskPython @taskArgs
$taskExit = $LASTEXITCODE
$taskWatch.Stop()
$taskReceipt = [ordered]@{
    schema = 'g31.external_python_wall.v1'
    status = $(if ($taskExit -eq 0) { 'exited_zero' } else { 'failed' })
    command = @($taskPython) + $taskArgs
    exitcode = $taskExit
    external_application_seconds = $taskWatch.Elapsed.TotalSeconds
    native_calls = 0
    real_model_predictions = 0
}
$taskText = $taskReceipt | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText("$taskOutput/external_application_wall.json", $taskText + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output $taskText
exit $taskExit
