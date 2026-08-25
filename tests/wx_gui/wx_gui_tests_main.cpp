// Stable smoke tests: wxUIActionSimulator (OS-level input injection) plus the
// event-layer (ProcessEvent) equivalents. Catch2 v3 (Catch2::Catch2WithMain)
// owns main(); wxApp is initialized via wxIMPLEMENT_APP_NO_MAIN + wxEntryStart.
//
// STATUS (as of this commit):
//   - Windows (wxMSW): Route A VALIDATED — focus/text/echo PASS deterministically
//     on a clean interactive session. The two environment hazards found during
//     the investigation are now checked at RUNTIME (the simulator tests SKIP
//     with the reason + recovery steps instead of failing):
//       1. Remote-control/mirroring layer (NetEase GameViewer "Virtual Display
//          Adapter" on this machine): suppresses synthetic input
//          (keybd_event/SendInput/mouse_event) — tests SKIP until it is fully
//          stopped (service included).
//       2. zh-CN Microsoft Pinyin IME composes synthesized keystrokes into CJK
//          characters (VK 'A' -> "奶"); ScopedUsKeyboardLayout activates US
//          English (0x0409) for the thread around sim.Text(). If the US layout
//          is not installed the tests SKIP with install instructions.
//   - macOS (wxOSX/Cocoa): SKIPPED by design — wxTextCtrl::SetFocus() never
//     grants keyboard focus inside the modal loop, so synthetic events have no
//     target (a wxWidgets platform defect, not an OrcaSlicer issue). See
//     tests/wx_gui/ADVERSARIAL_LOOP_JOURNAL.md for the full conclusion.
//
// Layering (agreed): three injection tiers, from most to least environment-
// dependent:
//   1. ProcessEvent — in-process event dispatch. The daily batch path: no
//      foreground window, no mouse grabbing, immune to IME and remote-control
//      layers. Headless-safe.
//   2. Win32MessageSimulator (Windows) — sent WM_* messages through the
//      NATIVE window procedure (standard controls process them exactly like
//      real input). Works even while a remote-control layer is running (the
//      low-level hooks never see sent messages), needs no foreground/focus,
//      bypasses IME. See section (0c).
//   3. wxUIActionSimulator — true OS-level injection through the input
//      pipeline; reserved for a handful of clean-session smoke tests.
// The "event injection" tests below are the canonical shape for tier 1.
//
// How to run (simulator tests are NOT headless-safe — they need an interactive
// desktop session with no remote-display layer intercepting input):
//   cmake --build build --target wx_gui_tests
//   build/tests/wx_gui/wx_gui_tests "[gui]"

#include <catch_main.hpp>

#include <wx/wx.h>
#include <wx/evtloop.h>
#include <wx/uiaction.h>

#include "libslic3r/Utils.hpp" // Slic3r::set_data_dir / set_var_dir / resources_dir

#include <boost/filesystem.hpp> // path join for var_dir

#if defined(ORCA_FULL_GUI_APP)
    #include "slic3r/GUI/GUI_App.hpp"  // wxGetApp(), GUI_App
    #include "slic3r/GUI/GUI_Init.hpp" // GUI_InitParams
#endif

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <functional>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#ifdef __WXMSW__
    #include <wx/msw/wrapwin.h> // HWND, GetForegroundWindow, GetFocus, AttachThreadInput
    #include <winsvc.h>         // OpenSCManager/EnumServicesStatusEx for remote-control scan
#endif

