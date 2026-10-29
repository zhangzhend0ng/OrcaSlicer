#ifndef slic3r_PluginHostPainting_hpp_
#define slic3r_PluginHostPainting_hpp_

#pragma once

// Internal to plugin/host/: the facet-painting Plater methods (FDM support /
// seam / MMU / fuzzy-skin paint data as typed per-facet arrays), implemented
// in PluginHostPainting.cpp. Extends the Plater py::class_ registered by
// register_app (PluginHostApp.cpp); called from there after its own chain.

#include <pybind11/pybind11.h>

#include <slic3r/GUI/Plater.hpp>

namespace Slic3r::host_bindings {

void register_painting_methods(pybind11::class_<GUI::Plater, std::unique_ptr<GUI::Plater, pybind11::nodelete>>& plater);

} // namespace Slic3r::host_bindings

#endif /* slic3r_PluginHostPainting_hpp_ */
