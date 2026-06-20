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

} // namespace Slic3r
