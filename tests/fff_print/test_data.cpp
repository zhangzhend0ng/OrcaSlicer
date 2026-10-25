#include "test_data.hpp"

#include "libslic3r/TriangleMesh.hpp"
#include "libslic3r/GCodeReader.hpp"
#include "libslic3r/Config.hpp"
#include "libslic3r/Print.hpp"
#include "libslic3r/Format/OBJ.hpp"
#include "libslic3r/Format/STL.hpp"

#include <cstdlib>
#include <fstream>
#include <string>

#include <boost/nowide/cstdio.hpp>
#include <boost/filesystem.hpp>
#include <libslic3r/ModelArrange.hpp>

using namespace std;

namespace Slic3r { namespace Test {

DynamicPrintConfig default_print_config()
{
    const FullPrintConfig &defaults = FullPrintConfig::defaults();
    DynamicPrintConfig config;
    config.apply(static_cast<const PrintObjectConfig &>(defaults), true);
    config.apply(static_cast<const PrintRegionConfig &>(defaults), true);
    config.apply(static_cast<const PrintConfig &>(defaults), true);
    return config;
}

static bool verbose_gcode() 
{
    const char *v = std::getenv("SLIC3R_TESTS_GCODE");
    if (v == nullptr)
    	return false;
    std::string s(v);
    return s == "1" || s == "on" || s == "yes";
}

void init_print(std::vector<TriangleMesh> &&meshes, Slic3r::Print &print, Slic3r::Model &model, const DynamicPrintConfig &config_in, bool comments)
{
	DynamicPrintConfig config = default_print_config();
    config.apply(config_in);

    if (verbose_gcode())
        config.set_key_value("gcode_comments", new ConfigOptionBool(true));

    for (const TriangleMesh &t : meshes) {
		ModelObject *object = model.add_object();
		object->name += "object.stl";
		object->add_volume(std::move(t));
		object->add_instance();
	}
    arrange_objects(model, get_bed_shape(config), ArrangeParams{ scaled(min_object_distance(config))}, [](arrangement::ArrangePolygon&) {});
	for (ModelObject *mo : model.objects) {
        mo->ensure_on_bed();
		print.auto_assign_extruders(mo);
    }

	print.apply(model, config);
    print.validate();
    print.set_status_silent();
}

void init_print(std::initializer_list<TestMesh> test_meshes, Slic3r::Print &print, Slic3r::Model &model, const Slic3r::DynamicPrintConfig &config_in, bool comments)
{
	std::vector<TriangleMesh> triangle_meshes;
	triangle_meshes.reserve(test_meshes.size());
	for (const TestMesh test_mesh : test_meshes)
		triangle_meshes.emplace_back(mesh(test_mesh));
	init_print(std::move(triangle_meshes), print, model, config_in, comments);
}

void init_print(std::initializer_list<TriangleMesh> input_meshes, Slic3r::Print &print, Slic3r::Model &model, const DynamicPrintConfig &config_in, bool comments)
{
	std::vector<TriangleMesh> triangle_meshes;
	triangle_meshes.reserve(input_meshes.size());
	for (const TriangleMesh &input_mesh : input_meshes)
		triangle_meshes.emplace_back(input_mesh);
	init_print(std::move(triangle_meshes), print, model, config_in, comments);
}

void init_print(std::initializer_list<TestMesh> meshes, Slic3r::Print &print, Slic3r::Model &model, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items, bool comments)
{
	Slic3r::DynamicPrintConfig config = default_print_config();
	config.set_deserialize_strict(config_items);
	init_print(meshes, print, model, config, comments);
}

void init_print(std::initializer_list<TriangleMesh> meshes, Slic3r::Print &print, Slic3r::Model &model, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items, bool comments)
{
	Slic3r::DynamicPrintConfig config = default_print_config();
	config.set_deserialize_strict(config_items);
	init_print(meshes, print, model, config, comments);
}

void init_and_process_print(std::initializer_list<TestMesh> meshes, Slic3r::Print &print, const DynamicPrintConfig &config, bool comments)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config, comments);
	print.process();
}

void init_and_process_print(std::initializer_list<TriangleMesh> meshes, Slic3r::Print &print, const DynamicPrintConfig &config, bool comments)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config, comments);
	print.process();
}

void init_and_process_print(std::initializer_list<TestMesh> meshes, Slic3r::Print &print, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items, bool comments)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config_items, comments);
	print.process();
}

void init_and_process_print(std::initializer_list<TriangleMesh> meshes, Slic3r::Print &print, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items, bool comments)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config_items, comments);
	print.process();
}

std::string slice(std::initializer_list<TestMesh> meshes, const DynamicPrintConfig &config, bool comments)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config, comments);
	return gcode(print);
}

std::string slice(std::initializer_list<TriangleMesh> meshes, const DynamicPrintConfig &config, bool comments)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config, comments);
	return gcode(print);
}

std::string slice(std::initializer_list<TestMesh> meshes, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items, bool comments)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config_items, comments);
	return gcode(print);
}

std::string slice(std::initializer_list<TriangleMesh> meshes, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items, bool comments)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config_items, comments);
	return gcode(print);
}

} } // namespace Slic3r::Test

#include <catch2/catch_test_macros.hpp>

SCENARIO("init_print functionality", "[test_data]") {
	GIVEN("A default config") {
		Slic3r::DynamicPrintConfig config = Slic3r::Test::default_print_config();
		WHEN("init_print is called with a single mesh.") {
			Slic3r::Model model;
			Slic3r::Print print;
			Slic3r::Test::init_print({ Slic3r::Test::TestMesh::cube_20x20x20 }, print, model, config, true);
			THEN("One mesh/printobject is in the resulting Print object.") {
				REQUIRE(print.objects().size() == 1);
			}
			THEN("print.process() doesn't crash.") {
				REQUIRE_NOTHROW(print.process());
			}
			THEN("Export gcode functions outputs text.") {
				REQUIRE(! Slic3r::Test::gcode(print).empty());
			}
#if 0
			THEN("Embedded meshes exported") {
				std::string path = "C:\\data\\temp\\embedded_meshes\\";
				for (auto kvp : Slic3r::Test::mesh_names) {
					Slic3r::TriangleMesh m = mesh(kvp.first);
					std::string name = kvp.second;
					REQUIRE(Slic3r::store_stl((path + name + ".stl").c_str(), &m, true) == true);
					REQUIRE(Slic3r::store_obj((path + name + ".obj").c_str(), &m) == true);
				}
			}
#endif
		}
	}
}
