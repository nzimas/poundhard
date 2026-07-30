cmake_minimum_required(VERSION 3.10)
project(PhSoftcut)
set(CMAKE_CXX_STANDARD 14)
if(NOT SC_PATH)
    message(FATAL_ERROR "SC_PATH must point at a SuperCollider source tree")
endif()
if(NOT SOFTCUT_PATH)
    message(FATAL_ERROR "SOFTCUT_PATH must point at a softcut-lib checkout")
endif()
include_directories(
    ${SC_PATH}/include/plugin_interface
    ${SC_PATH}/include/common
    ${SOFTCUT_PATH}/include
    ${SOFTCUT_PATH}/src)
# TWO builds of the same source. supernova loads only the *_supernova.so variants, and
# they are not just renamed copies: the SC plugin API's buffer macros compile differently
# under -DSUPERNOVA, taking real locks because supernova runs unit generators in parallel.
# Shipping only the plain .so is why the server reported "PhSoftcut not installed".
add_library(PhSoftcut MODULE PhSoftcut.cpp)
set_target_properties(PhSoftcut PROPERTIES PREFIX "" SUFFIX ".so")
target_link_libraries(PhSoftcut ${SOFTCUT_LIB})

add_library(PhSoftcut_supernova MODULE PhSoftcut.cpp)
target_compile_definitions(PhSoftcut_supernova PRIVATE SUPERNOVA=1)
set_target_properties(PhSoftcut_supernova PROPERTIES PREFIX "" SUFFIX ".so")
target_link_libraries(PhSoftcut_supernova ${SOFTCUT_LIB})
