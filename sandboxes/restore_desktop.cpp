#include <windows.h>
#include <cstdio>
int main()
{
    // Show current active desktop name first
    HDESK hInput = ::OpenInputDesktop(0, FALSE, DESKTOP_READOBJECTS);
    wchar_t name[128]{};
    DWORD len = 0;
    if (hInput) {
        ::GetUserObjectInformationW(hInput, UOI_NAME, name, sizeof(name), &len);
        std::printf("[restore] active desktop now: %ls\n", name);
        ::CloseDesktop(hInput);
    }
    HDESK hDefault = ::OpenDesktopW(L"Default", 0, FALSE, DESKTOP_SWITCHDESKTOP);
    if (!hDefault) { std::printf("[restore] OpenDesktop Default failed %u\n", ::GetLastError()); return 1; }
    if (!::SwitchDesktop(hDefault)) { std::printf("[restore] SwitchDesktop failed %u\n", ::GetLastError()); return 1; }
    std::printf("[restore] switched back to Default\n");
    ::CloseDesktop(hDefault);
    return 0;
}
