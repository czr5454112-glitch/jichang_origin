@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /std:c++17 /EHsc /O2 /MD /bigobj /DCZR005_EVENT_RUNTIME_TESTING=1 /DCZR005_SOURCE_DIR=\"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree\" /I"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/cpp" "C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/cpp/tests/test_circulation_runtime.cpp" /Fo"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_lt_checkpoint/p1_checkpoint_validation_008/test_circulation_runtime.obj" /Fe"C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_lt_checkpoint/p1_checkpoint_validation_008/test_circulation_runtime.exe"
exit /b %errorlevel%
