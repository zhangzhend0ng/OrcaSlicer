#!/bin/bash
CASES="m3j_mixing_entry m3k_mixing_match m3l_mixing_delta m3m_mixing_filaments m3n_mixing_cancel m3o_mixing_nomodel m3p_mixing_persist m3q_mixing_view m3r_mixing_progress m3s_mixing_hover m3t_mixing_add_ratio m3u_mixing_ratio_flow m3v_mixing_cycle_input m3w_mixing_cycle_flow m3x_mixing_match m3y_mixing_gradient m3z_mixing_compat m4a_mixing_gates m4b_batch_manual m4c_mixing_panel m4d_mixing_filops m4e_mixing_paint m4f_mixing_cap64 m4g_mixing_sublayer m4h_mixing_templates m4i_mixing_slice m4j_mixing_samecolor"
PASS=0; FAIL=0; FAILED=""
for c in $CASES; do
  echo "=== $c ==="
  ./.venv/Scripts/python.exe ${c}.py > artifacts/regress_${c}.log 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then PASS=$((PASS+1)); echo "[$c] GREEN (${rc})";
  else FAIL=$((FAIL+1)); FAILED="$FAILED $c"; echo "[$c] RED rc=$rc"; tail -5 artifacts/regress_${c}.log; fi
done
echo "=== REGRESSION SUMMARY: PASS=$PASS FAIL=$FAIL ==="
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
exit $((FAIL > 0 ? 1 : 0))
