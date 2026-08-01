# Round 16 — integer / sign-conversion hygiene audit

Harness: integer-safety (N), type-safety (N). All demo TUs.

## Audit
Compiled each demo TU with -Wconversion -Wsign-conversion (stricter than the
project's default flags, which suppress -Wsign-compare). Result: zero genuine
sign-conversion or narrowing warnings in any demo source file. The static_casts
present (device.size()→int limit, rows.size()→int, m_index→int, enabled_count→int)
are all on naturally-bounded values (extruder counts ≤ MAXIMUM_FILAMENT_NUMBER,
small row counts) where narrowing cannot occur in practice.

## Other items reviewed this round (no action)
- num_physical is provably ≥1 whenever rows is non-empty (all_unmapped→rows.size()
  ≥1; mapped→max_t+1≥1), so set_num_extruders never gets 0 here.
- design_to_device sized from max_design_extruder over ALL entries (incl. unmet),
  so it covers every design extruder; set_map bounds-checked.
- fallback_device_id "always exists" comment is accurate: non-empty rows ⟹ ≥1
  resolved entry ⟹ ≥1 non-zero design_to_device.
- temp_storage lifetime: SliceInputs holds it by value; model_ref points at it;
  both outlive the single Print::apply call that consumes them.
- Placeholder "PLA"/1.75 for empty T-number slots are documented ("sane default");
  acceptable for demo scope.

## Verdict: APPROVE — no code change. Integer/sign hygiene is clean under strict
warnings; the static_casts are on bounded values.
