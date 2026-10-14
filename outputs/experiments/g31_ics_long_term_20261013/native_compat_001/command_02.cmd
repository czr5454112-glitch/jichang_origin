@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
"C:\Program Files\CMake\bin\ctest.EXE" --test-dir C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\build_lt_native_compat\native_compat_001 --output-on-failure --output-junit C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\outputs\experiments\g31_ics_long_term_20261013\native_compat_001\junit.xml
exit /b %errorlevel%
