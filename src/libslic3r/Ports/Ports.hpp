#ifndef libslic3r_Ports_Ports_hpp_
#define libslic3r_Ports_Ports_hpp_

// Phase 2 interface catalog for breaking the Core/GUI dependency cycle.
// All interfaces are defined in libslic3r (Layer 2).
// Implementations live in Application (Layer 3).

#include "libslic3r/Ports/IProgressReporter.hpp"
#include "libslic3r/Ports/IModelArranger.hpp"
#include "libslic3r/Ports/IGCodeConsumer.hpp"
#include "libslic3r/Ports/IPlateDataProvider.hpp"
#include "libslic3r/Ports/IConfigResolver.hpp"
#include "libslic3r/Ports/INotificationSink.hpp"

#endif /* libslic3r_Ports_Ports_hpp_ */
