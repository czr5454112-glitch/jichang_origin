@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
set VSLANG=1033
"C:\Program Files\CMake\bin\cmake.EXE" --build C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\build_lt_session_010 --clean-first --parallel 2 --target czr005_circulation test_circulation_runtime
exit /b %errorlevel%
