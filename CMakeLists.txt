cmake_minimum_required(VERSION 3.20)
project(czr005 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

enable_testing()

add_library(ics_core INTERFACE)
target_include_directories(ics_core INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/cpp)

