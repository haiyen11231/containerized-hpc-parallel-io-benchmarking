#!/bin/bash
# Sync h5bench results from ASPIRE 2A, WITHOUT destroying anything that is not
# benchmark output.
#
# Why this script exists: an earlier ad-hoc sync did
#     rm -rf results/<study>
# which wiped the whole directory -- including a hand-written README.md that
# lived there. Only the data subdirectories should ever be replaced.
#
# Usage:
#   ./sync_results.sh              # all studies
#   ./sync_results.sh intra_node   # one study

set -u
cd "$(dirname "$0")"

REMOTE=/home/users/ntu/haiyen00/scratch/fyp/experiments/baseline/h5bench
HOST=aspire2a

ALL_STUDIES=(
  intra_node
  inter_node/weak_scaling
  inter_node/strong_scaling
  inter_node/collective_io
  inter_node/cold_read_validation
)
STUDIES=("${@:-${ALL_STUDIES[@]}}")
[ $# -gt 0 ] && STUDIES=("$@")

# Only these are benchmark output and safe to replace wholesale. Anything else
# in results/<study>/ (README.md, notes, figures) is left alone.
DATA_DIRS=(native container payload)

for s in "${STUDIES[@]}"; do
  echo "=== $s ==="
  mkdir -p "results/$s" "scripts/$s/logs"

  for d in "${DATA_DIRS[@]}"; do
    rm -rf "results/$s/$d"
    scp -q -r "${HOST}:${REMOTE}/$s/$d" "results/$s/" 2>/dev/null
  done

  # Job logs live under scripts/, replaced in full -- they are pure output.
  rm -rf "scripts/$s/logs"; mkdir -p "scripts/$s/logs"
  scp -q -r "${HOST}:${REMOTE}/$s/logs/." "scripts/$s/logs/" 2>/dev/null

  rc=$(ssh -o ConnectTimeout=20 "$HOST" "find $REMOTE/$s -name '*.csv' 2>/dev/null | wc -l")
  rl=$(ssh -o ConnectTimeout=20 "$HOST" "ls $REMOTE/$s/logs/*.out 2>/dev/null | wc -l")
  lc=$(find "results/$s" -name '*.csv' 2>/dev/null | wc -l | tr -d ' ')
  ll=$(ls "scripts/$s/logs"/*.out 2>/dev/null | wc -l | tr -d ' ')

  v="OK"
  [ "$lc" != "$rc" ] && v="MISMATCH"
  [ "$ll" != "$rl" ] && v="MISMATCH"
  printf '  csv %s/%s   logs %s/%s   %s\n' "$lc" "$rc" "$ll" "$rl" "$v"

  # Confirm nothing non-data was collateral damage.
  if [ -f "results/$s/README.md" ]; then
    echo "  README.md preserved"
  fi
done

echo
echo "total: $(find results -name '*.csv' | wc -l | tr -d ' ') CSVs, \
$(find scripts -name '*.out' | wc -l | tr -d ' ') job logs, $(du -sh results | cut -f1)"
echo "READMEs under results/: $(find results -name 'README.md' | wc -l | tr -d ' ')"
