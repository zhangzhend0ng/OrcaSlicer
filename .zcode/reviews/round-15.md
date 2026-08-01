# Round 15 — 3D expected render showed stale colour for just-edited recipe

Harness: PRD §5 (gaps spoken / honest render), consistency. File: Plater.cpp
get_expected_render_colors.

## Finding
get_expected_render_colors (feeds the 3D object render) used a realised colour
when `recipe.valid && preview_color.IsOk()`. But a freshly hand-edited recipe
(apply_edited_recipe) sets delta_e=inf and does NOT refresh preview_color — so
its stored preview_color is the PRE-edit realised colour. The 3D model rendered
that stale colour while the panel's expected swatch (which guards on
std::isfinite(delta_e), round-05) correctly hid it. The two render surfaces
disagreed, and the 3D view misrepresented the new recipe (PRD §5).

## Fix
Added the same `std::isfinite(e->recipe.delta_e)` guard to get_expected_render_colors
that the row's expected swatch uses. For a just-edited recipe both surfaces now
fall back to the design colour (until the next Match re-solves); for solved
Direct/Synth entries the realised colour still shows. Consistent + honest.

## Adversarial re-check
- Just-edited recipe (delta_e=inf): 3D model AND swatch both show design colour. ✓
- Solved direct (delta_e finite < threshold): realised colour in both. ✓
- Solved synth (delta_e finite): realised colour in both. ✓
- Unmet (no recipe/preview): design colour in both. ✓
- <cmath> already included in Plater.cpp. ✓

## Verdict: APPROVE (fix applied), build green.
