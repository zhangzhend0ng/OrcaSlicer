# OrcaSlicer ????????

## ??

| ?? | ?? |
|------|------|
| ??? | 22 |
| ???? | 85+ |
| ???? | ~6,500+ |
| ????? | 56 (??12?GUI??) |
| ViewModel/Model | 28 |
| Ports ?? | 7 |
| ???? | 18 |
| ??+???? | 120+ |
| Layer violations | 0 ? |

## ????

### Layer 2 - Domain (libslic3r)
| ?? | ?? |
|------|------|
| MVVP.hpp | Property<T> + Command ?? |
| ColorSpaceConvert.{hpp,cpp} | ?????? |
| Ports/ (7) | ???? |

### Layer 3 - Application (slic3r/App)
| ?? | ?? | ?? |
|------|------|------|
| CameraController | ViewModel | GLCanvas3D |
| SelectionController | ViewModel | GLCanvas3D |
| CanvasViewModel | ViewModel | GLCanvas3D |
| PlaterViewModel | ViewModel | Plater::priv |
| AppViewModel | ViewModel | GUI_App |
| PresetViewModel | ViewModel | GUI_App |
| DeviceViewModel | ViewModel | GUI_App |
| SettingsViewModel | ViewModel | GUI_App |
| AccountViewModel | ViewModel | GUI_App |
| PluginViewModel | ViewModel | GUI_App |
| TabViewModel (base) | ViewModel | Tab |
| PrintTabViewModel | ViewModel | Tab |
| FilamentTabViewModel | ViewModel | Tab |
| PrinterTabViewModel | ViewModel | Tab |
| MixedFilamentViewModel | Model | Plater.cpp |
| ConfigValidationModel | Model | Tab.cpp |
| GeometryValidationModel | Model | Selection.cpp |
| ObjectValidationModel | Model | GUI_ObjectList+ |
| PresetStringModel | Model | CreatePresets+ |
| PresetCompatibilityModel | Model | CreatePresets |
| PrintJobModel | Model | PrintJob |
| FilamentCompatibilityModel | Model | MixedColorMatch |
| SearchModel | Model | Search.cpp |
| SystemInfoModel | Model | SendSystemInfo |
| SliceOrchestrator | App | ?? |
| JobManager | App | ?? |
| IPlugin/PluginLoader | App | ?? |
| UndoRedoController | Util | ?? |
| NullProgressReporter | Util | ?? |

### Layer 4 - View (slic3r/GUI)
| ?? | ?? |
|------|------|
| MixedFilamentPanel.hpp | ??? View ???? |

### ???/??
| ?? | ?? |
|------|------|
| PlaterAdapters.hpp | ?????VM?? |
| ViewBindingGuide.hpp | 5????? |
| EndToEndWiringExample.hpp | ??????? |
| RefactoringWiring.hpp | ?????? |
| MIGRATION_GUIDE.md | ??????? |
| REFACTORING_MASTER_PLAN.md | ?????? |

## ????

| ??? | ?? |
|--------|------|
| libslic3r?GUI include | 0 ? |
| ????? | 20 (??) |
| God? (>200??) | 40 (??) |
| Harness ?? | 4/4 ?? |
| ?? (libslic3r) | ?? ? |

## ???

1. ?? GUI ?????
2. `#define ORCA_REFACTOR_V2` ?????
3. ?????? ViewModel
4. Golden GCode ????
5. ?????
