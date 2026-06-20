#ifndef slic3r_App_MixedFilamentPanel_hpp_
#define slic3r_App_MixedFilamentPanel_hpp_

// ============================================================
// REAL View layer example: Mixed Filament wxPanel
// ============================================================
//
// This is a production-ready View that binds to
// MixedFilamentViewModel using the standard 5 binding patterns
// documented in ViewBindingGuide.hpp.
//
// Architecture:
//   MixedFilamentPanel (View)  ?Property?  MixedFilamentViewModel
//   - wxPanel subclass                       - pure C++ logic
//   - only layout + rendering               - knows nothing of wx
//
// This file compiles into the final binary.
// It demonstrates the exact pattern to follow for all panels.
// ============================================================

#include <wx/panel.h>
#include <wx/sizer.h>
#include <wx/scrolwin.h>
#include <wx/stattext.h>
#include <wx/button.h>
#include <wx/bitmap.h>

#include "slic3r/App/MixedFilamentViewModel.hpp"
#include "libslic3r/MVVP.hpp"

#include <vector>
#include <functional>

namespace Slic3r::GUI {

/// View: Mixed Filament panel in the Plater sidebar.
/// Subscribes to MixedFilamentViewModel::entries and renders rows.
/// ZERO knowledge of Print, PresetBundle, or model objects.
class MixedFilamentPanel : public wxPanel {
public:
    MixedFilamentPanel(wxWindow* parent);

    /// Bind this View to a ViewModel. Call once after construction.
    void bind(MixedFilamentViewModel* vm);

private:
    MixedFilamentViewModel* vm_{nullptr};

    // UI widgets (owned, never accessed by ViewModel)
    wxScrolledWindow* m_entryList{nullptr};
    wxBoxSizer*       m_entrySizer{nullptr};
    wxButton*         m_addBtn{nullptr};
    wxButton*         m_deleteBtn{nullptr};
    wxStaticText*     m_statusText{nullptr};

    // Active subscriptions (RAII - auto-unsubscribe on destruction)
    std::vector<MVVP::Property<std::vector<MixedFilamentViewModel::Entry>>::Subscription> m_subs;

    // ?? Binding helper (the ONLY bridge between MVVM and wx) ??
    template<typename T>
    void bindProperty(MVVP::Property<T>& prop,
                      std::function<void(const T&)> onChanged)
    {
        auto sub = prop.subscribe(
            [this, cb = std::move(onChanged)](const T& v, const T&) {
                // Rule: ALWAYS dispatch to main thread
                CallAfter([cb, v] { cb(v); });
            });
        m_subs.push_back(std::move(sub));
    }

    // ?? View update functions (called from Property subscriptions) ??
    void rebuildEntries(
        const std::vector<MixedFilamentViewModel::Entry>& entries);
    void updateButtons();
    void updateStatus();
};

// ============================================================
// IMPLEMENTATION
// ============================================================

inline MixedFilamentPanel::MixedFilamentPanel(wxWindow* parent)
    : wxPanel(parent, wxID_ANY)
{
    auto* mainSizer = new wxBoxSizer(wxVERTICAL);

    // ?? Header: title + add/delete buttons ??
    auto* headerSizer = new wxBoxSizer(wxHORIZONTAL);
    auto* title = new wxStaticText(this, wxID_ANY, _L("Mixed Filaments"));
    headerSizer->Add(title, 1, wxALIGN_CENTER);
    m_addBtn = new wxButton(this, wxID_ANY, _L("+"));
    m_deleteBtn = new wxButton(this, wxID_ANY, _L("-"));
    headerSizer->Add(m_addBtn, 0);
    headerSizer->Add(m_deleteBtn, 0);
    mainSizer->Add(headerSizer, 0, wxEXPAND | wxALL, 4);

    // ?? Entry list (scrollable) ??
    m_entryList = new wxScrolledWindow(this, wxID_ANY);
    m_entryList->SetScrollRate(0, 20);
    m_entrySizer = new wxBoxSizer(wxVERTICAL);
    m_entryList->SetSizer(m_entrySizer);
    mainSizer->Add(m_entryList, 1, wxEXPAND);

    // ?? Status bar ??
    m_statusText = new wxStaticText(this, wxID_ANY, "");
    mainSizer->Add(m_statusText, 0, wxEXPAND | wxALL, 2);

    SetSizer(mainSizer);
}

inline void MixedFilamentPanel::bind(MixedFilamentViewModel* vm)
{
    vm_ = vm;

    // ?? Property ? Widget bindings ??

    // entries change ? rebuild entire list
    bindProperty(vm_->entries,
        [this](const auto& entries) { rebuildEntries(entries); });

    // selectedIndex change ? highlight the right row
    bindProperty(vm_->selectedIndex,
        [this](int) { updateButtons(); });

    // hasMixedFilaments ? show/hide status text
    bindProperty(vm_->hasMixedFilaments,
        [this](bool has) {
            m_statusText->SetLabel(has ? "" : _L("No mixed filaments defined"));
            Layout();
        });

    // ?? Widget event ? Command bindings ??

    m_addBtn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        if (vm_) vm_->addMix.execute();
    });

    m_deleteBtn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        if (vm_) vm_->deleteSelectedMix.execute();
    });

    // Initial render
    rebuildEntries(vm_->entries.get());
    updateButtons();
}

inline void MixedFilamentPanel::rebuildEntries(
    const std::vector<MixedFilamentViewModel::Entry>& entries)
{
    // Clear old widgets
    m_entrySizer->Clear(true);

    for (size_t i = 0; i < entries.size(); ++i) {
        const auto& entry = entries[i];
        auto* row = new wxPanel(m_entryList, wxID_ANY);
        auto* rowSizer = new wxBoxSizer(wxHORIZONTAL);

        // Color swatch (12x12 panel with background fill)
        auto* swatch = new wxPanel(row, wxID_ANY,
            wxDefaultPosition, wxSize(12, 12));
        wxColour wxColor = wxColour(entry.displayColor);
        swatch->SetBackgroundColour(wxColor);
        rowSizer->Add(swatch, 0, wxALIGN_CENTER | wxRIGHT, 4);

        // Label
        auto* label = new wxStaticText(row, wxID_ANY, entry.label);
        if (entry.isSelected)
            label->SetFont(label->GetFont().Bold());
        rowSizer->Add(label, 1, wxALIGN_CENTER);

        // Click handler for selection
        row->Bind(wxEVT_LEFT_DOWN, [this, idx = entry.mixId](wxMouseEvent&) {
            if (vm_) vm_->setSelection(idx);
        });

        row->SetSizer(rowSizer);
        m_entrySizer->Add(row, 0, wxEXPAND | wxALL, 2);
    }

    m_entryList->FitInside();
    m_entryList->Layout();
    Layout();
    Refresh();
}

inline void MixedFilamentPanel::updateButtons()
{
    bool hasSelection = vm_ && vm_->selectedIndex.get() >= 0;
    m_deleteBtn->Enable(hasSelection);
}

inline void MixedFilamentPanel::updateStatus()
{
    auto& entries = vm_->entries.get();
    m_statusText->SetLabel(
        entries.empty() ? _L("No mixed filaments defined")
                        : wxString::Format(_L("%d mixed filament(s)"),
                                           static_cast<int>(entries.size())));
}

} // namespace Slic3r::GUI

#endif /* slic3r_App_MixedFilamentPanel_hpp_ */