// ---------------------------------------------------------------------------
// (0) Win32 input-target diagnostics (Windows-only).
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
// (0b) RUNTIME environment prerequisites for OS-level input injection.
//
// The simulator posts events through the OS input stream, so it only works in
// an interactive session with no remote-control layer intercepting input and
// (on zh-CN Windows) a non-IME keyboard layout it can activate. These were
// previously documented in comments only; now they are checked at runtime and
// the tests SKIP with the reason + recovery steps when the environment cannot
// deliver. Returns a non-empty reason string when the environment is unusable.
// ---------------------------------------------------------------------------
#ifdef __WXMSW__
static std::string windows_sim_env_problem()
{
    // --- 1. remote-control / mirroring layer present? ---
    // NetEase GameViewer (and similar session-level remote-control tools)
    // suppress keybd_event()/SendInput()/mouse_event() from processes in the
    // session: the inject is accepted into the global key state but never
    // queued for retrieval (see ADVERSARIAL_LOOP_JOURNAL.md, iteration 1,
    // shape T3 — the settled root cause). Scan display-adapter names and
    // running services for the known tools.
    static const wchar_t* const kKnownAdapterMarkers[] = {
        L"gameviewer", L"teamviewer", L"anydesk", L"sunlogin",
        L"todesk", L"awesun", L"parsec", L"vnc",
    };
    DISPLAY_DEVICEW dd;
    dd.cb = sizeof(dd);
    for (DWORD i = 0; EnumDisplayDevicesW(nullptr, i, &dd, 0); ++i) {
        wxString name(dd.DeviceString);
        name.MakeLower();
        for (const wchar_t* marker : kKnownAdapterMarkers) {
            if (name.Contains(wxString(marker))) {
                return "runtime env check: a known remote-control layer is active "
                       "(display adapter \"" + wxString(dd.DeviceString).ToStdString() +
                       "\"), which suppresses synthetic input so wxUIActionSimulator "
                       "cannot deliver events. Recovery: fully stop it — e.g. NetEase "
                       "GameViewer tray app plus its 'GameViewerService' service — or "
                       "uninstall it, then re-run. See tests/wx_gui/"
                       "ADVERSARIAL_LOOP_JOURNAL.md for background.";
            }
        }
        dd.cb = sizeof(dd); // docs: re-initialize before each call
    }

    static const wchar_t* const kKnownServiceNames[] = {
        L"GameViewerService", L"GameViewerServer", L"TeamViewer", L"AnyDesk",
        L"ToDesk_Service", L"SunloginClient", L"AweSunService", L"uvnc_service",
        L"Parsec",
    };
    SC_HANDLE scm = ::OpenSCManagerW(nullptr, nullptr, SC_MANAGER_ENUMERATE_SERVICE);
    if (scm) {
        DWORD needed = 0, returned = 0;
        ::EnumServicesStatusExW(scm, SC_ENUM_PROCESS_INFO, SERVICE_WIN32,
                                SERVICE_STATE_ALL, nullptr, 0, &needed, &returned,
                                nullptr, nullptr);
        if (::GetLastError() == ERROR_MORE_DATA && needed > 0) {
            std::vector<BYTE> buf(needed);
            if (::EnumServicesStatusExW(scm, SC_ENUM_PROCESS_INFO, SERVICE_WIN32,
                                        SERVICE_STATE_ALL, buf.data(),
                                        static_cast<DWORD>(buf.size()), &needed,
                                        &returned, nullptr, nullptr)) {
                auto* svc = reinterpret_cast<ENUM_SERVICE_STATUS_PROCESSW*>(buf.data());
                for (DWORD j = 0; j < returned; ++j, ++svc) {
                    wxString name(svc->lpServiceName);
                    name.MakeLower();
                    for (const wchar_t* known : kKnownServiceNames) {
                        if (name == wxString(known).MakeLower()) {
                            ::CloseServiceHandle(scm);
                            return "runtime env check: remote-control service '" +
                                   wxString(svc->lpServiceName).ToStdString() +
                                   "' is running; it suppresses synthetic input so "
                                   "wxUIActionSimulator cannot deliver events. "
                                   "Recovery: stop it (net stop " +
                                   wxString(svc->lpServiceName).ToStdString() +
                                   " or Services.msc), then re-run. See tests/wx_gui/"
                                   "ADVERSARIAL_LOOP_JOURNAL.md for background.";
                        }
                    }
                }
            }
        }
        ::CloseServiceHandle(scm);
    }

    // --- 2. keyboard layout ---
    // sim.Text() needs a non-IME layout on the thread: the default zh-CN layout
    // composes synthesized keystrokes into CJK characters. ScopedUsKeyboardLayout
    // switches to US English (0x0409) around the sim call; if that layout is not
    // even installed, the sim cannot be made IME-safe.
    if (LOWORD(reinterpret_cast<DWORD_PTR>(::GetKeyboardLayout(0))) != 0x0409) {
        HKL hUs = ::LoadKeyboardLayoutW(L"00000409", KLF_NOTELLSHELL | KLF_SUBSTITUTE_OK);
        if (hUs) {
            ::UnloadKeyboardLayout(hUs); // probe only; the RAII guard does the real work
        } else {
            return "runtime env check: the active keyboard layout is not US English "
                   "(0x0409) and the US English layout is not installed, so sim.Text() "
                   "cannot bypass IME composition. Recovery: add 'English (United "
                   "States)' under Windows Settings -> Time & Language -> Language, "
                   "or switch the active layout, then re-run.";
        }
    }
    return {};
}
#elif defined(__WXOSX__)
static std::string macos_sim_env_problem()
{
    return "SKIP on macOS by design: wxOSX/Cocoa never grants keyboard focus "
           "inside the modal loop, so synthetic events have no target (a wxWidgets "
           "platform defect, not an OrcaSlicer issue). See tests/wx_gui/"
           "ADVERSARIAL_LOOP_JOURNAL.md for the full conclusion.";
}
#endif

