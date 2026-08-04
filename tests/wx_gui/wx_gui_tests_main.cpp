// PoC: validate that wxUIActionSimulator can drive a real wxDialog, with
// Catch2 v3 (Catch2::Catch2WithMain) owning main().
//
// STATUS (as of this commit):
//   - macOS (wxOSX/Cocoa): ENVIRONMENT WORKS but EVENTS DON'T DELIVER.
//     The plumbing (wxApp via wxIMPLEMENT_APP_NO_MAIN + wxEntryStart, modal
//     loop, dialog show) all succeeds, and wxTheApp->IsActive() is true. But
//     wxTextCtrl::SetFocus() never grants keyboard focus inside the modal loop
//     (a known wxOSX/Cocoa defect), so sim.Text()/MouseClick() events have no
//     target and the test FAILS. This is a wxWidgets-on-macOS limitation, not
//     an OrcaSlicer issue — see the INFO diagnostics in the test output.
//
//   - Windows (wxMSW): UNVERIFIED — the primary target for this PoC.
//     wxMSW's SetFocus() maps to the reliable Win32 focus model, and
//     wxUIActionSimulator uses keybd_event()/mouse_event() (real input stream)
//     rather than macOS's CGEventPost-to-session-tap. Focus is expected to
//     work here. Run this test on Windows to confirm.
//
// What this proves (if green on Windows):
//   1. wxApp can be initialized WITHOUT taking over main() (via
//      wxIMPLEMENT_APP_NO_MAIN + wxEntryStart), coexisting with Catch2's main.
//   2. wxUIActionSimulator actually delivers events to a real wxDialog.
//   3. The CMake plumbing (wx headers + libslic3r_gui link) is correct.
//
// How to run (NOT headless-safe — needs an interactive desktop session):
//   cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
//         -DSLIC3R_GUI=ON -DBUILD_TESTS=ON <prefix-path & policy flags>
//   cmake --build build --target wx_gui_tests
//   build/tests/wx_gui/wx_gui_tests "wxUIActionSimulator echoes text on button click"

#include <catch_main.hpp>

#include <wx/wx.h>
#include <wx/evtloop.h>
#include <wx/uiaction.h>

#include <chrono>
#include <thread>

// ---------------------------------------------------------------------------
// (1) wxApp: derived class registered via NO_MAIN (does NOT define main(),
//     which Catch2::Catch2WithMain already owns). wxEntryStart will instantiate
//     this class as wxTheApp.
// ---------------------------------------------------------------------------
class PoCApp : public wxApp
{
public:
    bool OnInit() override
    {
        // Return true so wx considers the app initialized. We do NOT create a
        // top-level window here — each test creates its own dialog.
        return true;
    }
};
wxIMPLEMENT_APP_NO_MAIN(PoCApp);

// ---------------------------------------------------------------------------
// (2) One-shot wx initialization for the whole test process.
//     wxEntryStart creates wxTheApp (running PoCApp::OnInit). It is NOT
//     idempotent after wxEntryCleanup, so we gate it on a static flag and only
//     clean up never (process exit will reclaim everything). wxInitialize()
//     alone is insufficient — it does not create a GUI wxApp / Cocoa event
//     loop, which wxUIActionSimulator's macOS backend requires.
// ---------------------------------------------------------------------------
static bool ensure_wx_initialized()
{
    static bool s_tried = false;
    static bool s_ok    = false;
    if (s_tried) return s_ok;
    s_tried = true;

    static int         argc = 1;
    static char        arg0[] = "wx_gui_tests";
    static char*       argv[] = {arg0, nullptr};
    s_ok = wxEntryStart(argc, argv);
    return s_ok;
}

// Small helper: pump the event loop for up to ~ms milliseconds so CGEventPost
// events get routed into the native queue and dispatched to handlers. macOS's
// wxUIActionSimulator sets shouldWaitForEvent which blocks DispatchTimeout up
// to 1s waiting for the synthesized event; a plain wxYield() is usually enough
// but we add a tiny sleep as a safety margin for cross-process event delivery.
static void pump_events(int ms = 50)
{
    wxYield();
    if (ms > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(ms));
        wxYield();
    }
}

