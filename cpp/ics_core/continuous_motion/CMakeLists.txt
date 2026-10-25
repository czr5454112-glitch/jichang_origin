cmake_minimum_required(VERSION 3.18)
project(g31_continuous_motion LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(pybind11 CONFIG REQUIRED)
# Keep the verified module ABI; this is a separate engine from czr005_cpp.
pybind11_add_module(g31_nowait core.cpp)
if(MSVC)
  target_compile_options(g31_nowait PRIVATE /O2 /EHsc /bigobj)
endif()
set_target_properties(g31_nowait PROPERTIES
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python")
foreach(config RELEASE DEBUG RELWITHDEBINFO MINSIZEREL)
  set_target_properties(g31_nowait PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY_${config} "${CMAKE_BINARY_DIR}/python"
    RUNTIME_OUTPUT_DIRECTORY_${config} "${CMAKE_BINARY_DIR}/python")
endforeach()
