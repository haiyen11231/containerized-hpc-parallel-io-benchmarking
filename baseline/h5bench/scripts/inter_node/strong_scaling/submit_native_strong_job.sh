#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4 8)

REPS=${REPS:-10}

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  JOBNAME="h5bench_native_strong_${NODES}n"
  OUTFILE="logs/${JOBNAME}.out"

  # 128 ncpus reaches q4 only if walltime > 02:00:01; below that it falls
  # into qdev, whose 256-ncpu cap is shared cluster-wide. 2+ nodes -> q5.
  if [ "$NODES" -eq 1 ]; then WT=02:30:00; else WT=01:00:00; fi

  echo "Submitting ${JOBNAME} (Nodes: ${NODES}, Reps: ${REPS})..."

  qsub -N "$JOBNAME" \
       -o "$OUTFILE" \
       -l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb \
       -l walltime=${WT} \
       -v NODE_COUNT=${NODES},REPS=${REPS} \
       h5bench_native_strong.pbs
done
