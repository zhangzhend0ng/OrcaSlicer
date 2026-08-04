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
//   - Windows (wxMSW): VALIDATED (route A works). Two environment requirements:
//       1. No remote-control/mirroring layer intercepting session input. This
//          machine runs NetEase GameViewer (with a "GameViewer Virtual Display
//          Adapter"); while it is active, synthetic input injection
//          (keybd_event/SendInput/mouse_event) is suppressed — the test must be
//          run with GameViewer fully stopped (service included).
//       2. A non-IME keyboard layout must be active for the thread during
//          sim.Text(). The default zh-CN layout uses the Microsoft Pinyin IME,
//          which INTERCEPTS synthesized keystrokes and composes CJK characters
//          (e.g. VK 'A' -> "奶") instead of the literal 'A'. ScopedUsKeyboard-
//          Layout (below) activates US English (0x0409) for the thread around
//          the sim call, after which sim.Text("hello") and sim.MouseClick()
//          both deliver correctly: focus=PASS, text=PASS, echo=PASS
//          (deterministic across runs). Mouse clicks are not IME-affected.
//
// What this proves (if green on a clean Windows console):
//   1. wxApp can be initialized WITHOUT taking over main() (via
//      wxIMPLEMENT_APP_NO_MAIN + wxEntryStart), coexisting with Catch2's main.
//   2. wxUIActionSimulator actually delivers events to a real wxWindow.
//   3. The CMake plumbing (wx headers + libslic3r_gui link) is correct.
//
// How to run (NOT headless-safe — needs an interactive desktop session with
// NO remote-display/remote-control layer intercepting input):
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
#include <sstream>
#include <string>

#ifdef __WXMSW__
    #include <wx/msw/wrapwin.h> // HWND, GetForegroundWindow, GetFocus, AttachThreadInput
#endif

// ---------------------------------------------------------------------------
// Win32 input-target diagnostics (Windows-only).
//
// wxUIActionSimulator's wxMSW backend injects keystrokes/mouse events via
// keybd_event()/mouse_event() into the OS input stream. Those events are
// routed to the thread that owns the FOREGROUND window, and keystrokes are
// delivered to the window with Win32 keyboard focus (GetFocus()). If the
// foreground window is the console host (this test is a CONSOLE-subsystem exe
// launched from a shell), the injected events never reach our dialog — even
// though wxWindow::HasFocus() may report true.
//
// These helpers capture, at the moment the simulator runs, the Win32
// foreground window, the Win32 focus window, and whether they match the
// dialog / TextCtrl HWNDs. The captured strings surface as INFO diagnostics so
// a single run settles whether the failure is "wrong foreground target"
// (route-A needs a foreground/AttachThreadInput fix) vs something else.
// ---------------------------------------------------------------------------
#ifdef __WXMSW__
static std::string hwnd_str(HWND h)
{
    // Compact, readable handle rendering for diagnostics (avoid %p variance).
    std::ostringstream os;
    if (h == nullptr) { os << "NULL"; return os.str(); }
    os << "0x" << std::hex << reinterpret_cast<uintptr_t>(h);
    return os.str();
}

