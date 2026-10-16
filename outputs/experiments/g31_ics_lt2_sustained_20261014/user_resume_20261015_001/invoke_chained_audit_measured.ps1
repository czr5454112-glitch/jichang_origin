$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$launcher=Join-Path $PSScriptRoot 'launch_chained_audit_002.py'
$expected='e0d17efb1556414c813812459dcd40d1ae42a176c4877d14ba32081fcbb3f587'
if ((Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Audit launcher changed' }
$output=Join-Path (Split-Path -Parent $PSScriptRoot) 'full024_chained_2x_20261015_002_saved_audit_external_001.json'
if (Test-Path -LiteralPath $output) { throw 'Preserve previous external receipt' }
$start=[Diagnostics.Stopwatch]::GetTimestamp()
$utc=[DateTime]::UtcNow.ToString('o')
$code=$null
$failure=$null
try {
    & 'C:/PROGRAMING/python3.11.9/python.exe' $launcher --final-seal 'a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826'
    $code=$LASTEXITCODE
} catch { $failure=$_.Exception.Message }
$end=[Diagnostics.Stopwatch]::GetTimestamp()
$unchanged=(Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash.ToLowerInvariant() -eq $expected
$record=[ordered]@{
    schema='g31.chained_saved_audit.external_wall.v1'
    status=$(if ($code -eq 0 -and $null -eq $failure -and $unchanged) {'audit_application_exited_zero'} else {'audit_application_failed_or_unknown'})
    recorded_start_utc=$utc;recorded_end_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_wall_seconds=($end-$start)/[double][Diagnostics.Stopwatch]::Frequency
    launcher=$launcher;launcher_sha256=$expected;launcher_unchanged=$unchanged
    exit_code=$code;error=$failure;native_executions=0
    inner_child_budget_seconds=3600;complete_request_100ms_certified=$false
    scope='Full Python parent and child startup/import, independent saved-record checks, whole raw audit, final rehash and receipt export. Original producer timeout and unknown initial source-finalization stay unchanged.'
    exclusions='PowerShell/tool startup and prelaunch digest; this external post-exit digest/receipt serialization.'
}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 6))
$stream=[IO.File]::Open($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
[ordered]@{status=$record.status;wall_seconds=$record.whole_python_application_wall_seconds;sha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $failure) {throw $failure}
if (-not $unchanged) {throw 'Audit launcher changed during run'}
if ($code -ne 0) {exit $code}
