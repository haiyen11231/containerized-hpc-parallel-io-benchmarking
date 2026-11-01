#!/bin/bash
# Submits the strong-scaling study, one run: node counts x 2 combos x {native, container}.
# Each job requests exactly the nodes it uses (16 cores each). Native and container
# for the same (nodes, combo) are submitted back to back.
#
#   ./submit_strong_jobs.sh        # 1, 2 and 3 nodes (12 jobs)
#   ./submit_strong_jobs.sh 1      # 1 node only (4 jobs)
#   ./submit_strong_jobs.sh 2 3    # 2 and 3 nodes
cd "$(dirname "$0")"

if [ $# -gt 0 ]; then NODE_COUNTS=("$@"); else NODE_COUNTS=(1 2 3); fi

declare -A NODELISTS=(
  [1]="tate01"
  [2]="tate01,tate03"
  [3]="tate01,tate02,tate03"
)

# Same time limit for every job 
TIME="00:20:00"

COMBOS=(
  "MPIIO shared"
  "POSIX fpp"
)

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  [ -n "${NODELISTS[$NODES]}" ] || { echo "Unknown node count: $NODES (use 1, 2 or 3)"; exit 1; }
  for combo in "${COMBOS[@]}"; do
    read -r API MODEL <<< "$combo"
    API_LOWER=$(echo "$API" | tr '[:upper:]' '[:lower:]')
    for VARIANT in native container; do
      JOBNAME="ior_${VARIANT}_strong_${NODES}n_${API_LOWER}_${MODEL}"
      echo "Submitting ${JOBNAME} on ${NODELISTS[$NODES]} (time $TIME)..."

      sbatch -J "$JOBNAME" \
             --nodes="$NODES" \
             --nodelist="${NODELISTS[$NODES]}" \
             --time="$TIME" \
             -o "logs/${JOBNAME}_%j.out" \
             -e "logs/${JOBNAME}_%j.err" \
             --export="ALL,NODE_COUNT=${NODES},API=${API},MODEL=${MODEL}" \
             "ior_${VARIANT}_inter_strong.sbatch"
    done
  done
done
