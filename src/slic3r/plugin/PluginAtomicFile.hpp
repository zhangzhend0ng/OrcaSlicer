#pragma once
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>
#ifdef _WIN32
// ADAPTED (port): guard like libslic3r/pchheader.hpp (see PluginFileLock.hpp for the rationale).
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace Slic3r {
// Publish a complete file in one rename. Never remove the old file first.
inline std::error_code write_file_atomically(const std::string& path, const std::string& contents)
{
    namespace fs = std::filesystem;
    static std::atomic<unsigned long> sequence{0};
    fs::path                          scratch;
    std::error_code                   error;
    try {
        const auto destination = fs::u8path(path);
        fs::create_directories(destination.parent_path());
        scratch = destination.parent_path() / (".write-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) +
                                               "-" + std::to_string(++sequence));
        if (!fs::create_directory(scratch))
            return std::make_error_code(std::errc::file_exists);
        const auto    temporary = scratch / "payload";
        std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
        output.write(contents.data(), static_cast<std::streamsize>(contents.size()));
        output.close();
        if (!output)
            error = std::make_error_code(std::errc::io_error);
        else {
#ifdef _WIN32
            if (!MoveFileExW(temporary.c_str(), destination.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
                error = std::error_code(static_cast<int>(GetLastError()), std::system_category());
#else
            fs::rename(temporary, destination, error);
#endif
        }
    } catch (const fs::filesystem_error& ex) {
        error = ex.code();
    } catch (...) {
        error = std::make_error_code(std::errc::io_error);
    }
    if (!scratch.empty()) {
        std::error_code ignored;
        fs::remove_all(scratch, ignored);
    }
    return error;
}
} // namespace Slic3r
