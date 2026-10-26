#include "slic3r/plugin/PluginManager.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include "libslic3r/Utils.hpp"
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <boost/nowide/filesystem.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>
using namespace Slic3r;
namespace wheel_fs = std::filesystem;
using json = nlohmann::json;
namespace {
void require(bool value,const std::string& message) { if(!value) throw std::runtime_error(message); }
void write(const wheel_fs::path& path,const json& data) { std::ofstream out(path);out<<data.dump(2)<<'\n';require(bool(out),"write observation"); }
std::string bytes(const wheel_fs::path& path) { std::ifstream in(path,std::ios::binary);return {std::istreambuf_iterator<char>(in),{}}; }
json contents(const wheel_fs::path& root) {
    json out=json::object();if(!wheel_fs::exists(root))return out;
    for(const auto& e:wheel_fs::recursive_directory_iterator(root))if(e.is_regular_file())out[e.path().lexically_relative(root).u8string()]=wheel_fs::file_size(e.path());
    return out;
}
}
int main(int argc,char** argv) {
    boost::nowide::args utf8(argc,argv);boost::nowide::nowide_filesystem();
    if(argc!=5)return 2;
    boost::log::core::get()->set_logging_enabled(false);
    const std::string scenario=argv[1];const wheel_fs::path fixtures=wheel_fs::u8path(argv[2]),profile=wheel_fs::u8path(argv[3]),output=wheel_fs::u8path(argv[4]);
    json result{{"scenario",scenario},{"passed",false},{"observations",json::array()},{"failures",json::array()}};
    auto& manager=PluginManager::instance();bool initialized=false;
    const auto check=[&](bool value,const std::string& message) { if(!value)result["failures"].push_back(message); };
    try {
        const bool restart = scenario == "entry_restart";
        const bool case_alias = scenario == "entry_case_alias";
        require(restart ? wheel_fs::is_directory(profile) : !wheel_fs::exists(profile), "fresh isolated profile required (restart reuses an entry profile)");
        wheel_fs::create_directories(profile);set_data_dir(profile.u8string());
        bool case_insensitive = false;
        if (case_alias) {
            const auto probe = profile / "CaseSensitivityProbe";
            std::ofstream(probe) << "probe";
            case_insensitive = wheel_fs::exists(profile / "casesensitivityprobe");
            wheel_fs::remove(probe);
            result["filesystem_case_insensitive"] = case_insensitive;
        }
        require(manager.initialize(),PythonInterpreter::instance().last_error());initialized=true;manager.discover_plugins();
        const bool dependency=scenario.rfind("dependency_",0)==0,legacy=scenario.find("legacy")!=std::string::npos;
        const bool reject_bad = !legacy && (!case_alias || case_insensitive);
        const std::string module=dependency?"cachedep":"cacheprobe",filename=module+"-1.0.0-py3-none-any.whl";
        const auto input=fixtures/scenario;PluginDescriptor entry;std::string error;
        if (restart) {
            const auto entries = manager.get_plugin_descriptors();
            require(entries.size() == 1, "restart requires one installed entry wheel");
            entry = entries.front();
        } else {
            require(manager.install_plugin((dependency?input/"consumer.py":input/"bad"/filename).u8string(),entry,error),"install: "+error);manager.rescan_plugins();
        }
        const wheel_fs::path installed=dependency?wheel_fs::u8path(entry.plugin_root)/filename:wheel_fs::u8path(entry.entry_path);
        if(dependency)wheel_fs::copy_file(input/"bad"/filename,installed);
        const auto cache=installed.parent_path()/"__whl_extracted__"/(dependency?installed.stem():wheel_fs::path(module));
        if(legacy) {
            // A real successful extraction with no new marker models the old
            // format; then remove an actual required resource before first load.
            require(extract_zip_to_directory((input/"good"/filename).u8string(),cache.u8string(),error),error);
            wheel_fs::remove(cache/module/"resource.txt");
        }
        const auto load=[&](const char* phase) {
            error.clear();manager.load_plugin(entry.plugin_key,true);
            const bool loaded=manager.wait_for_plugin_load(entry.plugin_key,std::chrono::seconds(30),error);
            require(loaded==manager.is_plugin_loaded(entry.plugin_key),"load observation mismatch");
            json observation{{"phase",phase},{"loaded",loaded},{"error",error},{"cache_exists",wheel_fs::exists(cache)},{"cache_files",contents(cache)}};
            std::string payload;
            if(loaded) {
                std::string execute_error;const auto returned=manager.run_script_capability(entry.plugin_key,"Wheel cache probe",execute_error);
                require(execute_error.empty() && returned.status==PluginResult::Success,"actual callback: "+execute_error);
                payload=returned.data;observation["actual_callback_data"]=payload;
                require(manager.unload_plugin(entry.plugin_key),"unload real callback");
            }
            result["observations"].push_back(observation);write(output,result);
            return std::pair<bool,std::string>{loaded,payload};
        };
        if (restart) {
            const auto file = cache / module / "resource.txt";
            const auto before = wheel_fs::last_write_time(file);
            const auto loaded = load("cross_process_complete_cache_reuse");
            check(loaded.first && loaded.second == "UPDATED", "cross-process cache callback differs");
            check(wheel_fs::last_write_time(file) == before, "cross-process complete cache was rewritten");
        } else {
        if (case_alias && !case_insensitive) {
            const auto distinct = load("distinct_case_sensitive_entries");
            check(distinct.first && distinct.second == "ORIGINAL" && bytes(cache / module / "RESOURCE.TXT") == "COLLISION",
                  "case-sensitive filesystem did not preserve both distinct wheel entries");
            wheel_fs::copy_file(input / "good" / filename, installed, wheel_fs::copy_options::overwrite_existing);
        }
        if(reject_bad) {
            const auto first=load("first_corrupt_load");check(!first.first,"first corrupt archive unexpectedly loaded");
            if(wheel_fs::exists(cache))wheel_fs::copy(cache,output.parent_path()/(scenario+"-first-failed-cache"),wheel_fs::copy_options::recursive);
            check(!wheel_fs::exists(cache),"failed extraction published a partial final cache");
            const auto second=load("same_corrupt_retry");check(!second.first,"retry imported a failed extraction cache");
            wheel_fs::copy_file(input/"good"/filename,installed,wheel_fs::copy_options::overwrite_existing);
        }
        const auto repaired=load(legacy?"legacy_unmarked_cache_recovery":"good_archive_repair");
        check(repaired.first && repaired.second==(legacy?"ORIGINAL":"COMPLETE"),"valid archive did not rebuild complete bytes");
        const auto file=cache/module/"resource.txt";const auto before=wheel_fs::exists(file)?wheel_fs::last_write_time(file):wheel_fs::file_time_type{};
        const auto warm=load("complete_cache_reuse");check(warm==repaired,"warm cached module changed");
        check(wheel_fs::exists(file)&&wheel_fs::last_write_time(file)==before,"valid complete cache was unnecessarily rewritten");
        if (reject_bad) {
            wheel_fs::copy_file(input / "bad" / filename, installed, wheel_fs::copy_options::overwrite_existing);
            const auto rejected = load("corrupt_replacement_rejected");
            check(!rejected.first && bytes(file) == repaired.second, "corrupt wheel replacement consumed or damaged the old complete cache");
            wheel_fs::copy_file(input / "good" / filename, installed, wheel_fs::copy_options::overwrite_existing);
            check(load("restored_archive_reuse") == repaired, "restoring valid wheel lost the old complete cache");
        }
        std::ofstream(file, std::ios::binary | std::ios::trunc) << "X";
        check(load("truncated_cached_resource_recovery") == repaired, "truncated cached resource was trusted");
        std::ofstream(cache / ".orca-wheel-cache.json", std::ios::trunc) << "{invalid completion record";
        check(load("invalid_completion_record_recovery") == repaired, "invalid completion record was trusted");
        wheel_fs::remove(file);const auto missing=load("missing_cached_resource_recovery");
        check(missing==repaired,"missing cached resource was trusted");
        wheel_fs::copy_file(input/"updated"/filename,installed,wheel_fs::copy_options::overwrite_existing);
        const auto updated=load("changed_archive_recovery");check(updated.first&&updated.second=="UPDATED","changed wheel reused stale cache");
        // Generic extraction must preserve an existing complete destination on failure.
        const auto previous=profile/"atomic-extract";wheel_fs::create_directories(previous);std::ofstream(previous/"sentinel")<<"old intact";
        if(reject_bad) {
            error.clear();const bool ok=extract_zip_to_directory((input/"bad"/filename).u8string(),previous.u8string(),error);
            check(!ok && contents(previous)==json{{"sentinel",10}} && bytes(previous/"sentinel")=="old intact","failed extraction modified a preexisting directory");
        }
        } // Initial recovery scenarios; restart only validates persistence/reuse.
        result["passed"]=result["failures"].empty();result["cache_path"]=cache.u8string();result["installed_wheel"]=installed.u8string();
    } catch(const std::exception& e) { result["fatal_error"]=e.what(); }
    if(initialized)manager.shutdown();PythonInterpreter::instance().shutdown();
    result["interpreter_stopped"]=!PythonInterpreter::instance().is_initialized();write(output,result);
    std::cout<<(result["passed"].get<bool>()?"PASS ":"FAIL ")<<scenario<<'\n';return result["passed"].get<bool>()?0:1;
}
