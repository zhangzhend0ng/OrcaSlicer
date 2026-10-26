// Bounded NumPy bulk and same-process lifecycle observations, not a leak proof.
#include "libslic3r/TriangleMesh.hpp"
#include "libslic3r/Polygon.hpp"
#include "libslic3r/Utils.hpp"
#include "slic3r/plugin/PluginManager.hpp"
#include "slic3r/plugin/PluginDependencyInstaller.hpp"
#include "slic3r/plugin/PythonInterpreter.hpp"
#include <pybind11/embed.h>
#include <pybind11/numpy.h>
#include <boost/log/core.hpp>
#include <boost/nowide/args.hpp>
#include <boost/nowide/filesystem.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <stdexcept>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <psapi.h>
#elif defined(__APPLE__)
#include <mach/mach.h>
#elif defined(__linux__)
#include <unistd.h>
#endif
using namespace Slic3r;
namespace bulk_fs = std::filesystem;
namespace py = pybind11;
using json = nlohmann::json;
using Clock = std::chrono::steady_clock;
namespace {
void require(bool ok,const std::string& what){if(!ok)throw std::runtime_error(what);}
void save(const bulk_fs::path& p,const json& value){std::ofstream f(p);require(bool(f),"Cannot write report");f<<value.dump(2)<<'\n';}
template<class F> double duration_ms(F fn){auto start=Clock::now();fn();return std::chrono::duration<double,std::milli>(Clock::now()-start).count();}
json memory()
{
    json result;
#if defined(_WIN32)
    PROCESS_MEMORY_COUNTERS_EX counters{};
    counters.cb = static_cast<DWORD>(sizeof(counters));
    require(GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),
                                 static_cast<DWORD>(sizeof(counters))) != 0, "Cannot sample current process memory");
    result={{"rss_bytes", counters.WorkingSetSize}, {"private_commit_bytes", counters.PrivateUsage},
            {"source", "GetProcessMemoryInfo current WorkingSetSize / PrivateUsage; private commit is not resident memory"}};
#elif defined(__APPLE__)
    mach_task_basic_info_data_t basic{};mach_msg_type_number_t count=MACH_TASK_BASIC_INFO_COUNT;
    require(task_info(mach_task_self(),MACH_TASK_BASIC_INFO,reinterpret_cast<task_info_t>(&basic),&count)==KERN_SUCCESS,"Cannot sample current RSS");
    task_vm_info_data_t vm{};count=TASK_VM_INFO_COUNT;
    require(task_info(mach_task_self(),TASK_VM_INFO,reinterpret_cast<task_info_t>(&vm),&count)==KERN_SUCCESS,"Cannot sample footprint");
    result={{"rss_bytes",basic.resident_size},{"phys_footprint_bytes",vm.phys_footprint},
            {"source","mach task_info current resident_size / phys_footprint; not ru_maxrss"}};
#elif defined(__linux__)
    std::ifstream f("/proc/self/statm");uint64_t virtual_pages=0,resident_pages=0;f>>virtual_pages>>resident_pages;
    require(bool(f),"Cannot sample current RSS");result={{"rss_bytes",resident_pages*uint64_t(sysconf(_SC_PAGESIZE))},{"source","/proc/self/statm current resident pages"}};
#else
    throw std::runtime_error("Current-RSS sampler is not implemented on this platform");
