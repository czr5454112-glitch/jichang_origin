param([Parameter(Mandatory=$true)][ValidateSet('delivery_gate','business')][string]$Phase)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH = 'src;.;tests'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$readyPath = Join-Path $taskRoot 'outputs/experiments/g31_ics_lt2_sustained_20261014/native_public_preference_ready_001.json'
$readyExpected = '4a3dd52905058f1b270c11bfd2299ba146cae8bf8b4fecc78bada4f96ea16ec4'
$reviewPath = Join-Path $taskRoot 'outputs/experiments/g31_ics_lt2_sustained_20261014/native_public_preference_independent_source_review_001.json'
$reviewExpected = '16f9e88ed1c799193dfbbc788cbfd2498801299e9f6dfd8b6391d090c6969087'
if ((Get-FileHash -LiteralPath $readyPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $readyExpected) { throw 'Prepared identity changed' }
if ((Get-FileHash -LiteralPath $reviewPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $reviewExpected) { throw 'Independent review changed' }
$ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
$command = @($ready.commands.$Phase)
if ($command[0] -ne 'C:/PROGRAMING/python3.11.9/python.exe' -or $command[1] -ne '-m' -or $command[2] -ne 'scripts.experiments.g31_ics_circulation.research_native_public_preference') { throw 'Unexpected command' }
$plan = $ready.plans.$Phase
if ((Get-FileHash -LiteralPath $plan.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.sha256) { throw 'Prepared plan changed' }
$output = Split-Path -Parent $plan.path
$receiptPath = Join-Path $output 'powershell_launch_receipt.json'
if (Test-Path -LiteralPath $receiptPath) { throw 'Preserve previous attempt' }
$wrapperHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$executable = [string]$command[0]
$arguments = @($command | Select-Object -Skip 1)
$started = [Diagnostics.Stopwatch]::GetTimestamp()
$utcStart = [DateTime]::UtcNow.ToString('o')
$code = $null
$failure = $null
try { & $executable @arguments; $code = $LASTEXITCODE } catch { $failure = $_.Exception.Message }
$ended = [Diagnostics.Stopwatch]::GetTimestamp()
$unchanged = ((Get-FileHash -LiteralPath $readyPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $readyExpected) -and ((Get-FileHash -LiteralPath $plan.path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $plan.sha256) -and ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $wrapperHash)
$record = [ordered]@{
    schema='g31.native_public_preference.powershell_launch_receipt.v1'
    phase=$Phase
    status=$(if ($code -eq 0 -and $null -eq $failure -and $unchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    command=$command; ready_sha256=$readyExpected; review_sha256=$reviewExpected; plan_sha256=$plan.sha256; wrapper_sha256=$wrapperHash
    recorded_start_utc=$utcStart; recorded_end_utc=[DateTime]::UtcNow.ToString('o'); powershell_process_id=$PID
    whole_application_campaign_wall_seconds=($ended-$started)/[double][Diagnostics.Stopwatch]::Frequency
    exit_code=$code; error=$failure; evidence_identities_unchanged=$unchanged
    complete_request_100ms_certified=$false
    scope='Entire Python startup/import and bounded180s worker, including all evidence revalidation and serial branches. Process success alone does not certify all branches, protection or utility.'
    exclusions='PowerShell/tool startup and prelaunch hashes; post-exit rehash and receipt serialization. These are experiment harness costs, not a certified cold-service measurement.'
}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 12))
$stream = [IO.File]::Open($receiptPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
[ordered]@{status=$record.status;wall_seconds=$record.whole_application_campaign_wall_seconds;receipt_sha256=(Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $failure) { throw $failure }
if (-not $unchanged) { throw 'Identity changed during launch' }
if ($code -ne 0) { exit $code }
