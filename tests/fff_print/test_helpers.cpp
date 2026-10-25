#include "test_helpers.hpp"

#include "libslic3r/TriangleMesh.hpp"
#include "libslic3r/GCodeReader.hpp"
#include "libslic3r/Config.hpp"
#include "libslic3r/Print.hpp"
#include "libslic3r/Format/OBJ.hpp"
#include "libslic3r/Format/STL.hpp"

#include <cstdlib>
#include <string>

#include <boost/filesystem.hpp>
#include <libslic3r/ModelArrange.hpp>

#include "test_utils.hpp"

using namespace std;

namespace Slic3r { namespace Test {

DynamicPrintConfig multifilament_config(unsigned int filaments, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> extra)
{
	// Single nozzle, `filaments` filaments. Colours must be DISTINCT: filament grouping
	// treats same-colour filaments as one and the tool-order path then drops/segfaults.
	static const char *palette[] = { "#FF0000", "#00FF00", "#0000FF", "#FFFF00",
	                                 "#FF00FF", "#00FFFF", "#FF8000", "#8000FF" };
	std::string diameters, colours, flush;
	for (unsigned int i = 0; i < filaments; ++i) {
		diameters += (i ? "," : "") + std::string("1.75");
		colours   += (i ? ";" : "") + std::string(palette[i % (sizeof(palette) / sizeof(palette[0]))]);
		for (unsigned int j = 0; j < filaments; ++j)
			flush += ((i || j) ? "," : "") + std::string(i == j ? "0" : "280");
	}

	DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
	config.set_deserialize_strict({ { "nozzle_diameter", "0.4" }, { "filament_diameter", diameters } });
	config.set_num_filaments(filaments);

	// These are read by filament id during export but absent from filament_option_keys(),
	// so set_num_filaments leaves them size 1; size them too, else out-of-range access.
	const auto &defaults = FullPrintConfig::defaults();
	for (const char *key : { "filament_type", "filament_vendor", "filament_start_gcode" })
		static_cast<ConfigOptionVectorBase *>(config.option(key, true))->resize(filaments, defaults.option(key));

	// flush_volumes_matrix must be sized filaments*filaments or export rejects it.
	config.set_deserialize_strict({ { "filament_colour", colours }, { "flush_volumes_matrix", flush } });

	if (extra.size() > 0)
		config.set_deserialize_strict(extra);
	return config;
}

void init_print(std::vector<TriangleMesh> &&meshes, Slic3r::Print &print, Slic3r::Model &model, const DynamicPrintConfig &config_in,
                const std::vector<std::vector<ConfigBase::SetDeserializeItem>> *per_object_overrides, bool arrange)
{
	DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.apply(config_in);
    config.set_key_value("gcode_comments", new ConfigOptionBool(true));

    size_t object_idx = 0;
    for (const TriangleMesh &t : meshes) {
		ModelObject *object = model.add_object();
		object->name += "object.stl";
		object->add_volume(std::move(t));
		object->add_instance();

		if (per_object_overrides && object_idx < per_object_overrides->size() && !(*per_object_overrides)[object_idx].empty()) {
			DynamicPrintConfig oc;
			for (const auto &item : (*per_object_overrides)[object_idx])
				oc.set_deserialize_strict(item.opt_key, item.opt_value);
			object->config.apply(oc);
		}
		++object_idx;
	}
    if (arrange)
        arrange_objects(model, InfiniteBed{}, ArrangeParams{ scaled(min_object_distance(config))});
	for (ModelObject *mo : model.objects) {
        mo->ensure_on_bed();
		print.auto_assign_extruders(mo);
    }

	print.apply(model, config);
    print.validate();
    print.set_status_silent();
}

void init_print(std::initializer_list<TestMesh> test_meshes, Slic3r::Print &print, Slic3r::Model &model, const Slic3r::DynamicPrintConfig &config_in)
{
	std::vector<TriangleMesh> triangle_meshes;
	triangle_meshes.reserve(test_meshes.size());
	for (const TestMesh test_mesh : test_meshes)
		triangle_meshes.emplace_back(mesh(test_mesh));
	init_print(std::move(triangle_meshes), print, model, config_in);
}

void init_print(std::initializer_list<TriangleMesh> input_meshes, Slic3r::Print &print, Slic3r::Model &model, const DynamicPrintConfig &config_in)
{
	std::vector<TriangleMesh> triangle_meshes;
	triangle_meshes.reserve(input_meshes.size());
	for (const TriangleMesh &input_mesh : input_meshes)
		triangle_meshes.emplace_back(input_mesh);
	init_print(std::move(triangle_meshes), print, model, config_in);
}

void init_print(std::initializer_list<TestMesh> meshes, Slic3r::Print &print, Slic3r::Model &model, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Slic3r::DynamicPrintConfig config = Slic3r::DynamicPrintConfig::full_print_config();
	config.set_deserialize_strict(config_items);
	init_print(meshes, print, model, config);
}

void init_print(std::initializer_list<TriangleMesh> meshes, Slic3r::Print &print, Slic3r::Model &model, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Slic3r::DynamicPrintConfig config = Slic3r::DynamicPrintConfig::full_print_config();
	config.set_deserialize_strict(config_items);
	init_print(meshes, print, model, config);
}

void init_and_process_print(std::initializer_list<TestMesh> meshes, Slic3r::Print &print, const DynamicPrintConfig &config)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config);
	print.process();
}