// Call at the top of every test that drives wxUIActionSimulator (and the raw
// Win32 probes, which have the same environment requirements): SKIPs the test
// with the reason + recovery steps when the environment cannot deliver.
static void skip_if_sim_environment_unusable()
{
#ifdef __WXMSW__
    const std::string reason = windows_sim_env_problem();
#elif defined(__WXOSX__)
    const std::string reason = macos_sim_env_problem();
#else
    const std::string reason; // wxGTK: no known blockers, run as-is
#endif
    if (!reason.empty())
        SKIP(reason);
}

// ---------------------------------------------------------------------------
// (0c) MESSAGE-LEVEL injection (Windows-only): the "works even with a
//      remote-control layer running" path.
//
// wxUIActionSimulator's wxMSW backend goes through the OS input pipeline
// (keybd_event/mouse_event), which remote-control software (e.g. NetEase
// GameViewer) filters in a WH_KEYBOARD_LL/WH_MOUSE_LL hook by dropping
// LLKHF_INJECTED events. SENT messages (SendMessage — the same mechanism as
// pywinauto's send_chars()/Click() and AutoHotkey's ControlSend) do NOT
// traverse the low-level hooks: the hook chain only runs for messages fetched
// from the input queue (Raymond Chen, "You can't simulate keyboard input with
// PostMessage, revisited") — so this simulator keeps working in that
// environment. It also needs no foreground window, no keyboard focus, and no
// non-IME layout: WM_CHAR carries the literal character and the standard
// controls process it directly. Events flow through the native window
// procedure (unlike ProcessEvent), but no real input state (GetAsyncKeyState,
// cursor, focus) is produced.
// ---------------------------------------------------------------------------
#ifdef __WXMSW__
class Win32MessageSimulator
{
public:
    // Type text by SENDING WM_CHAR to the control (synchronous — the same
    // approach as pywinauto's send_chars() and AutoHotkey's ControlSend:
    // reliable, works without focus and without the window being visible or
    // active). Standard edit controls (wxTextCtrl on wxMSW is a plain
    // single-line EDIT) insert the character and emit wxEVT_TEXT exactly as
    // for real typing.
    //
    // NOTE: SendMessage (not PostMessage) on purpose — posted messages need
    // the queue pumped, and this test process runs no resident event loop
    // (wxEntryStart without OnRun), so wxYield() does not reliably dispatch
    // them. A synchronous send goes straight through the window procedure.
    void Text(HWND hwnd, const wxString& text)
    {
        for (wxChar ch : text)
            ::SendMessageW(hwnd, WM_CHAR, static_cast<WPARAM>(ch), 0);
    }

    // Left-click the center of the control by SENDING WM_LBUTTONDOWN + UP.
    // Standard button controls (wxButton on wxMSW is a plain BS_PUSHBUTTON)
    // send BN_CLICKED (-> the wxEVT_BUTTON handler) when both the down and the
    // up point fall inside the client area.
    void MouseClick(HWND hwnd)
    {
        RECT rc{};
        ::GetClientRect(hwnd, &rc);
        const LPARAM lp = MAKELPARAM(rc.right / 2, rc.bottom / 2);
        ::SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp);
        ::SendMessageW(hwnd, WM_LBUTTONUP, 0, lp);
    }
};
#endif

// ---------------------------------------------------------------------------
// (1) wxApp: derived class registered via NO_MAIN (does NOT define main(),
//     which Catch2::Catch2WithMain already owns). wxEntryStart will instantiate
//     this class as wxTheApp.
//
//     Full-app mode (ORCA_FULL_GUI_APP, see CMake option WX_GUI_FULL_APP):
//     PoCApp is compiled OUT and the REAL GUI_App (wxIMPLEMENT_APP in
//     GUI_App.cpp, linked via libslic3r_gui) becomes wxTheApp, so tests can
//     drive the actual application (MainFrame, Plater, dialogs).
// ---------------------------------------------------------------------------
#if !defined(ORCA_FULL_GUI_APP)
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
#endif

