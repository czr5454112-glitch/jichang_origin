$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'bridge_saved_text_actor_prepare_001'
$taskPlan=Join-Path $taskFolder 'plan.json'
$taskPlanSha='6a56cee53dc46444a96815210076863e37738f449f73b50e845c48d39e887f4a'
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json
if ($taskReady.status -ne 'ready_for_separate_saved_audit' -or $taskReady.plan_sha256 -ne $taskPlanSha -or $taskReady.wrapper_sha256 -ne $taskWrapperSha) {throw 'Review identity changed'}
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha -or (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPythonSha) {throw 'Plan or interpreter changed'}
if ((Get-FileHash -LiteralPath (Join-Path $taskFolder 'root_source_review_001.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReady.root_review.sha256) {throw 'Root review changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if ((Test-Path -LiteralPath $taskDestination) -or (Test-Path -LiteralPath (Join-Path $taskFolder 'execution_claim.json'))) {throw 'Preserve previous attempt'}
$taskStart=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.audit_bridge_saved_text_actor --execute --output $taskFolder --plan-sha256 $taskPlanSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskWall=($taskEnd-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskRecord=[ordered]@{
    schema='g31.bridge.same_text_actor.external_application_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged -and $taskWall -le 600) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStart;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_600_seconds=($taskWall -le 600)
    plan_sha256=$taskPlanSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_seconds=600;new_api_rows=37270;old_complete_prefix_rows=27218
    native_calls=0;new_predictions=0;original_2400_timeout_unchanged=$true;prior_saved600_timeout_unchanged=$true
    scope='Separate saved-only full policy/physical/FIFO/Storage/clock/cap audit. All37270new and27218old rows/hashes/actual arguments remain checked. Original C semantic_api comparison restored. Actor result comes from second standard parse of the exact same already-read gzip text; observer retains first row. One-row text sidecar clears in finally. Original default decoder domain/guards remain; resource failures may differ and stay unknown. Includes Python startup, all reads/parses/hash/comparison/replay/derived export/cleanup/exit. Only all_job_states write/hash redirects to this new directory.'
    exclusions='PowerShell/tool startup and explicit prelaunch/postexit digest checks plus this outer receipt export are harness work outside the Python interval.'
    limitations='No native execution, independent native-state replay, full business success/protection or complete request100ms claim. Fixed local cost probes do not guarantee full600 completion. Source/pure work may overlap; this is not an isolated performance comparison.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskWall -gt 600) {exit 1}
if ($taskCode -ne 0) {exit $taskCode}
