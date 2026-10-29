#ifndef slic3r_GUI_Utils_FixModelByWin10_hpp_
#define slic3r_GUI_Utils_FixModelByWin10_hpp_

#include <functional>
#include <string>
#include "../GUI/Widgets/ProgressDialog.hpp"

class ProgressDialog;

namespace Slic3r {

class Model;
class ModelObject;
class Print;

#ifdef HAS_WIN10SDK

extern bool is_windows10();

// Progress function, to be called regularly to update the progress.
typedef std::function<void (const char * /* message */, unsigned /* progress */)> ProgressFn;
typedef std::function<void ()> ThrowOnCancelFn;
// Repair a 3mf through the WinRT Printing3D API; the computation core under
// fix_model_by_win10_sdk_gui, usable without its progress dialog.
extern void fix_model_by_win10_sdk(const std::string &path_src, const std::string &path_dst, ProgressFn on_progress, ThrowOnCancelFn throw_on_cancel);

// returt false, if fixing was canceled
extern bool fix_model_by_win10_sdk_gui(ModelObject &model_object, int volume_idx,GUI::ProgressDialog &progress_dlg, const wxString &msg_header, std::string &fix_result);

#else /* HAS_WIN10SDK */

inline bool is_windows10() { return false; }

#endif /* HAS_WIN10SDK */

} // namespace Slic3r

#endif /* slic3r_GUI_Utils_FixModelByWin10_hpp_ */
