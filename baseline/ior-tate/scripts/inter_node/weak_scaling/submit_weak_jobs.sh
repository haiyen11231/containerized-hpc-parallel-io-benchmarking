#!/bin/bash
# Submits the weak-scaling study: RUNS rounds x 3 node counts x 2 combos x {native, container}.
# Every job reserves all 3 nodes (set in the .sbatch files); the job places ranks
# on 1, 2 or 3 of them according to NODE_COUNT. Native and container for the same
# (nodes, combo) are submitted back to back.
#
#   ./submit_weak_jobs.sh                  # runs 1..3
#   RUNS=5 ./submit_weak_jobs.sh           # runs 1..5
cd "$(dirname "$0")"

RUNS=${RUNS:-3}
NODE_COUNTS=(1 2 3)

COMBOS=(
  "MPIIO shared"
  "POSIX fpp"
)

mkdir -p logs

for ((RUN = 1; RUN <= RUNS; RUN++)); do
  for NODES in "${NODE_COUNTS[@]}"; do
    for combo in "${COMBOS[@]}"; do
      read -r API MODEL <<< "$combo"
      API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
      for VARIANT in native container; do
        JOBNAME="ior_${VARIANT}_weak_${NODES}n_${API_LOWER}_${MODEL}_run${RUN}"
        echo "Submitting ${JOBNAME}..."

        sbatch -J "$JOBNAME" \
               -o "logs/${JOBNAME}_%j.out" \
               --export="ALL,NODE_COUNT=${NODES},API=${API},MODEL=${MODEL},RUN=${RUN}" \
               "ior_${VARIANT}_inter_weak.sbatch"
      done
    done
  done
done
