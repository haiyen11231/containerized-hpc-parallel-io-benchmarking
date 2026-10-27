#!/bin/bash
cd "$(dirname "$0")"

MODES=(weak strong)
NODE_COUNTS=(1 8)   # only the two endpoints -- see GUIDE.md experiment design
REPS=${REPS:-2}

mkdir -p logs

for VARIANT in native container; do
  for MODE in "${MODES[@]}"; do
    for N in "${NODE_COUNTS[@]}"; do
      JOBNAME="h5bench_${VARIANT}_scaling_darshan_${MODE}_n${N}"
      echo "Submitting ${JOBNAME} (MODE=${MODE} NODE_COUNT=${N} REPS=${REPS})..."
      qsub -N "$JOBNAME" -o "logs/${JOBNAME}.out" \
           -l select=${N}:ncpus=128:mpiprocs=128:mem=64gb \
           -v MODE=${MODE},NODE_COUNT=${N},REPS=${REPS} \
           "h5bench_${VARIANT}_scaling_darshan.pbs"
    done
  done
done
