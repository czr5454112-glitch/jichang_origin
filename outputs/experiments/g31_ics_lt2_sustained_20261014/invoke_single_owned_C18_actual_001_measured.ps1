$ErrorActionPreference = 'Stop'
$taskWatch = [System.Diagnostics.Stopwatch]::StartNew()
$startedUtc = [DateTime]::UtcNow.ToString('o')
$workspace = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree'
$output = Join-Path $workspace 'outputs\experiments\g31_ics_lt2_sustained_20261014\single_owned_C18_prepare_002'
$python = 'C:\PROGRAMING\python3.11.9\python.exe'
$planSha = '4ac4569ad5145ccf62e83a39d29ad238077bf00fa0657c130fb12916cfb91bdc'
$module = 'scripts.experiments.g31_ics_circulation.launch_initial_owner_route_single_capture_owned_codec_campaign'
$argv = @('-m', $module, '--output', $output, '--campaign-sha256', $planSha)
$receiptPath = Join-Path $output 'actual_external_application_wall.json'
$stdoutPath = Join-Path $output 'actual_outer_stdout.log'
$stderrPath = Join-Path $output 'actual_outer_stderr.log'
$pins = [ordered]@{
  $python = '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
  (Join-Path $output 'campaign.json') = $planSha
  (Join-Path $output 'root_review_001.json') = 'de24dfe036794e4e9a83378ccbd99e6ff421a7456d0dabbb8ffda3cf50d0b278'
  (Join-Path $workspace 'scripts\experiments\g31_ics_circulation\launch_initial_owner_route_single_capture_owned_codec_campaign.py') = '5817787502c9323da99a90ba1c564bcf0be96e96ab38f6366762fec773416e70'
  (Join-Path $workspace 'scripts\experiments\g31_ics_circulation\initial_owner_route_single_capture_owned_codec_campaign.py') = '5e1c7e358d69fd7448a0ff3af5837afc9a8b0171d47fff44991b190a23b928e8'
}
$result = [ordered]@{
  schema = 'g31.single_owned_C18.actual_external_application_wall.v1'
  status = 'unknown_before_dispatch'
  started_utc = $startedUtc
  output = $output
  cwd = $workspace
  command = @($python) + $argv
  campaign_sha256 = $planSha
  wrapper = $PSCommandPath
  wrapper_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
  shared_child_limit_seconds = 600
  automatic_retries = 0
  actual_direct_C_supported = $null
  actual_fallback_count = $null
  source_before = [ordered]@{}
  source_after = [ordered]@{}
  source_changed = @()
}
$exitCode = 1
$launched = $false
foreach ($path in @($receiptPath, $stdoutPath, $stderrPath, (Join-Path $output 'execution_claim.json'), (Join-Path $output 'worker_claim.json'), (Join-Path $output 'receipt.json'), (Join-Path $output 'external_launch_receipt.json'))) {
  if (Test-Path -LiteralPath $path) { throw "actual already attempted or occupied: $path" }
}
try {
  foreach ($pair in $pins.GetEnumerator()) {
    $actual = (Get-FileHash -LiteralPath $pair.Key -Algorithm SHA256).Hash.ToLowerInvariant()
    $result.source_before[$pair.Key] = $actual
    if ($actual -ne $pair.Value) { throw "prelaunch pin changed: $($pair.Key)" }
  }
  Set-Location -LiteralPath $workspace
  $result.python_launch_utc = [DateTime]::UtcNow.ToString('o')
  $pythonWatch = [System.Diagnostics.Stopwatch]::StartNew()
  $launched = $true
  & $python @argv 1> $stdoutPath 2> $stderrPath
  $exitCode = $LASTEXITCODE
  $pythonWatch.Stop()
  $result.python_launch_to_exit_seconds = $pythonWatch.Elapsed.TotalSeconds
  $result.python_exit_utc = [DateTime]::UtcNow.ToString('o')
  $result.exitcode = $exitCode
  $result.status = if ($exitCode -eq 0) { 'exited_zero_pending_evidence' } else { 'failed_or_unknown_process' }
  $innerPath = Join-Path $output 'external_launch_receipt.json'
  if (Test-Path -LiteralPath $innerPath) {
    $inner = Get-Content -LiteralPath $innerPath -Raw | ConvertFrom-Json
    $result.inner_launcher_status = $inner.status
    $result.inner_process = $inner.process
  }
  $producerPath = Join-Path $output 'receipt.json'
  if (Test-Path -LiteralPath $producerPath) {
    $producer = Get-Content -LiteralPath $producerPath -Raw | ConvertFrom-Json
    $result.producer_status = $producer.status
    $result.producer_source_changed = @($producer.source_changed)
    if ($exitCode -eq 0 -and $inner.status -eq 'campaign_process_exited' -and $producer.status -eq 'completed_finite_request_cohort' -and $producer.branches -eq 18 -and $producer.campaign_sha256 -eq $planSha -and @($producer.source_changed).Count -eq 0) {
      $result.status = 'completed_original18_once'
    }
  }
} catch {
  $result.status = 'unknown_external_wrapper_error'
  $result.error = $_.Exception.ToString()
  if ($launched -and $pythonWatch.IsRunning) {
    $pythonWatch.Stop()
    $result.python_launch_to_error_seconds = $pythonWatch.Elapsed.TotalSeconds
  }
  $exitCode = 1
} finally {
  foreach ($pair in $pins.GetEnumerator()) {
    try {
      $actual = (Get-FileHash -LiteralPath $pair.Key -Algorithm SHA256).Hash.ToLowerInvariant()
      $result.source_after[$pair.Key] = $actual
      if ($actual -ne $pair.Value) { $result.source_changed += $pair.Key }
    } catch { $result.source_changed += $pair.Key }
  }
  $result.artifacts = [ordered]@{}
  foreach ($name in @('external_launch_receipt.json','receipt.json','verification.json','branch_ledger.json','C_provider_lifetime.json','predictor_lifetime.json','run_acceptance.json','actual_outer_stdout.log','actual_outer_stderr.log')) {
    $path = Join-Path $output $name
    if (Test-Path -LiteralPath $path) {
      $result.artifacts[$name] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
  }
  if ($result.source_changed.Count -gt 0) { $result.status = 'unknown_source_changed'; $exitCode = 1 }
  $result.finished_utc = [DateTime]::UtcNow.ToString('o')
  $result.wrapper_through_preexport_seconds = $taskWatch.Elapsed.TotalSeconds
  $result.scope = 'Python launch-to-exit includes launcher startup, owned600 child setup/native/RPC/full saved verification/cleanup/final export. Outer wrapper prechecks and artifact readback separately included through preexport; this receipt final write is outside that last timestamp. No retry, no direct-C/fallback inference, no full-request100ms assertion.'
  $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 40))
  $stream = [IO.File]::Open($receiptPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
  try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush() } finally { $stream.Dispose() }
}
$taskWatch.Stop()
Write-Output ('actual_status=' + $result.status + ' python_seconds=' + $result.python_launch_to_exit_seconds + ' wrapper_total_seconds=' + $taskWatch.Elapsed.TotalSeconds)
exit $exitCode
