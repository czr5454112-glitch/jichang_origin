$ErrorActionPreference = 'Stop'
$taskRoot = 'C:/PROGRAMING/czr005/.g31_ics_circulation_worktree'
$taskOutput = "$taskRoot/outputs/experiments/g31_ics_lt2_sustained_20261014/owned_full32_runtime_prepare_001"
$taskPlanSha = '6f4434bcf87d8e35d709eabfed5561b6461adde71389b92c8042072a9e6c4bc5'
$taskReadySha = '23e2f1d8f53f15538b6a0de3a1c789881b49f2ffa5d50728cc5def1c0e716731'
$taskReviewSha = '05a8502fabb9ce7436571e4f6675b957e8f0074fd30125d0f179a727264cd312'
if ((Get-FileHash -LiteralPath "$taskOutput/plan.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) { throw 'plan pin mismatch' }
if ((Get-FileHash -LiteralPath "$taskOutput/ready.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReadySha) { throw 'ready pin mismatch' }
if ((Get-FileHash -LiteralPath "$taskOutput/root_review_001.json" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReviewSha) { throw 'root review pin mismatch' }
if (Test-Path -LiteralPath "$taskOutput/execution_claim.json") { throw 'execution already claimed' }
if (Test-Path -LiteralPath "$taskOutput/external_application_wall.json") { throw 'external receipt already exists' }
$taskReady = Get-Content -LiteralPath "$taskOutput/ready.json" -Raw | ConvertFrom-Json
$taskCommand = @($taskReady.execute_command)
$taskPython = $taskCommand[0]
$taskArgs = @($taskCommand | Select-Object -Skip 1)
$taskWrapperSha = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Location -LiteralPath $taskRoot
$taskWatch = [System.Diagnostics.Stopwatch]::StartNew()
& $taskPython @taskArgs
$taskExit = $LASTEXITCODE
$taskWatch.Stop()
$taskReceipt = [ordered]@{
    schema = 'g31.external_python_wall.v1'
    status = $(if ($taskExit -eq 0 -and $taskWatch.Elapsed.TotalSeconds -le 360) { 'exited_zero_within_external_limit' } else { 'failed_or_external_limit_exceeded' })
    command = $taskCommand
    exitcode = $taskExit
    external_application_seconds = $taskWatch.Elapsed.TotalSeconds
    fixed_application_seconds = 360
    plan_sha256 = $taskPlanSha
    ready_sha256 = $taskReadySha
    root_review_sha256 = $taskReviewSha
    wrapper_path = $PSCommandPath
    wrapper_sha256 = $taskWrapperSha
    plan_after_sha256 = (Get-FileHash -LiteralPath "$taskOutput/plan.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    ready_after_sha256 = (Get-FileHash -LiteralPath "$taskOutput/ready.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    bounded_execution_sha256 = $(if (Test-Path -LiteralPath "$taskOutput/bounded_execution.json") { (Get-FileHash -LiteralPath "$taskOutput/bounded_execution.json" -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null })
    native_calls = 0
    actual_C_loads = 0
    scope = 'One fixed full96 model conformance; not a performance comparison or 100ms certification.'
}
$taskText = $taskReceipt | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText("$taskOutput/external_application_wall.json", $taskText + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output $taskText
if ($taskWatch.Elapsed.TotalSeconds -gt 360) { exit 1 }
exit $taskExit