// Full-app mode: create an isolated data dir so the test boot never touches
// the user's real configuration (app_config.ini, preset backups, ...). The
// installed system presets (vendor bundles, installed by ConfigWizard into
// %APPDATA%\Snapmaker_Orca\system) are copied in READ-ONLY fashion so
// PresetBundle::load_presets() finds real presets and load_selections() has
// something to select — an empty system dir crashes in load_selections.
static std::string make_test_data_dir()
{
#ifdef __WXMSW__
    wchar_t tmp[MAX_PATH]{};
    ::GetTempPathW(MAX_PATH, tmp);
    const std::wstring dir = std::wstring(tmp) + L"wx_gui_tests_data_" + std::to_wstring(::GetCurrentProcessId());
    ::CreateDirectoryW(dir.c_str(), nullptr);

    namespace fs = std::filesystem;
    const fs::path test_data(dir);
    const fs::path system_src = fs::path(std::getenv("APPDATA") != nullptr ? std::getenv("APPDATA") : "") /
                                "Snapmaker_Orca" / "system";
    if (fs::exists(system_src)) {
        std::error_code ec;
        fs::copy(system_src, test_data / "system", fs::copy_options::recursive | fs::copy_options::overwrite_existing, ec);
        if (ec)
            std::fprintf(stderr, "[wx_gui] warning: could not copy system presets from %ls: %s\n",
                         system_src.c_str(), ec.message().c_str());
    } else {
        std::fprintf(stderr, "[wx_gui] warning: no installed system presets at %ls — full-app boot may crash in load_selections\n",
                     system_src.c_str());
    }
    return wxString(dir).ToStdString();
#else
    return "/tmp/wx_gui_tests_data";
#endif
}

