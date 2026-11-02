#!/bin/bash
# Submits the inter-node Darshan profiling set: MPI-IO shared, -t 1m, lock fix,
# for each node count x {native, container}, one job each. Native and container
# for the same node count are submitted back to back.
#
#   ./submit_inter_darshan.sh          # 2 and 3 nodes (4 jobs)
#   ./submit_inter_darshan.sh 2        # 2 nodes only
cd "$(dirname "$0")"

if [ $# -gt 0 ]; then NODE_COUNTS=("$@"); else NODE_COUNTS=(2 3); fi

# Same node sets as the scaling studies
declare -A NODELISTS=(
  [1]="tate01"
  [2]="tate01,tate03"
  [3]="tate01,tate02,tate03"
)

REPS=5

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  [ -n "${NODELISTS[$NODES]}" ] || { echo "Unknown node count: $NODES (use 1, 2 or 3)"; exit 1; }
  for VARIANT in native container; do
    JOBNAME="darshan_${VARIANT}_inter_${NODES}n_mpiio_shared_t1m_lock3"
    echo "Submitting ${JOBNAME} on ${NODELISTS[$NODES]}..."

    sbatch -J "$JOBNAME" \
           --nodes="$NODES" \
           --nodelist="${NODELISTS[$NODES]}" \
           -o "logs/${JOBNAME}_%j.out" \
           -e "logs/${JOBNAME}_%j.err" \
           --export="ALL,NODE_COUNT=${NODES},REPS=${REPS}" \
           "ior_${VARIANT}_inter_darshan.sbatch"
  done
done
