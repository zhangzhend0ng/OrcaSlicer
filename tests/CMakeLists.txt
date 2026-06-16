# TODO Add individual tests as executables in separate directories
# add_subirectory(<testcase>)

set(TEST_DATA_DIR ${CMAKE_CURRENT_SOURCE_DIR}/data)
file(TO_NATIVE_PATH "${TEST_DATA_DIR}" TEST_DATA_DIR)
set(TEST_RESOURCES_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../resources)
file(TO_NATIVE_PATH "${TEST_RESOURCES_DIR}" TEST_RESOURCES_DIR)

# Catch2 v3 via FetchContent (cmake/catch2.cmake)
include(${CMAKE_CURRENT_SOURCE_DIR}/../cmake/catch2.cmake)

set(CATCH_EXTRA_ARGS "" CACHE STRING "Extra arguments for catch2 test suites.")

add_library(test_common INTERFACE)
target_compile_definitions(test_common INTERFACE TEST_DATA_DIR=R"\(${TEST_DATA_DIR}\)" TEST_RESOURCES_DIR=R"\(${TEST_RESOURCES_DIR}\)" CATCH_CONFIG_FAST_COMPILE)
target_include_directories(test_common INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(test_common INTERFACE Catch2::Catch2WithMain)
if (MSVC)
    target_compile_options(test_common INTERFACE /FI"${CMAKE_CURRENT_SOURCE_DIR}/catch_main.hpp")
else()
    target_compile_options(test_common INTERFACE -include "${CMAKE_CURRENT_SOURCE_DIR}/catch_main.hpp")
endif()

if (APPLE)
    target_link_libraries(test_common INTERFACE "-liconv -framework IOKit" "-framework CoreFoundation" -lc++)
endif()

set_property(GLOBAL PROPERTY USE_FOLDERS ON)

# Common link libraries for all tests that depend on libslic3r.
# libslic3r is a STATIC library; its PRIVATE dependencies are not propagated,
# so every test executable must explicitly link them.
set(TEST_LINK_LIBS
    test_common
    libslic3r
    boost_libs
    Boost::log
    TBB::tbb
    TBB::tbbmalloc
    OpenSSL::Crypto
    clipper
    qhull
    mcut
    glu-libtess
    JPEG::JPEG
    PNG::PNG
    ZLIB::ZLIB
    noise::noise
    qoi
    semver
    libslic3r_cgal
    ${EXPAT_LIBRARIES}
    ${OCCT_LIBS}
    ${FREETYPE_LIBRARIES}
)

# --- end common link libs ---


add_subdirectory(libnest2d)
add_subdirectory(libslic3r)
add_subdirectory(slic3rutils)
add_subdirectory(fff_print)
add_subdirectory(sla_print)
add_subdirectory(cpp17 EXCLUDE_FROM_ALL)    # does not have to be built all the time
# add_subdirectory(example)
