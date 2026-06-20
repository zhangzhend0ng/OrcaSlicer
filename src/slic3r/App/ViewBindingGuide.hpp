#ifndef slic3r_App_ViewBindingGuide_hpp_
#define slic3r_App_ViewBindingGuide_hpp_

// ============================================================
// View Binding Pattern for wxWidgets
// ============================================================
//
// This file documents the standard pattern for binding MVVM
// Property<T> and Command to wxWidgets controls.
// It is NOT compiled ? it serves as a reference for developers
// implementing actual View panels.
//
// ============================================================
// Pattern 1: Property<T> ? wxWidget
// ============================================================
//
// Every Property subscription MUST dispatch to the main thread
// via CallAfter(), because Property::set() may be called from
// a worker thread (e.g., slice progress callback).
//
// Example:
//
//   class ColorMixPanel : public wxPanel {
//       MixedFilamentViewModel* vm_;
//       wxScrolledWindow* m_entryList;
//       wxStaticText*     m_statusLabel;
//
//       void bind(MixedFilamentViewModel* vm) {
//           vm_ = vm;
//
//           // Pattern: subscribe ? CallAfter ? update widget
//           vm_->entries.subscribe([this](const auto& entries, const auto&) {
//               CallAfter([this, entries] {
//                   rebuildEntryList(entries);
//               });
//           });
//
//           vm_->hasMixedFilaments.subscribe([this](bool has, bool) {
//               CallAfter([this, has] {
//                   m_entryList->Show(has);
//                   m_statusLabel->SetLabel(has ? "" : "No mixed filaments");
//                   Layout();
//               });
//           });
//       }
//   };
//
// ============================================================
// Pattern 2: wxWidget event ? Command
// ============================================================
//
// View forwards user actions to ViewModel via Commands.
// The ViewModel executes business logic and updates Properties,
// which in turn trigger the View to refresh.
//
// Example:
//
//   void bind(MixedFilamentViewModel* vm) {
//       m_addBtn->Bind(wxEVT_BUTTON, [vm](wxCommandEvent&) {
//           vm->addMix.execute();
//       });
//       m_deleteBtn->Bind(wxEVT_BUTTON, [vm](wxCommandEvent&) {
//           vm->deleteSelectedMix.execute();
//       });
//   }
//
// ============================================================
// Pattern 3: Coarse-grained Property design
// ============================================================
//
// DO NOT create a Property for every individual field.
// wxWidgets repaints the ENTIRE widget on each update.
//
// BAD:
//   Property<double> filamentDiameter;
//   Property<int>    nozzleTemp;
//   Property<int>    bedTemp;
//
// GOOD:
//   Property<std::vector<FilamentInfo>> filaments;  // single update
//
// ============================================================
// Pattern 4: Thread safety
// ============================================================
//
// Every Property subscriber MUST CallAfter() to dispatch to
// the main thread. This is the ONLY place thread safety matters.
//
//    vm.sliceProgress.subscribe([this](double pct, double) {
//        CallAfter([this, pct] {            // ? ALWAYS
//            m_gauge->SetValue((int)pct);
//        });
//    });
//
// ============================================================
// Pattern 5: Undo/Redo
// ============================================================
//
// The ViewModel owns the UndoRedoController. The View observes
// canUndo/canRedo Properties to enable/disable toolbar buttons.
//
//    vm.canUndo.subscribe([this](bool can, bool) {
//        CallAfter([this, can] { m_undoBtn->Enable(can); });
//    });
//
// ============================================================

#endif /* slic3r_App_ViewBindingGuide_hpp_ */
