#pragma once

#include <boost/filesystem.hpp>
#include <boost/nowide/fstream.hpp>
#include <miniz.h>
#include <filesystem>
#include <fstream>

namespace Slic3r {
// release_2.4.1 adapter for the upstream archive helpers. The native path
// preserves Unicode and extended-length Windows paths without changing miniz.
inline boost::filesystem::path extended_path(const boost::filesystem::path& input)
{
    auto result = boost::filesystem::absolute(input).lexically_normal();
#ifdef _WIN32
    auto native = result.wstring();
    if (native.rfind(L"\\\\?\\", 0) != 0) {
        if (native.rfind(L"\\\\", 0) == 0)
            native = L"\\\\?\\UNC\\" + native.substr(2);
        else
            native = L"\\\\?\\" + native;
    }
    return boost::filesystem::path(native);
#else
    return result;
#endif
}
inline bool extract_zip_entry_to_file(mz_zip_archive* archive, mz_uint index, const boost::filesystem::path& path)
{
    const auto    native = extended_path(path);
    std::ofstream output(std::filesystem::path(native.native()), std::ios::binary | std::ios::trunc);
    if (!output)
        return false;
    const auto writer = [](void* context, mz_uint64 offset, const void* data, size_t size) -> size_t {
        auto& stream = *static_cast<std::ofstream*>(context);
        stream.seekp(static_cast<std::streamoff>(offset));
        stream.write(static_cast<const char*>(data), static_cast<std::streamsize>(size));
        return stream ? size : 0;
    };
    const bool extracted = mz_zip_reader_extract_to_callback(archive, index, writer, &output, 0);
    output.close();
    return extracted && bool(output);
}
} // namespace Slic3r
