#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4 8)

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  JOBNAME="h5bench_container_weak_${NODES}n"
  OUTFILE="logs/${JOBNAME}.out"

  echo "Submitting ${JOBNAME} ..."
  JOB_ID=$(qsub -N "$JOBNAME" -o "$OUTFILE" \
                -l select=${NODES}:ncpus=64:mpiprocs=64:mem=64gb \
                -v NODE_COUNT=${NODES} \
                h5bench_container_weak.pbs)
  echo "  -> Assigned Job ID: ${JOB_ID}"
done

echo "All weak scaling jobs submitted independently -- no ordering guaranteed."
