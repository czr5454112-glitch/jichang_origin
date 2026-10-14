@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
"C:\Program Files\CMake\bin\cmake.EXE" --build C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\build_lt_native_compat\native_compat_001 --clean-first --parallel 2
exit /b %errorlevel%
