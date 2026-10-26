#pragma once

#include <filesystem>
#include <stdexcept>
#include <system_error>
#ifdef _WIN32
// ADAPTED (port): guard like libslic3r/pchheader.hpp — this header reaches every TU that
// includes PluginManager.hpp; a bare windows.h would define min/max macros and break
// BoundingBox.hpp member initializer lists downstream.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <cerrno>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace Slic3r {
// The file persists; only the OS-owned lock represents ownership. Removing the
// file would let another process lock a different inode while this one is held.
class PluginFileLock
{
public:
    explicit PluginFileLock(const std::filesystem::path& path)
    {
#ifdef _WIN32
        m_handle = ::CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        if (m_handle == INVALID_HANDLE_VALUE)
            throw std::system_error(::GetLastError(), std::system_category(), "Cannot open plugin installation lock");
        BY_HANDLE_FILE_INFORMATION info{};
        OVERLAPPED offset{};
        if (!::GetFileInformationByHandle(m_handle, &info) || (info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) ||
            !::LockFileEx(m_handle, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &offset)) {
            ::CloseHandle(m_handle);
            m_handle = INVALID_HANDLE_VALUE;
            throw std::runtime_error("Plugin installation lock is busy or invalid");
        }
#else
        m_fd = ::open(path.c_str(), O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (m_fd < 0)
            throw std::system_error(errno, std::generic_category(), "Cannot open plugin installation lock");
        struct stat info{};
        if (::fstat(m_fd, &info) != 0 || !S_ISREG(info.st_mode) || ::flock(m_fd, LOCK_EX | LOCK_NB) != 0) {
            ::close(m_fd);
            m_fd = -1;
            throw std::runtime_error("Plugin installation lock is busy or invalid");
        }
#endif
    }
    ~PluginFileLock()
    {
#ifdef _WIN32
        if (m_handle != INVALID_HANDLE_VALUE) ::CloseHandle(m_handle);
#else
        if (m_fd >= 0) ::close(m_fd);
#endif
    }
    PluginFileLock(const PluginFileLock&) = delete;
    PluginFileLock& operator=(const PluginFileLock&) = delete;
    PluginFileLock(PluginFileLock&&) = delete;
    PluginFileLock& operator=(PluginFileLock&&) = delete;
private:
#ifdef _WIN32
    HANDLE m_handle = INVALID_HANDLE_VALUE;
#else
    int m_fd = -1;
#endif
};
} // namespace Slic3r
