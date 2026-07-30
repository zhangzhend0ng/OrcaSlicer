# Repository Guidelines

## Project Structure & Module Organization
Snapmaker_Orca’s C++17 sources live in `src/`, split by feature modules and platform adapters. User assets, icons, and printer presets are in `resources/`; translations stay in `localization/`. Tests sit in `tests/`, grouped by domain (`libslic3r/`, `sla_print/`, etc.) with fixtures under `tests/data/`. CMake helpers reside in `cmake/`, and longer references in `doc/` and `SoftFever_doc/`. Automation scripts belong in `scripts/` and `tools/`. Treat everything in `deps/` and `deps_src/` as vendored snapshots—do not modify without mirroring upstream tags.

## Build, Test, and Development Commands
Use out-of-source builds:
- `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` configures dependencies and generates build files.
- `cmake --build build --target Snapmaker_Orca --config Release` compiles the app; add `--parallel` to speed up.
- `cmake --build build --target tests` then `ctest --test-dir build --output-on-failure` runs automated suites.
Platform helpers such as `build_linux.sh`, `build_release_macos.sh`, and `build_release_vs2022.bat` wrap the same flow with toolchain flags. Use `build_release_macos.sh -sx` when reproducing macOS build issues, and `scripts/DockerBuild.sh` for reproducible container builds.

## Coding Style & Naming Conventions
`.clang-format` enforces 4-space indents, a 140-column limit, aligned initializers, and brace wrapping for classes and functions. Run `clang-format -i <file>` before committing; the CMake `clang-format` target is available when LLVM tools are on your PATH. Prefer `CamelCase` for classes, `snake_case` for functions and locals, and `SCREAMING_CASE` for constants, matching conventions in `src/`. Keep headers self-contained and align include order with the IWYU pragmas.

## Testing Guidelines
Unit tests rely on Catch2 (`tests/catch2/`). Name specs after the component under test—for example `tests/libslic3r/TestPlanarHole.cpp`—and tag long-running cases so `ctest -L fast` remains useful. Cover new algorithms with deterministic fixtures or sample G-code stored in `tests/data/`. Document manual printer validation or regression slicer checks in your PR when automated coverage is insufficient.

## Commit & Pull Request Guidelines
The history favors concise, sentence-style subject lines with optional issue references, e.g., `Fix grid lines origin for multiple plates (#10724)`. Squash fixups locally before opening a PR. Complete `.github/pull_request_template.md`, include reproduction steps or screenshots for UI changes, and mention impacted presets or translations. Link issues via `Closes #NNNN` when applicable, and call out dependency bumps or profile migrations for maintainer review.

## Security & Configuration Tips
Follow `SECURITY.md` for vulnerability reporting. Keep API tokens and printer credentials out of tracked configs; use `sandboxes/` for experimental settings. When touching third-party code in `deps_src/`, record the upstream commit or release in your PR description and run the relevant platform build script to confirm integration.

## Reuse Before You Build (anti-reinvention checklist)
This codebase already has rich facilities for filament, colour, mixing, and matching. Before introducing any new struct/widget/algorithm in these areas, prove the existing one is insufficient — do not silently build a parallel, weaker copy. A past change re-invented a bespoke 2-component recipe model next to `MixedFilament` / `MixedColorMatchRecipeResult`, silently dropping gradient/pattern fields; that drift is exactly what this section exists to prevent.

Before adding new code in the filament/colour/mix/match domain, run this check:
1. **Is there an existing data model?** Search `src/libslic3r/MixedFilament.hpp`, `MixedColorMatchHelpers.hpp`, `filamentsync/FilamentData.hpp`, `PresetBundle.hpp`. If a struct already holds the shape you need (recipe, colours, types), store/reuse it verbatim — do not project it into a bespoke subset of fields. Storing the full object preserves information the UI or solver may later produce.
2. **Is there an existing algorithm?** `color_delta_e00`, `build_best_color_match_recipe`, `batch_match_model_colors`, `extract_model_colors` cover colour distance, single-colour recipe solve, batch solve, model-colour extraction. Reuse them; verify purity (no hidden `preset_bundle` reads) before assuming a function is a drop-in.
3. **Is there an existing widget/dialog?** `MixedFilamentDialog` (RATIO/CYCLE/MATCH/GRADIENT, slider, tri-picker, gradient selector, live preview), `MixedFilamentBadge`, `FilamentColorMapBox`, `get_extruder_color_icon`. Pop the dialog / embed the widget rather than building a new control.
4. **Is there an existing signal?** `EVT_FILAMENT_USAGE_CHANGED`, `EVT_FILAMENT_COLOR_CHANGED`, `load_ams_list`. Bind these instead of inventing refresh paths.
5. **If you duplicate a constant, link its twin.** When a threshold must be local, leave a `MUST stay in sync with <file:line>` comment and a TODO to hoist it shared. Never let two copies of a magic number drift unannotated.
6. **Comment the filter semantics, not just the code.** When two checks look similar (e.g. same-type filter vs `check_compatible`), state explicitly that they are orthogonal and both required — a "redundant, kept defensive" comment caused a real misunderstanding here.