// RAII guard that activates a non-IME keyboard layout (US English, 0x0409) for
// the current thread for its lifetime, then restores the previous layout and
// unloads the US layout. On zh-CN systems the Microsoft Pinyin IME is active by
// default and INTERCEPTS synthesized keystrokes — sim.Text('A') gets composed
// into a CJK character (e.g. "奶") instead of producing the literal 'A'. With
// a non-IME layout active, keybd_event('A') yields the literal WM_CHAR 'a'.
// This makes wxUIActionSimulator's keyboard path usable for ASCII text.
class ScopedUsKeyboardLayout
{
public:
    ScopedUsKeyboardLayout()
    {
        m_hUs   = ::LoadKeyboardLayoutW(L"00000409", KLF_NOTELLSHELL | KLF_SUBSTITUTE_OK);
        m_hPrev = m_hUs ? ::ActivateKeyboardLayout(m_hUs, 0) : nullptr;
    }
    ~ScopedUsKeyboardLayout()
    {
        if (m_hPrev) ::ActivateKeyboardLayout(m_hPrev, 0);
        if (m_hUs)   ::UnloadKeyboardLayout(m_hUs);
    }
private:
    HKL m_hUs   = nullptr;
    HKL m_hPrev = nullptr;
};
#endif

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
//     wxEntryStart calls wxApp::Initialize() + common post-init, creating
//     wxTheApp (our PoCApp). NOTE: unlike wxEntry, wxEntryStart does NOT run
//     OnInit() or the main message loop (OnRun) — we keep wx alive for the
//     whole process and rely on per-test modal loops / wxYield() to pump
//     events. It is NOT idempotent after wxEntryCleanup, so we gate it on a
//     static flag and never clean up (process exit reclaims everything).
//     wxInitialize() alone is insufficient — it does not create a GUI wxApp /
//     Cocoa event loop, which wxUIActionSimulator's macOS backend requires.
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

// Small helper: pump the event loop for up to ~ms milliseconds so injected
// input events get retrieved from the native queue and dispatched to handlers.
//   - On wxMSW the backend uses keybd_event()/mouse_event() (no shouldWait);
//     a single wxYield() after the sim call is the canonical pattern, the loop
//     just adds a safety margin for slower dispatch.
//   - On wxOSX the backend posts via CGEventPost and sets shouldWaitForEvent,
//     which can block DispatchTimeout up to ~1s; the sleep margin helps there.
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

    // Win32 input-target diagnostics, captured at the moment sim.Text() runs.
    // Surfaced via INFO() lines so one run settles the failure cause.
    std::string m_diag_foreground;   // GetForegroundWindow() at sim time
    std::string m_diag_focus;        // GetFocus() at sim time
    std::string m_diag_dialog_hwnd;  // this dialog's HWND
    std::string m_diag_textctrl_hwnd;// TextCtrl's HWND
    bool        m_diag_fg_is_dialog = false;     // foreground == dialog HWND?
    bool        m_diag_focus_is_textctrl = false; // Win32 focus == TextCtrl HWND?
    bool        m_used_attach_thread_input = false; // did we apply the foreground fix?

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
#ifdef __WXMSW__
            // --- Win32 input-target diagnostics + foreground acquisition ---
            // keybd_event()/mouse_event() deliver to the foreground thread's
            // message queue; if the foreground window is the console host (we
            // are a CONSOLE-subsystem exe), events never reach us. Capture the
            // ground truth, then try to make ourselves foreground via
            // AttachThreadInput (shares the input state with whoever currently
            // has foreground, which lets SetForegroundWindow succeed).
            HWND hDlg = static_cast<HWND>(GetHWND());
            HWND hTxt = static_cast<HWND>(m_input->GetHWND());
            m_diag_dialog_hwnd   = hwnd_str(hDlg);
            m_diag_textctrl_hwnd = hwnd_str(hTxt);

            m_input->SetFocus();
            wxYield(); // let WM_FOCUS messages settle

            HWND hFg   = ::GetForegroundWindow();
            HWND hFocs = ::GetFocus();
            m_diag_foreground = hwnd_str(hFg);
            m_diag_focus      = hwnd_str(hFocs);
            m_diag_fg_is_dialog       = (hFg == hDlg);
            m_diag_focus_is_textctrl  = (hFocs == hTxt);

            // Attempt foreground acquisition: attach our input state to the
            // current foreground thread, raise ourselves, detach. This is the
            // standard workaround when SetForegroundWindow alone would just
            // flash the taskbar (foreground lock). Cheap and reversible.
            DWORD  fgPid     = 0;
            DWORD  fgTid     = ::GetWindowThreadProcessId(hFg, &fgPid);
            DWORD  ourTid    = ::GetCurrentThreadId();
            bool   attached  = ::AttachThreadInput(ourTid, fgTid, TRUE);
            m_used_attach_thread_input = attached;
            ::SetForegroundWindow(hDlg);
            ::SetFocus(hTxt);
            if (attached)
                ::AttachThreadInput(ourTid, fgTid, FALSE);
            wxYield(); // let activation/focus changes propagate

            // Re-read foreground/focus after the acquisition attempt.
            hFg   = ::GetForegroundWindow();
            hFocs = ::GetFocus();
            m_diag_foreground        = hwnd_str(hFg);
            m_diag_focus             = hwnd_str(hFocs);
            m_diag_fg_is_dialog      = (hFg == hDlg);
            m_diag_focus_is_textctrl = (hFocs == hTxt);
