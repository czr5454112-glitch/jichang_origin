$ErrorActionPreference = 'Stop'
$targetPid = 34512
$expectedCreated = [DateTimeOffset]::Parse('2026-10-15T15:58:17.484634+08:00').UtcDateTime
$expectedCommand = '"C:\PROGRAMING\python3.11.9\python.exe" -m scripts.experiments.g31_ics_circulation.review_original_low_wip_repeat_saved --output C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\outputs\experiments\g31_ics_lt2_sustained_20261014\original_low_wip_repeat_prepare_001 --expected-ready-sha256 822cc0e73d71a2c44efcc36618fcc11941c350b54c9621fda3081a6d8a8f4ca4 --report C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\outputs\experiments\g31_ics_lt2_sustained_20261014\original_low_wip_repeat_independent_actual_review_001.json'
$receiptPath = 'C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\outputs\experiments\g31_ics_lt2_sustained_20261014\original_low_wip_repeat_review_observer_001.json'
if (Test-Path -LiteralPath $receiptPath) { throw 'observer_receipt_exists' }
$started = [DateTime]::UtcNow
$deadline = $started.AddSeconds(300)
if ($expectedCreated.AddSeconds(1800) -lt $deadline) { $deadline = $expectedCreated.AddSeconds(1800) }
$record = [ordered]@{
    schema = 'g31.offline_review.supplemental_process_bound.v1'
    target_pid = $targetPid
    expected_creation_utc = $expectedCreated.ToString('o')
    expected_command = $expectedCommand
    observer_start_utc = $started.ToString('o')
    supplemental_deadline_utc = $deadline.ToString('o')
    originally_preregistered_hard_limit = $false
    original_launch_to_creation_wall_measured = $false
    status = 'supplemental_wait_active'
    purpose = 'Only the identified offline saved-record review; no native simulation process is targeted.'
}
function Save-Receipt { $record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding utf8 }
Save-Receipt
try {
    while ($true) {
        $target = Get-CimInstance Win32_Process -Filter "ProcessId=$targetPid"
        if ($null -eq $target) { $record.status = 'target_exited_during_supplemental_wait'; break }
        $creation = ([DateTime]$target.CreationDate).ToUniversalTime()
        if ($creation -ne $expectedCreated -or $target.CommandLine -cne $expectedCommand) {
            $record.status = 'identity_mismatch_no_termination'; throw 'target_identity_mismatch'
        }
        $record.last_verified_utc = [DateTime]::UtcNow.ToString('o')
        if ([DateTime]::UtcNow -ge $deadline) {
            Stop-Process -Id $targetPid -ErrorAction Stop
            $record.status = 'supplemental_deadline_exact_offline_process_terminated'
            $record.termination_identity_verified = $true
            break
        }
        Start-Sleep -Seconds 2
    }
} catch {
    $record.error = $_.Exception.Message
    if ($record.status -eq 'supplemental_wait_active') { $record.status = 'observer_error_no_completion_claim' }
    throw
} finally {
    $finished = [DateTime]::UtcNow
    $record.observer_end_utc = $finished.ToString('o')
    $record.observer_wall_seconds = ($finished - $started).TotalSeconds
    $record.creation_to_final_observation_seconds = ($finished - $expectedCreated).TotalSeconds
    Save-Receipt
}
