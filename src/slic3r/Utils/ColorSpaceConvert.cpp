#include "ColorSpaceConvert.hpp"
#include <wx/colordlg.h>
#include <boost/algorithm/string.hpp>

std::string color_to_string(const wxColour &color)
{
    return wxString::Format("(%d,%d,%d)", int(color.Red()), int(color.Green()), int(color.Blue())).ToStdString();
}

wxColour string_to_wxColor(const std::string &str)
{
    wxColour color;
    std::vector<std::string> result;
    boost::split(result, str, boost::is_any_of("(,)"));
    if (result.size() >= 5) {
        color = wxColour(std::stoi(result[1]), std::stoi(result[2]), std::stoi(result[3]), std::stoi(result[4]));
    }
    return color;
}
