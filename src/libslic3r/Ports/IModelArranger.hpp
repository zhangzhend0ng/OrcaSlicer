#ifndef libslic3r_Ports_IModelArranger_hpp_
#define libslic3r_Ports_IModelArranger_hpp_

#include <vector>

namespace Slic3r {

class Model;
class DynamicPrintConfig;

/// Interface for plate arrangement strategy.
/// Defined in libslic3r (Layer 2), implemented by Application (Layer 3).
/// Replaces: Plater::arrange() called from Print::apply().
class IModelArranger {
public:
    virtual ~IModelArranger() = default;

    /// Arrange model instances on the build plate.
    /// Returns true if arrangement was successful.
    virtual bool arrange(Model& model, const DynamicPrintConfig& config) = 0;
};

} // namespace Slic3r

#endif /* libslic3r_Ports_IModelArranger_hpp_ */
