cmake_minimum_required(VERSION 3.20)
project(g31_planning_v2_typed_encoder LANGUAGES CXX)

# Separate data-only prototype. Never link a circulation/simulator library.
find_package(Python3 3.11.9 EXACT COMPONENTS Interpreter Development.Module REQUIRED)
Python3_add_library(_g31_planning_v2_typed_encoder MODULE WITH_SOABI encoder.cpp)
target_compile_features(_g31_planning_v2_typed_encoder PRIVATE cxx_std_17)
set_target_properties(_g31_planning_v2_typed_encoder PROPERTIES
  CXX_EXTENSIONS OFF LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/python")
if(MSVC)
  target_compile_options(_g31_planning_v2_typed_encoder PRIVATE /W4 /WX /Brepro)
  target_link_options(_g31_planning_v2_typed_encoder PRIVATE /Brepro)
else()
  target_compile_options(_g31_planning_v2_typed_encoder PRIVATE -Wall -Wextra -Werror)
endif()
