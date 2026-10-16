$ErrorActionPreference = 'Stop'
$studyRoot = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$studyOutput = Join-Path $studyRoot 'outputs\experiments\g31_ics_lt2_sustained_20261014\future_later_fork_pure_002'
Set-Location -LiteralPath $studyRoot
$studyWatch = [Diagnostics.Stopwatch]::StartNew()
& 'C:\PROGRAMING\python3.11.9\python.exe' -m scripts.experiments.g31_ics_circulation.run_future_later_fork_pure --output $studyOutput
$studyCode = $LASTEXITCODE
$studyWatch.Stop()
$studyReceipt = [ordered]@{schema='g31.whole_python_application_wall.v1'; exitcode=$studyCode; whole_python_wall_seconds=$studyWatch.Elapsed.TotalSeconds; native_calls=0; real_model_predictions=0; wrapper_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()}
$studyReceipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $studyOutput 'external_application_wall.json') -Encoding utf8
exit $studyCode

