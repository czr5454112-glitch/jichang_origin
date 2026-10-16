$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH='src;.;tests'
$env:PYTHONIOENCODING='utf-8'
$taskFolder=Join-Path (Split-Path -Parent $PSScriptRoot) 'serialize_once_tape_prepare_001'
$taskPlan=Join-Path $taskFolder 'plan.json'
$taskPlanSha='41491a21ab797038ccfa4939b54a5c4666c0bd5840fa68f79797ffe6cded9e2d'
if ((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskPlanSha) {throw 'Changed plan'}
$taskReview=Get-Content -LiteralPath (Join-Path $taskFolder 'root_source_review_001.json') -Raw | ConvertFrom-Json
$taskWrapperSha=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskReview.status -ne 'passed_fixed_saved_fixture_cost_gate_ready' -or $taskReview.wrapper_sha256 -ne $taskWrapperSha) {throw 'Missing source review'}
$taskPython='C:/PROGRAMING/python3.11.9/python.exe'
$taskPythonSha=(Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskPythonSha -ne '5f7b89a612c9b8af1d6456cdfcd1dbe5ca630849e79aebced9bee9a6694952ec') {throw 'Changed interpreter'}
$taskOutput=Join-Path $taskFolder 'external_application_wall.json'
if (Test-Path -LiteralPath $taskOutput) {throw 'Preserve prior attempt'}
$taskStarted=[DateTime]::UtcNow.ToString('o')
$taskStart=[Diagnostics.Stopwatch]::GetTimestamp()
& $taskPython -m scripts.experiments.g31_ics_circulation.measure_serialize_once_tape --output $taskFolder --execute --plan-sha256 $taskPlanSha
$taskCode=$LASTEXITCODE
$taskEnd=[Diagnostics.Stopwatch]::GetTimestamp()
$taskUnchanged=((Get-FileHash -LiteralPath $taskPlan -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPlanSha -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskWrapperSha -and (Get-FileHash -LiteralPath $taskPython -Algorithm SHA256).Hash.ToLowerInvariant() -eq $taskPythonSha)
$taskWall=($taskEnd-$taskStart)/[double][Diagnostics.Stopwatch]::Frequency
$taskRecord=[ordered]@{schema='g31.serialize_once_tape.external_application_wall.v1';status=$(if ($taskCode -eq 0 -and $taskUnchanged) {'application_exited_zero'} else {'application_failed_or_unknown'});started_utc=$taskStarted;whole_python_application_seconds=$taskWall;within120_seconds=($taskWall -le 120);exit_code=$taskCode;evidence_unchanged=$taskUnchanged;plan_sha256=$taskPlanSha;wrapper_sha256=$taskWrapperSha;python_sha256=$taskPythonSha;native_calls=0;mock_calls=32;complete_100ms_certified=$false;scope='Python launch-to-exit includes imports, pin checks, owned120s child, saved8fixture load/decode, fixedABBA32 mock calls including equal response deepcopy and wholeTape/gzip/hash/manifest/clocks, saved ordered readback, receipts and cleanup. No native/policy/application100ms inference or division of shared work.';exclusions='PowerShell/tool startup, outer pre/post hashes and this receipt write are declared harness overhead. Other research heavy processes paused; unrelated user/system load uncontrolled.'}
$taskBytes=[Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 5))
$taskStream=[IO.File]::Open($taskOutput,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try {$taskStream.Write($taskBytes,0,$taskBytes.Length)} finally {$taskStream.Dispose()}
[ordered]@{status=$taskRecord.status;whole_python_application_seconds=$taskWall;sha256=(Get-FileHash -LiteralPath $taskOutput -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Compress
if (-not $taskUnchanged) {throw 'Measurement identities changed'}
exit $taskCode
