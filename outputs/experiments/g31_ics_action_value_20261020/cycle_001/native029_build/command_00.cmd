@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b %errorlevel%
set VSLANG=1033
"C:\Program Files\CMake\bin\cmake.EXE" -S C:\PROGRAMING\czr005\.g31_ics_circulation_worktree -B C:\PROGRAMING\czr005\.g31_ics_circulation_worktree\build_lt_session_029 -DCMAKE_BUILD_TYPE=Release -DCMAKE_TRY_COMPILE_CONFIGURATION=Release -DCZR005_BUILD_PYBIND=ON -DPython3_EXECUTABLE=C:\PROGRAMING\python3.11.9\python.exe -Dpybind11_DIR=C:\PROGRAMING\python3.11.9\Lib\site-packages\pybind11\share\cmake\pybind11 -G Ninja -DCMAKE_MAKE_PROGRAM=C:\Users\38908\.conda\envs\czr005\Library\bin\ninja.exe
exit /b %errorlevel%