// ---------------------------------------------------------------------------
// (3) The dialog under test: a TextCtrl + an "Echo" button + a StaticText.
//     Clicking the button (wxEVT_BUTTON) copies the TextCtrl value into the
//     StaticText. This is the simplest possible "user interaction → observable
//     state change" loop to exercise with the simulator.
//
// On macOS, wx focus management only works while a modal event loop is running
// (ShowModal). A non-modal Show() leaves SetFocus() ineffective, so the
// synthesized keyboard/mouse events have no target. We therefore run the
// simulator INSIDE the modal loop, scheduled via CallAfter, and capture the
// observable result in m_result before calling EndModal.
// ---------------------------------------------------------------------------
class EchoDialog : public wxDialog
{
public:
    wxTextCtrl*   m_input = nullptr;
    wxButton*     m_btn   = nullptr;
    wxStaticText* m_echo  = nullptr;

    // Populated by the in-modal simulation step, read by the test after EndModal.
    wxString m_input_after_text;
    wxString m_echo_after_click;
    bool     m_textctrl_had_focus = false;

    EchoDialog()
        : wxDialog(nullptr, wxID_ANY, "wxUIActionSimulator PoC",
                   wxDefaultPosition, wxDefaultSize,
                   wxCAPTION | wxSYSTEM_MENU)
    {
        auto* sizer = new wxBoxSizer(wxVERTICAL);
        m_input = new wxTextCtrl(this, wxID_ANY, wxEmptyString, wxDefaultPosition, wxSize(200, wxDefaultCoord));
        m_btn   = new wxButton(this, wxID_ANY, "Echo");
        m_echo  = new wxStaticText(this, wxID_ANY, "(empty)", wxDefaultPosition, wxSize(200, wxDefaultCoord));

        sizer->Add(m_input, 0, wxALL | wxEXPAND, 10);
        sizer->Add(m_btn, 0, wxALL | wxALIGN_CENTER, 10);
        sizer->Add(m_echo, 0, wxALL | wxEXPAND, 10);
        SetSizerAndFit(sizer);

        m_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
            m_echo->SetLabelText(m_input->GetValue());
        });

        Centre(wxBOTH);
    }

    // Drive the simulator from inside the modal loop. CallAfter queues this on
    // the modal event loop, so by the time it runs the dialog is shown, mapped,
    // and has working focus management.
    void run_simulation(wxUIActionSimulator& sim)
    {
        CallAfter([this, &sim]() {
            // --- typing test ---
            m_input->SetFocus();
            wxYield();
            m_textctrl_had_focus = m_input->HasFocus();
            sim.Text("hello");
            // pump within the modal loop so CGEventPost events get dispatched
            for (int i = 0; i < 10 && m_input->GetValue() != "hello"; ++i) {
                wxYield();
                std::this_thread::sleep_for(std::chrono::milliseconds(30));
            }
            m_input_after_text = m_input->GetValue();

            // --- click test ---
            // Seed the input, then click the button by coordinates.
            m_input->SetValue("world");
            wxYield();
            // Click at the button's screen center.
            wxRect br = m_btn->GetScreenRect();
            wxUIActionSimulator msim;
            msim.MouseMove(wxPoint(br.x + br.width / 2, br.y + br.height / 2));
            wxYield();
            msim.MouseClick();
            for (int i = 0; i < 10 && m_echo->GetLabelText() != "world"; ++i) {
                wxYield();
                std::this_thread::sleep_for(std::chrono::milliseconds(30));
            }
            m_echo_after_click = m_echo->GetLabelText();

            EndModal(wxID_OK);
        });
    }
};

// ---------------------------------------------------------------------------
// (4) The test itself.
//     Strategy: show the dialog modally (which runs a proper event loop and
//     enables wx focus management on macOS), schedule the simulation via
//     CallAfter so it executes inside that modal loop, capture observable
//     results on the dialog, then EndModal. Assertions run after the modal
//     loop returns.
// ---------------------------------------------------------------------------
TEST_CASE("wxUIActionSimulator echoes text on button click", "[gui]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;

    wxUIActionSimulator sim;
    dlg.run_simulation(sim);

    // ShowModal runs the modal event loop; run_simulation's CallAfter fires
    // inside it, drives the simulator, and calls EndModal to return here.
    dlg.ShowModal();

    // ---- assertions (after the modal loop + simulation completed) ----
    INFO("TextCtrl had focus inside modal loop = " << (dlg.m_textctrl_had_focus ? "true" : "false"));
    CHECK(dlg.m_textctrl_had_focus);

    INFO("TextCtrl value after sim.Text(\"hello\") = \"" << dlg.m_input_after_text << "\"");
    CHECK(dlg.m_input_after_text == "hello");

    INFO("Echo label after sim.MouseClick on button = \"" << dlg.m_echo_after_click << "\"");
    CHECK(dlg.m_echo_after_click == "world");
}
