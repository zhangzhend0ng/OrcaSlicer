#ifndef libslic3r_Ports_IPlateDataProvider_hpp_
#define libslic3r_Ports_IPlateDataProvider_hpp_

namespace Slic3r {

struct BoundingBoxf3;

/// Interface for querying plate/bed geometry.
/// Defined in libslic3r (Layer 2), implemented by Application (Layer 3).
/// Replaces: Plater::priv accessed from Print for bed shape queries.
class IPlateDataProvider {
public:
    virtual ~IPlateDataProvider() = default;

    /// Get the printable bounding box for the current plate.
    virtual BoundingBoxf3 plate_bounding_box() const = 0;

    /// Check if a given position is within the printable area.
    virtual bool is_position_printable(double x, double y, double z) const = 0;
};

} // namespace Slic3r

#endif /* libslic3r_Ports_IPlateDataProvider_hpp_ */
