#!/bin/bash
cd "$(dirname "$0")"

RANKS_LIST=(16 32 64)

mkdir -p logs

for R in "${RANKS_LIST[@]}"; do
  JOBNAME="h5bench_native_intraweak_r${R}"
  OUTFILE="logs/${JOBNAME}.out"

  echo "Submitting ${JOBNAME} ..."
  JOB_ID=$(qsub -N "$JOBNAME" -o "$OUTFILE" \
                -l select=1:ncpus=${R}:mpiprocs=${R}:mem=${R}gb \
                -v RANKS=${R} \
                h5bench_native_intra_weak.pbs)
  echo "  -> Assigned Job ID: ${JOB_ID}"
done

echo "All intra-node weak scaling jobs submitted independently -- no ordering guaranteed."
