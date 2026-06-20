#ifndef slic3r_App_EndToEndWiringExample_hpp_
#define slic3r_App_EndToEndWiringExample_hpp_

// ============================================================
// END-TO-END WIRING EXAMPLE: Plater MixFilament Panel
// ============================================================
//
// This demonstrates the complete migration of Plater.cpp's
// mixed filament computation from inline lambdas to MVVM.
//
// REAL CALL SITE in Plater.cpp (~line 6425):
//
//   auto decode_manual_pattern_ids = [num_physical](const std::string &pattern,
//                                                     unsigned int       component_a,
//                                                     unsigned int       component_b,
//                                                     size_t             wall_loops) {
//       return build_grouped_manual_pattern_preview_sequence(
//           pattern, component_a, component_b, num_physical, wall_loops);
//   };
//
// AFTER MIGRATION (Plater::priv::update_color_mix_panel):
// ============================================================

#ifdef ORCA_REFACTOR_V2

// In Plater.hpp, add to priv:
//   #include "slic3r/App/PlaterAdapters.hpp"
//   PlaterAdapters m_adapters;

#include "slic3r/App/PlaterAdapters.hpp"
#include "slic3r/App/MixedFilamentViewModel.hpp"

// === STEP 1: Replace inline lambda with ViewModel method ===
//
// OLD:
//   auto decode_manual_pattern_ids = [num_physical](...) {
//       return build_grouped_manual_pattern_preview_sequence(...);
//   };
//
// NEW:
//   // No lambda needed. Call adapter directly:
//   auto seq = m_adapters.buildMixedPreviewSequence(
//       makeMixedFilament(a, b), num_physical, wall_loops);

// === STEP 2: Replace blend_display_color_from_sequence ===
//
// OLD:
//   std::string blended = blend_display_color_from_sequence(colors, sequence);
//
// NEW:
//   std::string blended = m_adapters.blendMixedColor(colors, sequence);

// === STEP 3: Bind ViewModel output to wxPanel widgets ===
//
// In the panel initialization (Plater::priv constructor or init method):
//
//   m_adapters.mixedFilament.entries.subscribe(
//       [this](const std::vector<MixedFilamentViewModel::Entry>& entries,
//              const std::vector<MixedFilamentViewModel::Entry>& old) {
//           // ALWAYS dispatch to main thread
//           CallAfter([this, entries] {
//               rebuildMixedFilamentPanel(entries);
//           });
//       });
//
//   m_adapters.mixedFilament.selectedIndex.subscribe(
//       [this](int idx, int oldIdx) {
//           CallAfter([this, idx] {
//               highlightSelectedRow(idx);
//           });
//       });

// === STEP 4: The rebuild function ===
//
//   void rebuildMixedFilamentPanel(
//       const std::vector<MixedFilamentViewModel::Entry>& entries)
//   {
//       // Clear old widgets
//       m_color_mix_sizer->Clear(true);
//
//       for (const auto& entry : entries) {
//           auto* row = new wxPanel(m_color_mix_panel);
//           auto* rowSizer = new wxBoxSizer(wxHORIZONTAL);
//
//           // Color swatch (12x12 wxPanel with background color)
//           auto* swatch = new wxPanel(row, wxID_ANY,
//               wxDefaultPosition, wxSize(12, 12));
//           wxColor wxColor = parseHexColor(entry.displayColor);
//           swatch->SetBackgroundColour(wxColor);
//           rowSizer->Add(swatch, 0, wxALIGN_CENTER | wxRIGHT, 4);
//
//           // Label ("F1+F2+F3")
//           auto* label = new wxStaticText(row, wxID_ANY, entry.label);
//           rowSizer->Add(label, 1, wxALIGN_CENTER);
//
//           // Three-dot menu button
//           auto* menuBtn = new ScalableButton(row, wxID_ANY, "menu_filament");
//           menuBtn->Bind(wxEVT_BUTTON, [this, idx = entry.mixId](wxCommandEvent&) {
//               m_adapters.mixedFilament.setSelection(idx);
//               showMixedFilamentMenu(idx);
//           });
//           rowSizer->Add(menuBtn, 0);
//
//           row->SetSizer(rowSizer);
//           m_color_mix_sizer->Add(row, 0, wxEXPAND | wxALL, 2);
//       }
//
//       m_color_mix_panel->Layout();
//       m_color_mix_panel->Refresh();
//   }

// === STEP 5: Handle add/delete via Commands ===
//
//   m_add_mix_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
//       m_adapters.mixedFilament.addMix.execute();
//   });
//
//   m_delete_mix_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
//       m_adapters.mixedFilament.deleteSelectedMix.execute();
//   });

// === STEP 6: Sync from Plater data to ViewModel ===
//
// Called whenever physical filaments or mixed config changes:
//
//   void syncToViewModel() {
//       std::vector<std::string> colors;
//       std::vector<double> nozzles;
//       for (int i = 0; i < num_physical; ++i) {
//           colors.push_back(get_filament_color_hex(i));
//           nozzles.push_back(get_nozzle_diameter(i));
//       }
//       m_adapters.syncMixedFilaments(colors, nozzles,
//           wxGetApp().preset_bundle->mixed_filaments.get_all());
//   }

// ============================================================
// RESULT:
//   - 13 static functions removed from Plater.cpp
//   - ~500 lines of inline computation replaced by ViewModel calls
//   - Mixed filament logic is independently testable
//   - wxPanel only handles layout + rendering
//   - ViewModel can be tested without opening a window
// ============================================================

#endif // ORCA_REFACTOR_V2

#endif /* slic3r_App_EndToEndWiringExample_hpp_ */
