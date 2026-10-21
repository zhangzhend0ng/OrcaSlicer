
include(ProcessorCount)
ProcessorCount(NPROC)

if(DEFINED OPENSSL_ARCH)
    set(_cross_arch ${OPENSSL_ARCH})
else()
    if(WIN32)
        set(_cross_arch "VC-WIN64A")
    elseif(APPLE)
        set(_cross_arch "darwin64-arm64-cc")
	endif()
endif()

set(_openssl_dir ${DESTDIR})

if(WIN32)
    set(_conf_cmd perl Configure )
    set(_cross_comp_prefix_line "")
    configure_file(
        ${CMAKE_CURRENT_LIST_DIR}/build_windows.bat.in
        ${CMAKE_CURRENT_BINARY_DIR}/build_windows.bat
        @ONLY
    )
    configure_file(
        ${CMAKE_CURRENT_LIST_DIR}/build_windows_clean.bat.in
        ${CMAKE_CURRENT_BINARY_DIR}/build_windows_clean.bat
        @ONLY
    )
    set(_make_cmd "${CMAKE_CURRENT_BINARY_DIR}/build_windows.bat")
    set(_install_cmd ${_make_cmd} install_sw)
else()
    if(APPLE)
        set(_conf_cmd export MACOSX_DEPLOYMENT_TARGET=${CMAKE_OSX_DEPLOYMENT_TARGET} && ./Configure -mmacosx-version-min=${CMAKE_OSX_DEPLOYMENT_TARGET})
        # OPENSSLDIR is only where OpenSSL looks at runtime for cert.pem, certs/
        # and openssl.cnf; install_sw installs nothing there. Point it at the
        # system CA bundle, the one libcurl already uses here, so the bundled
        # Python's ssl module can verify HTTPS. Elsewhere it stays the prefix:
        # Windows Python reads the system certificate store, and on Linux, where
        # the bundle's location differs by distro, CurlGlobalInit points
        # SSL_CERT_FILE at it at startup.
        set(_openssl_dir /etc/ssl)
    else()
        # A static library that is embedded into a shared object must not export
        # its symbols. On Linux the running process also loads the system OpenSSL
        # 3.x (WebKitGTK/gnutls pull in libcrypto.so.3), and CPython's _ssl and
        # _hashlib are dlopened (RTLD_LOCAL) DSOs that each embed this OpenSSL.
        # With default visibility their unversioned OpenSSL references are
        # preempted by that global 3.x copy, mixing the 1.1.1 and 3.x ABIs and
        # corrupting the heap (ssl.create_default_context() aborts). Hidden
        # visibility makes each embedded copy self-contained. Linux-only: macOS
        # binds dylibs with a two-level namespace (no interposition) and ships no
        # OpenSSL, and Windows has no equivalent flag and no system OpenSSL to
        # collide with.
        set(_openssl_extra_cflags -fvisibility=hidden)
        set(_conf_cmd "./config")
    endif()
    set(_cross_comp_prefix_line "")
    set(_make_cmd make -j${NPROC})
    set(_install_cmd make -j${NPROC} install_sw)
    if (CMAKE_CROSSCOMPILING)
        set(_cross_comp_prefix_line "--cross-compile-prefix=${TOOLCHAIN_PREFIX}-")

        if (${CMAKE_SYSTEM_PROCESSOR} STREQUAL "aarch64" OR ${CMAKE_SYSTEM_PROCESSOR} STREQUAL "arm64")
            set(_cross_arch "linux-aarch64")
        elseif (${CMAKE_SYSTEM_PROCESSOR} STREQUAL "armhf") # For raspbian
            # TODO: verify
            set(_cross_arch "linux-armv4")
        endif ()
    endif ()
endif()

ExternalProject_Add(dep_OpenSSL
    #EXCLUDE_FROM_ALL ON
    URL "https://github.com/openssl/openssl/releases/download/openssl-3.5.7/openssl-3.5.7.tar.gz"
    URL_HASH SHA256=A8C0D28A529CA480F9F36CF5792E2CD21984552A3C8E4AA11A24AA31AEAC98E8
    # URL "https://github.com/openssl/openssl/archive/refs/tags/openssl-3.1.2.tar.gz"
    # URL_HASH SHA256=8c776993154652d0bb393f506d850b811517c8bd8d24b1008aef57fbe55d3f31
    DOWNLOAD_DIR ${DEP_DOWNLOAD_DIR}/OpenSSL
	CONFIGURE_COMMAND ${_conf_cmd} ${_cross_arch}
        "--openssldir=${_openssl_dir}"
        "--prefix=${DESTDIR}"
        ${_cross_comp_prefix_line}
        ${_openssl_extra_cflags}
        no-shared
        no-asm
        no-apps
        no-ssl3-method
        no-dynamic-engine
    BUILD_IN_SOURCE ON
    BUILD_COMMAND ${_make_cmd} build_libs
    INSTALL_COMMAND ${_install_cmd}
)

if (CMAKE_GENERATOR MATCHES "Visual Studio")
    # OpenSSL builds with cl, but MSBuild runs nmake in this project's toolset
    # environment, and ClangCL's puts clang's headers first. Use the default.
    set_target_properties(dep_OpenSSL PROPERTIES VS_PLATFORM_TOOLSET "$(DefaultPlatformToolset)")
endif ()

ExternalProject_Add_Step(dep_OpenSSL install_cmake_files
    DEPENDEES install

    COMMAND ${CMAKE_COMMAND} -E copy_directory openssl "${DESTDIR}${CMAKE_INSTALL_LIBDIR}/cmake/openssl"
    WORKING_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}"
)

if (NOT WIN32)
    # OpenSSL's object rules do not depend on the configured flags or paths, so
    # reconfiguring it (a new compiler flag, a different --openssldir) relinks
    # the archives from stale objects instead of recompiling them, and the
    # change silently has no effect. Drop the objects whenever this recipe
    # changes so the next build actually recompiles them.
    ExternalProject_Get_Property(dep_OpenSSL SOURCE_DIR)
    ExternalProject_Add_Step(dep_OpenSSL clean_objects
        DEPENDEES configure
        DEPENDERS build
        COMMAND make clean
        WORKING_DIRECTORY "${SOURCE_DIR}"
        DEPENDS "${CMAKE_CURRENT_LIST_FILE}"
        COMMENT "OpenSSL: cleaning objects after a recipe change"
    )
endif ()