void init_and_process_print(std::initializer_list<TriangleMesh> meshes, Slic3r::Print &print, const DynamicPrintConfig &config)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config);
	print.process();
}

void init_and_process_print(std::initializer_list<TestMesh> meshes, Slic3r::Print &print, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config_items);
	print.process();
}

void init_and_process_print(std::initializer_list<TriangleMesh> meshes, Slic3r::Print &print, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Slic3r::Model model;
	init_print(meshes, print, model, config_items);
	print.process();
}

// ADAPTED (fork): the definitions of mesh_names / mesh(TestMesh) / model() / gcode() that the
// upstream original of this file carried collide at link time with the fork's canonical
// test_data.cpp fixtures (same mangled names). The fork builds both files into fff_print_tests,
// so only the fixtures unique to this file are defined here; the shared four bind to test_data.cpp.

std::string slice(std::initializer_list<TestMesh> meshes, const DynamicPrintConfig &config)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config);
	return gcode(print);
}

std::string slice(std::initializer_list<TriangleMesh> meshes, const DynamicPrintConfig &config)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config);
	return gcode(print);
}

std::string slice(std::initializer_list<TestMesh> meshes, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config_items);
	return gcode(print);
}

std::string slice(std::initializer_list<TriangleMesh> meshes, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(meshes, print, model, config_items);
	return gcode(print);
}

std::string slice_with_object_overrides(std::initializer_list<TriangleMesh> meshes, const DynamicPrintConfig &config,
	const std::vector<std::vector<ConfigBase::SetDeserializeItem>> &per_object_overrides)
{
	Slic3r::Print print;
	Slic3r::Model model;
	init_print(std::vector<TriangleMesh>(meshes), print, model, config, &per_object_overrides);
	return gcode(print);
}

std::string slice_two_cubes_arranged(std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	return slice({ cube(20), cube(20) }, config_items);
}

void place_two_cubes_apart(double gap, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items,
	Print &print, Model &model)
{
	TriangleMesh a = cube(20);
	a.translate(80, 80, 0);
	TriangleMesh b = cube(20);
	b.translate(80 + 20 + gap, 80, 0);
	std::vector<TriangleMesh> meshes;
	meshes.push_back(std::move(a));
	meshes.push_back(std::move(b));

	DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
	config.set_deserialize_strict(config_items);
	init_print(std::move(meshes), print, model, config, nullptr, /*arrange=*/false);
}

std::string slice_two_cubes_apart(double gap, std::initializer_list<Slic3r::ConfigBase::SetDeserializeItem> config_items)
{
	Print print;
	Model model;
	place_two_cubes_apart(gap, config_items, print, model);
	return gcode(print);
}

std::set<double> layers_with_role(const std::string &gcode, const std::string &role)
{
    std::set<double> layers;
    GCodeReader parser;
    parser.parse_buffer(gcode, [&layers, &role](GCodeReader &self, const GCodeReader::GCodeLine &line) {
        if (line.extruding(self) && line.comment().find(role) != std::string_view::npos)
            layers.insert(self.z());
    });
    return layers;
}

double max_z(const std::string &gcode)
{
    double z = 0.0;
    GCodeReader parser;
    parser.parse_buffer(gcode, [&z](GCodeReader &self, const GCodeReader::GCodeLine &) {
        z = std::max(z, static_cast<double>(self.z()));
    });
    return z;
}

int role_passes(const std::string &gcode, const std::string &role)
{
    int passes = 0;
    bool in_role = false;
    GCodeReader reader;
    reader.parse_buffer(gcode, [&](GCodeReader &self, const GCodeReader::GCodeLine &line) {
        if (! line.extruding(self)) return;
        const bool is_role = line.comment().find(role) != std::string_view::npos;
        if (is_role && ! in_role) ++passes;
        in_role = is_role;
    });
    return passes;
}

std::vector<std::string> role_sequence(const std::string &gcode, const std::vector<std::string> &roles)
{
    std::vector<std::string> seq;
    std::string current;
    GCodeReader reader;
    reader.parse_buffer(gcode, [&](GCodeReader &self, const GCodeReader::GCodeLine &line) {
        if (! line.extruding(self)) return;
        const std::string_view comment = line.comment();
        for (const std::string &role : roles)
            if (comment.find(role) != std::string_view::npos) {
                if (current != role) { seq.push_back(role); current = role; }
                break;
            }
    });
    return seq;
}

} } // namespace Slic3r::Test

#include <catch2/catch_all.hpp>

SCENARIO("init_print functionality", "[test_helpers]") {
	GIVEN("A default config") {
		Slic3r::DynamicPrintConfig config = Slic3r::DynamicPrintConfig::full_print_config();
		WHEN("init_print is called with a single mesh.") {
			Slic3r::Model model;
			Slic3r::Print print;
			Slic3r::Test::init_print({ Slic3r::Test::cube(20) }, print, model, config);
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