// ---------------------------------------------------------------------------
// (2) One-shot wx initialization for the whole test process.
//     wxEntryStart calls wxApp::Initialize() + common post-init, creating
//     wxTheApp. NOTE: unlike wxEntry, wxEntryStart does NOT run OnInit() or
//     the main message loop (OnRun) — we keep wx alive for the whole process
//     and rely on per-test modal loops / wxYield() to pump events. It is NOT
//     idempotent after wxEntryCleanup, so we gate it on a static flag and
//     never clean up (process exit reclaims everything).
//
//     Full-app mode additionally: points Slic3r::data_dir() at a temp folder
//     BEFORE the GUI_App constructor runs (init_app_config() reads it in the
//     ctor), then calls wxTheApp->OnInit() manually (that is where the real
//     on_init_inner boots MainFrame/Plater — ORCA_GUI_TEST_MODE=1 skips the
//     network/splash/registry side effects and hides the main window).
//
//     NOTE on a private desktop (CreateDesktop/SetThreadDesktop): verified
//     experimentally that wx startup HANGS on any desktop other than the
//     interactive one — wxEntryStart never returns, with or without
//     SwitchDesktop — so that "background desktop" idea is abandoned; the
//     hidden main window keeps tests out of the user's way instead.
// ---------------------------------------------------------------------------
// Not static: wx_gui_app_tests.cpp (full-app tests) declares it extern.
bool ensure_wx_initialized()
{
    static bool s_tried = false;
    static bool s_ok    = false;
    if (s_tried) return s_ok;
    s_tried = true;

    static int   argc = 1;
    static char  arg0[] = "wx_gui_tests";
    static char* argv[] = {arg0, nullptr};

#if defined(ORCA_FULL_GUI_APP)
    // The real app flow wires init_params in GUI::GUI_Run(); wxEntryStart never
    // does, so feed a default params block ourselves or on_init_inner crashes
    // dereferencing the null init_params in load_presets.
    static int                 test_argc = 1;
    static char                test_arg0[] = "wx_gui_tests";
    static char*               test_argv[] = {test_arg0, nullptr};
    static Slic3r::GUI::GUI_InitParams test_init_params;
    test_init_params.argc = test_argc;
    test_init_params.argv = test_argv;

    Slic3r::set_data_dir(make_test_data_dir());
    // Snapmaker_Orca.cpp does these during its own startup; the test process
    // has no main app, so do them here: var_dir() feeds every ScalableBitmap
    // lookup, and save_main_thread_id() marks this thread as the main thread
    // (AppConfig::save() throws CriticalException otherwise).
    Slic3r::set_var_dir((boost::filesystem::path(Slic3r::resources_dir()) / "images").string());
    Slic3r::save_main_thread_id();
    s_ok = wxEntryStart(argc, argv) && wxTheApp != nullptr;
    if (s_ok) {
        // wxEntryStart instantiates whatever wxCreateApp() resolves to. With the
        // GUI_App factory pulled in (this TU references GUI_App directly) it is
        // the real GUI_App; if the link order ever resolves the inline
        // wxWidgets default (wxDummyConsoleApp) instead, replace it explicitly.
        auto* gui_app = dynamic_cast<Slic3r::GUI::GUI_App*>(wxAppConsole::GetInstance());
        if (gui_app == nullptr) {
            gui_app = new Slic3r::GUI::GUI_App();
            delete wxAppConsole::GetInstance();
            wxAppConsole::SetInstance(gui_app);
        }
        gui_app->init_params = &test_init_params;
        try {
            s_ok = gui_app->OnInit();
        } catch (const std::exception& e) {
            std::fprintf(stderr, "[ensure] OnInit threw: %s\n", e.what());
            s_ok = false;
        } catch (...) {
            std::fprintf(stderr, "[ensure] OnInit threw unknown exception\n");
            s_ok = false;
        }
        if (s_ok) {
            // The app now owns a live MainFrame (+ render threads/timers). If we
            // let process exit reclaim everything, wx static destruction races
            // with those and SIGSEGVs after the test summary. Clean up wx in an
            // atexit hook (runs before static dtors) instead.
            static bool cleanup_registered = false;
            if (!cleanup_registered) {
                cleanup_registered = true;
                std::atexit([]() {
                    if (wxTheApp != nullptr) {
                        wxTheApp->ExitMainLoop();
                        wxEntryCleanup();
                    }
                });
            }
        }
    }
    return s_ok;
#else
    s_ok = wxEntryStart(argc, argv);
    return s_ok;
#endif
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

// Poll cond() up to `attempts` times, yielding + sleeping between tries so
// injected input gets retrieved from the native queue and dispatched, then
// return the final state of cond().
template <typename F>
static bool wait_until(F&& cond, int attempts = 10, int delay_ms = 30)
{
    for (int i = 0; i < attempts; ++i) {
        if (cond()) return true;
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
    }
    return cond();
}

// ---------------------------------------------------------------------------
// (3) The dialog under test: a TextCtrl + an "Echo" button + a StaticText.
//     Clicking the button (wxEVT_BUTTON) copies the TextCtrl value into the
//     StaticText. This is the simplest possible "user interaction -> observable
//     state change" loop, shared by the simulator smoke tests and the
//     event-injection tests.
//
// Each smoke test installs its own m_sim_step (typing, clicking, or both);
// run_simulation() executes it INSIDE the modal loop (via CallAfter), where wx
// focus management works, then EndModal returns to the test.
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

    // Win32 input-target diagnostics, captured at the moment the simulator
    // runs. Surfaced via INFO() lines so one run settles the failure cause.
    std::string m_diag_foreground;   // GetForegroundWindow() at sim time
    std::string m_diag_focus;        // GetFocus() at sim time
    std::string m_diag_dialog_hwnd;  // this dialog's HWND
    std::string m_diag_textctrl_hwnd;// TextCtrl's HWND
    bool        m_diag_fg_is_dialog = false;     // foreground == dialog HWND?
    bool        m_diag_focus_is_textctrl = false; // Win32 focus == TextCtrl HWND?
    bool        m_used_attach_thread_input = false; // did we apply the foreground fix?

    // The simulation step for the CURRENT test (simulator tests only).
#if wxUSE_UIACTIONSIMULATOR
    std::function<void(EchoDialog&, wxUIActionSimulator&)> m_sim_step;
#endif

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
#if wxUSE_UIACTIONSIMULATOR
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

            // Per-test action (installed by the smoke test before ShowModal).
            m_sim_step(*this, sim);
            EndModal(wxID_OK);
        });
    }
#endif
};

// Small RAII event counter, mirroring wxWidgets' test EventCounter pattern
// (docs/contributing/how-to-write-unit-tests.md): counting the events
// themselves proves delivery, independent of the final control state that the
// other assertions also check. Used by both the simulator smoke tests and the
// event-injection tests.
class EventCounter
{
public:
    // NOTE: no Unbind in the destructor — the lambda functor cannot be
    // reliably unbound across wx versions, and each counter outlives the
    // window it is bound to only within a single test scope.
    EventCounter(wxWindow* win, wxEventTypeTag<wxCommandEvent> type)
    {
        win->Bind(type, [this](wxCommandEvent&) { ++m_count; });
    }
    int count() const { return m_count; }
private:
    int m_count = 0;
};

// ---------------------------------------------------------------------------
// (4) Simulator smoke tests.
//
// Everything below that drives wxUIActionSimulator is guarded per the
// wxWidgets unit-test guide (docs/contributing/how-to-write-unit-tests.md):
// wrap simulator tests in #if wxUSE_UIACTIONSIMULATOR. The raw Win32 probes in
// section (6) do not use the simulator and stay unguarded. Every test here
// starts with skip_if_sim_environment_unusable(), so on an environment that
// cannot deliver synthetic input the tests SKIP (with the reason + recovery
// steps) instead of failing.
// ---------------------------------------------------------------------------
#if wxUSE_UIACTIONSIMULATOR

