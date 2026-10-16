$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'C:/PROGRAMING/czr005/.g31_ics_circulation_worktree'
$env:PYTHONPATH='src;.;tests'
$started=[DateTime]::UtcNow.ToString('o')
$watch=[Diagnostics.Stopwatch]::StartNew()
& 'C:/PROGRAMING/python3.11.9/python.exe' -m scripts.experiments.g31_ics_circulation.launch_historical_saved_audit
$exit=$LASTEXITCODE
$watch.Stop()
$dest='C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/outputs/experiments/g31_ics_lt2_sustained_20261014/live_obligation_historical_saved_audit_001'
$receipt=[ordered]@{schema='g31.saved_historical_audit_external_wall.v1';status=if($exit -eq 0){'application_exited_zero'}else{'application_failed'};exit_code=$exit;started_utc=$started;ended_utc=[DateTime]::UtcNow.ToString('o');whole_python_application_seconds=$watch.Elapsed.TotalSeconds;owned_child_hard_limit_seconds=180;native_executions=0;model_evaluations=0;scope='Complete Python application startup through exit; PowerShell setup and this outer receipt export excluded.'}
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ($dest+'/external_application_wall.json') -Encoding utf8
exit $exit
