cmake_minimum_required(VERSION 3.20)
project(czr005 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

enable_testing()

option(CZR005_BUILD_PYBIND "Build Python bindings with pybind11" ON)

add_library(ics_core INTERFACE)
target_include_directories(ics_core INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/cpp)

add_executable(test_cpp_core_smoke cpp/tests/test_cpp_core_smoke.cpp)
target_link_libraries(test_cpp_core_smoke PRIVATE ics_core)
target_compile_definitions(test_cpp_core_smoke PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME cpp_core_smoke COMMAND test_cpp_core_smoke)

add_executable(test_event_driven_junction cpp/tests/test_event_driven_junction.cpp)
target_link_libraries(test_event_driven_junction PRIVATE ics_core)
target_compile_definitions(test_event_driven_junction PRIVATE CZR005_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME event_driven_junction COMMAND test_event_driven_junction)

if(CZR005_BUILD_PYBIND)
  find_package(Python3 COMPONENTS Interpreter Development.Module REQUIRED)
  find_package(pybind11 CONFIG REQUIRED)

  pybind11_add_module(czr005_cpp cpp/ics_core/bindings/czr005_cpp.cpp)
  target_link_libraries(czr005_cpp PRIVATE ics_core)
  set_target_properties(
    czr005_cpp
    PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python
      RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python
      ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/python)

  add_test(
    NAME pybind_smoke
    COMMAND
      ${CMAKE_COMMAND} -E env
      "PYTHONPATH=$<TARGET_FILE_DIR:czr005_cpp>"
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/cpp/tests/test_pybind_smoke.py)
  set_tests_properties(pybind_smoke PROPERTIES DEPENDS czr005_cpp)
endif()