#endif

            // --- typing test ---
            m_input->SetFocus();
            wxYield();
            m_textctrl_had_focus = m_input->HasFocus();
#ifdef __WXMSW__
            // Activate a non-IME layout so synthesized ASCII keystrokes are not
            // composed into CJK by the active Microsoft Pinyin IME.
            ScopedUsKeyboardLayout usLayout;
#endif
            sim.Text("hello");
            // Pump the modal loop so the injected keybd_event() messages get
            // retrieved and dispatched (single wxYield() is the canonical wx
            // pattern; the loop adds margin for slower dispatch).
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

#ifdef __WXMSW__
    // Diagnostics that settle WHY events do/don't arrive. If foreground !=
    // dialog HWND at sim time, the injected keybd_event()/mouse_event() stream
    // is routed to the console host (or some other window) and never reaches
    // the TextCtrl — that is the real failure mode for a CONSOLE-subsystem
    // test exe, and it is independent of wx focus management.
    INFO("[diag] dialog HWND=" << dlg.m_diag_dialog_hwnd
         << " TextCtrl HWND=" << dlg.m_diag_textctrl_hwnd
         << " | Win32 foreground=" << dlg.m_diag_foreground
         << " (isDialog=" << (dlg.m_diag_fg_is_dialog ? "yes" : "no") << ")"
         << " | Win32 focus=" << dlg.m_diag_focus
         << " (isTextCtrl=" << (dlg.m_diag_focus_is_textctrl ? "yes" : "no") << ")"
         << " | AttachThreadInput applied=" << (dlg.m_used_attach_thread_input ? "yes" : "no"));
#endif

    INFO("TextCtrl value after sim.Text(\"hello\") = \"" << dlg.m_input_after_text << "\"");
    CHECK(dlg.m_input_after_text == "hello");

    INFO("Echo label after sim.MouseClick on button = \"" << dlg.m_echo_after_click << "\"");
    CHECK(dlg.m_echo_after_click == "world");
}

