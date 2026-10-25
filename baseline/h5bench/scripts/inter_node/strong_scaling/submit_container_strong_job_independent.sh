#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(4 2 1)

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  JOBNAME="h5bench_container_strong_${NODES}n"
  OUTFILE="logs/${JOBNAME}.out"

  echo "Submitting ${JOBNAME} ..."
  JOB_ID=$(qsub -N "$JOBNAME" -o "$OUTFILE" \
                -l select=${NODES}:ncpus=64:mpiprocs=64:mem=64gb \
                -v NODE_COUNT=${NODES} \
                h5bench_container_strong.pbs)
  echo "  -> Assigned Job ID: ${JOB_ID}"
done

echo "All strong scaling jobs submitted independently -- no ordering guaranteed."