// (4a) smoke_text_echo: synthetic keystrokes reach the focused TextCtrl and
// mutate it. Focus is a precondition of typing, so it is asserted here too.
TEST_CASE("smoke_text_echo: sim.Text reaches focused TextCtrl", "[gui][smoke]")
{
    skip_if_sim_environment_unusable();

    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    wxUIActionSimulator sim;
    dlg.m_sim_step = [](EchoDialog& d, wxUIActionSimulator& s) {
        d.m_input->SetFocus();
        wxYield();
        d.m_textctrl_had_focus = d.m_input->HasFocus();
#ifdef __WXMSW__
        // Activate a non-IME layout so synthesized ASCII keystrokes are not
        // composed into CJK by the active Microsoft Pinyin IME.
        ScopedUsKeyboardLayout usLayout;
#endif
        s.Text("hello");
        // Pump the modal loop so the injected keybd_event() messages get
        // retrieved and dispatched.
        wait_until([&d]() { return d.m_input->GetValue() == "hello"; });
        d.m_input_after_text = d.m_input->GetValue();
    };
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
}

// (4b) smoke_button_click: a synthetic mouse click on the button's screen
// coordinates drives wxEVT_BUTTON and the echo handler.
TEST_CASE("smoke_button_click: sim.MouseClick drives the button", "[gui][smoke]")
{
    skip_if_sim_environment_unusable();

    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    wxUIActionSimulator sim;
    dlg.m_sim_step = [](EchoDialog& d, wxUIActionSimulator& s) {
        // Seed the input, then click the button by coordinates.
        d.m_input->SetValue("world");
        wxYield();
        wxRect br = d.m_btn->GetScreenRect();
        s.MouseMove(wxPoint(br.x + br.width / 2, br.y + br.height / 2));
        wxYield();
        s.MouseClick();
        wait_until([&d]() { return d.m_echo->GetLabelText() == "world"; });
        d.m_echo_after_click = d.m_echo->GetLabelText();
    };
    dlg.run_simulation(sim);
    dlg.ShowModal();

    INFO("Echo label after sim.MouseClick on button = \"" << dlg.m_echo_after_click << "\"");
    CHECK(dlg.m_echo_after_click == "world");
}

// (4c) smoke_event_delivery: EventCounter proves the events the simulator
// produces actually arrive at the controls, independent of the final control
// state that (4a)/(4b) assert.
TEST_CASE("smoke_event_delivery: EventCounter proves sim events arrive", "[gui][smoke]")
{
    skip_if_sim_environment_unusable();

    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    // Event-delivery proof independent of the final-state assertions.
    EventCounter text_events(dlg.m_input, wxEVT_TEXT);
    EventCounter button_events(dlg.m_btn, wxEVT_BUTTON);

    wxUIActionSimulator sim;
    dlg.m_sim_step = [](EchoDialog& d, wxUIActionSimulator& s) {
        // --- typing ---
        d.m_input->SetFocus();
        wxYield();
#ifdef __WXMSW__
        ScopedUsKeyboardLayout usLayout; // bypass IME composition
#endif
        s.Text("hello");
        wait_until([&d]() { return d.m_input->GetValue() == "hello"; });
        d.m_input_after_text = d.m_input->GetValue();

        // --- click ---
        d.m_input->SetValue("world"); // seeds the echo target (also fires wxEVT_TEXT)
        wxYield();
        wxRect br = d.m_btn->GetScreenRect();
        s.MouseMove(wxPoint(br.x + br.width / 2, br.y + br.height / 2));
        wxYield();
        s.MouseClick();
        wait_until([&d]() { return d.m_echo->GetLabelText() == "world"; });
        d.m_echo_after_click = d.m_echo->GetLabelText();
    };
    dlg.run_simulation(sim);
    dlg.ShowModal();

    // SetValue("world") also fires wxEVT_TEXT, so expect >= 1 from sim.Text;
    // the button event can only come from the click.
    INFO("wxEVT_TEXT delivered = " << text_events.count() << " (expected >= 1 from sim.Text)");
    CHECK(text_events.count() >= 1);
    INFO("wxEVT_BUTTON delivered = " << button_events.count() << " (expected exactly 1 from sim.MouseClick)");
    CHECK(button_events.count() == 1);
}

