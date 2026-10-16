param(
    [Parameter(Mandatory=$true)][ValidateSet('full024_resumed_1x_20261015_001','full024_resumed_2x_20261015_001')][string]$Attempt,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$attemptRoot = Join-Path (Split-Path -Parent $PSScriptRoot) $Attempt
$receipt = Get-Content -LiteralPath (Join-Path $attemptRoot 'receipt.json') -Raw | ConvertFrom-Json
if ($receipt.status -notin @('failed','hard_timeout')) { throw 'Source attempt has not terminated with a resumable failure.' }
$identityPath = Join-Path $PSScriptRoot 'active_process_identity_004.json'
$identities = @(Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json)
$expected = @($identities | Where-Object { $_.CommandLine.Contains($Attempt) })
if ($expected.Count -ne 2) { throw 'Expected one previously observed parent and one worker.' }
$rows = @()
foreach ($identity in $expected) {
    $current = @(Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId=' + [int]$identity.ProcessId))
    if ($current.Count -ne 0) { throw ('PID still exists; no absence record written: ' + $identity.ProcessId) }
    $rows += [ordered]@{ expected=$identity; observed=$null; old_identity_present=$false }
}
$destination = [IO.Path]::GetFullPath((Join-Path $taskRoot $Output))
$allowedRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)) + [IO.Path]::DirectorySeparatorChar
if (-not $destination.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Observation output must remain within this experiment directory.' }
if (Test-Path -LiteralPath $destination) { throw 'Observation output already exists; retain it.' }
$record = [ordered]@{
    schema='g31.terminated_resume_process_observation.v1'
    observed_utc=[DateTime]::UtcNow.ToString('o')
    all_original_identities_absent=$true
    source_attempt=$attemptRoot
    source_receipt_sha256=(Get-FileHash -LiteralPath (Join-Path $attemptRoot 'receipt.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    prior_identity_reference=[ordered]@{path=$identityPath;sha256=(Get-FileHash -LiteralPath $identityPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    processes=$rows
}
[IO.File]::WriteAllText($destination, ($record | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
Get-FileHash -LiteralPath $destination -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json -Compress
