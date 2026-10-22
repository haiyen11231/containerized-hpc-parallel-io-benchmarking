#!/bin/bash
cd "$(dirname "$0")"

BENCHES=(allreduce alltoall)
MODES=(weak strong)
NP_LIST=(8 16 32 64 128)
REPS=${REPS:-10}

mkdir -p logs

for B in "${BENCHES[@]}"; do
  for M in "${MODES[@]}"; do
    for NP in "${NP_LIST[@]}"; do
      JOBNAME="osu_container_collective_intra_ucx_${B}_${M}_np${NP}"
      echo "Submitting ${JOBNAME} (bench: ${B}, mode: ${M}, np: ${NP}, reps: ${REPS})..."
      qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
           -l select=1:ncpus=${NP}:mpiprocs=${NP}:mem=16gb \
           -v BENCH=${B},MODE=${M},NP=${NP},REPS=${REPS} \
           osu_container_collective_intra_ucx.pbs
    done
  done
done
