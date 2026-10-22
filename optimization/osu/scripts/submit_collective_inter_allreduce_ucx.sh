#!/bin/bash
cd "$(dirname "$0")"

MODES=(weak strong)
NODE_COUNTS=(2 4 8)
REPS=${REPS:-10}

mkdir -p logs

for M in "${MODES[@]}"; do
  for N in "${NODE_COUNTS[@]}"; do
    JOBNAME="osu_container_collective_inter_allreduce_ucx_${M}_n${N}"
    echo "Submitting ${JOBNAME} (mode: ${M}, nodes: ${N}, ranks: $((N*128)), reps: ${REPS})..."
    # Same resources as the baseline inter-node collective jobs, so the only
    # difference between baseline and optimized is the MCA transport flags.
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=${N}:ncpus=128:mpiprocs=128:mem=64gb \
         -v MODE=${M},NODES=${N},REPS=${REPS} \
         osu_container_collective_inter_allreduce_ucx.pbs
  done
done
