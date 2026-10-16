param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$experimentRoot = Split-Path -Parent $PSScriptRoot
$attemptName = 'full024_chained_2x_20261015_001'
$attemptRoot = Join-Path $experimentRoot $attemptName
$receiptPath = Join-Path $attemptRoot 'receipt.json'
$receiptHash = (Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ($receipt.schema -ne 'g31.chained_sparse_sealed_resume_worker.v1' -or $receipt.status -notin @('failed','hard_timeout')) { throw 'Chained attempt is not a terminated resumable failure.' }
$identityPath = Join-Path $PSScriptRoot 'active_process_identity_005.json'
$identityHash = (Get-FileHash -LiteralPath $identityPath -Algorithm SHA256).Hash.ToLowerInvariant()
$identities = @(Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json)
$expected = @($identities | Where-Object { $_.CommandLine.Contains($attemptName) })
if ($expected.Count -ne 2 -or @($expected.ProcessId | Sort-Object -Unique).Count -ne 2) { throw 'Expected one previously recorded parent and one worker.' }
$parent = @($expected | Where-Object { $_.CommandLine -notmatch '\s--worker(?:\s|$)' })
$worker = @($expected | Where-Object { $_.CommandLine -match '\s--worker(?:\s|$)' })
if ($parent.Count -ne 1 -or $worker.Count -ne 1 -or $worker[0].ParentProcessId -ne $parent[0].ProcessId) { throw 'Recorded process ownership mismatch.' }
$rows = @()
foreach ($identity in $expected) {
    if ([int]$identity.ProcessId -le 0 -or [string]::IsNullOrEmpty($identity.CreationDate)) { throw 'Missing recorded process identity.' }
    $observed = @(Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId=' + [int]$identity.ProcessId))
    if ($observed.Count -ne 0) { throw ('PID exists; no absence record written: ' + $identity.ProcessId) }
    $rows += [ordered]@{ expected=$identity; observed=$null; old_identity_present=$false }
}
if ((Get-FileHash -LiteralPath $receiptPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $receiptHash -or (Get-FileHash -LiteralPath $identityPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $identityHash) { throw 'Source receipt or previously recorded identity changed during observation.' }
$destination = [IO.Path]::GetFullPath((Join-Path $taskRoot $Output))
$allowedRoot = [IO.Path]::GetFullPath($experimentRoot) + [IO.Path]::DirectorySeparatorChar
if (-not $destination.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Observation output outside experiment directory.' }
$record = [ordered]@{
    schema='g31.terminated_resume_process_observation.v1'
    observed_utc=[DateTime]::UtcNow.ToString('o')
    all_original_identities_absent=$true
    source_attempt=$attemptRoot
    source_receipt_sha256=$receiptHash
    prior_identity_reference=[ordered]@{path=$identityPath;sha256=$identityHash}
    processes=$rows
}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 12))
$stream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
Get-FileHash -LiteralPath $destination -Algorithm SHA256 | Select-Object Path,Hash | ConvertTo-Json -Compress
