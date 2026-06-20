#include "slic3r/App/GeometryValidationModel.hpp"

#include <cmath>
#include <algorithm>
#include <boost/algorithm/string.hpp>

namespace Slic3r {

bool GeometryValidationModel::isLeftHanded(const Transform3d::ConstLinearPart& m)
{
    return m.determinant() < 0;
}

bool GeometryValidationModel::isLeftHanded(const Transform3d& m)
{
    return isLeftHanded(m.linear());
}

bool GeometryValidationModel::isRotationXYSynchronized(
    const Transform3d& rot_xyz_from,
    const Transform3d& rot_xyz_to)
{
    const Eigen::AngleAxisd angle_axis(
        (rot_xyz_from * rot_xyz_to.inverse()).rotation());
    const Vec3d  axis  = angle_axis.axis();
    const double angle = angle_axis.angle();

    if (std::abs(angle) < 1e-8)
        return true;

    // Rotation should be purely around Z axis
    return std::abs(axis.x()) < 1e-8 &&
           std::abs(axis.y()) < 1e-8 &&
           std::abs(std::abs(axis.z()) - 1.0) < 1e-8;
}

std::string GeometryValidationModel::localeToApiFormat(std::string langCode)
{
    boost::replace_all(langCode, "_", "-");
    return langCode;
}


std::string GeometryValidationModel::decodePathExtra(const std::string& extra)
{
    // Original from GUI_App.cpp L1372
    // Parses UPX-style encoded path data: marker [u][p][len_lo][len_hi]...[0x01]...data...
    const char* p = extra.data();
    const char* e = p + extra.length();
    while (p + 4 < e) {
        auto len = static_cast<uint16_t>(
            (static_cast<uint16_t>(static_cast<unsigned char>(p[2]))) |
            (static_cast<uint16_t>(static_cast<unsigned char>(p[3])) << 8));
        if (p[0] == 'u' && p[1] == 'p' && len >= 5 &&
            p + 4 + len < e && p[4] == '') {
            return std::string(p + 9, p + 4 + len);
        } else {
            p += 4 + len;
        }
    }
    return extra;
}

} // namespace Slic3r