// ---------------------------------------------------------------------------
// (5) Variant: NON-MODAL top-level frame, simulator driven DIRECTLY (no
//     ShowModal, no CallAfter). This is the canonical wxWidgets test pattern
//     (see tests/controls/textctrltest.cpp and tests/validators/valnum.cpp in
//     the wxWidgets tree): the control is a child of a shown top-level window
//     and the sim is driven from the test thread with a single wxYield() per
//     action. It isolates whether the modal+CallAfter structure (vs foreground
//     vs focus) is what blocks event delivery on wxMSW.
// ---------------------------------------------------------------------------
TEST_CASE("wxUIActionSimulator drives non-modal frame directly", "[gui]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    wxFrame frame(nullptr, wxID_ANY, "wxUIActionSimulator non-modal");
    auto* input = new wxTextCtrl(&frame, wxID_ANY, wxEmptyString,
                                 wxDefaultPosition, wxSize(200, wxDefaultCoord));
    auto* btn   = new wxButton(&frame, wxID_ANY, "Echo");
    auto* echo  = new wxStaticText(&frame, wxID_ANY, "(empty)",
                                   wxDefaultPosition, wxSize(200, wxDefaultCoord));
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(input, 0, wxALL | wxEXPAND, 10);
    sizer->Add(btn, 0, wxALL | wxALIGN_CENTER, 10);
    sizer->Add(echo, 0, wxALL | wxEXPAND, 10);
    frame.SetSizerAndFit(sizer);
    frame.Centre(wxBOTH);

    bool clicked = false;
    btn->Bind(wxEVT_BUTTON, [&](wxCommandEvent&) {
        echo->SetLabelText(input->GetValue());
        clicked = true;
    });

    frame.Show();
    frame.Raise();

    // Give the window manager a moment to make the frame foreground + mapped.
    pump_events(100);

#ifdef __WXMSW__
    HWND hFrame = static_cast<HWND>(frame.GetHWND());
    HWND hTxt   = static_cast<HWND>(input->GetHWND());
    HWND hFg    = ::GetForegroundWindow();
    INFO("[diag2] frame HWND=" << hwnd_str(hFrame) << " TextCtrl HWND=" << hwnd_str(hTxt)
         << " | Win32 foreground=" << hwnd_str(hFg)
         << " (isFrame=" << ((hFg == hFrame) ? "yes" : "no") << ")");
#endif

    // --- typing: canonical pattern, single yield after sim.Text ---
    input->SetFocus();
    pump_events(30);
    const bool had_focus = input->HasFocus();

#ifdef __WXMSW__
    ScopedUsKeyboardLayout usLayout;
#endif
    wxUIActionSimulator sim;
    sim.Text("hello");
    pump_events(150); // canonical uses a single wxYield(); the slack aids dispatch

    const wxString input_after = input->GetValue();

    // --- click: canonical pattern ---
    input->SetValue("world");
    pump_events(30);
    wxRect br = btn->GetScreenRect();
    sim.MouseMove(wxPoint(br.x + br.width / 2, br.y + br.height / 2));
    pump_events(30);
    sim.MouseClick();
    pump_events(150);

    const wxString echo_after = echo->GetLabelText();

    frame.Show(false);
    frame.Destroy();

    INFO("TextCtrl had focus (non-modal frame) = " << (had_focus ? "true" : "false"));
    CHECK(had_focus);

    INFO("TextCtrl value after sim.Text(\"hello\") [non-modal] = \"" << input_after << "\"");
    CHECK(input_after == "hello");

    INFO("Echo label after sim.MouseClick [non-modal] = \"" << echo_after << "\"");
    CHECK(echo_after == "world");
}

