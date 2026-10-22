#!/bin/bash
cd "$(dirname "$0")"

MODES=(weak strong)
NODE_COUNTS=(2 4 8)
ALG=${ALG:-2}
REPS=${REPS:-10}

mkdir -p logs

for M in "${MODES[@]}"; do
  for N in "${NODE_COUNTS[@]}"; do
    JOBNAME="osu_container_collective_inter_alltoall_ucx_alglock_${M}_n${N}_a${ALG}"
    echo "Submitting ${JOBNAME} (mode: ${M}, nodes: ${N}, alg: ${ALG}, reps: ${REPS})..."
    qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
         -l select=${N}:ncpus=128:mpiprocs=128:mem=64gb \
         -v MODE=${M},NODES=${N},ALG=${ALG},REPS=${REPS} \
         osu_container_collective_inter_alltoall_ucx_alglock.pbs
  done
done
