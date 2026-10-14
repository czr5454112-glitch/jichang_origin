@echo off
call "C:\PROGRAMING\visual studio\Visual studio\VC\Auxiliary\Build\vcvars64.bat"
set VSLANG=1033
cmake -S "C:/PROGRAMING/czr005/.g31_ics_circulation_worktree" -B "C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_g31_current" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_TRY_COMPILE_CONFIGURATION=Release -DCZR005_BUILD_PYBIND=OFF -DCMAKE_MAKE_PROGRAM="C:/Users/38908/.conda/envs/czr005/Library/bin/ninja.exe"
if errorlevel 1 exit /b %errorlevel%
cmake --build "C:/PROGRAMING/czr005/.g31_ics_circulation_worktree/build_g31_current" --clean-first --parallel 2 
exit /b %errorlevel%