#endif
    return result;
}
std::shared_ptr<TriangleMesh> grid(int side)
{
    indexed_triangle_set its;its.vertices.reserve(size_t(side+1)*size_t(side+1));its.indices.reserve(size_t(side)*size_t(side)*2);
    for(int y=0;y<=side;++y)for(int x=0;x<=side;++x)its.vertices.emplace_back(float(x),float(y),0.f);
    for(int y=0;y<side;++y)for(int x=0;x<side;++x){int a=y*(side+1)+x,b=a+1,c=a+side+1,d=c+1;its.indices.emplace_back(a,b,d);its.indices.emplace_back(a,d,c);}
    return std::make_shared<TriangleMesh>(std::move(its));
}
json python_counts(bool consume_watch)
{
    PythonGILState gil;require(bool(gil),"No GIL");
    auto gc=py::module_::import("gc"),sys=py::module_::import("sys"),builtins=py::module_::import("builtins");
    json result;result["gc_collected"]=gc.attr("collect")().cast<size_t>();
    if(consume_watch){
        py::dict watch=builtins.attr("_orca_bulk_watch");py::list refs=watch["refs"];
        size_t alive=0;for(py::handle ref:refs)if(!ref().is_none())++alive;
        result["observed_weakrefs"]=py::len(refs);result["alive_weakrefs"]=alive;
        result["unload_calls"]=watch["unload_calls"].cast<int>();
        py::delattr(builtins,"_orca_bulk_watch");
    }
    size_t modules=0;py::dict module_dict=sys.attr("modules");
    for(auto item:module_dict){auto name=py::str(item.first).cast<std::string>();if(name=="orca_benchmark_bulk"||name.find("orca_benchmark_bulk.")==0)++modules;}
    result["plugin_module_count"]=modules;
    result["gc_tracked_objects"]=py::len(gc.attr("get_objects")());
    result["python_allocated_blocks"]=sys.attr("getallocatedblocks")().cast<size_t>();
    return result;
}
}
int main(int argc,char**argv)
{
    boost::nowide::args utf8(argc,argv);boost::nowide::nowide_filesystem();if(argc!=3)return 2;
    json plan;{std::ifstream f(bulk_fs::u8path(argv[1]));if(!f)return 2;f>>plan;}
    const std::string mode=plan.at("mode");const bool prepare=mode=="prepare";
    const auto profile=bulk_fs::u8path(plan.at("profile").get<std::string>()),output=bulk_fs::u8path(argv[2]);
    const auto wheelhouse=bulk_fs::u8path(plan.at("wheelhouse").get<std::string>()),wheel=bulk_fs::u8path(plan.at("wheel").get<std::string>());
    const int side=plan.value("side",512),warmups=plan.value("warmups",10),cycles=plan.value("cycles",100);
    if((mode!="prepare"&&mode!="run")||side<4||side>1024||side%2||warmups<0||warmups>100||cycles<1||cycles>1000||bulk_fs::exists(output))return 2;
    if(!prepare&&!plan.value("validation_only",false)&&!plan.value("idle_confirmed",false))return 2;
    const auto marker=profile/"numpy-bulk-profile.json";
    if(prepare){if(bulk_fs::exists(profile))return 3;bulk_fs::create_directories(profile);save(marker,{{"schema",1},{"purpose","isolated-numpy-bulk"}});}
    else {std::ifstream f(marker);json marker_data;if(!f)return 3;f>>marker_data;if(marker_data.value("purpose","")!="isolated-numpy-bulk")return 3;}
    bulk_fs::create_directories(output.parent_path());set_data_dir(profile.u8string());boost::log::core::get()->set_logging_enabled(false);
    json report={{"schema",1},{"mode",mode},{"passed",false},{"validation_only",plan.value("validation_only",false)},
        {"scope","same-process bounded actual runtime / NumPy / capability lifecycle; no GUI or unbounded leak claim"},
        {"timing_scope","warm within-process callback batches; not independent cold processes"},
        {"sampling_policy","current RSS before load / after load / after execute / after unload / after gc and released native polygon; no allocator pressure relief"},
        {"measurement_overhead","one transient JSON record and weakref list per cycle; samples stream to disk, not retained in native memory"}};
    auto& manager=PluginManager::instance();int exit_code=0;
    try{
        report["initialize_ms"]=duration_ms([&]{require(manager.initialize(),PythonInterpreter::instance().last_error());});
        std::string error;
        require(plugin_loader::configure_dependency_install({true,wheelhouse.u8string()},error),error);
        if(prepare){
            report["offline_install_excluded_ms"]=duration_ms([&]{require(plugin_loader::install_packages({"numpy==2.2.6"},error),error);PluginDescriptor descriptor;require(manager.install_plugin(wheel.u8string(),descriptor,error),error);});
        }
        manager.discover_plugins(false,true);require(manager.get_discovery_error().empty(),manager.get_discovery_error());
        const auto descriptors=manager.get_plugin_descriptors();require(descriptors.size()==1,"Expected one isolated benchmark package");
        const auto key=descriptors.front().plugin_key;report["plugin_key"]=key;
        manager.wait_for_all_plugin_loads();if(manager.is_plugin_loaded(key))require(manager.unload_plugin(key),"Initial package unload failed");
        {PythonGILState gil;require(bool(gil),"No NumPy GIL");auto np=py::module_::import("numpy");report["numpy_version"]=np.attr("__version__").cast<std::string>();report["numpy_file"]=np.attr("__file__").cast<std::string>();require(report["numpy_version"]=="2.2.6","Unexpected NumPy version");}
        if(!prepare){
            auto mesh=grid(side);report["shape"]={{"side",side},{"vertices",mesh->its.vertices.size()},{"triangles",mesh->its.indices.size()},
                {"native_mesh_bytes",mesh->its.vertices.size()*sizeof(stl_vertex)+mesh->its.indices.size()*sizeof(stl_triangle_vertex_indices)},
                {"polygon_points",side*side},{"warmups",warmups},{"measured_cycles",cycles}};
            report["python_baseline"]=python_counts(false);report["memory_baseline"]=memory();
            const auto samples_path=bulk_fs::path(output.u8string()+".samples.jsonl");std::ofstream samples(samples_path);require(bool(samples),"Cannot open samples");report["samples_file"]=samples_path.u8string();
            for(int cycle=-warmups;cycle<cycles;++cycle){
                json sample={{"cycle",cycle},{"warmup",cycle<0},{"passed",false}};
                try {
                sample["memory"]["before_load"]=memory();
                sample["load_ms"]=duration_ms([&]{manager.load_plugin(key);require(manager.wait_for_plugin_load(key,std::chrono::seconds(45),error),error);});
                sample["memory"]["after_load"]=memory();
                std::weak_ptr<PluginCapabilityInterface> capability;
                {const auto caps=manager.get_plugin_capabilities(key);require(caps.size()==1,"Capability inventory mismatch");capability=caps.front();}
                // ADAPTED: qualified for this tree's header set, where the libslic3r umbrella
                // also exposes ClipperLib::Polygon (ambiguous under `using namespace Slic3r`).
                auto polygon=std::make_unique<Slic3r::Polygon>();
                {PythonGILState gil;require(bool(gil),"No configure GIL");auto module=py::module_::import("orca_benchmark_bulk");auto builtins=py::module_::import("builtins");py::dict watch;watch["refs"]=py::list();watch["unload_calls"]=0;builtins.attr("_orca_bulk_watch")=watch;
                    module.attr("configure")(py::cast(mesh),py::cast(polygon.get(),py::return_value_policy::reference),side,watch);}
                ExecutionResult result;
                sample["dispatch_execute_ms"]=duration_ms([&]{result=manager.run_script_capability(key,"Benchmark NumPy Bulk",error);require(error.empty()&&result.status==PluginResult::Success,"Bulk callback: "+error+" "+result.message);});
                sample["bulk"]=json::parse(result.data);require(sample["bulk"].value("passed",false),"Callback correctness failed");
                const int64_t n=int64_t(side)*side,k=n/4;int64_t sum=0;for(const auto& p:polygon->points)sum+=p.x()+p.y();
                require(polygon->points.size()==size_t(n)&&polygon->points.front()==Point(7,-11)&&polygon->points.back()==Point(7,-10)&&sum==n*(k-4),"Native consumer rejected NumPy polygon writeback");
                sample["native_polygon_checksum"]=sum;sample["mesh_owners_after_execute"]=mesh.use_count();sample["memory"]["after_execute"]=memory();
                sample["unload_ms"]=duration_ms([&]{require(manager.unload_plugin(key),"Real package unload failed");});
                sample["memory"]["after_unload_before_gc"]=memory();sample["python"]=python_counts(true);
                require(sample["python"]["alive_weakrefs"]==0&&sample["python"]["plugin_module_count"]==0&&sample["python"]["unload_calls"]==1,"Python owners or plugin namespace survived unload/GC");
                require(capability.expired()&&mesh.use_count()==1&&!manager.is_plugin_loaded(key)&&manager.get_plugin_capabilities(key).empty(),"Native owners or capability registry survived cleanup");
                sample["native_capability_expired"]=true;sample["mesh_owners_after_cleanup"]=mesh.use_count();polygon.reset();
                std::this_thread::sleep_for(std::chrono::milliseconds(20));sample["memory"]["after_cleanup"]=memory();sample["passed"]=true;
                } catch (const std::exception& error) {
                    sample["error"]=error.what(); samples<<sample.dump()<<'\n'; samples.flush(); throw;
                }
                samples<<sample.dump()<<'\n';samples.flush();require(bool(samples),"Cannot persist sample");
            }
        }
        report["passed"]=true;
    }catch(const std::exception& e){report["error"]=e.what();exit_code=1;}
    report["manager_shutdown_ms"]=duration_ms([&]{manager.shutdown();});
    report["interpreter_shutdown_ms"]=duration_ms([&]{PythonInterpreter::instance().shutdown();});
    report["memory_after_shutdown"]=memory();save(output,report);std::cout<<(exit_code?"FAIL":"PASS")<<" numpy bulk "<<mode<<'\n';return exit_code;
}