// ---------------------------------------------------------------------------
// (6) Raw probe (Windows-only, throwaway diagnostic): bypass wxUIActionSimulator
//     and call keybd_event() directly on a focused, foreground wxTextCtrl, then
//     run a native PeekMessage/TranslateMessage/DispatchMessage loop. Reports
//     whether the OS accepted the inject (GetAsyncKeyState) and how many
//     WM_KEYDOWN/WM_CHAR were actually retrieved. This isolates OS-level input
//     injection from the wxUIActionSimulator abstraction.
// ---------------------------------------------------------------------------
#ifdef __WXMSW__
TEST_CASE("raw keybd_event reaches focused TextCtrl", "[gui][rawprobe]")
{
    REQUIRE(ensure_wx_initialized());

    wxFrame frame(nullptr, wxID_ANY, "raw keybd_event probe");
    auto* input = new wxTextCtrl(&frame, wxID_ANY, wxEmptyString,
                                 wxDefaultPosition, wxSize(200, wxDefaultCoord));
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(input, 0, wxALL | wxEXPAND, 10);
    frame.SetSizerAndFit(sizer);
    frame.Show();
    frame.Raise();
    pump_events(100);

    HWND hTxt = static_cast<HWND>(input->GetHWND());
    input->SetFocus();
    pump_events(50);
    HWND hFocusBefore = ::GetFocus();
    HWND hFgAfter     = ::GetForegroundWindow();

    ::keybd_event(0x41, 0, 0, 0);                       // WM_KEYDOWN 'A'
    const short asyncDown = ::GetAsyncKeyState(0x41);
    const bool  injectedAccepted = (asyncDown & 0x8000) != 0;
    ::keybd_event(0x41, 0, KEYEVENTF_KEYUP, 0);          // WM_KEYUP   'A'

    int nKey = 0, nChar = 0;
    for (int i = 0; i < 200; ++i) {
        MSG msg;
        while (::PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_KEYDOWN || msg.message == WM_KEYUP) nKey++;
            if (msg.message == WM_CHAR) nChar++;
            ::TranslateMessage(&msg);
            ::DispatchMessage(&msg);
        }
        if (nChar > 0) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    const wxString after = input->GetValue();

    INFO("[rawprobe] frame HWND=" << hwnd_str(static_cast<HWND>(frame.GetHWND()))
         << " TextCtrl HWND=" << hwnd_str(hTxt)
         << " | fg after focus=" << hwnd_str(hFgAfter)
         << " (isFrame=" << ((hFgAfter == static_cast<HWND>(frame.GetHWND())) ? "yes" : "no") << ")"
         << " | Win32 focus=" << hwnd_str(hFocusBefore)
         << " (isTextCtrl=" << ((hFocusBefore == hTxt) ? "yes" : "no") << ")"
         << " | GetAsyncKeyState('A')=0x" << std::hex << (static_cast<unsigned short>(asyncDown))
         << " (injectedAccepted=" << (injectedAccepted ? "yes" : "no") << ")"
         << " | raw PeekMessage retrieved: WM_KEYDOWN/UP=" << std::dec << nKey
         << " WM_CHAR=" << nChar << ")");
    INFO("TextCtrl value after raw keybd_event('A') = \"" << after << "\"");

    frame.Show(false);
    frame.Destroy();

    CHECK(after == "A");
}

// Variant: with IME bypassed. The Chinese IME (active on zh-CN systems)
// intercepts synthesized keystrokes and composes CJK characters instead of
// passing the literal VK through. Activate a non-IME layout (US English,
// 0x0409) for the thread before injecting, so WM_CHAR carries the literal 'A'.
TEST_CASE("raw keybd_event with US layout bypasses IME", "[gui][rawprobe2]")
{
    REQUIRE(ensure_wx_initialized());

    wxFrame frame(nullptr, wxID_ANY, "raw keybd_event IME bypass");
    auto* input = new wxTextCtrl(&frame, wxID_ANY, wxEmptyString,
                                 wxDefaultPosition, wxSize(200, wxDefaultCoord));
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(input, 0, wxALL | wxEXPAND, 10);
    frame.SetSizerAndFit(sizer);
    frame.Show();
    frame.Raise();
    pump_events(100);

    // Load + activate US English layout for THIS thread only (KLF_NOTELLSHELL:
    // don't broadcast; this won't disturb the user's shell layout).
    HKL hUs   = ::LoadKeyboardLayoutW(L"00000409", KLF_NOTELLSHELL | KLF_SUBSTITUTE_OK);
    HKL hPrev = ::ActivateKeyboardLayout(hUs, 0);

    HWND hTxt = static_cast<HWND>(input->GetHWND());
    input->SetFocus();
    pump_events(50);

    ::keybd_event(0x41, 0, 0, 0);
    ::keybd_event(0x41, 0, KEYEVENTF_KEYUP, 0);

    int nChar = 0;
    for (int i = 0; i < 200; ++i) {
        MSG msg;
        while (::PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_CHAR) nChar++;
            ::TranslateMessage(&msg);
            ::DispatchMessage(&msg);
        }
        if (nChar > 0) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }

    const wxString after = input->GetValue();

    // Restore prior layout + unload US layout so we leave the system clean.
    if (hPrev) ::ActivateKeyboardLayout(hPrev, 0);
    if (hUs)   ::UnloadKeyboardLayout(hUs);

    frame.Show(false);
    frame.Destroy();

    INFO("[rawprobe2] US layout activated, WM_CHAR count=" << nChar
         << " | TextCtrl value = \"" << after << "\"");
    CHECK(after == "A");
}
#endif
