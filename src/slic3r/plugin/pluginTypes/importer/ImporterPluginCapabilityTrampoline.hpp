#pragma once

#include "ImporterPluginCapability.hpp"
#include "../../PyPluginTrampoline.hpp"
#include "slic3r/plugin/PluginAuditManager.hpp"

#include <boost/filesystem.hpp>

#include <string>

namespace Slic3r {

class PyImporterPluginCapabilityTrampoline : public PyPluginCommonTrampoline<ImporterPluginCapability>
{
public:
    using PyPluginCommonTrampoline<ImporterPluginCapability>::PyPluginCommonTrampoline;

    std::vector<std::string> get_supported_extensions() const override
    {
        ORCA_PY_OVERRIDE_AUDITED(
            [] {},
            PYBIND11_OVERRIDE_PURE,
            std::vector<std::string>,
            ImporterPluginCapability,
            get_supported_extensions);
    }

    ExecutionResult import_file(const std::string& path) override
    {
        ORCA_PY_OVERRIDE_AUDITED(
            [&] {
                // The input file lives wherever the user picked it, typically outside
                // data_dir(), so reading it would otherwise hit the audit sandbox (and, on
                // a worker thread, a first-call fail-closed denial). Grant its folder as a
                // scoped read-only root: the user choosing the file in the host dialog is
                // the intent. The setup callback runs after the audit context is built, so
                // the scoped root is not cleared by its constructor.
                if (!path.empty())
                    ::Slic3r::PluginAuditManager::instance().add_scoped_allowed_root(
                        boost::filesystem::path(path).parent_path(), /*allow_write=*/false);
            },
            PYBIND11_OVERRIDE_PURE,
            ExecutionResult,
            ImporterPluginCapability,
            import_file, path);
    }
};

} // namespace Slic3r
