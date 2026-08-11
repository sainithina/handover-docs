#!/usr/bin/env bash
# Build clean handover zips for email / Drive upload.
# NEVER includes .env, .pem, or Case2 runs/.
set -euo pipefail

DOWNLOADS="${DOWNLOADS:-/Users/sainithinartham/Downloads}"
OUT="${OUT:-$DOWNLOADS/gravton-handover-zips}"
DOCS_ROOT="$DOWNLOADS/gravton-docs"

mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
echo "Writing zips to $OUT (stamp=$STAMP)"

# A) Docs pack
(
  cd "$DOCS_ROOT"
  zip -r "$OUT/01-sai-handover-docs-$STAMP.zip" sai-nithin-departure-handover \
    -x "*.DS_Store"
)
echo "OK 01 docs"

# B) Volume algorithm (P0)
if [[ -d "$DOWNLOADS/ai-demand-case2" ]]; then
  (
    cd "$DOWNLOADS"
    zip -r "$OUT/02-ai-demand-case2-algorithm-$STAMP.zip" ai-demand-case2 \
      -x "ai-demand-case2/runs/*" \
      -x "ai-demand-case2/hospitality_metrics/runs/*" \
      -x "ai-demand-case2/.env" \
      -x "ai-demand-case2/**/__pycache__/*" \
      -x "ai-demand-case2/**/*.pyc" \
      -x "ai-demand-case2/**/.DS_Store" \
      -x "ai-demand-case2/**/.venv/*" \
      -x "ai-demand-case2/**/*.egg-info/*"
  )
  echo "OK 02 case2 algorithm"
else
  echo "SKIP 02 — ai-demand-case2 missing"
fi

# C) Experiment forks (optional, smaller)
EXPERIMENT_ARGS=()
[[ -d "$DOWNLOADS/ai-demand-case2_overlap_discount" ]] && EXPERIMENT_ARGS+=(ai-demand-case2_overlap_discount)
[[ -d "$DOWNLOADS/ai-demand-case2_Intent_Match_Score" ]] && EXPERIMENT_ARGS+=(ai-demand-case2_Intent_Match_Score)
if ((${#EXPERIMENT_ARGS[@]})); then
  (
    cd "$DOWNLOADS"
    zip -r "$OUT/03-case2-experiments-$STAMP.zip" "${EXPERIMENT_ARGS[@]}" \
      -x "*/runs/*" \
      -x "*/.env" \
      -x "*/**/__pycache__/*" \
      -x "*/**/.DS_Store"
  )
  echo "OK 03 experiments"
else
  echo "SKIP 03 — no experiment forks"
fi

# D) Console (large) — opt-in via INCLUDE_CONSOLE=1
if [[ "${INCLUDE_CONSOLE:-0}" == "1" && -d "$DOWNLOADS/gravton-console" ]]; then
  (
    cd "$DOWNLOADS"
    zip -r "$OUT/04-gravton-console-$STAMP.zip" gravton-console \
      -x "gravton-console/.env" \
      -x "gravton-console/.venv/*" \
      -x "gravton-console/**/__pycache__/*" \
      -x "gravton-console/**/.pytest_cache/*" \
      -x "gravton-console/gravton_dump.sql" \
      -x "gravton-console/**/.DS_Store"
  )
  echo "OK 04 console"
else
  echo "SKIP 04 console (set INCLUDE_CONSOLE=1 to build)"
fi

# E) Frontend — opt-in via INCLUDE_FRONTEND=1
if [[ "${INCLUDE_FRONTEND:-0}" == "1" && -d "$DOWNLOADS/gravton-frontend" ]]; then
  (
    cd "$DOWNLOADS"
    zip -r "$OUT/05-gravton-frontend-$STAMP.zip" gravton-frontend \
      -x "gravton-frontend/.env" \
      -x "gravton-frontend/node_modules/*" \
      -x "gravton-frontend/dist/*" \
      -x "gravton-frontend/.tanstack/*" \
      -x "gravton-frontend/**/.DS_Store"
  )
  echo "OK 05 frontend"
else
  echo "SKIP 05 frontend (set INCLUDE_FRONTEND=1 to build)"
fi

echo
echo "Done. Contents:"
ls -lh "$OUT"/*"$STAMP"* 2>/dev/null || ls -lh "$OUT"
echo
echo "Reminder: transfer secrets via vault using credentials/CREDENTIALS_CHECKLIST.md — not email."
