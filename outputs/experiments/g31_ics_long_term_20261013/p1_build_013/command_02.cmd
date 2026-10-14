@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
set VSLANG=1033
"C:\Program Files\CMake\bin\ctest.EXE" --test-dir C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\build_lt_session_013 --output-on-failure -R ^circulation_runtime$ --output-junit C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\outputs\experiments\g31_ics_long_term_20261013\p1_build_013\native_junit.xml
exit /b %errorlevel%
