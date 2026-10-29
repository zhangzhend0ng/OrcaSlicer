#pragma once

#include "../../PythonPluginInterface.hpp"
#include <libslic3r/Model.hpp>

#include <pybind11/pybind11.h>

#include <string>
#include <vector>

namespace Slic3r {

// Per-call context handed to an Exporter capability. Typed struct, not a JSON payload —
// the slicing-pipeline ctx precedent (SlicingPipelineContext): the host pushes references,
// the plugin pulls what it needs (meshes via volume.mesh().vertices()/triangles() zero-copy
// numpy views) instead of the host pre-serializing a payload. Valid only for the duration
// of the export_file(ctx) call; do not stash references across calls.
struct ExporterContext {
    std::string       orca_version;
    // Export target the plugin writes itself. Its folder is granted as a scoped writable
    // root for the call (the user picked the path in the host's save dialog); the plugin
    // still writes the file through its own code, so the write is attributed to it.
    std::string       path;
    // Objects chosen for the export; empty means every object of the model.
    std::vector<int>  object_indices;
    // Read-only snapshot of the scene (a host-side clone, stable for the whole call).
    // Mesh access: model.object(i).volume(j).mesh(). Never orca.host.model() — that is
    // the live GUI model owned by the UI thread.
    const Model*      model { nullptr };
};

// Fork-first capability (upstream reserves the PluginCapabilityType::Exporter slot but has
// not implemented it on either absorbed line; see docs/plugins/API_REFERENCE.md §5.1).
// Contract minimal and fork-provisional; the module docstring is the reconciliation seam
// if upstream lands a different shape.
class ExporterPluginCapability : public PluginCapabilityInterface
{
public:
    static void RegisterBindings(pybind11::module_& module);

    PluginCapabilityType get_type() const override { return PluginCapabilityType::Exporter; }

    // Same materialization semantics as the importer's: resolved once under the GIL, then
    // only the C++-side cache below is consulted (registry lock must not take the GIL).
    virtual std::vector<std::string> get_supported_extensions() const = 0;

    // Synchronous export; the host drives this on a worker thread (the UI thread snapshots
    // the model, dispatches, and reports via a notification when the call returns).
    virtual ExecutionResult export_file(ExporterContext& ctx) = 0;

    const std::vector<std::string>& supported_extensions() const { return m_extensions; }
    void                            set_supported_extensions(std::vector<std::string> ext) { m_extensions = std::move(ext); }

private:
    std::vector<std::string> m_extensions;
};

} // namespace Slic3r
