$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'future_later_paired_six_prepare_001'
$taskPlan=Join-Path $taskFolder 'plan.json'
$taskPlanSha='5628a1262101d3a8bdcb21733d2185a538f752e81df12c26f207ebbb62ad9fbd'
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha='5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec'
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) {throw 'Prepared plan changed'}
if ((Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPythonSha) {throw 'Prepared interpreter changed'}
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
$taskReady=Get-Content -LiteralPath (Join-Path $taskFolder 'root_ready_001.json') -Raw | ConvertFrom-Json
if ($taskReady.status -ne 'ready_for_one_fixed_future_paired_six_attempt' -or $taskReady.plan_sha256 -ne $taskPlanSha -or $taskReady.wrapper_sha256 -ne $taskWrapperSha) {throw 'Review identity changed'}
if ((Get-FileHash -LiteralPath $taskReady.root_review.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReady.root_review.sha256) {throw 'Root review changed'}
$taskDestination=Join-Path $taskFolder 'external_application_wall.json'
if ((Test-Path -LiteralPath $taskDestination) -or (Test-Path -LiteralPath (Join-Path $taskFolder 'execution_claim.json'))) {throw 'Preserve previous attempt'}
$taskStart=[DateTime]::UtcNow.ToString('o')
$taskStamp=[Diagnostics.Stopwatch]::GetTimestamp()
$taskCode=$null
$taskError=$null
try {
    & $taskPython -m scripts.experiments.g31_ics_circulation.validate_future_later_paired_suffix --execute --output $taskFolder --expected-plan $taskPlanSha
    $taskCode=$LASTEXITCODE
} catch {$taskError=$_.Exception.Message}
$taskWall=([Diagnostics.Stopwatch]::GetTimestamp()-$taskStamp)/[double][Diagnostics.Stopwatch]::Frequency
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskRecord=[ordered]@{
    schema='g31.future_later_paired_six.external_wall.v1'
    status=$(if ($taskCode -eq 0 -and $null -eq $taskError -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'})
    started_utc=$taskStart;ended_utc=[DateTime]::UtcNow.ToString('o')
    whole_python_application_seconds=$taskWall;whole_python_within_120_seconds=($taskWall -le 120)
    plan_sha256=$taskPlanSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha
    evidence_unchanged=$taskUnchanged;exit_code=$taskCode;error=$taskError
    shared_owned_seconds=120;fixed_rows=6;maximum_initial_engines=6;maximum_prefix_cutpoints=14;expected_suffixes=12;expected_prefix_same_resumes=8;expected_future_resumes=12;expected_graph_forks=12;native_calls=0
    model_conformance_not_inferred_from_exit_code=$true;complete_native_request_100ms_certified=$false
    scope='Fixed6 original initial contexts, at most14 prefix cuts,8 same-action prefix resumes,12 future forks and12 suffix resumes. Both later choices cloned from same unconsumed first knownB cut before either suffix. Strict wire/current/past-action guards; unsupported firstB remains unknown with fixed6/12 denominator. Full returned predictions saved before frozen target reads; exact bytes/types/order/floathex/chronology, graph only allowed action change, parent/sibling alias isolation.156source/current/archive/runtime guards. All imports/setup/clones/model/audit/export/exit within120. No native authority, actual opaque-ID relation, hidden-state coverage, online utility or100ms claim.'
    exclusions='PowerShell/tool startup and explicit prelaunch/postexit digest checks plus this outer receipt export are harness work outside the Python interval.'
}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 6))
$taskStream=[IO.File]::Open($taskDestination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if ($null -ne $taskError) {throw $taskError}
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
if ($taskCode -ne 0) {exit $taskCode}

if ($taskWall -gt 120) {throw 'Whole Python future paired six-input budget exceeded'}
