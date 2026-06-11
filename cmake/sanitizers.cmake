# cmake/sanitizers.cmake — AddressSanitizer (ASan) and UndefinedBehaviorSanitizer (UBSan)
#
# Provides options ENABLE_ASAN and ENABLE_UBSAN that add the appropriate
# compiler and linker flags for GCC, Clang, and MSVC.
#
# ENABLE_ASAN defaults to ON for Debug builds, OFF otherwise.
# Override with -DENABLE_ASAN=OFF or -DENABLE_ASAN=ON on the command line.
#
# Usage:
#   include(cmake/sanitizers.cmake)
#   cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug          # ASan auto-enabled
#   cmake -S . -B build -DENABLE_ASAN=ON -DENABLE_UBSAN=ON
#
# On GCC / Clang, ASan and UBSan can coexist: both -fsanitize=address
# and -fsanitize=undefined are passed.
#
# On MSVC, only ASan is supported (/fsanitize=address). UBSan is not
# available; enabling UBSAN on MSVC emits a warning and is a no-op.

# ASan: auto-enable for Debug builds unless explicitly overridden
if(DEFINED ENABLE_ASAN)
    # User explicitly set it; honour their choice
elseif(CMAKE_BUILD_TYPE STREQUAL "Debug")
    set(ENABLE_ASAN ON CACHE BOOL "Enable AddressSanitizer (ASan) — detect memory errors" FORCE)
else()
    set(ENABLE_ASAN OFF CACHE BOOL "Enable AddressSanitizer (ASan) — detect memory errors" FORCE)
endif()

# UBSan: always opt-in due to -fno-sanitize-recover=all (breaks non-test binaries)
option(ENABLE_UBSAN "Enable UndefinedBehaviorSanitizer (UBSan) — detect undefined behavior" OFF)

# ── ASan ──────────────────────────────────────────────────────────────────────
if(ENABLE_ASAN)
    # ASan is available on MSVC starting with Visual Studio 2019 16.9
    # https://devblogs.microsoft.com/cppblog/address-sanitizer-for-msvc-now-generally-available/
    if(MSVC)
        add_compile_options(/fsanitize=address)
        add_compile_definitions(_DISABLE_STRING_ANNOTATION=1 _DISABLE_VECTOR_ANNOTATION=1)
    else()
        add_compile_options(-fsanitize=address -fno-omit-frame-pointer)
        add_link_options(-fsanitize=address)

        # GCC needs explicit -lasan for static linking in some configurations
        if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
            add_link_options(-lasan)
        endif()
    endif()

    message(STATUS "AddressSanitizer (ASan) enabled")
endif()

# ── UBSan ─────────────────────────────────────────────────────────────────────
if(ENABLE_UBSAN)
    if(MSVC)
        message(WARNING "UndefinedBehaviorSanitizer (UBSan) is not supported on MSVC — ignored")
    else()
        add_compile_options(
            -fsanitize=undefined
            -fsanitize=signed-integer-overflow
            -fsanitize=implicit-conversion
            -fno-sanitize-recover=all
        )
        add_link_options(-fsanitize=undefined)

        if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
            add_link_options(-lubsan)
        endif()

        message(STATUS "UndefinedBehaviorSanitizer (UBSan) enabled")
    endif()
endif()

# ── LeakSanitizer note ────────────────────────────────────────────────────────
# ASan includes LeakSanitizer (LSan) by default on Linux x86_64.
# To disable LSan at runtime: ASAN_OPTIONS=detect_leaks=0 ./your_binary
# To run with extra UBSan checks at runtime: UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1 ./your_binary