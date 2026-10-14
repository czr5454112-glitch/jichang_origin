@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
"C:\Program Files\CMake\bin\cmake.EXE" -S C:\PROGRAMING\czr005\.g31_ics_circulation_worktree -B C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\build_lt_native_compat\native_compat_001 -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TRY_COMPILE_CONFIGURATION=Release -DCZR005_BUILD_PYBIND=OFF -DCMAKE_MAKE_PROGRAM=C:\Users\38908\.conda\envs\czr005\Library\bin\ninja.exe
exit /b %errorlevel%
