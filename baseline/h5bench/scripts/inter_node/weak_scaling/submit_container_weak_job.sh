#!/bin/bash
cd "$(dirname "$0")"

NODE_COUNTS=(1 2 4 8)

REPS=${REPS:-10}

mkdir -p logs

for NODES in "${NODE_COUNTS[@]}"; do
  JOBNAME="h5bench_container_weak_${NODES}n"
  OUTFILE="logs/${JOBNAME}.out"

  # PBS routes on ncpus AND walltime. A 1-node job is 128 ncpus and only
  # reaches q4 if walltime > 02:00:01; below that it lands in qdev, whose
  # 256-ncpu cap is shared cluster-wide. 2+ nodes (256+ ncpus) go to q5,
  # which has no walltime floor.
  if [ "$NODES" -eq 1 ]; then WT=02:30:00; else WT=01:00:00; fi

  echo "Submitting ${JOBNAME} (Nodes: ${NODES}, Reps: ${REPS}, walltime: ${WT})..."

  qsub -N "$JOBNAME" \
       -o "$OUTFILE" \
       -l select=${NODES}:ncpus=128:mpiprocs=128:mem=64gb \
       -l walltime=${WT} \
       -v NODE_COUNT=${NODES},REPS=${REPS} \
       h5bench_container_weak.pbs
done
