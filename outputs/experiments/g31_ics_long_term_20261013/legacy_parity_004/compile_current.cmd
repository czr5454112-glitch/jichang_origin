@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /std:c++17 /EHsc /O2 /MD /bigobj /I"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/cpp" "C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/cpp/tests/g31_legacy_replay_fixture.cpp" /Fo"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_lt_checkpoint/legacy_parity_004/current.obj" /Fe"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_lt_checkpoint/legacy_parity_004/current.exe"
exit /b %errorlevel%
