#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4 8)

REPS=${REPS:-10}

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  JOBNAME="h5bench_container_strong_${NODES}n"
  OUTFILE="logs/${JOBNAME}.out"

  echo "Submitting ${JOBNAME} (Nodes: ${NODES}, Reps: ${REPS})..."

  qsub -N "$JOBNAME" \
       -o "$OUTFILE" \
       -l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb \
       -v NODE_COUNT=${NODES},REPS=${REPS} \
       h5bench_container_strong.pbs
done