// ---------------------------------------------------------------------------
// (4d) Variant: NON-MODAL top-level frame, simulator driven DIRECTLY (no
// ShowModal, no CallAfter). This is the canonical wxWidgets test pattern (see
// tests/controls/textctrltest.cpp and tests/validators/valnum.cpp in the
// wxWidgets tree): the control is a child of a shown top-level window and the
// sim is driven from the test thread with a single wxYield() per action. It
// keeps exercising the non-modal delivery path (the journal settled that the
// modal structure was NOT the blocker — the environment was).
// ---------------------------------------------------------------------------
TEST_CASE("wxUIActionSimulator drives non-modal frame directly", "[gui]")
{
    skip_if_sim_environment_unusable();

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

    // Event-delivery proof independent of the final-state assertions below.
    EventCounter text_events(input, wxEVT_TEXT);
    EventCounter button_events(btn, wxEVT_BUTTON);

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

    // SetValue("world") also fires wxEVT_TEXT, so expect 1 (typed) + 1 (seeded).
    INFO("wxEVT_TEXT delivered = " << text_events.count() << " (expected >= 1 from sim.Text)");
    CHECK(text_events.count() >= 1);
    INFO("wxEVT_BUTTON delivered = " << button_events.count() << " (expected 1 from sim.MouseClick)");
    CHECK(button_events.count() == 1);

    INFO("TextCtrl value after sim.Text(\"hello\") [non-modal] = \"" << input_after << "\"");
    CHECK(input_after == "hello");

    INFO("Echo label after sim.MouseClick [non-modal] = \"" << echo_after << "\"");
    CHECK(echo_after == "world");
}
#endif // wxUSE_UIACTIONSIMULATOR

// ---------------------------------------------------------------------------
// (5) EVENT-LAYER injection tests (NO wxUIActionSimulator, NOT guarded).
//
// The daily-batch path: deliver events in-process via ProcessEvent(). This is
// synchronous, needs no foreground window, does not steal the mouse, and is
// immune to IME composition and remote-control input interception — so these
// tests are headless-safe and need no environment gates. They mirror the three
// smoke tests above (button click / text echo / event arrival) through the
// event layer only:
//
//   wxCommandEvent evt(wxEVT_BUTTON, btn->GetId());
//   evt.SetEventObject(btn);
//   btn->GetEventHandler()->ProcessEvent(evt);
// ---------------------------------------------------------------------------

// Button click: the command event reaches the echo handler and the label
// updates — the same observable state change as smoke_button_click.
TEST_CASE("event_inject_button_click: ProcessEvent(wxEVT_BUTTON) echoes the input", "[gui][eventinject]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    dlg.m_input->SetValue("world");

    wxCommandEvent evt(wxEVT_BUTTON, dlg.m_btn->GetId());
    evt.SetEventObject(dlg.m_btn);
    const bool handled = dlg.m_btn->GetEventHandler()->ProcessEvent(evt);

    INFO("ProcessEvent(wxEVT_BUTTON) handled = " << (handled ? "true" : "false"));
    REQUIRE(handled); // the echo handler must receive the event
    CHECK(dlg.m_echo->GetLabelText() == "world");
}

// Text echo: what the wxMSW port dispatches when the user types — the value is
// set (state) and wxEVT_TEXT is sent (notification) — flows through the event
// layer, and the full echo path (text -> click -> label) works end to end.
TEST_CASE("event_inject_text_echo: ProcessEvent(wxEVT_TEXT) carries the text", "[gui][eventinject]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    EventCounter text_events(dlg.m_input, wxEVT_TEXT);

    dlg.m_input->SetValue("hello");
    wxCommandEvent tevt(wxEVT_TEXT, dlg.m_input->GetId());
    tevt.SetEventObject(dlg.m_input);
    tevt.SetString("hello");
    const bool text_handled = dlg.m_input->GetEventHandler()->ProcessEvent(tevt);

    wxCommandEvent bevt(wxEVT_BUTTON, dlg.m_btn->GetId());
    bevt.SetEventObject(dlg.m_btn);
    const bool btn_handled = dlg.m_btn->GetEventHandler()->ProcessEvent(bevt);

    REQUIRE(text_handled);
    REQUIRE(btn_handled);
    INFO("wxEVT_TEXT delivered = " << text_events.count() << " (expected >= 1)");
    CHECK(text_events.count() >= 1);
    INFO("Echo label after event-layer text + click = \"" << dlg.m_echo->GetLabelText() << "\"");
    CHECK(dlg.m_echo->GetLabelText() == "hello");
}

