#ifndef slic3r_App_CanvasViewModel_hpp_
#define slic3r_App_CanvasViewModel_hpp_

#include "libslic3r/MVVP.hpp"
#include "slic3r/App/CameraController.hpp"
#include "slic3r/App/SelectionController.hpp"

#include <memory>

namespace Slic3r {

/// Rendering options exposed as observable state.
struct RenderOptions {
    bool showLabels{true};
    bool showAxes{true};
    bool showBedGrid{true};
    bool wireframeMode{false};
    bool transparentMode{false};
    int  previewMode{0}; // 0=none, 1=line type, 2=speed, 3=fan, etc.
};

/// Tool type identifier.
enum class ToolType {
    Select,
    Move,
    Scale,
    Rotate,
    PlaceFaceOnBed,
    Cut,
    SupportPainter,
    SeamPainter,
    Measure,
    SLA_Supports,
    SLA_Hollow,
    SLA_Drill,
};

/// MVVP ViewModel for the 3D canvas.
/// Extracted from GLCanvas3D (772 methods).
/// Aggregates CameraController, SelectionController, and tool state.
/// Pure C++, zero OpenGL/wxWidgets dependency.
class CanvasViewModel {
public:
    // ?? Sub-controllers (owned) ??
    CameraController    camera;
    SelectionController selection;

    // ?? Observable State ??
    MVVP::Property<RenderOptions> renderOptions{RenderOptions{}};
    MVVP::Property<ToolType>      activeTool{ToolType::Select};
    MVVP::Property<bool>          gizmoActive{false};
    MVVP::Property<bool>          needsRedraw{false};

    // ?? Commands ??
    MVVP::Command zoomToFit{
        [this] { /* zoom camera to fit scene */ }
    };
    MVVP::Command toggleLabels{
        [this] {
            auto r = renderOptions.get();
            r.showLabels = !r.showLabels;
            renderOptions.set(r);
            needsRedraw.set(true);
        }
    };
    MVVP::Command toggleAxes{
        [this] {
            auto r = renderOptions.get();
            r.showAxes = !r.showAxes;
            renderOptions.set(r);
            needsRedraw.set(true);
        }
    };
    MVVP::Command setToolSelect  { [this] { activeTool.set(ToolType::Select);  } };
    MVVP::Command setToolMove    { [this] { activeTool.set(ToolType::Move);    } };
    MVVP::Command setToolScale   { [this] { activeTool.set(ToolType::Scale);   } };
    MVVP::Command setToolRotate  { [this] { activeTool.set(ToolType::Rotate);  } };
    MVVP::Command setToolCut     { [this] { activeTool.set(ToolType::Cut);     } };

    // ?? Continuous input (delegates to active tool / camera / selection) ??
    void onMouseDown(int x, int y, bool shift);
    void onMouseMove(int x, int y);
    void onMouseUp();
    void onMouseWheel(int delta);

    // Mark that the View should redraw
    void requestRedraw() { needsRedraw.set(true); }
    void acknowledgeRedraw() { needsRedraw.set(false); }
};

} // namespace Slic3r

#endif /* slic3r_App_CanvasViewModel_hpp_ */
