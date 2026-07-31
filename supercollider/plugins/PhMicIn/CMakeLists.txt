cmake_minimum_required(VERSION 3.10)
project(PhMicIn)
set(CMAKE_CXX_STANDARD 11)
include_directories(${SC_PATH}/include/plugin_interface ${SC_PATH}/include/common
                    ${CMAKE_CURRENT_SOURCE_DIR})
add_library(PhMicIn MODULE PhMicIn.cpp)
set_target_properties(PhMicIn PROPERTIES PREFIX "" SUFFIX ".so")
target_link_libraries(PhMicIn rt)
# supernova loads ONLY *_supernova.so, so both variants are always built together.
add_library(PhMicIn_supernova MODULE PhMicIn.cpp)
set_target_properties(PhMicIn_supernova PROPERTIES PREFIX "" SUFFIX ".so")
target_compile_definitions(PhMicIn_supernova PRIVATE SUPERNOVA=1)
target_link_libraries(PhMicIn_supernova rt)
