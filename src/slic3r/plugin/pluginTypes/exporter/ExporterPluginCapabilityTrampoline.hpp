#pragma once

#include "ExporterPluginCapability.hpp"
#include "../../PyPluginTrampoline.hpp"
#include "slic3r/plugin/PluginAuditManager.hpp"

#include <boost/filesystem.hpp>

#include <string>
#include <vector>

namespace Slic3r {

class PyExporterPluginCapabilityTrampoline : public PyPluginCommonTrampoline<ExporterPluginCapability>
{
public:
    using PyPluginCommonTrampoline<ExporterPluginCapability>::PyPluginCommonTrampoline;

    std::vector<std::string> get_supported_extensions() const override
    {
        ORCA_PY_OVERRIDE_AUDITED(
            [] {},
            PYBIND11_OVERRIDE_PURE,
            std::vector<std::string>,
            ExporterPluginCapability,
            get_supported_extensions);
    }

    ExecutionResult export_file(ExporterContext& ctx) override
    {
        ORCA_PY_OVERRIDE_AUDITED(
            [&] {
                // The export target lives wherever the user picked it, typically outside
                // data_dir(); grant its folder as a scoped writable root so the plugin's
                // own write to ctx.path needs no separate prompt (the user picking the
                // path in the host's save dialog is the intent).
                if (!ctx.path.empty())
                    ::Slic3r::PluginAuditManager::instance().add_scoped_allowed_root(
                        boost::filesystem::path(ctx.path).parent_path());
            },
            PYBIND11_OVERRIDE_PURE,
            ExecutionResult,
            ExporterPluginCapability,
            export_file, ctx);
    }
};

} // namespace Slic3r
