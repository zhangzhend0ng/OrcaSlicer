#include "slic3r/plugin/host/PluginDockLayout.hpp"
#include <stdexcept>
#include <iostream>
int main()
{
    const std::string base = "plugin:fixture:dock";
    const std::string first = "name=" + base + ";caption=escaped\\|pipe\\;semi;state=42;bestw=321;";
    const std::string second = "name=" + base + "#2;caption=duplicate;state=43;bestw=456;";
    const std::string perspective = "layout2|name=main;state=1;|" + first + "|" + second + "|dock_size(1,0,0)=200|";
    using Slic3r::GUI::plugin_saved_pane_layout;
    if (plugin_saved_pane_layout(perspective, base) != first || plugin_saved_pane_layout(perspective, base + "#2") != second ||
        !plugin_saved_pane_layout(perspective, "missing").empty() || !plugin_saved_pane_layout("", base).empty())
        throw std::runtime_error("AUI pane lookup lost escaped separators or exact identity");
    using Slic3r::GUI::plugin_preserve_uncreated_panes;
    const std::string old_first = "name=" + base + ";caption=escaped\\|pipe\\;semi;state=42;dir=3;layer=2;row=1;bestw=1198;besth=170;";
    const std::string old_second = "name=" + base + "#2;caption=duplicate;state=43;dir=4;layer=1;row=2;bestw=275;besth=515;";
    const std::string startup = "layout2|name=sidebar;state=1;bestw=420;|name=main;state=1;|dock_size(4,0,0)=422|";
    const std::string previous = "layout2|name=sidebar;state=99;bestw=800;|" + old_first + '|' + old_second +
        "|dock_size(3,2,1)=190|dock_size(4,1,2)=277|dock_size(4,0,0)=900|dock_size(1,7,4)=333|";
    const auto merged = plugin_preserve_uncreated_panes(startup, previous);
    if (plugin_saved_pane_layout(merged, base) != old_first || plugin_saved_pane_layout(merged, base + "#2") != old_second ||
        merged.find("dock_size(3,2,1)=190|") == std::string::npos || merged.find("dock_size(4,1,2)=277|") == std::string::npos ||
        merged.find("bestw=800") != std::string::npos || merged.find("=900|") != std::string::npos || merged.find("=333|") != std::string::npos)
        throw std::runtime_error("Startup save lost absent plugin panes/dock sizes or overwrote current built-in layout");
    const std::string current_first = "name=" + base + ";caption=current;state=2;dir=3;layer=2;row=1;bestw=456;besth=180;";
    const auto active = startup + current_first + "|dock_size(3,2,1)=205|dock_size(4,1,2)=310|";
    const auto partial = plugin_preserve_uncreated_panes(active, previous);
    if (plugin_saved_pane_layout(partial, base) != current_first || plugin_saved_pane_layout(partial, base + "#2") != old_second ||
        partial.find("dock_size(3,2,1)=190|") != std::string::npos ||
        partial.find("dock_size(3,2,1)=205|") == std::string::npos ||
        partial.find("dock_size(4,1,2)=277|") != std::string::npos ||
        partial.find("dock_size(4,1,2)=310|") == std::string::npos)
        throw std::runtime_error("Existing or explicitly hidden panes must take precedence over saved state");
    if (plugin_preserve_uncreated_panes(merged, previous) != merged ||
        plugin_preserve_uncreated_panes(startup, "") != startup ||
        plugin_preserve_uncreated_panes(startup, "not a perspective") != startup ||
        plugin_preserve_uncreated_panes("bad", previous) != "bad")
        throw std::runtime_error("Pane preservation must be idempotent and leave invalid/empty layouts alone");
    std::cout << "PASS startup/partial plugin restore, current geometry precedence, associated dock sizes and repeated saves\n";
    std::cout << "PASS pane identity, duplicate suffix and escaped perspective records\n";
}
