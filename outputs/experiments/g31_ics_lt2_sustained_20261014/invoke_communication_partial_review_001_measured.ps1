$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = 'src;.;tests'
$taskPython = 'C:\PROGRAMING\python3.11.9\python.exe'
$taskOutput = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\outputs\experiments\g31_ics_lt2_sustained_20261014\live_communication_partial_review_001'
$taskStart = [DateTime]::UtcNow.ToString('o')
$taskClock = [Diagnostics.Stopwatch]::StartNew()
& $taskPython -m scripts.experiments.g31_ics_circulation.diagnose_live_communication_partial --execute --output $taskOutput
$taskExit = $LASTEXITCODE
$taskClock.Stop()
$taskReceipt = [ordered]@{
    schema = 'g31.communication_partial_review.external_wall.v1'
    status = $(if ($taskExit -eq 0) { 'application_closed' } else { 'application_failed_or_unknown' })
    started_utc = $taskStart
    ended_utc = [DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds = $taskClock.Elapsed.TotalSeconds
    exit_code = $taskExit
    wrapper_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    python_sha256 = (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
    native_calls = 0
    model_evaluations = 0
    original_timeout_preserved = $true
}
$taskReceipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskOutput 'external_application_wall.json') -Encoding utf8
exit $taskExit