// Event arrival: EventCounter counts exactly the events ProcessEvent delivers
// (the same proof as smoke_event_delivery, deterministic per dispatch).
TEST_CASE("event_inject_event_delivery: EventCounter sees ProcessEvent deliveries", "[gui][eventinject]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    EventCounter text_events(dlg.m_input, wxEVT_TEXT);
    EventCounter button_events(dlg.m_btn, wxEVT_BUTTON);

    const int text_before = text_events.count();
    wxCommandEvent tevt(wxEVT_TEXT, dlg.m_input->GetId());
    tevt.SetEventObject(dlg.m_input);
    tevt.SetString("hello");
    REQUIRE(dlg.m_input->GetEventHandler()->ProcessEvent(tevt));
    CHECK(text_events.count() == text_before + 1);

    const int button_before = button_events.count();
    wxCommandEvent bevt(wxEVT_BUTTON, dlg.m_btn->GetId());
    bevt.SetEventObject(dlg.m_btn);
    REQUIRE(dlg.m_btn->GetEventHandler()->ProcessEvent(bevt));
    CHECK(button_events.count() == button_before + 1);
}

// ---------------------------------------------------------------------------
// (5b) MESSAGE-LEVEL injection tests (Windows-only, NO wxUIActionSimulator).
//
// The same three smoke behaviors (text echo / button click / event arrival)
// driven by Win32MessageSimulator: sent WM_* messages to the control HWNDs.
// These work even while a remote-control layer (GameViewer) is running, need
// no foreground window, no keyboard focus, and bypass IME — so they need none
// of the environment gates from section (0b), and they run headless (the
// dialog is never shown).
// ---------------------------------------------------------------------------
#ifdef __WXMSW__

TEST_CASE("msg_inject_text_echo: WM_CHAR reaches the TextCtrl", "[gui][msginject]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    Win32MessageSimulator sim;
    sim.Text(static_cast<HWND>(dlg.m_input->GetHWND()), "hello");
    wait_until([&]() { return dlg.m_input->GetValue() == "hello"; });

    INFO("TextCtrl value after sent WM_CHAR = \"" << dlg.m_input->GetValue() << "\"");
    CHECK(dlg.m_input->GetValue() == "hello");
}

TEST_CASE("msg_inject_button_click: WM_LBUTTONDOWN/UP drives the button", "[gui][msginject]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    dlg.m_input->SetValue("world");

    Win32MessageSimulator sim;
    sim.MouseClick(static_cast<HWND>(dlg.m_btn->GetHWND()));
    wait_until([&]() { return dlg.m_echo->GetLabelText() == "world"; });

    INFO("Echo label after sent WM_LBUTTONDOWN/UP = \"" << dlg.m_echo->GetLabelText() << "\"");
    CHECK(dlg.m_echo->GetLabelText() == "world");
}

TEST_CASE("msg_inject_event_delivery: EventCounter sees sent messages", "[gui][msginject]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    EchoDialog dlg;
    EventCounter text_events(dlg.m_input, wxEVT_TEXT);
    EventCounter button_events(dlg.m_btn, wxEVT_BUTTON);

    Win32MessageSimulator sim;
    sim.Text(static_cast<HWND>(dlg.m_input->GetHWND()), "hello");
    wait_until([&]() { return dlg.m_input->GetValue() == "hello"; });
    dlg.m_input->SetValue("world"); // seeds the echo target (also fires wxEVT_TEXT)
    sim.MouseClick(static_cast<HWND>(dlg.m_btn->GetHWND()));
    wait_until([&]() { return dlg.m_echo->GetLabelText() == "world"; });

    INFO("wxEVT_TEXT delivered = " << text_events.count() << " (expected >= 1 from WM_CHAR)");
    CHECK(text_events.count() >= 1);
    INFO("wxEVT_BUTTON delivered = " << button_events.count() << " (expected exactly 1 from WM_LBUTTONDOWN/UP)");
    CHECK(button_events.count() == 1);
}
#endif // __WXMSW__

// ---------------------------------------------------------------------------
// (6) Raw probe (Windows-only, throwaway diagnostic): bypass wxUIActionSimulator
//     and call keybd_event() directly on a focused, foreground wxTextCtrl, then
//     run a native PeekMessage/TranslateMessage/DispatchMessage loop. Reports
//     whether the OS accepted the inject (GetAsyncKeyState) and how many
//     WM_KEYDOWN/WM_CHAR were actually retrieved. This isolates OS-level input
//     injection from the wxUIActionSimulator abstraction. Same environment
//     requirements as the simulator, hence the same runtime gate.
// ---------------------------------------------------------------------------
#ifdef __WXMSW__
TEST_CASE("raw keybd_event reaches focused TextCtrl", "[gui][rawprobe]")
{
    skip_if_sim_environment_unusable();

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
    skip_if_sim_environment_unusable();

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
