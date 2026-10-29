#pragma once

#include "../../PythonPluginInterface.hpp"

#include <pybind11/pybind11.h>

#include <string>
#include <utility>
#include <vector>

namespace Slic3r {

// Fork-first capability (upstream reserves the PluginCapabilityType::Importer slot but has
// not implemented it on either absorbed line; see docs/plugins/API_REFERENCE.md §5.1). The
// contract is deliberately minimal and marked fork-provisional in the module docstring:
//
//   import_file(path) converts the input into host-loadable mesh file(s) written under the
//   plugin's own storage (orca.host.plugin.storage()) and lists them in ExecutionResult.data
//   as {"files": [...]}; the host loads those through Model::read_from_file. No in-process
//   mesh payloads cross the boundary — the batch-3 review rejected JSON mesh payloads for
//   memory/robustness, and file exchange reuses the host's loaders, repair pipeline and
//   per-file error isolation instead of re-implementing them.
class ImporterPluginCapability : public PluginCapabilityInterface
{
public:
    static void RegisterBindings(pybind11::module_& module);

    PluginCapabilityType get_type() const override { return PluginCapabilityType::Importer; }

    // Python contract: lower-case, dot-prefixed extensions this importer claims (".hul", ...).
    // Resolved once at materialization under the GIL and never called again: dispatch consults
    // the C++-side cache below, because capability lookup runs under the plugin registry lock,
    // which must not take the GIL (see the get_name() note in PythonPluginInterface.hpp).
    virtual std::vector<std::string> get_supported_extensions() const = 0;

    // Synchronous conversion of one file; the host drives this on a worker thread while
    // load_files waits without pumping the wx queue. The trampoline grants dirname(path) as
    // a scoped read-only root, so reading the user's chosen input needs no separate
    // permission prompt (the user picking the file in the host dialog is the intent).
    //   Success           data = {"files": ["<plugin storage>/x.stl", ...]} (host-loadable)
    //   Skipped           this importer declines the file; the host falls back to its
    //                     built-in loader
    //   RecoverableError  this file failed; the batch continues
    //   FatalError        treated by the host as a per-file failure
    virtual ExecutionResult import_file(const std::string& path) = 0;

    // C++-only cache of the resolved extensions (validated: lower-case, dot-prefixed, unique).
    const std::vector<std::string>& supported_extensions() const { return m_extensions; }
    void                            set_supported_extensions(std::vector<std::string> ext) { m_extensions = std::move(ext); }

private:
    std::vector<std::string> m_extensions;
};

} // namespace Slic3r
