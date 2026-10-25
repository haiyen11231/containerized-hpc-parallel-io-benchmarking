#!/bin/bash
cd "$(dirname "$0")"

RANKS_LIST=(16 32 64)

mkdir -p logs

PREV_JOB_ID=""

for R in "${RANKS_LIST[@]}"; do
  JOBNAME="h5bench_native_intraweak_r${R}"
  OUTFILE="logs/${JOBNAME}.out"

  # Base qsub command
  QSUB_CMD="qsub -N $JOBNAME -o $OUTFILE -l select=1:ncpus=${R}:mpiprocs=${R}:mem=${R}gb -v RANKS=${R}"

  # Chain jobs together so they run strictly serially (preventing Lustre I/O contention)
  if [ -n "$PREV_JOB_ID" ]; then
    QSUB_CMD="${QSUB_CMD} -W depend=afterok:${PREV_JOB_ID}"
    echo "Submitting ${JOBNAME} (chained to wait for job ${PREV_JOB_ID})..."
  else
    echo "Submitting initial job ${JOBNAME}..."
  fi

  # Execute submission and capture the new Job ID
  PREV_JOB_ID=$($QSUB_CMD h5bench_native_intra_weak.pbs)
  echo "  -> Assigned Job ID: ${PREV_JOB_ID}"
done

echo "All intra-node weak scaling jobs successfully queued in safe serial order!"
