param(
    [Parameter(Mandatory=$true)][string]$ReadyPath,
    [Parameter(Mandatory=$true)][string]$ExpectedReadySha256,
    [Parameter(Mandatory=$true)][string]$ExternalReceipt
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$allowedOutput = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)) + [IO.Path]::DirectorySeparatorChar
$readyAbsolute = [IO.Path]::GetFullPath((Join-Path $taskRoot $ReadyPath))
$receiptAbsolute = [IO.Path]::GetFullPath((Join-Path $taskRoot $ExternalReceipt))
if (-not $readyAbsolute.StartsWith($allowedOutput, [StringComparison]::OrdinalIgnoreCase)) { throw 'Ready file outside experiment directory.' }
if (-not $receiptAbsolute.StartsWith($allowedOutput, [StringComparison]::OrdinalIgnoreCase)) { throw 'Receipt outside experiment directory.' }
if (Test-Path -LiteralPath $receiptAbsolute) { throw 'External receipt already exists; preserve the previous attempt.' }
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH = 'src;.;tests'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$harnessStart = [Diagnostics.Stopwatch]::GetTimestamp()
$utcStart = [DateTime]::UtcNow.ToString('o')
$readyHash = (Get-FileHash -LiteralPath $readyAbsolute -Algorithm SHA256).Hash.ToLowerInvariant()
if ($readyHash -ne $ExpectedReadySha256.ToLowerInvariant()) { throw 'Prepared command digest changed.' }
$ready = Get-Content -LiteralPath $readyAbsolute -Raw | ConvertFrom-Json
$planAbsolute = [IO.Path]::GetFullPath((Join-Path ([string]$ready.output) 'campaign.json'))
if (-not $planAbsolute.StartsWith($allowedOutput, [StringComparison]::OrdinalIgnoreCase)) { throw 'Prepared plan outside experiment directory.' }
$planHash = (Get-FileHash -LiteralPath $planAbsolute -Algorithm SHA256).Hash.ToLowerInvariant()
if ($planHash -ne $ready.campaign_sha256) { throw 'Prepared plan digest changed.' }
$command = @($ready.execute_command)
if ($command.Count -lt 6 -or $command[0] -ne 'C:\PROGRAMING\python3.11.9\python.exe' -or $command[1] -ne '-m' -or $command[2] -ne 'scripts.experiments.g31_ics_circulation.launch_original_route_update_native027_phase' -or $command -notcontains '--campaign-sha256') { throw 'Unexpected prepared native027 phase command.' }
$executable = [string]$command[0]
$arguments = @($command | Select-Object -Skip 1)
$interpreterHash = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
$wrapperHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$launchStamp = [Diagnostics.Stopwatch]::GetTimestamp()
$applicationExitCode = $null
$applicationError = $null
try {
    & $executable @arguments
    $applicationExitCode = $LASTEXITCODE
} catch {
    $applicationError = $_.Exception.Message
} finally {
    $endStamp = [Diagnostics.Stopwatch]::GetTimestamp()
    $finalReadyHash = (Get-FileHash -LiteralPath $readyAbsolute -Algorithm SHA256).Hash.ToLowerInvariant()
    $finalPlanHash = (Get-FileHash -LiteralPath $planAbsolute -Algorithm SHA256).Hash.ToLowerInvariant()
    $finalWrapperHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $identitiesUnchanged = $readyHash -eq $finalReadyHash -and $planHash -eq $finalPlanHash -and $wrapperHash -eq $finalWrapperHash
    $record = [ordered]@{
        schema = 'g31.original_route_native027_phase.powershell_launch_receipt.v1'
        status = $(if ($applicationError -eq $null -and $applicationExitCode -eq 0 -and $identitiesUnchanged) { 'application_exited_zero' } else { 'application_failed_or_unknown' })
        command = $command
        ready = [ordered]@{ path=$readyAbsolute; sha256=$readyHash; final_sha256=$finalReadyHash }
        preregistered_plan = [ordered]@{ path=$planAbsolute; sha256=$planHash; final_sha256=$finalPlanHash }
        interpreter = [ordered]@{ path=$executable; sha256=$interpreterHash }
        wrapper = [ordered]@{ path=$PSCommandPath; sha256=$wrapperHash; final_sha256=$finalWrapperHash }
        evidence_identities_unchanged = $identitiesUnchanged
        powershell_process_id = $PID
        recorded_start_utc = $utcStart
        recorded_end_utc = [DateTime]::UtcNow.ToString('o')
        stopwatch_frequency = [Diagnostics.Stopwatch]::Frequency
        harness_measured_start_tick = $harnessStart
        application_launch_tick = $launchStamp
        application_exit_tick = $endStamp
        whole_application_campaign_wall_seconds = ($endStamp-$launchStamp)/[double][Diagnostics.Stopwatch]::Frequency
        measured_harness_and_campaign_wall_seconds = ($endStamp-$harnessStart)/[double][Diagnostics.Stopwatch]::Frequency
        exit_code = $applicationExitCode
        error = $applicationError
        full_charge_policy = 'Whole six-cell campaign, including Python startup/import, source checks, native workers, diagnostics and saved-evidence verification. One shared 600-second inner Windows Job deadline. Charge full campaign to each declared root without division as conservative sensitivity, not isolated service latency. Outer launch-to-exit includes launcher startup.'
        exclusions = 'External PowerShell/tool startup before the measured clock; prelaunch PowerShell hash and command checks (included in measured_harness_and_campaign but outside application campaign); final evidence rehashes and writing this external receipt after application exit. These are experiment-harness work, not a certified platform cold-start measurement.'
        complete_100ms_certified = $false
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 12))
    $stream = [IO.File]::Open($receiptAbsolute, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    [ordered]@{ status=$record.status; whole_application_campaign_wall_seconds=$record.whole_application_campaign_wall_seconds; receipt=$receiptAbsolute; sha256=(Get-FileHash -LiteralPath $receiptAbsolute -Algorithm SHA256).Hash.ToLowerInvariant() } | ConvertTo-Json -Compress
}
if ($applicationError -ne $null) { throw $applicationError }
if (-not $identitiesUnchanged) { throw 'Evidence identities changed during application execution.' }
if ($applicationExitCode -ne 0) { exit $applicationExitCode }
