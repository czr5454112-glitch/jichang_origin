$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$taskBase = Join-Path $taskRoot 'outputs\experiments\g31_ics_lt2_sustained_20261014'
$taskOutput = Join-Path $taskBase 'single_capture_owned_codec_pure_001'
$taskPython = 'C:\PROGRAMING\python3.11.9\python.exe'
$taskStdout = Join-Path $taskBase 'single_capture_owned_codec_pure_001.outer.stdout.log'
$taskStderr = Join-Path $taskBase 'single_capture_owned_codec_pure_001.outer.stderr.log'
foreach ($taskPath in @($taskOutput, $taskStdout, $taskStderr)) {
    if (Test-Path -LiteralPath $taskPath) { throw "existing evidence refuses overwrite: $taskPath" }
}
Set-Location -LiteralPath $taskRoot
$taskClock = [System.Diagnostics.Stopwatch]::StartNew()
$taskStarted = [DateTime]::UtcNow.ToString('o')
$taskExit = $null
$taskError = $null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.run_single_capture_owned_codec_pure --output $taskOutput 1> $taskStdout 2> $taskStderr
    $taskExit = $LASTEXITCODE
} catch {
    $taskError = $_.ToString()
} finally {
    $taskClock.Stop()
    if (-not (Test-Path -LiteralPath $taskOutput)) { New-Item -ItemType Directory -Path $taskOutput | Out-Null }
    $taskReceipt = [ordered]@{
        schema = 'g31.single_capture.owned_codec.pure.external.v1'
        started_utc = $taskStarted
        ended_utc = [DateTime]::UtcNow.ToString('o')
        whole_python_wall_seconds = $taskClock.Elapsed.TotalSeconds
        exitcode = $taskExit
        exception = $taskError
        python = $taskPython
        python_sha256 = (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
        wrapper_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        expected_tests = 45
        binding_cases = 40
        archive_path_cases = 5
        native_calls = 0
        model_calls = 0
        C_loads = 0
        performance_runs = 0
    }
    $taskText = $taskReceipt | ConvertTo-Json -Depth 8
    $taskDestination = Join-Path $taskOutput 'external_application_wall.json'
    $taskStream = [System.IO.File]::Open($taskDestination, [System.IO.FileMode]::CreateNew)
    try {
        $taskBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($taskText)
        $taskStream.Write($taskBytes, 0, $taskBytes.Length)
    } finally { $taskStream.Dispose() }
    $taskText
}
if ($null -ne $taskError -or $null -eq $taskExit) { exit 1 }
exit $taskExit
