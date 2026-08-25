// desktop_probe.cpp — 验证"独立桌面"能否后台运行 GUI 测试并绕过 GameViewer。
//
// 实验假设：
//   1. CreateDesktop + SetThreadDesktop 后，当前线程的窗口在新桌面创建/渲染，
//      不干扰用户当前桌面（后台运行）。
//   2. WH_KEYBOARD_LL 低级钩子按桌面隔离 —— GameViewer 的输入拦截钩子挂在
//      WinSta0\Default，新桌面里 keybd_event() 注入不被吞。
//
// 用法：
//   desktop_probe.exe            —— 在当前桌面注入（对照组：GameViewer 拦截 → WM_CHAR=0）
//   desktop_probe.exe --desktop  —— 在新桌面注入（实验组：隔离成立 → WM_CHAR>=1）
//
// 结果判定：WM_CHAR retrieved / edit text 是否为 "A"。

#include <windows.h>

#include <cstdio>

static const wchar_t* kDesktopName = L"ZCodeProbeDesktop";

static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_DESTROY: ::PostQuitMessage(0); return 0;
    default: break;
    }
    return ::DefWindowProcW(hwnd, msg, wp, lp);
}

int wmain(int argc, wchar_t** argv)
{
    bool use_desktop = false;
    bool use_switch = false;
    for (int i = 1; i < argc; ++i) {
        if (wcscmp(argv[i], L"--desktop") == 0) use_desktop = true;
        if (wcscmp(argv[i], L"--switch") == 0) use_switch = true;
    }

    HDESK prev_desk = nullptr;
    if (use_desktop) {
        HDESK hd = ::CreateDesktopW(kDesktopName, nullptr, nullptr, 0,
                                    DESKTOP_CREATEWINDOW | DESKTOP_ENUMERATE |
                                        DESKTOP_READOBJECTS | DESKTOP_WRITEOBJECTS |
                                        DESKTOP_SWITCHDESKTOP,
                                    nullptr);
        if (!hd) { std::printf("[probe] CreateDesktop failed %u\n", ::GetLastError()); return 1; }
        if (!::SetThreadDesktop(hd)) { std::printf("[probe] SetThreadDesktop failed %u\n", ::GetLastError()); return 1; }
        std::printf("[probe] thread switched to desktop '%ls'\n", kDesktopName);
        if (use_switch) {
            // 把新桌面切成活动桌面（用户屏幕会闪切，测完切回）
            HDESK cur = ::OpenInputDesktop(0, FALSE, DESKTOP_SWITCHDESKTOP | DESKTOP_READOBJECTS);
            if (!::SwitchDesktop(hd)) { std::printf("[probe] SwitchDesktop failed %u\n", ::GetLastError()); return 1; }
            prev_desk = cur;
            std::printf("[probe] new desktop is now ACTIVE\n");
        }
    }

    WNDCLASSW wc{};
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = ::GetModuleHandleW(nullptr);
    wc.lpszClassName = L"ZCodeProbeEditClass";
    ::RegisterClassW(&wc);

    HWND hEdit = ::CreateWindowExW(0, L"EDIT", L"", WS_POPUP | WS_VISIBLE | WS_BORDER,
                                   0, 0, 200, 30, nullptr, nullptr, wc.hInstance, nullptr);
    if (!hEdit) { std::printf("[probe] CreateWindow failed %u\n", ::GetLastError()); return 1; }

    // 当前线程桌面 vs 窗口实际所在桌面
    HDESK thread_desk = ::GetThreadDesktop(::GetCurrentThreadId());
    wchar_t desk_name[128]{};
    DWORD   len = 0;
    ::GetUserObjectInformationW(thread_desk, UOI_NAME, desk_name, sizeof(desk_name), &len);
    std::printf("[probe] edit HWND=%p on thread desktop='%ls'\n", (void*)hEdit, desk_name);

    ::SetFocus(hEdit);
    MSG m;
    for (int i = 0; i < 50; ++i) {
        while (::PeekMessageW(&m, nullptr, 0, 0, PM_REMOVE)) { ::TranslateMessage(&m); ::DispatchMessageW(&m); }
        ::Sleep(5);
    }

    // 注入 'A'（与 rawprobe 测试相同的 OS 级注入路径）
    ::keybd_event(0x41, 0, 0, 0);
    const short async_down = ::GetAsyncKeyState(0x41);
    ::keybd_event(0x41, 0, KEYEVENTF_KEYUP, 0);
    std::printf("[probe] GetAsyncKeyState('A') after inject = 0x%04x\n",
                static_cast<unsigned short>(async_down));

    int n_char = 0;
    for (int i = 0; i < 300; ++i) {
        while (::PeekMessageW(&m, nullptr, 0, 0, PM_REMOVE)) {
            if (m.message == WM_CHAR) n_char++;
            ::TranslateMessage(&m);
            ::DispatchMessageW(&m);
        }
        if (n_char > 0) break;
        ::Sleep(5);
    }

    wchar_t buf[64]{};
    ::GetWindowTextW(hEdit, buf, 63);
    std::printf("[probe] WM_CHAR retrieved=%d, edit text=\"%ls\"\n", n_char, buf);
    std::printf("[probe] DONE\n");

    // 切回原活动桌面（仅 --switch 模式）
    if (prev_desk) {
        ::SwitchDesktop(prev_desk);
        ::CloseDesktop(prev_desk);
        std::printf("[probe] switched back to original desktop\n");
    }
    return 0;
}
