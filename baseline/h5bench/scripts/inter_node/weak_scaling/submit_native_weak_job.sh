#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4)

mkdir -p logs

PREV_JOB_ID=""

for NODES in "${NODE_COUNTS[@]}"; do
  JOBNAME="h5bench_native_weak_${NODES}n"
  OUTFILE="logs/${JOBNAME}.out"

  # Base qsub command
  QSUB_CMD="qsub -N $JOBNAME -o $OUTFILE -l select=${NODES}:ncpus=64:mpiprocs=64:mem=64gb -v NODE_COUNT=${NODES}"

  # Chain jobs together so they run strictly serially (preventing Lustre I/O contention)
  if [ -n "$PREV_JOB_ID" ]; then
    QSUB_CMD="${QSUB_CMD} -W depend=afterok:${PREV_JOB_ID}"
    echo "Submitting ${JOBNAME} (chained to wait for job ${PREV_JOB_ID})..."
  else
    echo "Submitting initial job ${JOBNAME}..."
  fi

  # Execute submission and capture the new Job ID
  PREV_JOB_ID=$($QSUB_CMD h5bench_native_weak.pbs)
  echo "  -> Assigned Job ID: ${PREV_JOB_ID}"
done

echo "All weak scaling jobs successfully queued in safe serial order!"
