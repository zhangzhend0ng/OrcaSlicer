#ifndef libslic3r_Ports_IGCodeConsumer_hpp_
#define libslic3r_Ports_IGCodeConsumer_hpp_

#include <string>
#include <string_view>

namespace Slic3r {

/// Interface for consuming generated GCode output.
/// Defined in libslic3r (Layer 2), implemented by Application (Layer 3).
/// Replaces: direct Plater manipulation from GCode generation code.
class IGCodeConsumer {
public:
    virtual ~IGCodeConsumer() = default;

    /// Receive the final GCode string after slicing completes.
    virtual void consume_gcode(std::string_view gcode) = 0;

    /// Receive incremental GCode preview data during slicing.
    virtual void consume_gcode_preview(std::string_view gcode_segment) = 0;
};

} // namespace Slic3r

#endif /* libslic3r_Ports_IGCodeConsumer_hpp_ */
