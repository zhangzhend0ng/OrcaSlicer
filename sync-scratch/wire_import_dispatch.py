import io

p = 'src/slic3r/GUI/Plater.cpp'
s = io.open(p, encoding='utf-8').read()

# --- include the importer capability type next to PluginManager ---
old_inc = '#include <slic3r/plugin/PluginManager.hpp>'
new_inc = ('#include <slic3r/plugin/PluginManager.hpp>\n'
           '#include <slic3r/plugin/pluginTypes/importer/ImporterPluginCapability.hpp>')
assert s.count(old_inc) == 1
s = s.replace(old_inc, new_inc)

# --- dispatch table: built once per load_files call, before the per-file loop ---
old_tbl = ('    auto *new_model = (!load_model || one_by_one) ? nullptr : new Slic3r::Model();\n'
           '    std::vector<size_t> obj_idxs;')
new_tbl = '''    auto *new_model = (!load_model || one_by_one) ? nullptr : new Slic3r::Model();
    std::vector<size_t> obj_idxs;

    // Plugin importer claims, resolved once before the loop so dispatch never touches the
    // registry lock (or the GIL) per file. Built-in loaders always win: the set below is
    // Model::read_from_file's branch list plus the STEP branch this function handles above.
    // Same-extension plugin conflicts resolve to the first registered, with a log line.
    std::map<std::string, std::shared_ptr<ImporterPluginCapability>> plugin_importers;
    {
        static const std::set<std::string> builtin_model_extensions = {
            ".stl", ".oltp", ".obj", ".svg", ".amf", ".3mf",
            ".usd", ".usda", ".usdc", ".usdz", ".abc", ".ply", ".stp", ".step",
        };
        for (const auto& cap : Slic3r::PluginManager::instance().get_plugin_capabilities(
                 "", PluginCapabilityType::Importer, /*only_enabled=*/true)) {
            auto* importer = dynamic_cast<ImporterPluginCapability*>(cap.get());
            if (importer == nullptr)
                continue;
            for (const std::string& ext : importer->supported_extensions()) {
                if (builtin_model_extensions.count(ext) > 0) {
                    BOOST_LOG_TRIVIAL(warning)
                        << "Plugin importer '" << importer->name() << "' claims built-in extension '"
                        << ext << "'; the built-in loader wins";
                    continue;
                }
                if (plugin_importers.emplace(ext, std::shared_ptr<ImporterPluginCapability>(cap, importer)).second ==
                    false)
                    BOOST_LOG_TRIVIAL(warning)
                        << "Multiple plugin importers claim '" << ext << "'; the first registered wins";
            }
        }
    }'''
assert s.count(old_tbl) == 1
s = s.replace(old_tbl, new_tbl)

# --- guard inside the read_from_file else branch ---
old_else = '                }else {\n                    model = Slic3r::Model:: read_from_file('
new_else = '''                }else {
                    bool handled_by_plugin_importer = false;
                    if (!plugin_importers.empty()) {
                        const std::string ext = boost::to_lower_copy(boost::filesystem::extension(path).string());
                        const auto  claimed   = plugin_importers.find(ext);
                        if (claimed != plugin_importers.end()) {
                            // Run the conversion on a worker thread and block WITHOUT pumping the
                            // wx queue (the batch-3 review contract: never call plugin Python on
                            // the UI thread, and never pump events under the modal load dialog --
                            // its Cancel is unresponsive for the conversion itself). The trampoline
                            // takes the GIL on the worker. A plugin raise travels through the
                            // promise into future.get() and lands in the catch below, exactly like
                            // a built-in loader failure.
                            std::promise<ExecutionResult> import_promise;
                            auto                        import_future = import_promise.get_future();
                            std::thread import_worker([&claimed, &path, &import_promise] {
                                try {
                                    import_promise.set_value(claimed->second->import_file(path.string()));
                                } catch (...) {
                                    import_promise.set_exception(std::current_exception());
                                }
                            });
                            ExecutionResult imported = import_future.get();
                            import_worker.join();
                            if (imported.status == PluginResult::Success) {
                                std::vector<std::string> produced;
                                std::string              import_error;
                                try {
                                    const auto payload = nlohmann::json::parse(imported.data);
                                    if (payload.is_object() && payload.contains("files") && payload["files"].is_array())
                                        for (const auto& f : payload["files"])
                                            if (f.is_string())
                                                produced.push_back(f.get<std::string>());
                                } catch (const std::exception&) {
                                    import_error = "importer returned an invalid result payload";
                                }
                                // Validate every produced file before anything touches the scene:
                                // host-loadable mesh formats only, and each inside the plugin's own
                                // storage (the plugin's write root; nothing outside it is accepted).
                                if (import_error.empty() && produced.empty())
                                    import_error = "importer returned no files";
                                if (import_error.empty()) {
                                    std::string storage_error;
                                    const boost::filesystem::path storage_root = boost::filesystem::path(
                                        Slic3r::PluginManager::instance().get_storage_dir(claimed->second->audit_plugin_key()));
                                    for (const std::string& f : produced) {
                                        const boost::filesystem::path produced_path(f);
                                        const std::string produced_ext = boost::to_lower_copy(produced_path.extension().string());
                                        if (produced_ext != ".stl" && produced_ext != ".obj" && produced_ext != ".3mf") {
                                            storage_error = "importer produced a non mesh file (" + produced_ext + ")";
                                            break;
                                        }
                                        boost::system::error_code ec;
                                        const boost::filesystem::path resolved = boost::filesystem::weakly_canonical(produced_path, ec);
                                        if (ec || !boost::filesystem::is_regular_file(resolved)) {
                                            storage_error = "importer produced a missing file (" + f + ")";
                                            break;
                                        }
                                        // Lexical containment under the plugin storage root.
                                        if (std::distance(storage_root.begin(), storage_root.end()) >
                                            std::distance(resolved.begin(), resolved.end()) ||
                                            !std::equal(storage_root.begin(), storage_root.end(), resolved.begin())) {
                                            storage_error = "importer produced a file outside its storage (" + f + ")";
                                            break;
                                        }
                                    }
                                    import_error = storage_error;
                                }
                                if (!import_error.empty()) {
                                    GUI::show_error(q, import_error);
                                } else {
                                    // Load the converted files through the public path once this
                                    // load finishes: re-entering load_files here (nested modal
                                    // dialogs and shared per-load state) is unsafe, CallAfter keeps
                                    // one load at a time. The original file reports no added indices.
                                    const std::vector<std::string> to_load = std::move(produced);
                                    GUI::wxGetApp().CallAfter([q, to_load] {
                                        q->load_files(to_load, LoadStrategy::LoadModel | LoadStrategy::AddDefaultInstances);
                                    });
                                }
                                handled_by_plugin_importer = true;
                            } else if (imported.status == PluginResult::Skipped) {
                                // The importer declined this file: fall through to the built-in
                                // loader below.
                            } else {
                                if (!imported.message.empty())
                                    GUI::show_error(q, imported.message);
                                handled_by_plugin_importer = true; // per-file failure; the batch continues
                            }
                        }
                    }
                    if (!handled_by_plugin_importer)
                    model = Slic3r::Model:: read_from_file('''
assert s.count(old_else) == 1
s = s.replace(old_else, new_else)
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('plater wiring ok')
